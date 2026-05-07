

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class IntentType(str, Enum):
    voice_command = 'voice_command_category'


@dataclass
class RoutedIntent:
    intent: IntentType
    reply: str
    url: Optional[str] = None
    query: Optional[str] = None  # for pin search
    handled_locally: bool = True 

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
    ...