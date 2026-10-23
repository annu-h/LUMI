"""
LUMI — Educational Dataset CSV Loader

Parses project-ready educational CSV files from local storage (data/educational/)
into LUMI's ContentItem data structure for offline voice and learning interactions.

Supported Datasets:
- alphabets.csv: Letters, example words, and introductory lessons
- animals.csv: Animal Q&A facts and categories
- basic_math.csv: Elementary addition/subtraction questions and answers
- colors.csv: Color recognition questions and answers
- fruits.csv: Fruit facts and trivia
- general_knowledge.csv: Science and space Q&A
- good_habits.csv: Daily hygiene and routines
- healthy_foods.csv: Nutrition and balanced diet Q&A
- numbers_counting.csv: Numerical sequence and counting questions
- shapes.csv: Geometry and shape identification questions
"""

from src import ContentItem
import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default educational datasets path within LUMI workspace
DEFAULT_EDUCATIONAL_DIR = Path(__file__).resolve().parent.parent / "data" / "educational"


@dataclass
class EducationalQuestion:
    """Represents a structured Q&A educational item."""
    source_file: str
    topic: str
    question: str
    answer: str
    category: str
    tts_text: str
    tags: list[str]


class EducationalContentLoader:
    """Loads and parses educational CSV files into ContentItem objects.
    
    Operates strictly offline without external network dependencies.
    Handles UTF-8 with BOM (utf-8-sig) and standard CSV formatting.
    """

    def __init__(self, data_dir: Optional[Path | str] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_EDUCATIONAL_DIR

    def is_available(self) -> bool:
        """Check whether the educational directory exists and contains CSVs."""
        return self.data_dir.is_dir() and any(self.data_dir.glob("*.csv"))

    def list_csv_files(self) -> list[str]:
        """Return list of filenames present in the educational directory."""
        if not self.data_dir.is_dir():
            return []
        return sorted(p.name for p in self.data_dir.glob("*.csv"))

    def load_all(self) -> list["ContentItem"]:
        """Load all educational CSV files into ContentItem instances."""
        from .content_catalog import ContentItem

        items: list[ContentItem] = []
        if not self.is_available():
            logger.info("Educational data directory not found or empty: %s", self.data_dir)
            return items

        loaders = {
            "alphabets.csv": self._load_alphabets,
            "animals.csv": self._load_animals,
            "basic_math.csv": self._load_basic_math,
            "colors.csv": self._load_colors,
            "fruits.csv": self._load_fruits,
            "general_knowledge.csv": self._load_general_knowledge,
            "good_habits.csv": self._load_good_habits,
            "healthy_foods.csv": self._load_healthy_foods,
            "numbers_counting.csv": self._load_numbers_counting,
            "shapes.csv": self._load_shapes,
        }

        for filename, loader_func in loaders.items():
            csv_path = self.data_dir / filename
            if csv_path.exists():
                try:
                    loaded = loader_func(csv_path)
                    items.extend(loaded)
                    logger.debug("Loaded %d items from %s", len(loaded), filename)
                except Exception as exc:
                    logger.error("Failed to parse %s: %s", filename, exc)

        return items

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        """Read CSV rows with BOM stripping and whitespace trimming."""
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                clean_row = {
                    (k.strip() if k else ""): (v.strip() if v else "")
                    for k, v in row.items() if k is not None
                }
                rows.append(clean_row)
            return rows

    def _load_alphabets(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for row in self._read_rows(path):
            letter = row.get("letter", "").strip()
            word = row.get("example_word", "").strip()
            lesson = row.get("lesson", "").strip()
            if not letter:
                continue

            # TTS-friendly speech text
            body = f"{lesson}. {letter} is for {word}!" if not lesson.endswith(f"for {word}") else f"{lesson}!"
            tags = ["alphabet", "letters", "reading", letter.lower(), word.lower()]
            items.append(ContentItem(
                id=f"edu_alphabet_{letter.lower()}",
                category="learn",
                title=f"Alphabet: Letter {letter.upper()}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_animals(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "wild animals")
            if not q or not a:
                continue
            body = f"Here is an animal question! {q} The answer is {a}!"
            tags = ["animals", "animal_quiz", "animal_stories", cat.lower(), a.lower()]
            items.append(ContentItem(
                id=f"edu_animal_{idx}",
                category="animal",
                title=f"Animal Fact: {a}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_basic_math(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "addition")
            if not q or not a:
                continue
            body = f"Let's practice some math! {q} The answer is {a}!"
            tags = ["math", "counting", "guessing_games", "numbers", cat.lower()]
            items.append(ContentItem(
                id=f"edu_math_{idx}",
                category="learn",
                title=f"Math: {cat.capitalize()}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_colors(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "colors")
            if not q or not a:
                continue
            body = f"Let's learn colors! {q} It's {a}!"
            tags = ["colors", "colors_shapes", "drawing", "art_stories", a.lower(), cat.lower()]
            items.append(ContentItem(
                id=f"edu_color_{idx}",
                category="learn",
                title=f"Colors: {a}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_fruits(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "fruit facts")
            if not q or not a:
                continue
            body = f"Here is a fruit question! {q} That's a {a}!"
            tags = ["fruits", "food", "healthy_foods", "guessing_games", a.lower(), cat.lower()]
            items.append(ContentItem(
                id=f"edu_fruit_{idx}",
                category="learn",
                title=f"Fruits: {a}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_general_knowledge(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "science")
            if not q or not a:
                continue
            body = f"Here is a fun fact! {q} The answer is {a}!"
            tags = ["general_knowledge", "science", "space", "guessing_games", "riddles", a.lower(), cat.lower()]
            items.append(ContentItem(
                id=f"edu_gk_{idx}",
                category="learn",
                title=f"Knowledge: {a}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_good_habits(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "hygiene")
            if not q or not a:
                continue
            body = f"Here is a healthy habit! {q} {a}!"
            tags = ["habits", "health", "hygiene", "good_habits", cat.lower()]
            items.append(ContentItem(
                id=f"edu_habit_{idx}",
                category="learn",
                title=f"Habit: {cat.capitalize()}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_healthy_foods(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "healthy")
            if not q or not a:
                continue
            body = f"Let's learn about eating healthy! {q} {a} is a wonderful choice!"
            tags = ["food", "health", "healthy_foods", "fruits", a.lower(), cat.lower()]
            items.append(ContentItem(
                id=f"edu_food_{idx}",
                category="learn",
                title=f"Healthy Food: {a}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_numbers_counting(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "counting")
            if not q or not a:
                continue
            body = f"Let's count! {q} The answer is {a}!"
            tags = ["counting", "numbers", "math", "counting_vehicles", cat.lower(), a.lower()]
            items.append(ContentItem(
                id=f"edu_number_{idx}",
                category="learn",
                title=f"Counting: {a}",
                body=body,
                tags=tags,
            ))
        return items

    def _load_shapes(self, path: Path) -> list["ContentItem"]:
        from .content_catalog import ContentItem
        items = []
        for idx, row in enumerate(self._read_rows(path), 1):
            q = row.get("question", "")
            a = row.get("answer", "")
            cat = row.get("category", "shapes")
            if not q or not a:
                continue
            body = f"Let's learn about shapes! {q} That's a {a}!"
            tags = ["shapes", "colors_shapes", "drawing", "art_stories", a.lower(), cat.lower()]
            items.append(ContentItem(
                id=f"edu_shape_{idx}",
                category="learn",
                title=f"Shape: {a}",
                body=body,
                tags=tags,
            ))
        return items
