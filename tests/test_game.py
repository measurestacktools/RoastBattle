"""Backend contract tests — Groq is mocked via monkeypatching openai.OpenAI."""

import json

import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    app_module._manual_key = None
    app_module._game = None
    yield
    app_module._manual_key = None
    app_module._game = None


# ---------------------------------------------------------------------------
# Fake Groq client
# ---------------------------------------------------------------------------
class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeModels:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    def list(self):
        if self.should_fail:
            raise Exception("401 Authentication failed: bad key")
        return []


class _FakeCompletions:
    def __init__(self, script, record):
        self.script = list(script)
        self.record = record

    def create(self, **kwargs):
        self.record.append(kwargs)
        if self.script:
            content = self.script.pop(0)
        else:
            content = json.dumps({"roast": "Default mock roast.", "ai_score": 5})
        return _FakeResp(content)


class _FakeChat:
    def __init__(self, script, record):
        self.completions = _FakeCompletions(script, record)


class _FakeClient:
    def __init__(self, script=None, fail_models=False, record=None):
        if record is None:
            record = []
        self.record = record
        self.chat = _FakeChat(script or [], record)
        self.models = _FakeModels(fail_models)


def patch_groq(monkeypatch, script, fail_models=False, record=None):
    """Monkeypatch openai.OpenAI so every construction returns our fake.

    script: list of raw model-output strings served in order (one per call).
    record: list that collects each completions.create kwargs (call count).
    """
    if record is None:
        record = []
    holder = {}

    def factory(*args, **kwargs):
        fake = holder.get("fake")
        if fake is None:
            fake = _FakeClient(
                script=list(script), fail_models=fail_models, record=record
            )
            holder["fake"] = fake
        return fake

    monkeypatch.setattr(app_module.openai, "OpenAI", factory)
    return record


def set_key_direct(value="gsk_testkey123"):
    app_module._manual_key = value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_home_200():
    r = client.get("/")
    assert r.status_code == 200


def test_status_unconfigured_shape():
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["configured"] is False
    assert body["source"] is None
    assert isinstance(body["model"], str)
    assert isinstance(body["message"], str)


def test_status_env_source(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_envkey")
    r = client.get("/api/status")
    body = r.json()
    assert body["configured"] is True
    assert body["source"] == "env"
    assert "gsk_envkey" not in r.text


def test_key_save_success_shape(monkeypatch):
    patch_groq(monkeypatch, script=[])
    r = client.post("/api/key", json={"key": "gsk_validkey"})
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "ok": True,
        "verified": True,
        "message": body["message"],
    }
    assert isinstance(body["message"], str)
    assert "gsk_validkey" not in r.text


def test_key_empty_400(monkeypatch):
    patch_groq(monkeypatch, script=[])
    r = client.post("/api/key", json={"key": "   "})
    assert r.status_code == 400
    assert "error" in r.json()


def test_key_invalid_401(monkeypatch):
    patch_groq(monkeypatch, script=[], fail_models=True)
    r = client.post("/api/key", json={"key": "gsk_badkey"})
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    assert "gsk_badkey" not in r.text  # no raw echo
    assert "traceback" not in r.text.lower()


def test_key_delete_shape(monkeypatch):
    patch_groq(monkeypatch, script=[])
    client.post("/api/key", json={"key": "gsk_validkey"})
    r = client.delete("/api/key")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["message"], str)


def test_start_needs_key():
    r = client.post("/api/start", json={"target": "My Alarm Clock", "style": "savage"})
    assert r.status_code == 401
    assert "error" in r.json()


