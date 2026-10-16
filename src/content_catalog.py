"""
LUMI — Content Catalog

Small, local content catalog (≤20 items per category for v1).
Content is accessed by category and optional hobby/profile preference.

No network access; all content is in-memory or loaded from local files.
"""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass
class ContentItem:
    id: str
    category: str
    title: str
    body: str             # TTS-ready text response
    tags: list[str] = field(default_factory=list)


class ContentCatalog:
    """In-memory content catalog for LUMI with educational CSV integration."""

    def __init__(self, educational_dir: Optional[Union[Path, str]] = None,
                 load_educational: bool = True) -> None:
        self._items: list[ContentItem] = _build_catalog()
        self._educational_loader = None

        if load_educational:
            try:
                from .educational_loader import EducationalContentLoader
                self._educational_loader = EducationalContentLoader(educational_dir)
                edu_items = self._educational_loader.load_all()
                self._items.extend(edu_items)
            except Exception as exc:
                # Keep core catalog resilient if educational files cannot be read
                pass

    def get_by_category(self, category: str,
                        prefer_tags: Optional[list[str]] = None) -> Optional[ContentItem]:
        """Return a content item for the given category.

        If prefer_tags is provided, tagged matches are returned first.
        Items within a priority tier are selected randomly.
        """
        matches = [i for i in self._items if i.category == category]
        if not matches:
            return None

        if prefer_tags:
            tagged = [i for i in matches
                      if any(t in prefer_tags for t in i.tags)]
            if tagged:
                return random.choice(tagged)

        return random.choice(matches)

    def get_by_id(self, item_id: str) -> Optional[ContentItem]:
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def get_by_tag(self, tag: str) -> list[ContentItem]:
        """Return all items containing a specific tag."""
        target = tag.lower()
        return [i for i in self._items if any(target == t.lower() for t in i.tags)]

    def get_alphabet_lesson(self, letter: str) -> Optional[ContentItem]:
        """Return the lesson for a specific letter."""
        return self.get_by_id(f"edu_alphabet_{letter.lower()}")

    def educational_count(self) -> int:
        """Return count of imported educational items."""
        return sum(1 for i in self._items if i.id.startswith("edu_"))

    def categories(self) -> list[str]:
        return sorted({i.category for i in self._items})


