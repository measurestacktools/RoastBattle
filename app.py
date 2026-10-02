"""RoastBattle backend — FastAPI + Groq.

Serves the frontend from static/ and exposes a small JSON API for a
3-round friendly roast battle game. No database, no auth, no multiplayer.
"""

import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
VALID_STYLES = ("friendly", "savage", "absurd", "overload")

FALLBACK_TARGETS = [
    "Gary the Overconfident Houseplant",
    "Sir Wobbles the Left Sock",
    "Captain Crumb the Couch Cushion",
    "Brenda the Dramatic Houseplant",
]

# Compact server-side blocklist (substring match, case-insensitive).
# Covers: slurs, hate, sexual content, threats/violence, self-harm,
# and attacks on real private people (doxxing-ish phrases).
BLOCKLIST = [
    # slurs / hate
    "nigger", "nigga", "faggot", "fagot", "kike", "chink", "spic",
    "tranny", "retard", "retarded",
    # hate / extremist
    "white power", "kkk", "gas the",
    # sexual
    "porn", "hentai", "blowjob", "handjob", "orgasm", "masturbat",
    "incest", "molest", "rape", "rapist", "pedophil",
    # threats / violence
    "kill yourself", "kys", "i will kill", "i'll kill", "gonna kill you",
    "shoot you", "stab you", "bomb you", "i will hurt", "death threat",
    # self-harm
    "self-harm", "selfharm", "cut myself", "cutting myself", "suicide",
    "hang myself", "overdose on purpose",
    # real-private-person attacks / doxxing
    "my neighbor john", "my ex's address", "doxx", "dox ",
    "home address", "phone number is",
]

REFUSAL_PHRASES = [
    "i'm sorry", "i am sorry", "i can't", "i cannot", "i'm unable",
    "i am unable", "as an ai", "i refuse", "against my guidelines",
    "i won't generate", "i will not generate",
]

SAFETY_SYSTEM = (
    "You are the host of ROAST BATTLE, a playful party game. "
    "Roast ONLY harmless, silly targets (the given target, which is always "
    "a willing player persona or a goofy fictional character). "
    "Never punch down. BANNED and never output: slurs, hate toward any "
    "protected group, sexual/explicit content, threats or encouragement of "
    "violence, self-harm content, or attacks on real private individuals "
    "(no names, addresses, or personal data). Keep every roast silly, "
    "exaggerated, and kind-spirited — funny, never objective or cruel. "
    "Always reply with compact JSON only, no markdown, no extra text."
)

# ---------------------------------------------------------------------------
# In-memory state (process memory only — never written to disk)
# ---------------------------------------------------------------------------
_manual_key: Optional[str] = None
_game: Optional[Dict[str, Any]] = None


def get_model() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


def get_api_key() -> Tuple[Optional[str], Optional[str]]:
    """Return (key, source). Source is 'settings', 'env', or None."""
    if _manual_key:
        return _manual_key, "settings"
    env_key = os.environ.get("GROQ_API_KEY", "").strip()
    if env_key:
        return env_key, "env"
    return None, None


def get_openai_client(api_key: str) -> "openai.OpenAI":
    return openai.OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


def is_unsafe(text: str) -> bool:
    lowered = text.lower()
    return any(b in lowered for b in BLOCKLIST)


def contains_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(p in lowered for p in REFUSAL_PHRASES)


def clamp_score(value: Any) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, n))


