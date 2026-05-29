# GrandAssist

> **Voice-controlled Chrome extension that helps seniors navigate the web hands-free.**
> Ask a question, open a site, scroll a page, or search your saved Pinterest pins — all by voice.

[![CI](https://github.com/ksenera/Tech_Assistant_for_Seniors/actions/workflows/ci.yml/badge.svg)](https://github.com/ksenera/Tech_Assistant_for_Seniors/actions/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen)
![Tests](https://img.shields.io/badge/tests-73%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![Manifest](https://img.shields.io/badge/chrome-manifest%20v3-blue)

Originally built at **ElleHacks 2025**. This is v1.1 — rewritten for production readiness.

---

## Measured performance

Results from the 100-query benchmark in `benchmarks/queries.json` (run `python -m benchmarks.run_benchmark` to reproduce):

| Metric                                 | Value                                   |
|----------------------------------------|-----------------------------------------|
| Intent classification accuracy         | **100%** on 100 senior-phrased queries  |
| Queries resolved without an LLM call   | **36%** (deflection rate)               |
| p95 local-routing latency              | **8 μs**                                |
| p50 local-routing latency              | **3.4 μs**                              |
| Projected OpenAI savings at 5k q/day   | **~$4.20 / month** (~36% call reduction)|
| Unit test coverage                     | **98.02%** across 73 tests              |
| OpenAI model used                      | `gpt-4o-mini`                           |

Why this matters: every query handled by the local router is a 300,000× latency improvement *and* a cost saving. Knowledge questions ("what is inflation") still use the LLM — that's the right tradeoff.

---

## Architecture

```
  ┌─────────────────────────┐     voice    ┌──────────────────────────┐
  │  Chrome Extension (MV3) │  ──────────▶ │   FastAPI backend         │
  │  ──────────────────────  │   POST       │   ──────────────────────  │
  │  • sidebar.html / css   │   /chat      │   1. intent_router         │
  │  • content.js (voice +  │              │      └─ local rules first  │
  │    DOM control)         │              │   2. if CHAT → gpt-4o-mini │
  │  • background.js (SW)   │              │   3. if PINS → Pinterest   │
  │                         │              │      v5 search_my_pins     │
  │  Web Speech API         │              │   4. log to SQLite         │
  └─────────────────────────┘  ◀──────────  └──────────────────────────┘
                                JSON reply
                                                       │
                                                       ▼
                                              ┌────────────────┐
                                              │  metrics.db    │
                                              │  (SQLite)      │
                                              └────────────────┘
                                                       │
                                                       ▼
                                                 GET /metrics
                                                 (aggregate stats)
```

### Request routing

```
User says: "open youtube"
  → intent_router.classify() → IntentType.OPEN_WEBSITE  (3 μs)
  → return {url, AI: "Opening YouTube"}  — no LLM call

User says: "show me my knitting pins"
  → intent_router.classify() → IntentType.SEARCH_MY_PINS  (5 μs)
  → GET /v5/search/pins?query=knitting + Bearer token
  → return {type: "pins", pins: [...]}

User says: "how do I change my password"
  → intent_router.classify() → IntentType.CHAT  (3 μs)
  → openai.chat.completions.create(model="gpt-4o-mini", ...)
  → return {AI: "...", type: "chat"}  — LLM used
```

---

## Features

**Voice commands (handled locally, no network call):**
- `Scroll down` / `Scroll up` / `Scroll to top`
- `New tab` / `Go back` / `Go forward`
- `Minimize` / `Close sidebar`
- `Open <site>` — 12 preset sites (YouTube, Gmail, Google, Amazon, Pinterest, etc.)

**Voice commands routed to the backend:**
- `Show me my <topic> pins` — Pinterest pin search via OAuth
- Anything else — falls through to gpt-4o-mini

**Accessibility (WCAG 2.1 AA):**
- 18px base font with 4-step user-controlled scaling (up to 1.65×)
- 7.2:1 contrast ratio on all text
- 44×44 px minimum tap targets
- `prefers-reduced-motion` honoured
- Full keyboard navigation, `Alt+M` toggles mic
- Drag-to-reposition sidebar
- Persistent preferences via `chrome.storage`

---

## Quickstart

### Backend

```bash
git clone https://github.com/ksenera/Tech_Assistant_for_Seniors.git
cd Tech_Assistant_for_Seniors

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt
cp .env.example .env             # defaults to free mock LLM responses

uvicorn backend.tech_assistant_for_seniors:app --reload
# → http://localhost:8000/docs
```

### LLM provider

The backend runs for free by default:

```env
LLM_PROVIDER=mock
```

For live model responses, switch providers in `.env`:

```env
# Hosted Gemini Developer API option with a free tier
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash

# Paid OpenAI API
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Free local Ollama option
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2
```

### Extension

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right)
3. Click **Load unpacked** → select the `extension/` folder
4. Pin the extension, click the icon on any tab to open the sidebar

### Tests

```bash
pytest                                        # full suite with coverage gate (80%)
pytest tests/test_intent_router.py -v         # just the router
python -m benchmarks.run_benchmark             # generate resume metrics
```

---

## Pinterest setup (optional)

To enable pin search, register an app at https://developers.pinterest.com/apps/ and add to `.env`:

```
PINTEREST_CLIENT_ID=...
PINTEREST_CLIENT_SECRET=...
PINTEREST_REDIRECT_URI=http://localhost:8000/auth/callback
```

Scopes required: `pins:read`, `boards:read`, `user_accounts:read`. Users authorise the extension via the OAuth redirect the first time they ask for a pin search.

> **Note:** Pinterest's public API only searches pins the signed-in user has saved — not all of Pinterest. This is intentional for our use case: seniors keeping track of their own saved content.

---

## Development notes

### Adding a new intent

1. Add a new `IntentType` enum value in `backend/intent_router.py`
2. Add classification logic in `classify()` above the CHAT fallback
3. Add a handler branch in `backend/tech_assistant_for_seniors.py::chat_endpoint`
4. Add test cases to `tests/test_intent_router.py` and an entry in `benchmarks/queries.json`
5. Re-run `python -m benchmarks.run_benchmark` — accuracy should stay at 100%

### Project layout

```
.
├── backend/
│   ├── intent_router.py          # pure rules, no I/O, fully unit-tested
│   ├── metrics.py                # SQLite request logger
│   ├── pinterest_client.py       # Pinterest API v5 wrapper
│   └── tech_assistant_for_seniors.py   # FastAPI app
├── extension/
│   ├── manifest.json
│   ├── scripts/{background,content}.js
│   ├── sidebar/{sidebar.html,sidebar.css}
│   └── images/icon-{16,48,128}.png
├── tests/                        # 73 tests, 98% coverage
├── benchmarks/                   # evaluation harness + ground-truth queries
└── .github/workflows/ci.yml      # runs tests + benchmark + manifest validation
```

---

## What changed in v1.1

- **Fixed broken OpenAI import** that crashed the backend
- **Added configurable LLM providers** — free mock default, optional OpenAI or Ollama
- **Extracted intent routing** into a pure module with unit tests (was a 60-line `if/elif` chain)
- **Added SQLite request metrics** — `/metrics` endpoint with cost tracking
- **Added Pinterest API v5** integration (OAuth + pin search)
- **Redesigned sidebar** — WCAG AA compliant, font scaling, minimize, drag
- **Added test suite** — 73 pytest cases, 98% coverage, CI-gated at 80%
- **Added benchmark harness** — 100-query evaluation with accuracy & latency reports
- **Manifest v3 hardening** — explicit host permissions, service worker cleanup

## Credits

Originally built at ElleHacks 2025 ([DoraHacks submission](https://dorahacks.io/buidl/22872)).
Voice recognition via the [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API).
Icons and design by Ksenia Erofeeva.

## License

MIT
