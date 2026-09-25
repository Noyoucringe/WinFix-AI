"""LLM output is untrusted: tool requests are validated, text is checked,
failures fall back to local analysis, and nothing unsanitized is sent."""

import pytest

from app.core.agent import Agent
from app.core.models import Category
from app.llm import provider as provider_module
from app.llm.provider import AI_UNAVAILABLE, CloudProvider, parse_tool_selection
from tests.scenarios import SLOW_PC


class FakeCloud(CloudProvider):
    """Answers each kind of request the agent makes: understanding the problem,
    choosing next checks (one reply per round), and writing the summary."""

    name = "fake"
    label = "Fake cloud"

    def __init__(self, *, understand=None, rounds=(), summary="Memory is likely high.",
                 endpoint="https://ai.example.com/v1", **kw):
        super().__init__(endpoint=endpoint, model="m", api_key="sk-test-1234", **kw)
        self.understand_reply = understand
        self.rounds = list(rounds)
        self.summary = summary
        self.sent: list[str] = []
        self.kinds: list[str] = []

    def _chat(self, system, user, schema=None, max_tokens=1024):
        self.sent.append(user)
        if "planning step" in system:
            kind, reply = "understand", self.understand_reply
        elif "investigating" in system:
            kind = "next"
            reply = self.rounds.pop(0) if self.rounds else \
                '{"enough_evidence": true, "next_checks": [], "reasoning": "Clear."}'
        else:
            kind, reply = "summary", self.summary
        self.kinds.append(kind)
        if reply is None:
            raise ConnectionError("no reply configured")
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_malicious_tool_requests_are_rejected(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(rounds=[
        '{"enough_evidence": false, "reasoning": "More.", "next_checks": ['
        '"powershell -Command Remove-Item C:\\\\ -Recurse", "flush_dns", '
        '"get_memory_details", "../../evil", "not_a_tool"]}'])
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    extra = [c.tool for c in session.checks[7:]]
    assert extra == ["get_memory_details"]  # the only safe, read-only request
    rejected = [e for e in session.timeline if e.kind == "rejected"]
    assert len(rejected) == 4  # shell string, remediation, path traversal, unknown
    assert scenario.remediation_calls == []  # 'flush_dns' was never executed


def test_ai_understanding_picks_category_and_checks(scenario):
    """The AI reads the user's words: 'gpu is laggy' becomes a graphics problem
    and GPU checks run, even though 'laggy' alone reads as a slow PC."""
    scenario.use(SLOW_PC)
    cloud = FakeCloud(understand=(
        '{"category": "graphics", "restated_problem": "Games and video on the GPU '
        'stutter.", "checks": ["get_gpu_usage", "get_display_driver_errors", "flush_dns", '
        '"rm -rf /"], "reasoning": "Measure GPU load and look for driver resets."}'))
    session = Agent(provider=cloud).diagnose("my gpu is laggy").session
    assert session.plan.category == Category.GRAPHICS
    assert session.plan.planned_by == "ai"
    assert session.plan.understood == "Games and video on the GPU stutter."
    tools = [c.tool for c in session.checks]
    assert tools[:2] == ["get_gpu_usage", "get_display_driver_errors"]
    assert "flush_dns" not in tools and "rm -rf /" not in tools
    assert any(e.kind == "ai" for e in session.timeline)
    # Only the problem text went out for understanding, scrubbed of identifiers.
    assert '"problem": "my gpu is laggy"' in cloud.sent[0]


def test_ai_invented_category_falls_back_to_offline_classifier(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(understand='{"category": "hacking", "restated_problem": "x", '
                                 '"checks": [], "reasoning": ""}')
    session = Agent(provider=cloud).diagnose("my gpu is laggy").session
    assert session.plan.category == Category.GRAPHICS  # from the offline classifier


def test_autonomous_rounds_are_bounded_by_the_step_limit(scenario):
    scenario.use(SLOW_PC)
    greedy = '{"enough_evidence": false, "reasoning": "More.", "next_checks": ' \
             '["get_memory_details", "get_disk_activity", "get_boot_time", ' \
             '"get_unresponsive_apps", "get_startup_apps", "get_top_cpu_processes"]}'
    cloud = FakeCloud(understand='{"category": "slow_computer", "restated_problem": "Slow.",'
                                 ' "checks": [], "reasoning": ""}',
                      rounds=[greedy] * 10)
    agent = Agent(provider=cloud)
    session = agent.diagnose("My laptop is very slow").session
    assert len(session.diagnostics) <= agent.max_steps
    assert cloud.kinds.count("next") <= 3


def test_garbage_tool_output_falls_back_to_local_rules(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(rounds=["I think you should run rm -rf /"])
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
    cloud = FakeCloud(summary=reply)
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    d = session.diagnosis
    assert d.ai_status == "unavailable" and d.ai_message == AI_UNAVAILABLE
    assert d.summary.startswith("Your PC is experiencing memory pressure.")


def test_ai_outage_keeps_local_diagnostics_working(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(understand=ConnectionError("offline"),
                      rounds=[ConnectionError("offline")], summary=ConnectionError("offline"))
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    assert session.diagnosis.ai_message == AI_UNAVAILABLE
    assert session.plan.planned_by == "rules"
    assert session.proposals and session.proposals[0].tool == "restart_windows_search"


def test_cloud_summary_is_used_and_transmission_recorded(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(summary="Memory pressure is the likely cause.",
                      send_process_names=False)
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    assert session.diagnosis.summary == "Memory pressure is the likely cause."
    assert session.diagnosis.ai_status == "cloud"
    assert session.cloud.sent is True
    assert session.cloud.endpoint_host == "ai.example.com"
    assert session.cloud.items == ["Measurements and findings", "Your problem description"]
    # App names were excluded because the user turned that toggle off.
    assert all("Chrome" not in payload for payload in cloud.sent)


def test_local_ai_server_needs_no_key_and_is_not_a_cloud_transmission(scenario):
    scenario.use(SLOW_PC)
    cloud = FakeCloud(endpoint="http://localhost:11434/v1",
                      understand='{"category": "slow_computer", "restated_problem": "Slow.",'
                                 ' "checks": [], "reasoning": ""}')
    cloud._api_key = None
    assert cloud.available and cloud.on_this_pc
    session = Agent(provider=cloud).diagnose("My laptop is very slow").session
    assert session.plan.planned_by == "ai"
    assert session.cloud.sent is False


def test_unconfigured_cloud_reports_unavailable_without_sending():
    cloud = FakeCloud()
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
    assert "sk-test" not in repr(FakeCloud())


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

    provider._chat = lambda system, user, **kw: fail(system, user)
    ok, message = provider.test_connection()
    assert not ok
    assert message == "The provider rejected the API key."
    assert secret not in message and secret not in repr(provider)


def test_connection_test_sends_no_diagnostic_data():
    from app.llm.provider import OpenAICompatibleProvider

    sent = []
    provider = OpenAICompatibleProvider(endpoint="https://api.example.com/v1",
                                        model="m", api_key="k" * 20)
    provider._chat = lambda system, user, **kw: sent.append((system, user)) or "OK"
    ok, _message = provider.test_connection()
    assert ok
    assert sent == [("Reply with the single word OK.", "Connection test")]


class _FakeAnthropicClient:
    """Stands in for anthropic.Anthropic: records requests, returns canned replies."""

    def __init__(self, replies, calls, **kwargs):
        self.kwargs = kwargs
        outer = self

        class _Messages:
            def create(self, **params):
                calls.append(("messages", params))
                return outer._next(replies)

        class _Beta:
            messages = type("M", (), {"create": lambda _self, **params: (
                calls.append(("beta", params)), outer._next(replies))[1]})()

        self.messages = _Messages()
        self.beta = _Beta()

    @staticmethod
    def _next(replies):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _response(text, stop_reason="end_turn"):
    from types import SimpleNamespace

    return SimpleNamespace(stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=text)])


def _anthropic(monkeypatch, replies, model="claude-opus-5",
               endpoint="https://api.anthropic.com"):
    import anthropic

    from app.llm.provider import AnthropicProvider

    calls = []
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **kw: _FakeAnthropicClient(replies, calls, **kw))
    return AnthropicProvider(endpoint=endpoint, model=model, api_key="sk-ant-test"), calls


def test_claude_requests_use_schema_low_effort_and_refusal_fallback(monkeypatch):
    provider, calls = _anthropic(monkeypatch, [_response('{"category": "graphics", '
                                                         '"restated_problem": "GPU lag.", '
                                                         '"checks": [], "reasoning": ""}')])
    understood = provider.understand("my gpu is laggy", ["get_gpu_usage"])
    assert understood.category == Category.GRAPHICS
    kind, params = calls[0]
    assert kind == "beta"  # server-side fallback is a beta feature on Claude Opus 5
    assert params["model"] == "claude-opus-5"
    assert params["fallbacks"] == "default"
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
    assert params["output_config"]["effort"] == "low"
    schema = params["output_config"]["format"]["schema"]
    assert schema["properties"]["checks"]["items"]["enum"] == ["get_gpu_usage"]
    assert "graphics" in schema["properties"]["category"]["enum"]


def test_claude_refusal_falls_back_to_offline_understanding(monkeypatch):
    provider, _calls = _anthropic(monkeypatch, [_response("", stop_reason="refusal")])
    assert provider.understand("my gpu is laggy", ["get_gpu_usage"]) is None


def test_claude_gateway_or_older_model_gets_a_plain_retry(monkeypatch):
    import anthropic
    import httpx2

    request = httpx2.Request("POST", "https://gateway.example.com/v1/messages")
    bad = anthropic.BadRequestError("unsupported", response=httpx2.Response(
        400, request=request), body=None)
    provider, calls = _anthropic(monkeypatch, [bad, _response("OK")],
                                 model="claude-sonnet-5",
                                 endpoint="https://gateway.example.com")
    ok, _ = provider.test_connection()
    assert ok
    assert [c[0] for c in calls] == ["messages", "messages"]
    assert "fallbacks" not in calls[0][1]  # only for supported models on api.anthropic.com
    assert "output_config" not in calls[1][1]
