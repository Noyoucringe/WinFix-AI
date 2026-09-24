"""LLM output is untrusted: tool requests are validated, text is checked,
failures fall back to local analysis, and nothing unsanitized is sent."""

import pytest

from app.core.agent import Agent
from app.core.models import Category
from app.llm import provider as provider_module
from app.llm.provider import AI_UNAVAILABLE, CloudProvider, parse_tool_selection
from tests.scenarios import SLOW_PC


class FakeCloud(CloudProvider):
    name = "fake"
    label = "Fake cloud"

    def __init__(self, replies, **kw):
        super().__init__(endpoint="https://ai.example.com/v1", model="m", api_key="sk-test-1234",
                         **kw)
        self.replies = list(replies)
        self.sent: list[str] = []

    def _chat(self, system, user):
        self.sent.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_malicious_tool_requests_are_rejected(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud([
        '{"tools": ["powershell -Command Remove-Item C:\\\\ -Recurse", "flush_dns", '
        '"get_memory_details", "../../evil", "not_a_tool"]}',
        "Your PC is likely short on memory.",
    ])
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    extra = [c.tool for c in session.checks[7:]]
    assert extra == ["get_memory_details"]  # the only safe, read-only request
    rejected = [e for e in session.timeline if e.kind == "rejected"]
    assert len(rejected) == 4  # shell string, remediation, path traversal, unknown
    assert scenario.remediation_calls == []  # 'flush_dns' was never executed


def test_garbage_tool_output_falls_back_to_local_rules(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(["I think you should run rm -rf /", "Memory is likely high."])
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    assert session.diagnosis is not None  # diagnosis completed regardless


@pytest.mark.parametrize("reply", [
    "Run this: ```powershell Stop-Service WSearch```",
    "Visit https://evil.example.com to fix it",
    "x" * 900,
    "",
])
def test_unsafe_or_bad_summaries_are_rejected(scenario, reply):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(['{"tools": []}', reply])
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    d = session.diagnosis
    assert d.ai_status == "unavailable" and d.ai_message == AI_UNAVAILABLE
    assert d.summary.startswith("Your PC is experiencing memory pressure.")


def test_ai_outage_keeps_local_diagnostics_working(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud([ConnectionError("offline"), ConnectionError("offline")])
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    assert session.diagnosis.ai_message == AI_UNAVAILABLE
    assert session.proposals and session.proposals[0].tool == "restart_windows_search"


def test_cloud_summary_is_used_and_transmission_recorded(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(['{"tools": []}', "Memory pressure is the likely cause."],
                      send_process_names=False)
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    assert session.diagnosis.summary == "Memory pressure is the likely cause."
    assert session.diagnosis.ai_status == "cloud"
    assert session.cloud.sent is True
    assert session.cloud.endpoint_host == "ai.example.com"
    assert session.cloud.items == ["Measurements and findings"]
    # App names were excluded because the user turned that toggle off.
    assert all("Chrome" not in payload for payload in cloud.sent)


def test_unconfigured_cloud_reports_unavailable_without_sending():
    cloud = FakeCloud([])
    cloud._api_key = None
    from tests.scenarios import results_for

    d = cloud.analyze("slow", Category.SLOW_COMPUTER, results_for(SLOW_PC))
    assert d.ai_message == AI_UNAVAILABLE and cloud.sent == []


def test_parse_tool_selection_is_strict():
    assert parse_tool_selection('ok {"tools": ["a", "b"]}') == ["a", "b"]
    for bad in ["no json", '{"tools": "a"}', '{"tools": [1, 2]}', "[]"]:
        with pytest.raises(Exception):
            parse_tool_selection(bad)


def test_provider_repr_never_contains_the_key():
    assert "sk-test" not in repr(FakeCloud([]))


def test_local_is_default_provider():
    assert provider_module.get_provider().name == "local"


def test_connection_test_errors_never_include_the_key():
    import httpx

    from app.llm.provider import OpenAICompatibleProvider

    secret = "sk-live-SECRETSECRETSECRET1234"
    provider = OpenAICompatibleProvider(endpoint="https://api.example.com/v1",
                                        model="m", api_key=secret)

    def fail(system, user):
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions",
                                headers={"Authorization": f"Bearer {secret}"})
        raise httpx.HTTPStatusError(f"401 for {secret}", request=request,
                                    response=httpx.Response(401, request=request))

    provider._chat = fail
    ok, message = provider.test_connection()
    assert not ok
    assert message == "The provider rejected the API key."
    assert secret not in message and secret not in repr(provider)


def test_connection_test_sends_no_diagnostic_data():
    from app.llm.provider import OpenAICompatibleProvider

    sent = []
    provider = OpenAICompatibleProvider(endpoint="https://api.example.com/v1",
                                        model="m", api_key="k" * 20)
    provider._chat = lambda system, user: sent.append((system, user)) or "OK"
    ok, _message = provider.test_connection()
    assert ok
    assert sent == [("Reply with the single word OK.", "Connection test")]