def test_start_success(monkeypatch):
    calls = patch_groq(
        monkeypatch,
        script=[json.dumps({"roast": "Your alarm clock needs therapy.", "ai_score": 8})],
    )
    set_key_direct()
    r = client.post("/api/start", json={"target": "My Alarm Clock", "style": "savage"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["round"] == 1
    assert body["target"] == "My Alarm Clock"
    assert body["style"] == "savage"
    assert body["roast"] == "Your alarm clock needs therapy."
    assert len(calls) == 1  # one Groq call per action
    assert calls[0]["temperature"] == 0.9
    assert 150 <= calls[0]["max_tokens"] <= 250


def test_start_empty_target_rejected(monkeypatch):
    set_key_direct()
    patch_groq(monkeypatch, script=[])
    r = client.post("/api/start", json={"target": "  ", "style": "friendly"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_start_long_target_rejected(monkeypatch):
    set_key_direct()
    patch_groq(monkeypatch, script=[])
    r = client.post("/api/start", json={"target": "x" * 121, "style": "friendly"})
    assert r.status_code == 400


def test_start_bad_style_rejected(monkeypatch):
    set_key_direct()
    patch_groq(monkeypatch, script=[])
    r = client.post("/api/start", json={"target": "My Alarm Clock", "style": "brutal"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_start_unsafe_redirected(monkeypatch):
    calls = patch_groq(
        monkeypatch,
        script=[json.dumps({"roast": "Fallback roast fires!", "ai_score": 6})],
    )
    set_key_direct()
    r = client.post(
        "/api/start", json={"target": "kill yourself you loser", "style": "absurd"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["redirected"] is True
    assert isinstance(body["notice"], str) and body["notice"]
    assert body["target"] != "kill yourself you loser"
    assert body["style"] == "absurd"
    assert body["round"] == 1
    assert isinstance(body["roast"], str) and body["roast"]
    assert len(calls) == 1


def test_comeback_requires_game(monkeypatch):
    set_key_direct()
    patch_groq(monkeypatch, script=[])
    r = client.post("/api/comeback", json={"text": "Oh yeah?"})
    assert r.status_code == 400


def test_comeback_text_validation(monkeypatch):
    set_key_direct()
    patch_groq(
        monkeypatch,
        script=[json.dumps({"roast": "R1 roast", "ai_score": 8})],
    )
    client.post("/api/start", json={"target": "My Alarm Clock", "style": "friendly"})
    r = client.post("/api/comeback", json={"text": "   "})
    assert r.status_code == 400
    r2 = client.post("/api/comeback", json={"text": "y" * 281})
    assert r2.status_code == 400


def test_comeback_flow_round1_to_final_with_math(monkeypatch):
    script = [
        json.dumps({"roast": "Round one roast!", "ai_score": 8}),  # a1 = 8
        json.dumps(
            {
                "verdict": "Spicy comeback!",
                "player_score": 7,  # s1 = 7
                "roast": "Round two roast!",
                "ai_score": 6,  # a2 = 6
            }
        ),
        json.dumps(
            {
                "verdict": "What a finale!",
                "player_score": 9,  # s2 = 9
                "roast": "Final roast!",
                "ai_score": 5,  # a3 = 5
                "funny_verdict": "The toaster wins on points!",
            }
        ),
    ]
    calls = patch_groq(monkeypatch, script=script)
    set_key_direct()

    r1 = client.post("/api/start", json={"target": "My Alarm Clock", "style": "friendly"})
    assert r1.status_code == 200 and r1.json()["round"] == 1

    r2 = client.post("/api/comeback", json={"text": "Well your snooze button is lazy!"})
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["ok"] is True
    assert b2["round"] == 2
    assert "done" not in b2
    assert b2["verdict"] == "Spicy comeback!"
    assert b2["player_score"] == 7
    assert b2["ai_score"] == 6
    assert b2["roast"] == "Round two roast!"

    r3 = client.post("/api/comeback", json={"text": "Take that, clock!"})
    assert r3.status_code == 200
    b3 = r3.json()
    assert b3["ok"] is True
    assert b3["round"] == 3
    assert b3["done"] is True
    assert b3["verdict"] == "What a finale!"
    assert b3["player_score"] == 9
    assert b3["ai_score"] == 5
    assert b3["roast"] == "Final roast!"
    # player_total = (7 + 9) * 5 = 80 ; ai_total = round(19/30*100) = 63
    assert b3["player_total"] == 80
    assert b3["ai_total"] == 63
    assert b3["winner"] == "PLAYER"
    assert b3["funny_verdict"] == "The toaster wins on points!"

    assert len(calls) == 3  # exactly one Groq call per action


def test_restart_clears_game_keeps_key(monkeypatch):
    patch_groq(
        monkeypatch,
        script=[json.dumps({"roast": "R1 roast", "ai_score": 7})],
    )
    client.post("/api/key", json={"key": "gsk_keepme"})
    client.post("/api/start", json={"target": "My Alarm Clock", "style": "friendly"})
    r = client.post("/api/restart")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # key kept
    status = client.get("/api/status").json()
    assert status["configured"] is True
    assert status["source"] == "settings"
    # game cleared
    r2 = client.post("/api/comeback", json={"text": "hello?"})
    assert r2.status_code == 400


def test_malformed_ai_retry_path(monkeypatch):
    calls = patch_groq(
        monkeypatch,
        script=[
            "this is definitely not json {{{",
            json.dumps({"roast": "Recovered roast!", "ai_score": 7}),
        ],
    )
    set_key_direct()
    r = client.post("/api/start", json={"target": "My Alarm Clock", "style": "overload"})
    assert r.status_code == 200
    assert r.json()["roast"] == "Recovered roast!"
    assert len(calls) == 2  # initial + ONE retry


def test_malformed_ai_twice_gives_friendly_error(monkeypatch):
    patch_groq(monkeypatch, script=["garbage one", "garbage two"])
    set_key_direct()
    r = client.post("/api/start", json={"target": "My Alarm Clock", "style": "friendly"})
    assert r.status_code == 502
    assert "error" in r.json()


def test_secret_never_in_responses(monkeypatch):
    secret = "gsk_SUPERSECRET999"
    script = [
        json.dumps({"roast": "R1 roast", "ai_score": 8}),
        json.dumps(
            {
                "verdict": "Nice!",
                "player_score": 6,
                "roast": "R2 roast",
                "ai_score": 6,
            }
        ),
        json.dumps(
            {
                "verdict": "Grand!",
                "player_score": 6,
                "roast": "Final roast",
                "ai_score": 6,
                "funny_verdict": "Everyone wins!",
            }
        ),
    ]
    patch_groq(monkeypatch, script=script, fail_models=False)
    r0 = client.post("/api/key", json={"key": secret})
    assert secret not in r0.text
    for resp in (
        client.get("/api/status"),
        client.post("/api/start", json={"target": "My Alarm Clock", "style": "friendly"}),
        client.post("/api/comeback", json={"text": "take that!"}),
        client.post("/api/comeback", json={"text": "and that!"}),
        client.delete("/api/key"),
    ):
        assert secret not in resp.text


def test_frontend_style_alias_accepted(monkeypatch):
    """The UI sends style=ai-overload; it must map to overload, not 400."""
    patch_groq(monkeypatch, script=[json.dumps({"roast": "R1", "ai_score": 7})])
    client.post("/api/key", json={"key": "gsk_test_integration"})
    r = client.post(
        "/api/start", json={"target": "My Alarm Clock", "style": "ai-overload"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["style"] == "overload"


def test_static_assets_served():
    """CSS/JS/favicon must load or the game renders dead (no console 404s)."""
    for path in ("/static/styles.css", "/static/app.js", "/favicon.ico"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert len(r.content) > 100, path