def extract_json(text: str) -> Dict[str, Any]:
    """Parse compact JSON from model output (tolerates code fences)."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("model did not return a JSON object")
    return parsed


def groq_json(
    api_key: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 200,
) -> Dict[str, Any]:
    """One Groq chat call (+ at most ONE retry on malformed JSON).

    Returns the parsed JSON dict. Raises ValueError with a friendly
    message if the model output stays unusable.
    """
    client = get_openai_client(api_key)
    resp = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.9,
    )
    content = (resp.choices[0].message.content or "").strip()
    try:
        return extract_json(content)
    except (ValueError, json.JSONDecodeError, AttributeError, IndexError):
        correction = (
            "That was not valid compact JSON. Reply again with ONLY a "
            "compact JSON object, no markdown, no extra text."
        )
        retry_messages = messages + [
            {"role": "assistant", "content": content or "..."},
            {"role": "user", "content": correction},
        ]
        resp2 = client.chat.completions.create(
            model=get_model(),
            messages=retry_messages,
            max_tokens=max_tokens,
            temperature=0.9,
        )
        content2 = (resp2.choices[0].message.content or "").strip()
        try:
            return extract_json(content2)
        except (ValueError, json.JSONDecodeError, AttributeError, IndexError):
            raise ValueError(
                "The AI sent back gibberish. Try again — the roast machine "
                "hiccuped."
            )


def style_hint(style: str) -> str:
    return {
        "friendly": "warm, supportive, gently teasing like a kind friend",
        "savage": "spicy and bold but still clean and kind-spirited, never cruel",
        "absurd": "surreal and ridiculous, flying-taco levels of nonsense",
        "overload": "maximum chaos energy, rapid-fire silly metaphors",
    }[style]


def round1_messages(target: str, style: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SAFETY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Write a Round-1 roast of {target!r} in a {style} style "
                f"({style_hint(style)}). Keep it to 2-4 sentences, playful, "
                "silly, never mean. Also rate your own roast 1-10 for fun "
                "(ai_score). Reply with ONLY compact JSON like "
                '{"roast": "...", "ai_score": 7}.'
            ),
        },
    ]


def round2_messages(target: str, style: str, comeback: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SAFETY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"The player just fired this comeback at {target!r} "
                f"({style} style, {style_hint(style)}): {comeback!r}. "
                "Give a short fun verdict on their comeback (1-2 sentences, "
                "playful, scores are just for fun and never objective), "
                "a player_score 1-10 for fun, then write your Round-2 roast "
                "of the player (2-4 sentences, silly and kind-spirited) plus "
                "your own ai_score 1-10 for fun. Reply with ONLY compact "
                "JSON like "
                '{"verdict": "...", "player_score": 7, '
                '"roast": "...", "ai_score": 6}.'
            ),
        },
    ]


def final_messages(target: str, style: str, comeback: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SAFETY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Final round! The player fired this comeback at {target!r} "
                f"({style} style): {comeback!r}. Give a short fun verdict "
                "(1-2 sentences, playful, scores are just for fun), "
                "a player_score 1-10 for fun, then your FINAL roast of the "
                "player (2-4 sentences, epic but kind-spirited) plus your "
                "own ai_score 1-10 for fun and a funny_verdict one-liner "
                "crowning the battle. Reply with ONLY compact JSON like "
                '{"verdict": "...", "player_score": 8, "roast": "...", '
                '"ai_score": 7, "funny_verdict": "..."}.'
            ),
        },
    ]


def fallback_roast(api_key: str, style: str, fallback: str) -> str:
    data = groq_json(api_key, round1_messages(fallback, style), max_tokens=200)
    roast = str(data.get("roast", "")).strip()
    ai_score = clamp_score(data.get("ai_score", 5))
    if not roast or contains_refusal(roast):
        roast = (
            f"{fallback} walks into the battle with the confidence of a "
            "toaster in a thunderstorm — brave, buzzing, and slightly "
            "burnt around the edges."
        )
        ai_score = 5
    return roast, ai_score


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="RoastBattle")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail)},
        )
    return JSONResponse(
        status_code=500,
        content={"error": "Something went sideways. Please try again."},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the app icon so browsers never 404 on /favicon.ico."""
    return FileResponse(str(STATIC_DIR / "favicon.svg"), media_type="image/svg+xml")


@app.get("/")
def home():
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index), media_type="text/html")
    return HTMLResponse(
        "<!doctype html><html><body>"
        "<h1>RoastBattle</h1>"
        "<p>Backend is running. Frontend files are on their way.</p>"
        "</body></html>"
    )


