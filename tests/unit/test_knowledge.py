"""Classification, evidence interpretation and fix proposals."""

import pytest

from app.core.models import Category, Level
from app.core.remediation_engine import RemediationEngine
from app.core.result import success_result
from app.core.safety import SafetyValidator
from app.knowledge import troubleshooting
from app.knowledge.categories import CATEGORIES, classify
from app.knowledge.remediations import FIXES
from tests.scenarios import SCENARIOS, results_for


@pytest.mark.parametrize("problem,expected", [
    ("My laptop is very slow", Category.SLOW_COMPUTER),
    ("My Wi-Fi keeps disconnecting", Category.WIFI_DISCONNECTING),
    ("Wi-Fi keeps disconnecting", Category.WIFI_DISCONNECTING),
    ("Windows Update isn't working", Category.WINDOWS_UPDATE),
    ("Windows Update isn’t working", Category.WINDOWS_UPDATE),
    ("My storage is almost full", Category.LOW_DISK_SPACE),
    ("My disk is almost full", Category.LOW_DISK_SPACE),
    ("Bluetooth isn't working", Category.BLUETOOTH),
    ("My audio isn't working", Category.AUDIO),
    ("Windows Search isn't working", Category.WINDOWS_SEARCH),
    ("My printer won't print", Category.PRINTER),
    ("My apps keep crashing", Category.APP_CRASHES),
])
def test_classify(problem, expected):
    assert classify(problem) == expected


def test_classify_unknown():
    assert classify("the weather is nice today") == Category.UNKNOWN


def test_short_keywords_match_whole_words_only():
    # "fan" must not fire on "infant", "hot" not on "photo".
    assert classify("my infant took a photo") == Category.UNKNOWN


def test_all_15_categories_defined():
    assert len(CATEGORIES) == 15
    for spec in CATEGORIES.values():
        assert spec.diagnostic_tools


def test_category_tools_are_registered_and_cataloged():
    from app.core.tool_registry import get_registry

    reg = get_registry()
    for spec in CATEGORIES.values():
        for tool in (*spec.diagnostic_tools, *spec.thorough_tools):
            assert reg.has(tool) and reg.get_tool(tool).read_only, tool
        for tool in spec.remediation_tools:
            assert reg.has(tool) and not reg.get_tool(tool).read_only, tool
            assert tool in FIXES, f"{tool} has no plain-language catalog entry"
        if spec.general_fix:
            assert spec.general_fix in spec.remediation_tools


def test_every_registered_fix_has_catalog_copy():
    from app.core.tool_registry import get_registry

    for spec in get_registry().list_tools(read_only=False):
        info = FIXES[spec.name]
        assert info.title and info.change and info.what_changes and info.steps


def test_slow_pc_matches_design_example():
    d = troubleshooting.analyze(Category.SLOW_COMPUTER, results_for(SCENARIOS["slow_pc"]))
    assert d.headline == "Your PC is experiencing memory pressure."
    assert d.level == Level.CAUTION
    ids = [c.id for c in d.possible_causes]
    assert ids[:2] == ["memory_pressure", "search_indexer"]
    assert "large_apps" in ids
    assert "unresponsive" not in ids  # the hung indexer is not double-counted
    cards = {c.key: c for c in d.evidence_cards}
    assert cards["memory"].value == "73.2%" and cards["memory"].status_text == "High"
    assert cards["cpu"].status_text == "Normal utilization"
    assert cards["disk"].detail == "47.7 GB free on C:"
    assert cards["top_app"].value == "Google Chrome"
    assert cards["top_app"].detail == "4.8 GB across 14 processes"
    assert cards["indexer"].value == "2.1 GB" and cards["indexer"].status_text == "Not responding"
    assert any("WinFix never closes your apps" in n for n in d.notes)


def test_evidence_values_come_from_measurements():
    evidence = results_for(SCENARIOS["slow_pc"])
    evidence["get_memory_usage"]["data"]["usage_percent"] = 91.4
    d = troubleshooting.analyze(Category.SLOW_COMPUTER, evidence)
    assert d.evidence_cards[0].value == "91.4%"
    assert d.level == Level.CRITICAL


def test_healthy_pc_reports_no_issue_and_no_fix():
    results = results_for(SCENARIOS["healthy_pc"])
    d = troubleshooting.analyze(Category.SLOW_COMPUTER, results)
    assert d.level == Level.OK
    assert "didn't find a problem" in d.headline
    assert RemediationEngine().propose(d, results) == []


