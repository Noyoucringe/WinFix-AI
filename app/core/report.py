"""Human-readable session reports (History > Export report)."""

from __future__ import annotations

from app import __version__
from app.core.models import Session, SessionResult
from app.knowledge.checks import info as check_info

RESULT_TEXT = {
    SessionResult.RESOLVED: "Resolved",
    SessionResult.NOT_RESOLVED: "Not resolved",
    SessionResult.NO_ISSUE: "No problem found",
    SessionResult.STOPPED: "Stopped by you",
    SessionResult.FAILED: "Failed",
    SessionResult.IN_PROGRESS: "In progress",
}


def _time(dt) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if dt else "—"


def session_report(session: Session, *, app_version: str | None = None) -> str:
    lines = [
        "WinFix AI — troubleshooting report",
        "=" * 36,
        f"Session ID:   {session.display_id}",
        f"Started:      {_time(session.created_at)}",
        f"Finished:     {_time(session.finished_at)}",
        f"Result:       {RESULT_TEXT.get(session.result, session.result.value)}",
        f"Problem:      \"{session.problem}\"",
        f"Analysis:     {'Cloud (' + (session.cloud.provider or '') + ')' if session.cloud.sent else 'On this PC'}",
        f"Sent to cloud: {', '.join(session.cloud.items) if session.cloud.sent else 'Nothing'}",
        f"WinFix AI version: {app_version or __version__}",
        "",
    ]
    if session.diagnosis:
        d = session.diagnosis
        lines += ["Diagnosis", "-" * 9, d.headline, d.summary, ""]
        for card in d.evidence_cards:
            lines.append(f"  {card.label}: {card.value} — {card.detail} ({card.status_text})")
        if d.possible_causes:
            lines += ["", "Possible causes:"]
            for i, cause in enumerate(d.possible_causes, 1):
                lines.append(f"  {i}. {cause.cause} ({cause.likelihood_word}) — {cause.detail}")
        for note in d.notes:
            lines.append(f"  Note: {note}")
        lines.append("")
    lines += ["Checks run (read-only)", "-" * 22]
    for check in session.checks:
        duration = f" · {check.duration_ms:.0f} ms" if check.duration_ms else ""
        lines.append(f"  [{check.status}] {check.label}: {check.summary} "
                     f"(source: {check.source or check_info(check.tool).source}{duration})")
    lines.append("")
    if session.remediations:
        lines += ["Changes made", "-" * 12]
        for r in session.remediations:
            status = "applied" if r.success else "not applied"
            lines.append(f"  {r.tool}: {status}; approved by you at {_time(r.approved_at)}"
                         + ("; ran with administrator permission" if r.elevated else ""))
            if r.error:
                lines.append(f"    Detail: {r.error.get('message', '')}")
        lines.append("")
    else:
        lines += ["Changes made: none", ""]
    for i, v in enumerate(session.verifications, 1):
        lines += [f"Verification {i}", "-" * 14, v.headline, v.summary]
        for c in v.checks:
            lines.append(f"  {c.label}: {c.before} → {c.after}")
        if v.found:
            lines.append(f"  {v.found}")
        lines.append("")
    lines += ["Timeline", "-" * 8]
    for event in session.timeline:
        lines.append(f"  {_time(event.at)}  {event.title}"
                     + (f" — {event.detail}" if event.detail else ""))
    return "\n".join(lines) + "\n"
