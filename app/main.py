"""WinFix AI entrypoint / CLI.

Subcommands:

    gui        Launch the desktop application (default).
    serve      Start the FastAPI backend.
    diagnose   Run the agent on a problem and print the diagnosis.
    tools      List all registered diagnostic and remediation tools.
    report     Run a broad read-only diagnostic sweep and save a JSON report.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from app.core.config import get_settings
from app.core.logging_setup import setup_logging


def _cmd_gui(_args: argparse.Namespace) -> int:
    from app.gui.main_window import main as gui_main

    return gui_main()


def _cmd_serve(_args: argparse.Namespace) -> int:
    from app.api.server import run

    run()
    return 0


def _cmd_diagnose(args: argparse.Namespace) -> int:
    from app.core.agent import Agent
    from app.core.history import HistoryStore

    agent = Agent(history=HistoryStore())
    result = agent.diagnose(args.problem)
    s = result.session

    print(f"\nProblem:   {s.problem}")
    print(f"Category:  {s.plan.category.value if s.plan else 'unknown'}")
    print("\nReasoning:")
    for step in result.steps:
        print(f"  - {step.message}")
    print(f"\nDiagnosis: {s.diagnosis.summary if s.diagnosis else 'n/a'}")
    if s.diagnosis and s.diagnosis.possible_causes:
        print("\nPossible causes:")
        for c in s.diagnosis.possible_causes:
            print(f"  • {c.cause} ({c.likelihood_word}, {c.confidence:.0%})")
            for e in c.evidence:
                print(f"      - {e}")
    if s.proposals:
        print("\nRecommended fixes (require your approval):")
        for p in s.proposals:
            print(f"  • {p.title} [{p.risk_level.value} risk] -> {p.tool}")
    print(f"\nSession saved with id: {s.id}")
    return 0


def _cmd_tools(_args: argparse.Namespace) -> int:
    from app.core.tool_registry import get_registry

    reg = get_registry()
    print("Diagnostic tools (read-only):")
    for s in reg.list_tools(read_only=True):
        print(f"  {s.name:<32} {s.category:<12} {s.description}")
    print("\nRemediation tools (require approval):")
    for s in reg.list_tools(read_only=False):
        print(f"  {s.name:<32} {s.category:<12} [{s.risk_level.value}] {s.description}")
    return 0


def _cmd_report(_args: argparse.Namespace) -> int:
    from app.core.diagnostic_engine import DiagnosticEngine

    settings = get_settings()
    engine = DiagnosticEngine()
    tools = ["get_system_info", "get_cpu_usage", "get_memory_usage",
             "get_disk_usage", "get_network_adapters", "test_dns"]
    results = engine.run(tools)
    report = {"timestamp": datetime.now().isoformat(), "diagnostics": results}
    filename = settings.reports_dir / (
        f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    filename.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved to: {filename}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="winfix", description="WinFix AI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="Launch the desktop application")
    sub.add_parser("serve", help="Start the FastAPI backend")

    diag = sub.add_parser("diagnose", help="Diagnose a problem")
    diag.add_argument("problem", help="Describe the problem in natural language")

    sub.add_parser("tools", help="List registered tools")
    sub.add_parser("report", help="Run a broad diagnostic sweep and save JSON")
    return parser


def _helper_mode(argv: list[str]) -> int | None:
    """Elevated one-shot helper: ``--run-remediation TOOL --arguments JSON --result PATH``."""
    from app.core.elevation import HELPER_FLAG, helper_main

    if HELPER_FLAG not in argv:
        return None
    try:
        tool = argv[argv.index(HELPER_FLAG) + 1]
        arguments = argv[argv.index("--arguments") + 1]
        result = argv[argv.index("--result") + 1]
    except (ValueError, IndexError):
        return 2
    return helper_main(tool, arguments, result)


def main(argv: list[str] | None = None) -> int:
    import sys

    setup_logging()
    argv = list(sys.argv[1:] if argv is None else argv)
    helper = _helper_mode(argv)
    if helper is not None:
        return helper
    parser = build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "gui": _cmd_gui,
        "serve": _cmd_serve,
        "diagnose": _cmd_diagnose,
        "tools": _cmd_tools,
        "report": _cmd_report,
    }
    command = args.command or "gui"
    return dispatch[command](args)


if __name__ == "__main__":
    raise SystemExit(main())