@app.get("/api/status")
def api_status():
    key, source = get_api_key()
    model = get_model()
    if key:
        where = "your saved key" if source == "settings" else "the .env file"
        return {
            "ok": True,
            "configured": True,
            "source": source,
            "model": model,
            "message": f"Roast machine ready! Using the key from {where}.",
        }
    return {
        "ok": True,
        "configured": False,
        "source": None,
        "model": model,
        "message": "No Groq API key yet. Add one to start roasting!",
    }


class KeyBody(BaseModel):
    key: str = ""


@app.post("/api/key")
def save_key(body: KeyBody):
    global _manual_key
    key = (body.key or "").strip()
    if not key:
        return JSONResponse(
            status_code=400, content={"error": "That key looks empty. Paste it in and try again."}
        )
    try:
        client = get_openai_client(key)
        client.models.list()
    except Exception:
        return JSONResponse(
            status_code=401,
            content={"error": "Hmm, Groq didn't accept that key. Double-check it and try again."},
        )
    _manual_key = key
    return {"ok": True, "verified": True, "message": "Key saved! The roast machine is ready."}


@app.delete("/api/key")
def delete_key():
    global _manual_key
    _manual_key = None
    if os.environ.get("GROQ_API_KEY", "").strip():
        return {"ok": True, "message": "Cleared your saved key. Still using the one from the .env file."}
    return {"ok": True, "message": "Key cleared. Add a Groq key to keep roasting."}


class StartBody(BaseModel):
    target: str = ""
    style: str = ""


@app.post("/api/start")
def api_start(body: StartBody):
    global _game
    target = (body.target or "").strip()
    style = (body.style or "").strip()
    if style == "ai-overload":
        style = "overload"  # frontend data-style value for the AI Overload card
    if len(target) < 3 or len(target) > 120:
        return JSONResponse(
            status_code=400,
            content={"error": "Give your roast target a name between 3 and 120 characters."},
        )
    if style not in VALID_STYLES:
        return JSONResponse(
            status_code=400,
            content={"error": "Pick a battle style: friendly, savage, absurd, or overload."},
        )
    api_key, _source = get_api_key()
    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "Add your Groq API key first, then let's roast!"},
        )

    if is_unsafe(target):
        fallback = random.choice(FALLBACK_TARGETS)
        try:
            roast, ai_score = fallback_roast(api_key, style, fallback)
        except ValueError as e:
            return JSONResponse(status_code=502, content={"error": str(e)})
        except Exception:
            return JSONResponse(
                status_code=502,
                content={"error": "The AI fumbled the roast. Try again!"},
            )
        _game = {"target": fallback, "style": style, "round": 1, "a1": ai_score}
        return {
            "ok": True,
            "redirected": True,
            "notice": (
                "Whoa, that target crossed the line, so we swapped in a "
                "much safer (and sillier) opponent. Keep it playful!"
            ),
            "target": fallback,
            "style": style,
            "round": 1,
            "roast": roast,
        }

    try:
        data = groq_json(api_key, round1_messages(target, style), max_tokens=200)
    except ValueError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except Exception:
        return JSONResponse(
            status_code=502, content={"error": "The AI fumbled the roast. Try again!"}
        )
    roast = str(data.get("roast", "")).strip()
    ai_score = clamp_score(data.get("ai_score", 5))
    if not roast or contains_refusal(roast):
        fallback = random.choice(FALLBACK_TARGETS)
        try:
            roast, ai_score = fallback_roast(api_key, style, fallback)
        except ValueError as e:
            return JSONResponse(status_code=502, content={"error": str(e)})
        except Exception:
            return JSONResponse(
                status_code=502, content={"error": "The AI fumbled the roast. Try again!"}
            )
        _game = {"target": fallback, "style": style, "round": 1, "a1": ai_score}
        return {
            "ok": True,
            "redirected": True,
            "notice": (
                "The AI got shy about that one, so we swapped in a safer "
                "opponent. Rematch?"
            ),
            "target": fallback,
            "style": style,
            "round": 1,
            "roast": roast,
        }
    _game = {"target": target, "style": style, "round": 1, "a1": ai_score}
    return {"ok": True, "round": 1, "target": target, "style": style, "roast": roast}


