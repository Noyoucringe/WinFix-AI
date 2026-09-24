"""Integration tests for the verification engine's before/after comparison."""

from app.core.models import Category
from app.core.result import success_result
from app.core.verification_engine import VerificationEngine


def test_memory_improvement_detected(monkeypatch):
    engine = VerificationEngine()
    before = {"get_memory_usage": success_result("get_memory_usage",
                                                 {"usage_percent": 92})}
    # Force the "after" measurement to a lower value.
    monkeypatch.setattr(engine.registry, "execute_tool",
                        lambda name: success_result(name, {"usage_percent": 40}))
    result = engine.run(Category.HIGH_MEMORY, ["get_memory_usage"], before)
    assert result.improved is True
    assert result.metrics


def test_no_improvement_when_unchanged(monkeypatch):
    engine = VerificationEngine()
    before = {"get_memory_usage": success_result("get_memory_usage",
                                                 {"usage_percent": 40})}
    monkeypatch.setattr(engine.registry, "execute_tool",
                        lambda name: success_result(name, {"usage_percent": 40}))
    result = engine.run(Category.HIGH_MEMORY, ["get_memory_usage"], before)
    assert result.improved is False


def test_connectivity_recovery_detected(monkeypatch):
    engine = VerificationEngine()
    before = {"test_internet": success_result("test_internet",
                                              {"internet_reachable": False})}
    monkeypatch.setattr(engine.registry, "execute_tool",
                        lambda name: success_result(name, {"internet_reachable": True}))
    result = engine.run(Category.INTERNET_DOWN, ["test_internet"], before)
    assert result.improved is True


def test_no_measurable_signal(monkeypatch):
    engine = VerificationEngine()
    monkeypatch.setattr(engine.registry, "has", lambda name: False)
    result = engine.run(Category.BLUETOOTH, ["get_important_services"], {})
    assert result.improved is False
    assert "Could not measure" in result.summary
