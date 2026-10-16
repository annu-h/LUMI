"""
LUMI — JIBO Kids Educational Catalog

Exposes suitable letter-and-digit recordings from the JIBO Kids Corpus
through LUMI's educational content catalog.

Design decisions:
  - Only letters_digits task recordings are offered as alphabet/digit
    learning content.  The brush/colors/blocks tasks are catalogued
    as speech-evaluation material (not children's lessons).
  - Transcript content is inspected to determine if a record can reliably
    be associated with a specific letter or digit.
  - Original transcripts and task contexts are preserved.
  - Records are NOT assumed to be clean isolated pronunciations.

Privacy: Speaker identifiers are not exposed in catalog queries.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .jibo_adapter import JiboRecord, JiboDatasetAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Letters and digits we attempt to recognize from transcripts
LETTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS = set("0123456789")

# Common letter name spellings in transcripts
LETTER_NAMES = {
    "ay": "A", "a": "A",
    "bee": "B", "b": "B",
    "see": "C", "sea": "C", "c": "C",
    "dee": "D", "d": "D",
    "ee": "E", "e": "E",
    "eff": "F", "f": "F",
    "gee": "G", "g": "G",
    "aitch": "H", "h": "H",
    "eye": "I", "i": "I",
    "jay": "J", "j": "J",
    "kay": "K", "k": "K",
    "ell": "L", "l": "L",
    "em": "M", "m": "M",
    "en": "N", "n": "N",
    "oh": "O", "o": "O",
    "pee": "P", "p": "P",
    "cue": "Q", "queue": "Q", "q": "Q",
    "are": "R", "ar": "R", "r": "R",
    "ess": "S", "s": "S",
    "tee": "T", "t": "T",
    "you": "U", "u": "U",
    "vee": "V", "v": "V",
    "double-u": "W", "w": "W",
    "ex": "X", "x": "X",
    "why": "Y", "wye": "Y", "y": "Y",
    "zee": "Z", "zed": "Z", "z": "Z",
}

DIGIT_NAMES = {
    "zero": "0", "oh": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3",
    "four": "4", "for": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
    "ten": "10",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EducationalRecord:
    """A JIBO record annotated for educational use."""
    record_id: str
    audio_path: str
    transcript: Optional[str]
    content_type: str            # "letter" | "digit" | "speech_eval"
    target_value: Optional[str]  # The letter or digit, or None
    task_category: str           # Original JIBO task category
    confidence: str              # "high" | "low" | "none"
    original_transcript: Optional[str]  # Preserved unmodified transcript
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transcript analysis
# ---------------------------------------------------------------------------

def identify_letter_or_digit(transcript: Optional[str]) -> tuple[str, Optional[str], str]:
    """Analyze a transcript to identify a target letter or digit.

    Returns:
        (content_type, target_value, confidence)
        content_type: "letter" | "digit" | "speech_eval"
        target_value: The identified letter/digit or None
        confidence: "high" | "low" | "none"
    """
    if not transcript:
        return "speech_eval", None, "none"

    text = transcript.strip().lower()

    # Remove common filler/markers
    text = re.sub(r"\[.*?\]", "", text)  # Remove bracketed annotations
    text = re.sub(r"[^a-z0-9\s-]", "", text)  # Keep alphanum, space, hyphen
    tokens = text.split()

    if not tokens:
        return "speech_eval", None, "none"

    # Single-token transcripts are the most reliable
    if len(tokens) == 1:
        tok = tokens[0]

        # Check single uppercase letter
        if len(tok) == 1 and tok.upper() in LETTERS:
            return "letter", tok.upper(), "high"

        # Check single digit
        if tok in DIGITS or tok.isdigit():
            return "digit", tok, "high"

        # Check letter name spelling
        if tok in LETTER_NAMES:
            return "letter", LETTER_NAMES[tok], "high"

        # Check digit name
        if tok in DIGIT_NAMES:
            return "digit", DIGIT_NAMES[tok], "high"

    # If transcript has more than 3 words, it's a phrase/sentence, not a single target
    if len(tokens) > 3:
        return "speech_eval", None, "none"

    # Multi-token (2-3 words): look for a dominant letter/digit mention
    # Words like "you", "are", "why", "to", "for" are regular English words in multi-token contexts
    ambiguous_words = {"you", "are", "why", "to", "too", "for", "won", "ate", "oh"}
    letter_hits = []
    digit_hits = []

    for tok in tokens:
        if len(tok) == 1 and tok.upper() in LETTERS:
            letter_hits.append(tok.upper())
        elif tok in LETTER_NAMES and tok not in ambiguous_words:
            letter_hits.append(LETTER_NAMES[tok])
        elif (tok in DIGITS or tok.isdigit()):
            digit_hits.append(tok)
        elif tok in DIGIT_NAMES and tok not in ambiguous_words:
            digit_hits.append(DIGIT_NAMES[tok])

    # If exactly one letter or digit is identified, use it with low confidence
    if len(letter_hits) == 1 and not digit_hits:
        return "letter", letter_hits[0], "low"
    if len(digit_hits) == 1 and not letter_hits:
        return "digit", digit_hits[0], "low"

    # Complex or ambiguous transcript — classify as speech evaluation
    return "speech_eval", None, "none"


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------

class JiboEducationalCatalog:
    """Educational content catalog built from JIBO Kids records.

    Letters_digits → letter/digit learning content (when reliably identified).
    Brush/colors/blocks → speech evaluation material.
    """

    def __init__(self) -> None:
        self._records: list[EducationalRecord] = []
        self._by_letter: dict[str, list[EducationalRecord]] = {}
        self._by_digit: dict[str, list[EducationalRecord]] = {}
        self._speech_eval: list[EducationalRecord] = []

    @property
    def total_records(self) -> int:
        return len(self._records)

    def build_from_jibo_records(self, jibo_records: list[JiboRecord]) -> None:
        """Process JIBO records into educational catalog entries."""
        self._records.clear()
        self._by_letter.clear()
        self._by_digit.clear()
        self._speech_eval.clear()

        for jr in jibo_records:
            if jr.task_category == "letters_digits":
                content_type, target, confidence = identify_letter_or_digit(
                    jr.transcript_text
                )
            else:
                # Non-letter/digit tasks → speech evaluation
                content_type = "speech_eval"
                target = None
                confidence = "none"

            tags = [jr.task_category]
            if content_type == "letter" and target:
                tags.append(f"letter_{target}")
            elif content_type == "digit" and target:
                tags.append(f"digit_{target}")

            edu_rec = EducationalRecord(
                record_id=jr.record_id,
                audio_path=jr.audio_path,
                transcript=jr.transcript_text,
                content_type=content_type,
                target_value=target,
                task_category=jr.task_category,
                confidence=confidence,
                original_transcript=jr.transcript_text,
                tags=tags,
            )
            self._records.append(edu_rec)

            if content_type == "letter" and target:
                self._by_letter.setdefault(target, []).append(edu_rec)
            elif content_type == "digit" and target:
                self._by_digit.setdefault(target, []).append(edu_rec)
            else:
                self._speech_eval.append(edu_rec)

        logger.info(
            "Educational catalog built: %d letters, %d digits, %d speech_eval",
            sum(len(v) for v in self._by_letter.values()),
            sum(len(v) for v in self._by_digit.values()),
            len(self._speech_eval),
        )

    def query_letters(self, letter: Optional[str] = None) -> list[EducationalRecord]:
        """Get letter recordings, optionally filtered by specific letter."""
        if letter:
            return list(self._by_letter.get(letter.upper(), []))
        return [r for records in self._by_letter.values() for r in records]

    def query_digits(self, digit: Optional[str] = None) -> list[EducationalRecord]:
        """Get digit recordings, optionally filtered by specific digit."""
        if digit:
            return list(self._by_digit.get(str(digit), []))
        return [r for records in self._by_digit.values() for r in records]

    def query_speech_eval(self, task_category: Optional[str] = None) -> list[EducationalRecord]:
        """Get speech evaluation recordings, optionally filtered by task."""
        if task_category:
            return [r for r in self._speech_eval
                    if r.task_category == task_category]
        return list(self._speech_eval)

    def available_letters(self) -> list[str]:
        """Return sorted list of letters with available recordings."""
        return sorted(self._by_letter.keys())

    def available_digits(self) -> list[str]:
        """Return sorted list of digits with available recordings."""
        return sorted(self._by_digit.keys())

    def summary(self) -> dict:
        """Return a summary of the educational catalog."""
        return {
            "total_records": self.total_records,
            "letter_records": sum(len(v) for v in self._by_letter.values()),
            "digit_records": sum(len(v) for v in self._by_digit.values()),
            "speech_eval_records": len(self._speech_eval),
            "available_letters": self.available_letters(),
            "available_digits": self.available_digits(),
            "task_categories": sorted({r.task_category for r in self._records}),
        }
