"""Verification engine.

After a fix runs, WinFix repeats the measurements it took before the fix and
re-analyzes them with the same rules, so the comparison is like for like. It
reports two separate things:

* **action_effective** — did the change itself take effect (e.g. the service
  is running again)?
* **improved** — is the original problem gone (the causes that motivated the
  fix no longer appear in the fresh analysis)?

A fix that "worked as intended" can still leave the original issue in place,
and that is reported honestly rather than as success.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from app.core.logging_setup import get_logger
from app.core.models import (
    CheckStatus,
    Level,
    RemediationOutcome,
    RemediationProposal,
    Session,
    VerificationCheck,
    VerificationResult,
)
from app.core.tool_registry import get_registry
from app.knowledge import evidence as ev
from app.knowledge import troubleshooting
from app.knowledge.remediations import FixInfo, fix_info

logger = get_logger(__name__)

Results = dict[str, dict[str, Any]]
ProgressCallback = Callable[[str, dict], None]

MEMORY_DROP_POINTS = 2.0   # smaller changes are measurement noise
SPACE_GAIN_GB = 0.1
SIZE_DROP_RATIO = 0.8


# --- check definitions -----------------------------------------------------
@dataclass(frozen=True)
class CheckDef:
    label: str
    tools: tuple[str, ...]
    build: Callable[[Results, Results], VerificationCheck | None]
    phrase: Callable[[Results, Results], str] | None = None


def _service_check(name: str, label: str) -> CheckDef:
    def build(before: Results, after: Results) -> VerificationCheck | None:
        b, a = ev.service(before, name), ev.service(after, name)
        if not a:
            return None
        b_text = b.get("status_text", "Unknown") if b else "Not measured"
        a_ok = bool(a.get("running"))
        return VerificationCheck(
            label=label, before=b_text, after=a.get("status_text", "Unknown"),
            before_level=Level.OK if b and b.get("running") else Level.CAUTION,
            after_level=Level.OK if a_ok else Level.CAUTION,
            status=CheckStatus.OK if a_ok else CheckStatus.UNCHANGED)

    return CheckDef(label, ("get_important_services", "get_windows_update_status",
                            "get_network_services_status"), build,
                    lambda b, a: f"{label} is running")


def _search_service(before: Results, after: Results) -> VerificationCheck | None:
    b, a = ev.indexer(before), ev.indexer(after)
    if not a:
        return None

    def text(idx):
        if idx is None:
            return "Not measured"
        if not idx["responding"]:
            return "Not responding"
        return idx["status_text"]

    a_ok = a["running"] and a["responding"]
    return VerificationCheck(
        label="Windows Search service", before=text(b), after=text(a),
        before_level=Level.OK if b and b["running"] and b["responding"] else Level.CAUTION,
        after_level=Level.OK if a_ok else Level.CAUTION,
        status=CheckStatus.OK if a_ok else CheckStatus.UNCHANGED)


def _indexer_memory(before: Results, after: Results) -> VerificationCheck | None:
    b, a = ev.indexer(before), ev.indexer(after)
    if not a or not b:
        return None
    improved = a["memory_mb"] <= b["memory_mb"] * SIZE_DROP_RATIO
    healthy = a["memory_mb"] < troubleshooting.INDEXER_MEMORY_MB
    return VerificationCheck(
        label="Search indexer memory", before=ev.size_text(b["memory_mb"]),
        after=ev.size_text(a["memory_mb"]),
        before_level=(Level.CAUTION if b["memory_mb"] >= troubleshooting.INDEXER_MEMORY_MB
                      else Level.INFO),
        after_level=Level.OK if healthy else Level.CAUTION,
        status=CheckStatus.IMPROVED if improved else CheckStatus.UNCHANGED)


def _indexer_phrase(before: Results, after: Results) -> str:
    b, a = ev.indexer(before), ev.indexer(after)
    if b and a and b["memory_mb"] > a["memory_mb"]:
        return f"released {ev.size_text(b['memory_mb'] - a['memory_mb'])} of memory"
    return ""


def _memory_in_use(before: Results, after: Results) -> VerificationCheck | None:
    b, a = ev.memory(before), ev.memory(after)
    if not a or not b:
        return None

    def text(m):
        used = f" · {m['used_gb']:.1f} GB" if m.get("used_gb") is not None else ""
        return f"{m['percent']:.1f}%{used}"

    high_after = a["percent"] >= troubleshooting.MEMORY_HIGH
    dropped = b["percent"] - a["percent"] >= MEMORY_DROP_POINTS
    return VerificationCheck(
        label="Memory in use", before=text(b),
        after=text(a) + (" · Still high" if high_after else ""),
        before_level=(Level.CAUTION if b["percent"] >= troubleshooting.MEMORY_HIGH
                      else Level.OK),
        after_level=Level.CAUTION if high_after else Level.OK,
        status=(CheckStatus.IMPROVED if dropped and not high_after
                else CheckStatus.OK if not high_after else CheckStatus.UNCHANGED))


def _bool_check(label: str, key: str, good: str, bad: str) -> CheckDef:
    def build(before: Results, after: Results) -> VerificationCheck | None:
        b, a = ev.network(before).get(key), ev.network(after).get(key)
        if a is None:
            return None
        return VerificationCheck(
            label=label, before="Not measured" if b is None else (good if b else bad),
            after=good if a else bad,
            before_level=Level.OK if b else Level.CRITICAL,
            after_level=Level.OK if a else Level.CRITICAL,
            status=(CheckStatus.IMPROVED if a and not b else CheckStatus.OK if a
                    else CheckStatus.UNCHANGED))

    return CheckDef(label, (), build, lambda b, a: f"{label.lower()} is working")


def _free_space(before: Results, after: Results) -> VerificationCheck | None:
    b, a = ev.disk(before), ev.disk(after)
    if not a or not b or a["free_gb"] is None or b["free_gb"] is None:
        return None
    gained = a["free_gb"] - b["free_gb"] >= SPACE_GAIN_GB
    return VerificationCheck(
        label=f"Free space on {a['drive']}", before=f"{b['free_gb']:.1f} GB",
        after=f"{a['free_gb']:.1f} GB" + (" · Still low" if a["low"] else ""),
        before_level=Level.CAUTION if b["low"] else Level.OK,
        after_level=Level.CAUTION if a["low"] else Level.OK,
        status=CheckStatus.IMPROVED if gained else CheckStatus.UNCHANGED)


def _space_phrase(before: Results, after: Results) -> str:
    b, a = ev.disk(before), ev.disk(after)
    if b and a and a["free_gb"] is not None and b["free_gb"] is not None \
            and a["free_gb"] > b["free_gb"]:
        return f"freed {a['free_gb'] - b['free_gb']:.1f} GB"
    return ""


def _size_check(label: str, field: str) -> CheckDef:
    def build(before: Results, after: Results) -> VerificationCheck | None:
        b, a = ev.reclaimable(before), ev.reclaimable(after)
        if not a or not b or a.get(field) is None or b.get(field) is None:
            return None
        improved = a[field] <= b[field] * SIZE_DROP_RATIO
        return VerificationCheck(
            label=label, before=ev.size_text(b[field]), after=ev.size_text(a[field]),
            before_level=Level.CAUTION if b[field] >= troubleshooting.RECLAIM_MB else Level.INFO,
            after_level=Level.OK if a[field] < troubleshooting.RECLAIM_MB else Level.CAUTION,
            status=CheckStatus.IMPROVED if improved else CheckStatus.UNCHANGED)

    return CheckDef(label, ("get_reclaimable_space",), build)


def _adapters(before: Results, after: Results) -> VerificationCheck | None:
    b, a = ev.network(before)["adapters_up"], ev.network(after)["adapters_up"]
    if a is None:
        return None
    return VerificationCheck(
        label="Connected adapters", before="—" if b is None else str(b), after=str(a),
        after_level=Level.OK if a else Level.CRITICAL,
        status=CheckStatus.OK if a else CheckStatus.UNCHANGED)


def _explorer(before: Results, after: Results) -> VerificationCheck | None:
    groups = ev.app_groups(after)
    if not groups:
        return None
    running = any(g["name"].lower() == "explorer.exe" for g in groups)
    return VerificationCheck(label="Windows Explorer", before="Restarted",
                             after="Running" if running else "Not running",
                             after_level=Level.OK if running else Level.CAUTION,
                             status=CheckStatus.OK if running else CheckStatus.UNCHANGED)


def _unresponsive(before: Results, after: Results) -> VerificationCheck | None:
    a = ev.unresponsive_apps(after)
    b = ev.unresponsive_apps(before)
    return VerificationCheck(label="Apps not responding", before=str(len(b)), after=str(len(a)),
                             after_level=Level.OK if not a else Level.CAUTION,
                             status=CheckStatus.IMPROVED if len(a) < len(b)
                             else CheckStatus.UNCHANGED)


CHECKS: dict[str, CheckDef] = {
    "search_service": CheckDef("Windows Search service", ("get_search_indexer_status",
                                                          "get_important_services"),
                               _search_service, lambda b, a: "Windows Search is running normally"),
    "indexer_memory": CheckDef("Search indexer memory", ("get_running_processes",),
                               _indexer_memory, _indexer_phrase),
    "memory_in_use": CheckDef("Memory in use", ("get_memory_usage",), _memory_in_use,
                              lambda b, a: "memory use is back to normal"),
    "update_service": _service_check("wuauserv", "Windows Update service"),
    "bits_service": _service_check("bits", "Background download service"),
    "spooler_service": _service_check("Spooler", "Print Spooler"),
    "audio_service": _service_check("Audiosrv", "Windows Audio"),
    "bluetooth_service": _service_check("bthserv", "Bluetooth Support"),
    "wlan_service": _service_check("WlanSvc", "WLAN AutoConfig"),
    "dns": _bool_check("DNS resolution", "dns_working", "Working", "Failing"),
    "internet": _bool_check("Internet connection", "internet", "Connected", "No connection"),
    "gateway": _bool_check("Router connection", "gateway_reachable", "Responds", "No reply"),
    "free_space": CheckDef("Free space", ("get_disk_free_space",), _free_space, _space_phrase),
    "temp_files": _size_check("Temporary files", "temp_mb"),
    "recycle_bin": _size_check("Recycle Bin", "recycle_mb"),
    "adapter": CheckDef("Connected adapters", ("get_network_adapters",), _adapters),
    "explorer": CheckDef("Windows Explorer", ("get_running_processes",), _explorer),
    "unresponsive": CheckDef("Apps not responding", ("get_unresponsive_apps",), _unresponsive),
}

_ORDINALS = ["first", "second", "third", "fourth"]


def check_ids(info: FixInfo) -> list[str]:
    ids = list(info.checks) + list(info.extra.get("also_checks", ()))
    return [i for i in dict.fromkeys(ids) if i in CHECKS]


class VerificationEngine:
    def __init__(self) -> None:
        self.registry = get_registry()

    # --- planning ----------------------------------------------------------
    def tools_for(self, session: Session, proposal: RemediationProposal) -> list[str]:
        """The same measurements that were taken before the fix."""
        info = fix_info(proposal.tool)
        before = session.diagnostics
        wanted: list[str] = list(proposal.verification_tools or info.verify_tools)
        for cid in check_ids(info):
            wanted.extend(CHECKS[cid].tools)
        if session.diagnosis:
            for cause in session.diagnosis.possible_causes:
                if cause.id in self._targets(session, proposal):
                    wanted.extend(cause.sources)
        ordered = [t for t in dict.fromkeys(wanted) if self.registry.has(t)]
        # Like-for-like: prefer tools that produced evidence before the fix.
        measured = [t for t in ordered if t in before and before[t].get("success")]
        extra = [t for t in (proposal.verification_tools or info.verify_tools)
                 if t in ordered and t not in measured]
        return measured + extra

    def pending_checks(self, session: Session,
                       proposal: RemediationProposal) -> list[VerificationCheck]:
        """Rows to show while measuring: before values known, after pending."""
        rows = []
        for cid in check_ids(fix_info(proposal.tool)):
            row = CHECKS[cid].build(session.diagnostics, session.diagnostics)
            if row:
                row.after, row.after_level, row.status = "Measuring…", Level.INFO, \
                    CheckStatus.UNAVAILABLE
                rows.append(row)
        return rows

    @staticmethod
    def _targets(session: Session, proposal: RemediationProposal) -> set[str]:
        targets = set()
        if proposal.cause_id:
            targets.add(proposal.cause_id)
        if session.diagnosis:
            problems = [c for c in session.diagnosis.possible_causes
                        if c.level in (Level.CAUTION, Level.CRITICAL)]
            if problems:
                targets.add(problems[0].id)
        return targets

    # --- run -----------------------------------------------------------------
    def run(
        self,
        session: Session,
        proposal: RemediationProposal,
        outcome: RemediationOutcome,
        *,
        settle_seconds: float | None = None,
        progress: ProgressCallback | None = None,
    ) -> VerificationResult:
        info = fix_info(proposal.tool)
        attempt = max(1, len(session.remediations))
        before = session.diagnostics

        if not outcome.success:
            return self._not_applied(outcome, info, attempt)

        delay = info.settle_seconds if settle_seconds is None else settle_seconds
        if delay > 0:
            time.sleep(delay)

        fresh: Results = {}
        for tool in self.tools_for(session, proposal):
            fresh[tool] = self.registry.execute_tool(tool)
            if progress:
                progress(tool, fresh[tool])
        after = {**before, **fresh}

        category = session.diagnosis.category if session.diagnosis else None
        after_diag = troubleshooting.analyze(category, after) if category else None

        checks, phrases = [], []
        for cid in check_ids(info):
            definition = CHECKS[cid]
            row = definition.build(before, after)
            if row is None:
                continue
            checks.append(row)
            if row.status in (CheckStatus.OK, CheckStatus.IMPROVED) and definition.phrase:
                phrase = definition.phrase(before, after)
                if phrase:
                    phrases.append(phrase)

        primary = checks[0] if checks else None
        action_effective = None if primary is None else primary.status in (
            CheckStatus.OK, CheckStatus.IMPROVED)

        targets = self._targets(session, proposal)
        remaining = [c for c in (after_diag.possible_causes if after_diag else [])
                     if c.id in targets and c.level in (Level.CAUTION, Level.CRITICAL)]
        if proposal.evidence_backed:
            improved = bool(action_effective is not False and not remaining)
        else:
            # Nothing specific was measured before, so success means the change
            # took effect and the fresh checks show no problem.
            improved = bool(action_effective) and (
                after_diag is None or after_diag.level in (Level.OK, Level.INFO))

        result = VerificationResult(
            improved=improved, action_effective=action_effective, checks=checks,
            remaining_causes=[c.id for c in remaining],
            before={t: before.get(t) for t in fresh},
            after=fresh,
            metrics=[f"{c.label}: {c.before} → {c.after}" for c in checks],
        )
        self._write_copy(result, info, phrases, remaining, attempt, after)
        logger.info("verification complete",
                    extra={"component": "engine", "event": "verify", "tool": proposal.tool,
                           "status": "resolved" if improved else "not_resolved"})
        return result

    # --- wording -------------------------------------------------------------
    @staticmethod
    def _join(phrases: list[str]) -> str:
        phrases = [p for p in phrases if p]
        if not phrases:
            return ""
        text = phrases[0]
        if len(phrases) == 2:
            text += f" and {phrases[1]}"
        elif len(phrases) > 2:
            text += ", " + ", ".join(phrases[1:-1]) + f", and {phrases[-1]}"
        return text[0].upper() + text[1:]

    def _write_copy(self, result: VerificationResult, info: FixInfo, phrases: list[str],
                    remaining, attempt: int, after: Results) -> None:
        ordinal = _ORDINALS[min(attempt, len(_ORDINALS)) - 1]
        if result.improved:
            result.headline = info.success_headline
            sentence = self._join(phrases)
            result.summary = ((sentence + ". ") if sentence else "") + \
                "WinFix confirmed this by measuring your PC after the fix."
            app = ev.top_app(after)
            if app and app["memory_mb"] >= 1536:
                result.note = (f"{app['display_name']} is still using "
                               f"{ev.size_text(app['memory_mb'])}. If your PC feels slow "
                               "again, start a new troubleshooting session.")
            return
        if result.action_effective is False:
            result.headline = "The fix didn't take effect."
            result.summary = ("WinFix applied the change, but measuring your PC afterwards "
                              "shows it didn't work.")
            result.found = "The measurements after the fix are shown below."
            return
        result.headline = f"The {ordinal} fix did not resolve the problem."
        result.summary = ("WinFix verified the system after applying the fix, but the "
                          "original issue is still present.")
        done = self._join([p for p in phrases if "back to normal" not in p])
        still = " ".join(c.detail for c in remaining[:2])
        result.found = (f"The fix worked as intended: {done[0].lower() + done[1:]}. "
                        if done else "The change was applied. ") + still
        app = ev.top_app(after)
        if app and any(c.id == "memory_pressure" for c in remaining):
            result.found += (f" The next checks look at the apps using the most memory, "
                             f"starting with {app['display_name']} "
                             f"({ev.size_text(app['memory_mb'])}).")
        result.note = ("The change WinFix made is still in place. " + info.kept_note).strip()

    @staticmethod
    def _not_applied(outcome: RemediationOutcome, info: FixInfo, attempt: int) -> VerificationResult:
        error = outcome.error or {}
        message = str(error.get("message") or "The fix could not be completed.")
        kind = error.get("type", "")
        if kind == "ElevationDeclined":
            summary = "Administrator permission wasn't granted, so nothing was changed."
        elif kind == "UnsupportedPlatform":
            summary = "This fix can only be applied on Windows. Nothing was changed."
        else:
            summary = f"WinFix couldn't complete the change: {message}"
        return VerificationResult(improved=False, action_effective=False,
                                  headline="The fix couldn't be applied.", summary=summary,
                                  found="Your PC was measured before the fix; see the "
                                        "diagnosis for details.")
