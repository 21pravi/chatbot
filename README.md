# Gemini Multimodal Chatbot

A Flask + vanilla-JS web app that wraps Google's **Gemini** models in a clean,
modern chat interface. It handles **text, images, and PDFs** in a single
conversation, persists history to SQLite, and supports browser voice input.

The frontend is a single self-contained page with **no server-side template
tags**, so it renders correctly whether you open the file directly, preview it,
or serve it through the backend. Open it with no backend running and it shows a
styled preview with example prompts; run the backend and it goes live.

Built on the current unified **`google-genai`** SDK. The legacy
`google-generativeai` package and the `gemini-pro` / `gemini-pro-vision` model
names it used are both retired.

---

## Features

- **Multimodal** — plain text, text + image (vision), or text + PDF in one chat.
- **PDF Q&A** — uploaded PDFs are parsed and chunked into context automatically.
- **Persistent history** — every turn (images included) is stored in SQLite and reloaded on refresh.
- **Voice input** — dictate messages via the Web Speech API where supported.
- **Preview mode** — with no backend, the UI still renders fully and explains how to go live.
- **One-command deploy** — ships with `Procfile` and `render.yaml` for Render.

---

## Tech stack

| Layer     | Choice                                               |
| --------- | ---------------------------------------------------- |
| Backend   | Python 3.9+, Flask, Gunicorn                         |
| AI        | Google Gen AI SDK (`google-genai`), Gemini 3.5 Flash |
| PDF       | `pypdf`                                              |
| Storage   | SQLite (standard library)                            |
| Frontend  | Self-contained HTML + CSS + vanilla JS               |
| Config    | `python-dotenv`                                      |
| Tests     | `pytest`                                             |

---

## Project structure

```
chatbot/
├── app.py                 # Flask API + static host + Gemini integration
├── requirements.txt
├── Procfile               # gunicorn entry point (Render / Heroku)
├── render.yaml            # one-click Render deploy config
├── .env.example           # copy to .env and add your key
├── .gitignore
├── LICENSE
├── README.md
├── static/
│   └── index.html         # the entire frontend (no templating)
└── tests/
    └── test_app.py        # offline test suite (Gemini call mocked)
```

---

## Quick start

```bash
git clone https://github.com/21pravi/chatbot.git
cd chatbot

python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # then paste your key into .env
python app.py                        # open http://localhost:5000
```

Get a free API key from **[Google AI Studio](https://aistudio.google.com/apikey)**
and put it in `.env` as `GEMINI_API_KEY=...`.

> Just want to see the interface? Open `static/index.html` directly in a browser.
> It renders in preview mode (no live answers until the backend is running).

---

## Usage

- **Text** — type and press Enter (Shift+Enter for a new line).
- **Image** — click the image icon, pick a file, ask *"what's in this picture?"*
- **PDF** — click the PDF icon, pick a file, ask a question about its contents.
- **Voice** — click the mic and speak (Chrome/Edge).
- **New chat** clears the current view; history persists in the sidebar.

---

## Configuration

All optional, via environment variables (see `.env.example`):

| Variable         | Default            | Purpose                                     |
| ---------------- | ------------------ | ------------------------------------------- |
| `GEMINI_API_KEY` | —                  | Your Gemini key (required for live replies) |
| `GEMINI_MODEL`   | `gemini-3.5-flash` | Which Gemini model to call                  |
| `CHATBOT_DB`     | `chatbot_data.db`  | SQLite database file                        |
| `PORT`           | `5000`             | Port for `python app.py`                    |

`GOOGLE_API_KEY` works as an alias for `GEMINI_API_KEY`.

---

## API

| Method | Route          | Purpose                                            |
| ------ | -------------- | -------------------------------------------------- |
| GET    | `/`            | Serves the chat interface                          |
| GET    | `/api/history` | `{ model, api_ready, history[] }`                  |
| POST   | `/api/chat`    | `multipart/form-data`: `prompt`, `image?`, `pdf_file?` → `{ response }` or `{ error }` |

---

## Testing

The suite mocks the Gemini network call, so it runs fully offline with no key:

```bash
pip install pytest
pytest -q
```

Covers the text/image/PDF flow, utility functions, the SQLite round-trip, all
routes, the history endpoint, and error handling.

---

## Deploy to Render

1. Push this repo to GitHub.
2. On [Render](https://render.com), create a **New Web Service** from the repo
   (it auto-detects `render.yaml`).
3. Add `GEMINI_API_KEY` in the service's **Environment** settings.
4. Deploy. Render runs `gunicorn app:app`.

For any other host, the entry point is `gunicorn app:app`.

---

## License

[MIT](LICENSE)
