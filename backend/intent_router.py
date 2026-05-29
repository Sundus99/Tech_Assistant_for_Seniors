"""
Intent router for GrandAssist.

Classifies voice commands locally using keyword rules before falling back to an
LLM. This is the component that makes local routing metrics meaningful — every
query that resolves here is one fewer round-trip to OpenAI.

All functions are pure and synchronous so they can be unit-tested without
booting FastAPI or hitting the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class IntentType(str, Enum):
    """The buckets a voice command can fall into."""

    OPEN_WEBSITE = "open_website"
    SEARCH_REFUSAL = "search_refusal"
    SEARCH_MY_PINS = "search_my_pins"  # Pinterest API-backed
    CHAT = "chat"  # fallback -> LLM


@dataclass
class RoutedIntent:
    """The result of classifying a user query."""

    intent: IntentType
    reply: str
    url: Optional[str] = None
    query: Optional[str] = None  # for pin search
    handled_locally: bool = True  # False if LLM was needed


# --- Known websites the extension can open directly ---
# Ordered longest-first so multi-word hits (e.g. "duck duck go") match before
# single-word ones.
KNOWN_SITES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("youtube", "you tube"), "YouTube", "https://www.youtube.com/"),
    (("gmail",), "Gmail", "https://www.gmail.com/"),
    (("google",), "Google", "https://www.google.ca/"),
    (("facebook",), "Facebook", "https://www.facebook.com/"),
    (("hotmail", "outlook"), "Hotmail", "https://outlook.live.com/"),
    (("yahoo",), "Yahoo", "https://www.yahoo.com/"),
    (("bing",), "Bing", "https://www.bing.com/"),
    (("duckduckgo", "duck duck go", "duck duckgo"), "DuckDuckGo",
     "https://duckduckgo.com/"),
    (("amazon",), "Amazon", "https://www.amazon.ca/"),
    (("ebay",), "eBay", "https://www.ebay.ca/"),
    (("wikipedia",), "Wikipedia", "https://www.wikipedia.org/"),
    (("pinterest",), "Pinterest", "https://www.pinterest.com/"),
)

OPEN_VERBS: frozenset[str] = frozenset({"open", "launch", "go to", "take me to"})
PIN_VERBS: frozenset[str] = frozenset({"show me my", "find my", "search my pins",
                                        "my pins of", "my saved"})
GENERIC_SEARCH_VERBS: frozenset[str] = frozenset({"search for", "search the web",
                                                   "google"})


def _contains_any(text: str, needles: frozenset[str] | tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def classify(user_input: str) -> RoutedIntent:
    """
    Return the best local classification for a voice command.

    Returns an intent with ``handled_locally=False`` only for the CHAT bucket,
    which means the caller must fall back to the LLM.
    """
    if not user_input or not user_input.strip():
        return RoutedIntent(
            intent=IntentType.CHAT,
            reply="I didn't catch that — could you say it again?",
            handled_locally=True,
        )

    text = user_input.lower().strip()

    # Block "how do I..." questions from being eaten by the open-website path.
    is_howto = "how" in text and ("do i" in text or "to " in text)

    # --- Pinterest pin search (must run before "open website") ---
    if _contains_any(text, PIN_VERBS) and not is_howto:
        # Strip the verb phrase to extract the actual search term.
        query = text
        for verb in PIN_VERBS:
            if verb in query:
                query = query.split(verb, 1)[1].strip()
                break
        query = query.strip(" .?!,") or "recent"
        return RoutedIntent(
            intent=IntentType.SEARCH_MY_PINS,
            reply=f"Searching your saved pins for '{query}'.",
            query=query,
        )

    # --- Open a known website ---
    if _contains_any(text, OPEN_VERBS) and not is_howto:
        for aliases, display_name, url in KNOWN_SITES:
            if any(alias in text for alias in aliases):
                extra = ""
                if display_name == "YouTube":
                    extra = (" Now, in the search bar, type what you want to "
                             "watch and press Enter.")
                return RoutedIntent(
                    intent=IntentType.OPEN_WEBSITE,
                    reply=f"Opening {display_name}.{extra}",
                    url=url,
                )

    # --- Decline generic searches (we only do pin search) ---
    if _contains_any(text, GENERIC_SEARCH_VERBS) and not is_howto:
        return RoutedIntent(
            intent=IntentType.SEARCH_REFUSAL,
            reply=("I can't run web searches for you, but I can explain how. "
                   "Try: 'open Google' and I'll take you there."),
        )

    # --- Fallback: needs the LLM ---
    return RoutedIntent(
        intent=IntentType.CHAT,
        reply="",  # filled in by caller after LLM round-trip
        handled_locally=False,
    )
