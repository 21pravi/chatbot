"""
Gemini-powered multimodal chatbot — Flask backend (API + static host).

The frontend (static/index.html) is a self-contained page with no server-side
templating, so it renders correctly whether it's opened directly, previewed, or
served here. This backend does three things:

  * serves the frontend at  GET  /
  * returns chat history at  GET  /api/history
  * answers prompts at       POST /api/chat   (text, image, or PDF)

Chat turns persist to SQLite. The app degrades gracefully: with no API key it
still serves every page and returns a clear setup message instead of crashing.

Built on the unified Google Gen AI SDK (`google-genai`). The legacy
`google-generativeai` package and its `gemini-pro` / `gemini-pro-vision` model
names are both retired.
"""

import base64
import logging
import os
import re
import sqlite3
from contextlib import closing

from flask import Flask, g, jsonify, request, send_from_directory

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional at runtime
    pass

try:
    from google import genai
    from google.genai import types

    _GENAI_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - only hit when dep is absent
    genai = None
    types = None
    _GENAI_IMPORT_ERROR = exc

from pypdf import PdfReader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
DATABASE = os.environ.get("CHATBOT_DB", "chatbot_data.db")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def get_client():
    """Return a cached Gen AI client, or None if it cannot be created."""
    if genai is None or not API_KEY:
        return None
    if "genai_client" not in g:
        g.genai_client = genai.Client(api_key=API_KEY)
    return g.genai_client


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def create_database():
    with closing(sqlite3.connect(DATABASE)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt   TEXT,
                response TEXT,
                image    TEXT
            )
            """
        )
        conn.commit()


def add_chat_history(prompt, response, image_b64=None):
    with closing(sqlite3.connect(DATABASE)) as conn:
        conn.execute(
            "INSERT INTO chat_history (prompt, response, image) VALUES (?, ?, ?)",
            (prompt, response, image_b64),
        )
        conn.commit()


def get_chat_history():
    with closing(sqlite3.connect(DATABASE)) as conn:
        rows = conn.execute(
            "SELECT id, prompt, response, image FROM chat_history ORDER BY id"
        ).fetchall()
    return rows


# ---------------------------------------------------------------------------
# Text / PDF utilities
# ---------------------------------------------------------------------------
def get_pdf_text(pdf_file):
    reader = PdfReader(pdf_file)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def split_text(text, chunk_size=10000, overlap=1000):
    """Lightweight recursive-style splitter (drops the heavy langchain dep)."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks, start = [], 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            for sep in ("\n\n", "\n", ". ", " "):
                pivot = text.rfind(sep, start, end)
                if pivot > start:
                    end = pivot + len(sep)
                    break
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def format_response(prompt, text):
    if re.search(r"^\s*\d+\.", prompt, re.MULTILINE):
        return text
    if "```" in prompt and "```" not in text:
        return f"```\n{text}\n```"
    return text


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------
def generate_reply(prompt, image_bytes=None, image_mime=None, pdf_file=None):
    client = get_client()
    if client is None:
        raise RuntimeError(
            "Gemini is not configured. Set GEMINI_API_KEY in your environment "
            "(see .env.example) to enable live responses."
        )

    if pdf_file is not None:
        context = "\n".join(split_text(get_pdf_text(pdf_file)))
        contents = [f"{prompt}\n\nContext from the uploaded PDF:\n{context}"]
    elif image_bytes is not None:
        contents = [
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=image_mime or "image/png"),
        ]
    else:
        contents = [prompt]

    response = client.models.generate_content(model=MODEL_NAME, contents=contents)
    return (response.text or "").strip()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/history")
def api_history():
    history = [
        {"prompt": r[1], "response": r[2], "image": r[3]} for r in get_chat_history()
    ]
    return jsonify({"model": MODEL_NAME, "api_ready": bool(API_KEY), "history": history})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    prompt = (request.form.get("prompt") or "").strip()
    image = request.files.get("image")
    pdf_file = request.files.get("pdf_file")

    if not prompt and not image and not pdf_file:
        return jsonify({"error": "Please enter a message."}), 400

    # Read the image bytes ONCE so we can both send them to the model and store
    # them (the old code consumed the stream, saving an empty image).
    image_bytes = image_mime = image_b64 = None
    if image and image.filename:
        image_bytes = image.read()
        image_mime = image.mimetype or "image/png"
        image_b64 = base64.b64encode(image_bytes).decode("ascii")

    try:
        reply = generate_reply(
            prompt,
            image_bytes=image_bytes,
            image_mime=image_mime,
            pdf_file=pdf_file if (pdf_file and pdf_file.filename) else None,
        )
        reply = format_response(prompt, reply) or "Gemini returned an empty response."
        add_chat_history(prompt, reply, image_b64)
        return jsonify({"response": reply})
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the UI
        logger.exception("Generation failed")
        return jsonify({"error": str(exc)}), 500


@app.errorhandler(404)
def not_found(_e):
    return send_from_directory(STATIC_DIR, "index.html"), 200


# Initialise the DB at import time so `flask run`, gunicorn and tests all work.
create_database()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
