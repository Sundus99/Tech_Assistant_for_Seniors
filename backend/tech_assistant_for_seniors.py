"""
GrandAssist backend.

FastAPI app that:
  1. Routes voice commands through a local intent classifier first
     (cheap, deterministic, sub-millisecond).
  2. Falls back to a configurable LLM provider only when the local router
     can't handle it.
  3. Optionally proxies Pinterest pin search for users who have linked their
     account.
  4. Records every request to a local SQLite metrics DB so we can prove out
     the "% routed locally" claim with real numbers.

Run locally:
    uvicorn backend.tech_assistant_for_seniors:app --reload
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

import markdown
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from backend.intent_router import IntentType, classify
from backend.metrics import (
    MetricsStore,
    RequestRecord,
    estimate_cost_usd,
    timer_ms,
)
from backend.pinterest_client import PinterestClient

load_dotenv()

# ---- Config ----
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
METRICS_DB = os.getenv("METRICS_DB", "grandassist_metrics.db")

# ---- Globals ----
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
ollama_client = OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)
metrics = MetricsStore(METRICS_DB)
pinterest = PinterestClient()

# Extremely simple in-memory OAuth state + token map. For production you'd
# use Redis or a signed cookie; for the demo, this is fine.
_oauth_states: dict[str, float] = {}
_pinterest_tokens: dict[str, str] = {}  # session_id -> access_token

app = FastAPI(
    title="GrandAssist",
    description="Voice-controlled browser assistant for seniors.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Schemas ----
class UserRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    AI: str
    type: str
    url: str | None = None
    pins: list[dict[str, Any]] | None = None
    pinterest_auth_url: str | None = None


# ---- Helpers ----
def _llm_reply(user_input: str) -> tuple[str, int, int]:
    """Call the configured LLM provider. Returns text and token counts."""
    if LLM_PROVIDER == "mock":
        return _mock_reply(user_input), 0, 0
    if LLM_PROVIDER == "ollama":
        return _chat_completion_reply(ollama_client, OLLAMA_MODEL, user_input)
    if LLM_PROVIDER == "openai":
        return _chat_completion_reply(openai_client, OPENAI_MODEL, user_input)
    if LLM_PROVIDER == "gemini":
        return _gemini_reply(user_input)
    raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


def _mock_reply(user_input: str) -> str:
    """Free deterministic fallback for demos, tests, and fresh clones."""
    topic = user_input.strip().lower().rstrip(".?!")
    if "print" in topic:
        return (
            "To print this page, press Command and P on a Mac, or Control and P "
            "on Windows. A print window will open. Choose your printer, then "
            "click Print."
        )
    if "email" in topic or "gmail" in topic:
        return (
            "To send an email in Gmail, open Gmail and click Compose. Type the "
            "person's email address in the To box, add a short subject, then "
            "write your message in the large blank area. When you are ready, "
            "click Send."
        )
    if "inflation" in topic:
        return (
            "Inflation means prices are going up over time. For example, if "
            "groceries cost more this year than last year, that is inflation."
        )
    if "password" in topic:
        return (
            "To change a password, open the website or app, go to Account or "
            "Settings, then look for Password or Security. Choose a strong new "
            "password and save it somewhere safe."
        )
    if topic.startswith("how do i ") or topic.startswith("how to "):
        task = (
            topic.removeprefix("how do i ")
            .removeprefix("how to ")
            .strip()
        )
        return (
            f"To {task}, start by opening the website or app where you want to "
            "do it. Look for a clearly labeled button or menu, follow the "
            "prompts one step at a time, and review everything before you "
            "confirm or submit."
        )
    topic = user_input.strip().rstrip(".?!") or "that"
    return (
        f"Here is a simple way to think about {topic}: start with the main "
        "website or app, look for the relevant button or menu, and take it one "
        "step at a time. If something asks for money, a password, or personal "
        "information, pause and double-check before continuing."
    )


def _chat_completion_reply(client: OpenAI, model: str,
                           user_input: str) -> tuple[str, int, int]:
    """Call an OpenAI-compatible chat completions endpoint."""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": user_input}],
    )
    raw = response.choices[0].message.content or ""
    # Strip markdown so the sidebar can render plain text.
    reply = BeautifulSoup(markdown.markdown(raw), "html.parser").get_text()
    usage = response.usage
    return reply, usage.prompt_tokens or 0, usage.completion_tokens or 0


def _gemini_reply(user_input: str) -> tuple[str, int, int]:
    """Call Gemini Developer API via REST. Returns text and token counts."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "You are GrandAssist, a patient tech helper for seniors. "
                    "Answer in plain language with short, step-by-step guidance. "
                    "Avoid jargon. Mention safety checks for passwords, money, "
                    "or personal information."
                )
            }]
        },
        "contents": [{
            "parts": [{"text": user_input}]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 350,
        },
    }

    with httpx.Client(timeout=20) as client:
        response = client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    raw = "\n".join(part.get("text", "") for part in parts).strip()
    if not raw:
        raise ValueError("Gemini returned an empty response")

    reply = BeautifulSoup(markdown.markdown(raw), "html.parser").get_text()
    usage = data.get("usageMetadata", {})
    return (
        reply,
        usage.get("promptTokenCount", 0),
        usage.get("candidatesTokenCount", 0),
    )


