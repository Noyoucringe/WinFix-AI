"""Sign-in health check: read-only, reports only real problems."""

from __future__ import annotations

from app.core.health import HEALTH_TOOLS, run_health_check
from app.core.models import Level
from app.demo_evidence import STORAGE_FULL


def test_health_check_uses_only_read_only_tools(registry):
    for name in HEALTH_TOOLS:
        assert registry.get_tool(name).read_only


def test_health_check_flags_low_disk_space(scenario):
    scenario.use(STORAGE_FULL)
    report = run_health_check()
    assert report.needs_attention
    assert report.level in (Level.CAUTION, Level.CRITICAL)
    assert report.findings

