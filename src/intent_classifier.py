"""
LUMI — Deterministic Intent Classifier

Maps normalized text to one of the supported LUMI intents using
keyword/phrase matching. No generative AI is used.

Intents:
    HELLO, STORY, MUSIC, LEARN, ANIMALS, HOBBIES, FAVORITES,
    TIME, REPEAT, NEXT, BACK, STOP, HELP, EXIT, UNKNOWN
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .text_normalizer import normalize_text


class Intent(Enum):
    HELLO = "HELLO"
    STORY = "STORY"
    MUSIC = "MUSIC"
    LEARN = "LEARN"
    ANIMALS = "ANIMALS"
    HOBBIES = "HOBBIES"
    FAVORITES = "FAVORITES"
    TIME = "TIME"
    REPEAT = "REPEAT"
    NEXT = "NEXT"
    BACK = "BACK"
    STOP = "STOP"
    HELP = "HELP"
    EXIT = "EXIT"
    UNKNOWN = "UNKNOWN"


@dataclass
class ClassificationResult:
    intent: Intent
    confidence: float  # 0.0–1.0 — deterministic confidence, not calibrated
    raw_text: str
    normalized_text: str
    matched_pattern: Optional[str] = None


# Patterns ordered from most specific to least specific within each intent.
# Each entry: (compiled regex, intent, confidence, pattern description)
# Earlier intents in the list take priority for ambiguous matches.
@dataclass
class _PatternEntry:
    pattern: re.Pattern
    intent: Intent
    confidence: float
    description: str


def _build_patterns() -> list[_PatternEntry]:
    """Build the ordered pattern list for intent classification."""
    entries = []

    def add(pattern_str: str, intent: Intent, confidence: float = 0.9,
            desc: str = ""):
        entries.append(_PatternEntry(
            pattern=re.compile(pattern_str, re.IGNORECASE),
            intent=intent,
            confidence=confidence,
            description=desc or pattern_str,
        ))

    # --- EXIT (check before STOP to avoid "goodbye" matching STOP) ---
    add(r"\b(goodbye|bye\s*bye|see\s*you|good\s*night)\b", Intent.EXIT, 0.9, "exit")
    add(r"\b(exit|quit|shut\s*down|turn\s*off)\b", Intent.EXIT, 0.9, "exit-cmd")

    # --- STOP ---
    add(r"\b(stop|be\s*quiet|hush|silence|enough|shut\s*up)\b", Intent.STOP, 0.9,
        "stop")
    add(r"\bstop\s*(please|it|that|now)?\b", Intent.STOP, 0.85, "stop-please")
    add(r"\bno\s*more\b", Intent.STOP, 0.8, "no-more")

    # --- HELLO ---
    add(r"\b(hello|hi|hey|good\s*morning|good\s*afternoon|good\s*evening)\b",
        Intent.HELLO, 0.9, "greeting")
    add(r"\bhow\s*are\s*you\b", Intent.HELLO, 0.8, "how-are-you")
    add(r"\bwhat'?s\s*up\b", Intent.HELLO, 0.8, "whats-up")

    # --- STORY ---
    add(r"\b(tell|read)\s*(me\s+)?a?\s*story\b", Intent.STORY, 0.95, "tell-story")
    add(r"\bi\s*want\s*(a\s*)?story\b", Intent.STORY, 0.95, "want-story")
    add(r"\b(story\s*time|once\s*upon|bedtime\s*story)\b", Intent.STORY, 0.9,
        "story-time")
    add(r"\bread\s*(me\s+)?(a\s+)?book\b", Intent.STORY, 0.85, "read-book")
    add(r"\bstory\b", Intent.STORY, 0.7, "story-bare")

    # --- MUSIC ---
    add(r"\b(play|sing)\s*(me\s+)?(some\s+)?music\b", Intent.MUSIC, 0.95,
        "play-music")
    add(r"\b(play|sing)\s*(me\s+)?a?\s*song\b", Intent.MUSIC, 0.95, "play-song")
    add(r"\b(sing\s*along|let'?s\s*sing|music\s*time)\b", Intent.MUSIC, 0.9,
        "sing-along")
    add(r"\bsong\b", Intent.MUSIC, 0.7, "song-bare")
    add(r"\bmusic\b", Intent.MUSIC, 0.7, "music-bare")

    # --- ANIMALS (before LEARN to catch "tell me about elephants") ---
    add(r"\b(animal|animals|cat|dog|bird|fish|lion|elephant|dinosaur|bear|rabbit"
        r"|monkey|giraffe|zebra|tiger|horse|cow|pig|duck|frog|turtle|snake|whale"
        r"|dolphin|penguin|owl|butterfly|bee)s?\b",
        Intent.ANIMALS, 0.85, "animals")
    add(r"\btell\s*me\s*about\s+(an\s+)?(animal|cat|dog|bird|lion|elephant|dinosaur|bear|rabbit|monkey|giraffe|zebra|tiger|horse|cow|pig|duck|frog|turtle|snake|whale|dolphin|penguin|owl|butterfly|bee)s?\b",
        Intent.ANIMALS, 0.9, "tell-me-about-animal")
    add(r"\bwhat\s*(sound|noise)\s*(does|do)\b", Intent.ANIMALS, 0.8,
        "animal-sound")

    # --- LEARN ---
    add(r"\bteach\s*me\b", Intent.LEARN, 0.95, "teach-me")
    add(r"\b(i\s*want\s*to\s*)?learn\s*(something|new)?\b", Intent.LEARN, 0.9,
        "learn")
    add(r"\btell\s*me\s*(about|something)\b", Intent.LEARN, 0.8, "tell-me-about")
    add(r"\bwhat\s*is\b", Intent.LEARN, 0.75, "what-is")
    add(r"\bwhy\s*(is|do|does|are)\b", Intent.LEARN, 0.75, "why-question")

    # --- HOBBIES ---
    add(r"\b(hobby|hobbies|drawing|painting|coloring|craft|building|playing"
        r"|cooking|baking|gardening|dancing|sports|swimming)\b",
        Intent.HOBBIES, 0.85, "hobbies")
    add(r"\bwhat\s*can\s*i\s*do\b", Intent.HOBBIES, 0.7, "what-can-i-do")

    # --- FAVORITES ---
    add(r"\b(favorite|favourite)\b", Intent.FAVORITES, 0.85, "favorites")
    add(r"\bwhat\s*do\s*(you|i)\s*like\b", Intent.FAVORITES, 0.8, "what-do-i-like")
    add(r"\bbest\s*(thing|part|one)\b", Intent.FAVORITES, 0.7, "best-thing")

    # --- TIME ---
    add(r"\bwhat\s*time\s*is\s*it\b", Intent.TIME, 0.95, "what-time")
    add(r"\bwhat'?s\s*the\s*time\b", Intent.TIME, 0.95, "whats-the-time")
    add(r"\bwhat\s*day\s*(is\s*it|today)\b", Intent.TIME, 0.9, "what-day")
    add(r"\bwhat'?s\s*the\s*date\b", Intent.TIME, 0.9, "whats-the-date")

    # --- REPEAT ---
    add(r"\b(say\s*(that|it)\s*again|repeat|again\s*please|one\s*more\s*time)\b",
        Intent.REPEAT, 0.95, "repeat")
    add(r"\b(what\s*did\s*you\s*say|i\s*didn'?t\s*(hear|understand))\b",
        Intent.REPEAT, 0.85, "didnt-hear")
    add(r"\bagain\b", Intent.REPEAT, 0.65, "again-bare")

    # --- NEXT ---
    add(r"\b(next|skip|another\s*one|something\s*else|next\s*one)\b",
        Intent.NEXT, 0.9, "next")

    # --- BACK ---
    add(r"\b(go\s*back|previous|back|before|last\s*one)\b",
        Intent.BACK, 0.85, "back")

    # --- HELP ---
    add(r"\b(help|what\s*can\s*you\s*do|how\s*does\s*this\s*work)\b",
        Intent.HELP, 0.9, "help")
    add(r"\bi'?m\s*(confused|lost|stuck)\b", Intent.HELP, 0.8, "confused")

    return entries


# Build once at module load time.
_PATTERNS = _build_patterns()


def classify_intent(text: str) -> ClassificationResult:
    """Classify normalized text into a LUMI intent.

    Args:
        text: Raw or pre-normalized transcript text.

    Returns:
        ClassificationResult with the matched intent and metadata.
    """
    raw = text
    normalized = normalize_text(text)

    if not normalized:
        return ClassificationResult(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            raw_text=raw,
            normalized_text=normalized,
            matched_pattern="empty-text",
        )

    for entry in _PATTERNS:
        if entry.pattern.search(normalized):
            return ClassificationResult(
                intent=entry.intent,
                confidence=entry.confidence,
                raw_text=raw,
                normalized_text=normalized,
                matched_pattern=entry.description,
            )

    return ClassificationResult(
        intent=Intent.UNKNOWN,
        confidence=0.0,
        raw_text=raw,
        normalized_text=normalized,
        matched_pattern=None,
    )