# ---- Routes ----
@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "GrandAssist", "version": app.version, "status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(user_request: UserRequest) -> ChatResponse:
    """Main entry point — classify, route, respond, and log."""
    with timer_ms() as elapsed:
        routed = classify(user_request.user_input)

        prompt_tok = completion_tok = 0
        error: str | None = None
        pins_payload: list[dict[str, Any]] | None = None
        pinterest_auth: str | None = None

        try:
            if routed.intent == IntentType.OPEN_WEBSITE:
                resp = ChatResponse(
                    AI=routed.reply, type="open web page", url=routed.url
                )
            elif routed.intent == IntentType.SEARCH_REFUSAL:
                resp = ChatResponse(AI=routed.reply, type="chat")
            elif routed.intent == IntentType.SEARCH_MY_PINS:
                sid = user_request.session_id or ""
                token = _pinterest_tokens.get(sid)
                if not token:
                    state = secrets.token_urlsafe(16)
                    _oauth_states[state] = time.time()
                    pinterest_auth = pinterest.authorization_url(state)
                    resp = ChatResponse(
                        AI="To search your pins, please connect your "
                           "Pinterest account first.",
                        type="pinterest_auth_required",
                        pinterest_auth_url=pinterest_auth,
                    )
                else:
                    pins = await pinterest.search_my_pins(
                        token, routed.query or "", page_size=8
                    )
                    pins_payload = [p.__dict__ for p in pins]
                    resp = ChatResponse(
                        AI=routed.reply, type="pins", pins=pins_payload
                    )
            else:  # CHAT fallback -> LLM
                reply, prompt_tok, completion_tok = _llm_reply(
                    user_request.user_input
                )
                resp = ChatResponse(AI=reply, type="chat")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — broad-catch for metrics logging
            error = f"{type(exc).__name__}: {exc}"
            resp = ChatResponse(
                AI="Sorry, something went wrong. Please try again.",
                type="error",
            )

    metrics.record(RequestRecord(
        ts=time.time(),
        user_input=user_request.user_input[:200],
        intent=routed.intent.value,
        handled_locally=routed.handled_locally,
        latency_ms=elapsed[0],
        prompt_tokens=prompt_tok,
        completion_tokens=completion_tok,
        estimated_cost_usd=estimate_cost_usd(prompt_tok, completion_tok),
        error=error,
    ))

    return resp


@app.get("/metrics")
async def metrics_endpoint() -> dict[str, Any]:
    """Aggregate stats for the README / resume."""
    return metrics.summary()


@app.get("/auth/callback")
async def auth_callback(code: str, state: str,
                        session_id: str | None = None) -> JSONResponse:
    """Exchange Pinterest OAuth code for an access token."""
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")
    _oauth_states.pop(state, None)
    token_data = await pinterest.exchange_code(code)
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="No access token returned")
    sid = session_id or secrets.token_urlsafe(16)
    _pinterest_tokens[sid] = access_token
    return JSONResponse({"session_id": sid, "status": "connected"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception
                                       ) -> JSONResponse:
    """Catch-all so the extension always gets valid JSON back."""
    return JSONResponse(
        status_code=500,
        content={"AI": "Unexpected server error.", "type": "error"},
    )
