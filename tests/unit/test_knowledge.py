"""Tests for classification and evidence interpretation."""

import pytest

from app.core.models import Category
from app.core.result import success_result
from app.knowledge import troubleshooting
from app.knowledge.categories import CATEGORIES, classify


@pytest.mark.parametrize("problem,expected", [
    ("My laptop is very slow", Category.SLOW_COMPUTER),
    ("My Wi-Fi keeps disconnecting", Category.WIFI_DISCONNECTING),
    ("Windows Update is not working", Category.WINDOWS_UPDATE),
    ("My disk is almost full", Category.LOW_DISK_SPACE),
    ("Bluetooth isn't working", Category.BLUETOOTH),
    ("My audio isn't working", Category.AUDIO),
    ("Windows Search isn't working", Category.WINDOWS_SEARCH),
    ("My printer won't print", Category.PRINTER),
])
def test_classify(problem, expected):
    assert classify(problem) == expected


def test_classify_unknown():
    assert classify("the weather is nice today") == Category.UNKNOWN


def test_all_15_categories_defined():
    # 15 real categories (UNKNOWN is not in the map).
    assert len(CATEGORIES) == 15
    for spec in CATEGORIES.values():
        assert spec.diagnostic_tools  # every category names diagnostics


def test_category_remediations_reference_registered_tools():
    from app.core.tool_registry import get_registry

    reg = get_registry()
    for spec in CATEGORIES.values():
        for tool in spec.remediation_tools:
            assert reg.has(tool), f"{tool} not registered"
        for tool in spec.diagnostic_tools:
            assert reg.has(tool), f"{tool} not registered"


def test_analyze_high_memory_produces_cause():
    results = {
        "get_memory_usage": success_result("get_memory_usage", {
            "usage_percent": 93, "available_gb": 0.8, "swap_percent": 10}),
        "get_top_memory_processes": success_result("get_top_memory_processes", {
            "top_memory_processes": [{"name": "chrome", "memory_mb": 4800}]}),
    }
    diag = troubleshooting.analyze(Category.HIGH_MEMORY, results)
    assert diag.possible_causes
    top = diag.top_cause
    assert "memory" in top.cause.lower()
    assert any("93%" in e for e in top.evidence)
    assert top.confidence >= 0.7


def test_analyze_low_disk():
    results = {
        "get_disk_free_space": success_result("get_disk_free_space", {
            "free_gb": 2.0, "usage_percent": 96, "low_space": True}),
    }
    diag = troubleshooting.analyze(Category.LOW_DISK_SPACE, results)
    assert diag.top_cause.cause == "Low free disk space"


def test_analyze_dns_failure():
    results = {
        "ping_gateway": success_result("ping_gateway", {"reachable": True, "gateway": "1.1.1.1"}),
        "test_dns": success_result("test_dns", {"dns_working": False, "resolved_count": 0, "total": 2}),
    }
    diag = troubleshooting.analyze(Category.DNS_PROBLEMS, results)
    assert any("DNS" in c.cause for c in diag.possible_causes)


def test_analyze_no_signal():
    results = {
        "get_memory_usage": success_result("get_memory_usage", {
            "usage_percent": 20, "available_gb": 12, "swap_percent": 0}),
    }
    diag = troubleshooting.analyze(Category.HIGH_MEMORY, results)
    assert diag.possible_causes == []
    assert "not clearly" in diag.summary
