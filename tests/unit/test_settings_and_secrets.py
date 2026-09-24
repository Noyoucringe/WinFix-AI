"""User settings, API key storage, log redaction, elevation helper guards."""

import json
import logging

import pytest

from app.core import credentials, elevation, logging_setup, user_settings


def test_settings_roundtrip_and_defaults(tmp_path):
    store = user_settings.SettingsStore(tmp_path / "s.json")
    assert store.load().theme == "system"
    store.update(theme="dark", diagnostic_depth="thorough")
    reloaded = user_settings.SettingsStore(tmp_path / "s.json").load()
    assert reloaded.theme == "dark" and reloaded.diagnostic_depth == "thorough"


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert user_settings.SettingsStore(path).load().analysis == "local"
    assert (tmp_path / "s.corrupt.json").exists()


def test_settings_file_never_contains_api_key(tmp_path):
    store = user_settings.SettingsStore(tmp_path / "s.json")
    store.update(analysis="cloud", endpoint="https://api.example.com/v1")
    credentials.set_api_key("openai", "sk-live-SECRETSECRETSECRET1234")
    assert "sk-live" not in (tmp_path / "s.json").read_text()


@pytest.mark.parametrize("url,ok", [
    ("https://api.example.com/v1", True),
    ("http://localhost:11434/v1", True),
    ("http://api.example.com/v1", False),
    ("https://user:pass@api.example.com", False),
    ("ftp://example.com", False),
    ("not a url", False),
])
def test_endpoint_validation(url, ok):
    if ok:
        assert user_settings.validate_endpoint(url)
    else:
        with pytest.raises(user_settings.EndpointError):
            user_settings.validate_endpoint(url)


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, value):
        self.store[(service, user)] = value

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


def test_api_key_goes_to_credential_store_and_is_masked(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(credentials, "_keyring", lambda: fake)
    persisted, _ = credentials.set_api_key("openai", "sk-test-abcdef1234567F2A")
    assert persisted is True
    assert fake.store[("WinFix AI", "openai-api-key")].endswith("7F2A")
    assert credentials.describe("openai").startswith("Saved key ending in 7F2A.")
    assert credentials.masked("openai") == "•" * 24
    credentials.delete_api_key("openai")
    assert credentials.get_api_key("openai") is None


def test_api_key_without_credential_store_is_session_only():
    persisted, message = credentials.set_api_key("anthropic", "sk-ant-xyz1234567890")
    assert persisted is False and "until you close" in message
    assert "session only" in credentials.describe("anthropic")


def test_logs_never_contain_secrets(capsys):
    formatter = logging_setup.JsonFormatter()
    record = logging.LogRecord("t", logging.INFO, __file__, 1,
                               "calling with api_key=sk-live-SUPERSECRET123456 and "
                               "Authorization: Bearer abcdefghijklmnopqrstu", None, None)
    record.status = "token=hunter2hunter2"
    line = formatter.format(record)
    assert "SUPERSECRET" not in line and "abcdefghijklmnop" not in line
    assert "hunter2" not in line
    json.loads(line)


def test_elevation_helper_refuses_foreign_result_paths(tmp_path):
    assert elevation.helper_main("flush_dns", "{}", str(tmp_path / "x.json")) == 2


def test_elevation_helper_refuses_non_remediation(tmp_path):
    path = elevation.request_dir() / "t.json"
    elevation.helper_main("get_cpu_usage", "{}", str(path))
    result = json.loads(path.read_text())
    path.unlink()
    assert result["success"] is False and result["error"]["type"] == "SafetyError"


def test_elevation_helper_rejects_shell_strings():
    path = elevation.request_dir() / "u.json"
    elevation.helper_main("powershell -c evil", "{}", str(path))
    result = json.loads(path.read_text())
    path.unlink()
    assert result["success"] is False


def test_elevation_result_must_match_requested_tool():
    path = elevation.request_dir() / "v.json"
    path.write_text(json.dumps({"tool": "other", "success": True}))
    assert elevation.read_result("flush_dns", path)["success"] is False


def test_crashing_credential_backend_falls_back_to_session_only(monkeypatch):
    """Native keyring backends can raise BaseException subclasses (e.g. a Rust
    panic); WinFix must keep working and keep the key in memory only."""
    from app.core import credentials

    class Panic(BaseException):
        pass

    class Broken:
        def get_password(self, *a):
            raise Panic("backend crashed")

        set_password = delete_password = get_password

    monkeypatch.setattr(credentials, "_keyring", lambda: Broken())
    persisted, message = credentials.set_api_key("openai", "sk-test-abcdefghijklmnop1234")
    assert not persisted and "until you close" in message
    assert credentials.get_api_key("openai") == "sk-test-abcdefghijklmnop1234"
    credentials.delete_api_key("openai")
    assert credentials.get_api_key("openai") is None