def _build_catalog() -> list[ContentItem]:
    """Return the initial catalog.  All text is child-appropriate (0–6).
    Limit: ≤20 items per category.
    """
    items: list[ContentItem] = []

    # --- Stories ---
    items += [
        ContentItem(
            id="story_brave_bunny",
            category="story",
            title="The Brave Bunny",
            body=(
                "Once upon a time, a little bunny named Pip lived in a cozy burrow. "
                "One stormy day, Pip heard a small kitten crying in the rain. "
                "Even though Pip was scared of thunder, she hopped outside and "
                "brought the kitten safely home. Everyone cheered for brave Pip!"
            ),
            tags=["animals", "courage"],
        ),
        ContentItem(
            id="story_space_adventure",
            category="story",
            title="Space Adventure",
            body=(
                "A little robot named Beep zoomed past the moon and the stars. "
                "Beep discovered a planet made entirely of colorful bouncy balls! "
                "Beep collected one blue ball and one red ball as souvenirs, "
                "then zoomed back home to share the news with all the other robots."
            ),
            tags=["space", "adventure"],
        ),
        ContentItem(
            id="story_counting_caterpillar",
            category="story",
            title="The Counting Caterpillar",
            body=(
                "Carl the caterpillar loved to count leaves. "
                "One, two, three green leaves. Four, five yellow leaves. "
                "After counting ten leaves, Carl wove himself a cozy cocoon. "
                "When he woke up, he had beautiful wings — and flew away counting butterflies!"
            ),
            tags=["animals", "counting"],
        ),
    ]

    # --- Songs ---
    items += [
        ContentItem(
            id="song_twinkle",
            category="song",
            title="Twinkle Twinkle",
            body=(
                "Twinkle, twinkle, little star, how I wonder what you are! "
                "Up above the world so high, like a diamond in the sky."
            ),
            tags=["classic", "music"],
        ),
        ContentItem(
            id="song_wheels_bus",
            category="song",
            title="Wheels on the Bus",
            body=(
                "The wheels on the bus go round and round, round and round, round and round! "
                "The wheels on the bus go round and round, all through the town."
            ),
            tags=["vehicles", "music"],
        ),
        ContentItem(
            id="song_old_macdonald",
            category="song",
            title="Old MacDonald",
            body=(
                "Old MacDonald had a farm, E-I-E-I-O! "
                "And on his farm he had a cow, E-I-E-I-O! "
                "With a moo moo here, and a moo moo there, "
                "here a moo, there a moo, everywhere a moo moo!"
            ),
            tags=["animals", "music"],
        ),
    ]

    # --- Learning ---
    items += [
        ContentItem(
            id="learn_colors",
            category="learn",
            title="Colors",
            body=(
                "Let's learn colors! Red is the color of an apple. "
                "Blue is the color of the sky. Yellow is the color of the sun. "
                "Can you find something red near you right now?"
            ),
            tags=["colors"],
        ),
        ContentItem(
            id="learn_counting_5",
            category="learn",
            title="Counting to Five",
            body=(
                "Let's count together! One, two, three, four, five! "
                "Now let's count your fingers. Hold up your hand and count with me: "
                "one, two, three, four, five fingers!"
            ),
            tags=["counting"],
        ),
        ContentItem(
            id="learn_animal_sounds",
            category="learn",
            title="Animal Sounds",
            body=(
                "Animals make amazing sounds! A dog says woof woof. "
                "A cat says meow. A cow says moo. "
                "A lion says roar! Which animal sound is your favorite?"
            ),
            tags=["animals"],
        ),
    ]

    # --- Animals ---
    items += [
        ContentItem(
            id="animal_elephant",
            category="animal",
            title="Elephants",
            body=(
                "Elephants are the biggest land animals on Earth! "
                "They have long trunks they use to drink water and smell things. "
                "Baby elephants, called calves, are looked after by all the elephants "
                "in the herd — they are very caring animals."
            ),
            tags=["animals", "big"],
        ),
        ContentItem(
            id="animal_penguin",
            category="animal",
            title="Penguins",
            body=(
                "Penguins are birds that cannot fly, but they are amazing swimmers! "
                "They live in cold places near the South Pole. "
                "Baby penguins are called chicks, and penguin dads keep the eggs warm "
                "by balancing them on their feet."
            ),
            tags=["animals", "birds"],
        ),
    ]

    # --- Greetings (for HELLO intent) ---
    items += [
        ContentItem(
            id="greeting_hello",
            category="greeting",
            title="Hello",
            body="Hi there! I'm Lumi, your learning friend. What shall we do today?",
            tags=["greeting"],
        ),
        ContentItem(
            id="greeting_morning",
            category="greeting",
            title="Good Morning",
            body="Good morning! Are you ready for a fun day of learning and stories?",
            tags=["greeting", "morning"],
        ),
    ]

    # --- Help ---
    items += [
        ContentItem(
            id="help_main",
            category="help",
            title="Help",
            body=(
                "I can tell you stories, play songs, teach you new things, "
                "tell you about animals, or let you know what time it is. "
                "Just say what you'd like to do!"
            ),
            tags=["help"],
        ),
    ]

    # --- Unknown / UNKNOWN fallback ---
    items += [
        ContentItem(
            id="unknown_fallback",
            category="unknown",
            title="I didn't understand",
            body=(
                "Hmm, I didn't quite catch that. "
                "You can ask me for a story, a song, something to learn, "
                "or say 'help' to hear what I can do."
            ),
            tags=[],
        ),
    ]

    return items
