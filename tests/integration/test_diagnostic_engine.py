"""Integration tests for the diagnostic engine."""

from app.core.diagnostic_engine import DiagnosticEngine


def test_engine_runs_tools_and_collects_results():
    engine = DiagnosticEngine()
    results = engine.run(["get_cpu_usage", "get_memory_usage", "get_disk_usage"])
    assert set(results) == {"get_cpu_usage", "get_memory_usage", "get_disk_usage"}
    assert all("success" in r for r in results.values())


def test_engine_continues_after_failure():
    """A failing/unsupported tool must not stop the others."""
    engine = DiagnosticEngine()
    results = engine.run(["get_startup_apps", "get_cpu_usage"])
    assert "get_cpu_usage" in results and results["get_cpu_usage"]["success"]
    # get_startup_apps is recorded even if unsupported off-Windows.
    assert "get_startup_apps" in results


def test_engine_refuses_remediation_tool():
    engine = DiagnosticEngine()
    results = engine.run(["flush_dns"])
    assert results["flush_dns"]["success"] is False


def test_engine_progress_callback():
    seen = []
    engine = DiagnosticEngine()
    engine.run(["get_cpu_usage"], progress=lambda name, r: seen.append(name))
    assert seen == ["get_cpu_usage"]
