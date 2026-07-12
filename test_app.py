"""
Test suite for the Gemini chatbot.

The Gemini network call is mocked, so the whole suite runs offline with no
API key. Run with:  pytest -q
"""

import base64
import importlib
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    """Import app.py fresh with a temp DB and no API key."""
    monkeypatch.setenv("CHATBOT_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    import app as app_mod

    importlib.reload(app_mod)
    return app_mod


@pytest.fixture()
def client(app_module):
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


# --------------------------------------------------------------------------
# Pure utility functions
# --------------------------------------------------------------------------
def test_split_text_short_returns_single_chunk(app_module):
    assert app_module.split_text("hello world") == ["hello world"]


def test_split_text_empty_returns_nothing(app_module):
    assert app_module.split_text("   ") == []


def test_split_text_long_chunks_with_overlap(app_module):
    text = ("word " * 6000).strip()  # ~30k chars
    chunks = app_module.split_text(text, chunk_size=10000, overlap=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 10000 for c in chunks)


def test_format_response_wraps_code(app_module):
    out = app_module.format_response("show ```python", "print(1)")
    assert out.startswith("```") and out.endswith("```")


def test_format_response_plain_passthrough(app_module):
    assert app_module.format_response("hi", "hello") == "hello"


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def test_db_roundtrip(app_module):
    app_module.add_chat_history("q", "a", None)
    rows = app_module.get_chat_history()
    assert rows[-1][1] == "q" and rows[-1][2] == "a"


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
def test_home_serves_static_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Gemini" in r.data
    # No unrendered Jinja tags should ever reach the browser.
    assert b"{{" not in r.data and b"{%" not in r.data


def test_history_endpoint_shape(client):
    r = client.get("/api/history")
    assert r.status_code == 200
    body = r.get_json()
    assert body["model"] == "gemini-3.5-flash"
    assert body["api_ready"] is False
    assert body["history"] == []


def test_unknown_path_falls_back_to_app(client):
    r = client.get("/whatever")
    assert r.status_code == 200
    assert b"Gemini" in r.data


def test_api_empty_prompt_rejected(client):
    r = client.post("/api/chat", data={"prompt": "   "})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_api_without_key_returns_setup_message(client):
    r = client.post("/api/chat", data={"prompt": "hello"})
    assert r.status_code == 500
    assert "GEMINI_API_KEY" in r.get_json()["error"]


# --------------------------------------------------------------------------
# End-to-end request flow with a mocked model
# --------------------------------------------------------------------------
def test_api_text_prompt_mocked(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "generate_reply", lambda *a, **k: "mocked reply")
    r = client.post("/api/chat", data={"prompt": "hello"})
    assert r.status_code == 200
    assert r.get_json()["response"] == "mocked reply"
    assert app_module.get_chat_history()[-1][2] == "mocked reply"
    # and it shows up in history endpoint
    hist = client.get("/api/history").get_json()["history"]
    assert hist[-1]["prompt"] == "hello"


def test_api_image_prompt_persists_base64(client, app_module, monkeypatch):
    captured = {}

    def fake_generate(prompt, image_bytes=None, image_mime=None, pdf_file=None):
        captured["image_bytes"] = image_bytes
        captured["mime"] = image_mime
        return "saw the image"

    monkeypatch.setattr(app_module, "generate_reply", fake_generate)

    fake_png = b"\x89PNG\r\n\x1a\nfakeimagedata"
    data = {"prompt": "describe this", "image": (io.BytesIO(fake_png), "pic.png")}
    r = client.post("/api/chat", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert captured["image_bytes"] == fake_png
    stored_b64 = app_module.get_chat_history()[-1][3]
    assert base64.b64decode(stored_b64) == fake_png


def test_api_reports_model_error_cleanly(client, app_module, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(app_module, "generate_reply", boom)
    r = client.post("/api/chat", data={"prompt": "hi"})
    assert r.status_code == 500
    assert r.get_json()["error"] == "quota exceeded"