class ComebackBody(BaseModel):
    text: str = ""


@app.post("/api/comeback")
def api_comeback(body: ComebackBody):
    global _game
    text = (body.text or "").strip()
    if len(text) < 1 or len(text) > 280:
        return JSONResponse(
            status_code=400,
            content={"error": "Your comeback should be 1 to 280 characters. Short and spicy!"},
        )
    if not _game:
        return JSONResponse(
            status_code=400,
            content={"error": "No battle running. Start a new roast first!"},
        )
    api_key, _source = get_api_key()
    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "Add your Groq API key first, then let's roast!"},
        )

    target = _game["target"]
    style = _game["style"]
    current_round = _game["round"]

    if current_round == 1:
        try:
            data = groq_json(api_key, round2_messages(target, style, text), max_tokens=250)
        except ValueError as e:
            return JSONResponse(status_code=502, content={"error": str(e)})
        except Exception:
            return JSONResponse(
                status_code=502, content={"error": "The AI fumbled the roast. Try again!"}
            )
        verdict = str(data.get("verdict", "Spicy! The crowd goes mild-to-wild!")).strip()
        roast = str(data.get("roast", "")).strip()
        if not roast or contains_refusal(roast + " " + verdict):
            return JSONResponse(
                status_code=502,
                content={"error": "The AI got stage fright. Toss another comeback!"},
            )
        s1 = clamp_score(data.get("player_score", 5))
        a2 = clamp_score(data.get("ai_score", 5))
        _game.update({"round": 2, "s1": s1, "a2": a2})
        return {
            "ok": True,
            "round": 2,
            "verdict": verdict,
            "player_score": s1,
            "ai_score": a2,
            "roast": roast,
        }

    if current_round == 2:
        try:
            data = groq_json(api_key, final_messages(target, style, text), max_tokens=250)
        except ValueError as e:
            return JSONResponse(status_code=502, content={"error": str(e)})
        except Exception:
            return JSONResponse(
                status_code=502, content={"error": "The AI fumbled the roast. Try again!"}
            )
        verdict = str(data.get("verdict", "What a finale! Confetti everywhere!")).strip()
        roast = str(data.get("roast", "")).strip()
        funny_verdict = str(
            data.get("funny_verdict", "The judges declare everyone delightfully roasted!")
        ).strip()
        if not roast or contains_refusal(roast + " " + verdict):
            return JSONResponse(
                status_code=502,
                content={"error": "The AI got stage fright. Toss another comeback!"},
            )
        s2 = clamp_score(data.get("player_score", 5))
        a3 = clamp_score(data.get("ai_score", 5))
        s1 = int(_game.get("s1", 5))
        a1 = int(_game.get("a1", 5))
        a2 = int(_game.get("a2", 5))
        player_total = (s1 + s2) * 5
        ai_total = round((a1 + a2 + a3) / 30 * 100)
        if player_total > ai_total:
            winner = "PLAYER"
        elif ai_total > player_total:
            winner = "AI"
        else:
            winner = "DRAW"
        _game.update({"round": 3, "s2": s2, "a3": a3, "done": True})
        return {
            "ok": True,
            "round": 3,
            "done": True,
            "verdict": verdict,
            "player_score": s2,
            "ai_score": a3,
            "roast": roast,
            "player_total": player_total,
            "ai_total": ai_total,
            "winner": winner,
            "funny_verdict": funny_verdict,
        }

    return JSONResponse(
        status_code=400,
        content={"error": "That battle is over. Hit restart for a rematch!"},
    )


@app.post("/api/restart")
def api_restart():
    global _game
    _game = None
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8005"))
    uvicorn.run(app, host="127.0.0.1", port=port)