def test_low_disk_links_cleanup_fixes():
    results = results_for(SCENARIOS["storage_full"])
    d = troubleshooting.analyze(Category.LOW_DISK_SPACE, results)
    assert d.top_cause.id == "low_disk" and d.level == Level.CRITICAL
    tools = [p.tool for p in RemediationEngine().propose(d, results)]
    assert tools == ["clear_safe_temp_files", "empty_recycle_bin"]


def test_dns_failure_proposes_flush():
    results = results_for(SCENARIOS["dns_broken"])
    d = troubleshooting.analyze(Category.DNS_PROBLEMS, results)
    assert d.top_cause.id == "dns_failure"
    assert [p.tool for p in RemediationEngine().propose(d, results)][0] == "flush_dns"


def test_router_unreachable_resolves_adapter_parameter():
    results = results_for(SCENARIOS["wifi_router_down"])
    d = troubleshooting.analyze(Category.WIFI_DISCONNECTING, results)
    proposal = RemediationEngine().propose(d, results)[0]
    assert proposal.tool == "restart_network_adapter"
    assert proposal.parameters == {"adapter_name": "Wi-Fi"}  # the default-route adapter


def test_fix_with_unresolvable_parameters_is_never_offered():
    results = results_for(SCENARIOS["wifi_router_down"])
    results["ping_gateway"]["data"]["interface"] = None
    for adapter in results["get_network_adapters"]["data"]["adapters"]:
        adapter["virtual"] = True  # no real adapter to target
    d = troubleshooting.analyze(Category.WIFI_DISCONNECTING, results)
    tools = [p.tool for p in RemediationEngine().propose(d, results)]
    assert "restart_network_adapter" not in tools


@pytest.mark.parametrize("scenario,category", [
    ("slow_pc", Category.SLOW_COMPUTER),
    ("storage_full", Category.LOW_DISK_SPACE),
    ("wifi_router_down", Category.WIFI_DISCONNECTING),
    ("dns_broken", Category.DNS_PROBLEMS),
    ("update_service_stopped", Category.WINDOWS_UPDATE),
])
def test_every_proposal_passes_the_safety_gate_once_approved(scenario, category):
    """Regression: proposals used to lack required parameters, so approving
    them always failed validation."""
    results = results_for(SCENARIOS[scenario])
    d = troubleshooting.analyze(category, results)
    proposals = RemediationEngine().propose(d, results)
    assert proposals
    for p in proposals:
        SafetyValidator().validate_remediation(p.tool, approved=True, arguments=p.parameters)


def test_general_fix_is_marked_not_evidence_backed():
    results = {"get_important_services": success_result("get_important_services", {
        "services": {"Spooler": {"name": "Spooler", "label": "Print Spooler",
                                 "status": "running", "status_text": "Running",
                                 "healthy": True}}})}
    d = troubleshooting.analyze(Category.PRINTER, results)
    proposals = RemediationEngine().propose(d, results)
    assert [p.tool for p in proposals] == ["restart_print_spooler"]
    assert proposals[0].evidence_backed is False
    assert "No specific fault was measured" in proposals[0].reason


def test_close_apps_is_never_proposed():
    for name, evidence in SCENARIOS.items():
        results = results_for(evidence)
        for category in CATEGORIES:
            d = troubleshooting.analyze(category, results)
            tools = [p.tool for p in RemediationEngine().propose(d, results)]
            assert "terminate_unresponsive_application" not in tools


def test_disabled_update_service_is_left_alone():
    results = results_for(SCENARIOS["update_service_stopped"])
    wu = results["get_windows_update_status"]["data"]["services"]["wuauserv"]
    wu["start_type"] = "disabled"
    d = troubleshooting.analyze(Category.WINDOWS_UPDATE, results)
    assert d.top_cause.id == "update_disabled"
    assert RemediationEngine().propose(d, results) == []
    assert any("leaves that setting alone" in n for n in d.notes)


def test_bluetooth_missing_has_no_fake_fix():
    results = results_for(SCENARIOS["bluetooth_missing"])
    d = troubleshooting.analyze(Category.BLUETOOTH, results)
    assert d.top_cause.id == "bt_missing" and d.level == Level.CRITICAL
    # A general service restart is not offered when a critical fault is measured.
    assert RemediationEngine().propose(d, results) == []


def test_missing_fields_do_not_crash_analysis():
    results = {"get_memory_usage": success_result("get_memory_usage",
                                                  {"usage_percent": 93})}
    d = troubleshooting.analyze(Category.HIGH_MEMORY, results)
    assert d.top_cause.id == "memory_pressure"
    assert d.evidence_cards[0].detail == "In use"
