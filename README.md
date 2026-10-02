# RoastBattle

A playful 3-round roast battle game: you pick a target, the AI roasts it, you fire comebacks, and the crowd (a very unserious scoring system) crowns a winner.

## What is this?

RoastBattle is a tiny web game. The backend (this repo's Python part) talks to Groq's AI to generate silly, kind-spirited roasts and score your comebacks just for fun. A static frontend (`static/index.html` + `styles.css` + `app.js`) plays against the API below.

## Features

- Start a battle: pick a target (3–120 chars) and a style (`friendly`, `savage`, `absurd`, `overload`)
- 3 rounds: Round-1 AI roast → your comeback → Round-2 roast → your comeback → final roast + winner
- Fun-only scoring: every score is presented as silly entertainment, never objective
- Bring-your-own Groq key: paste it in the UI (verified, kept in server memory only) or use a `.env` file
- Safety: server blocklist + clean-only model instructions + refusal detection with auto-redirect to a goofy fallback opponent
- Restart anytime (keeps your key)

## Tech

- [FastAPI](https://fastapi.tiangolo.com/) — web API, serves `static/` on port 8005
- [Groq](https://groq.com/) via the OpenAI-compatible client (`https://api.groq.com/openai/v1`), model `openai/gpt-oss-120b` (override with `GROQ_MODEL`)
- `python-dotenv` loads `.env`; game state + key live in process memory only (no database)

## Requirements

- Python 3.10+
- A Groq API key (free at groq.com — key looks like `gsk_...`)
- pip packages: `pip install -r requirements.txt`

## Setup

```powershell
cd "C:\Users\rayan\Downloads\ai projects\RoastBattle"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env and paste your GROQ_API_KEY
```

Or without a virtualenv:

```powershell
pip install -r requirements.txt
```

## Groq key

Two ways (in-memory key wins if both exist):

1. **UI (recommended for sharing):** open the app, paste your key where asked. The backend verifies it with Groq (`models.list`) and holds it in process memory only — never written to disk.
2. **`.env` file:** set `GROQ_API_KEY=gsk_...` in `.env`.

Check status anytime: `GET /api/status` → `{"ok":true,"configured":...,"source":"settings"|"env"|null,...}`.

## Run

```powershell
python app.py
# or: uvicorn app:app --port 8005
```

Then open http://127.0.0.1:8005 in your browser. The backend serves `static/index.html` at `/`.

Run tests:

```powershell
python -m pytest tests/ -q
```

## How to play

1. Add your Groq key (UI or `.env`).
2. Enter a roast target (e.g. "my Monday-morning alarm clock") and pick a style.
3. Read the Round-1 roast, then type a comeback (1–280 chars).
4. Repeat for Round 2 — after your second comeback you get the final roast, both totals, and a winner (`PLAYER`, `AI`, or `DRAW`) plus a funny verdict.
5. Hit restart for a rematch (your key is kept).

Scoring (purely for laughs): `player_total = (s1 + s2) * 5`, `ai_total = round((a1 + a2 + a3) / 30 * 100)`, where each `s`/`a` score is 1–10 handed out by the AI for fun.

## Safety

- Targets are checked against a compact server-side blocklist (slurs, hate, sexual content, threats, self-harm, real-private-person attacks). Matches get auto-redirected to a goofy safe fallback like "Gary the Overconfident Houseplant".
- The model is instructed to roast harmless targets only and stay clean; if it refuses instead of roasting, the server redirects to the fallback too.
- Scores and verdicts are worded as fun, never objective. The server never returns your key or tracebacks.

## Limitations

- Single-player vs AI only — no multiplayer, accounts, or saved history.
- Game state lives in server memory: restarting the server ends the battle (key from `.env` survives, UI key does not).
- Needs internet + a valid Groq key; if the AI returns gibberish twice in a row you'll get a friendly "try again" error.
- One short Groq call per action (a second only if the first reply wasn't valid JSON).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Add your Groq API key first` (401) | Paste a key in the UI or set `GROQ_API_KEY` in `.env`, then restart |
| `Groq didn't accept that key` (401 on save) | Key is wrong/revoked — grab a fresh one from Groq console |
| `The AI fumbled the roast. Try again!` (502) | Temporary AI hiccup — retry the same action |
| Home page says "Frontend files are on their way" | The frontend agent hasn't dropped `static/index.html` in yet — backend is fine |
| Port already in use | Change `PORT` in `.env` or stop the other server on 8005 |
| Tests fail with import errors | Run from repo root with deps installed: `pip install -r requirements.txt` then `python -m pytest tests/ -q` |
