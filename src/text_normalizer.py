"""
LUMI — Text Normalizer

Normalizes transcribed text for intent classification:
- Lowercases
- Strips punctuation (except apostrophes in contractions)
- Collapses whitespace
- Strips leading/trailing whitespace
"""

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize a transcript for intent classification.

    Args:
        text: Raw transcript text.

    Returns:
        Cleaned, lowercased text suitable for intent matching.
    """
    if not text:
        return ""

    # Normalize Unicode (e.g., curly quotes → straight)
    text = unicodedata.normalize("NFKC", text)

    # Lowercase
    text = text.lower()

    # Remove punctuation except apostrophes (for contractions like "don't")
    # Keep letters, digits, spaces, and apostrophes
    text = re.sub(r"[^\w\s']", " ", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()
