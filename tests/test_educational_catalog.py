"""
LUMI — Tests for Educational CSV Datasets and Catalog Integration

Validates:
- Presence of all 10 educational CSV files in data/educational/
- Proper parsing of UTF-8 with BOM (utf-8-sig)
- Row counts, column headers, and data integrity
- EducationalContentLoader functionality
- ContentCatalog integration with educational items
- Voice and keypad routing with educational content
"""

import csv
import hashlib
from pathlib import Path
import pytest

from src.content_catalog import ContentCatalog, ContentItem
from src.educational_loader import EducationalContentLoader, DEFAULT_EDUCATIONAL_DIR
from src.intent_router import IntentRouter, Intent
from src.child_profile import ProfileService
from src.rtc_service import MockRTC


EXPECTED_FILES = {
    "alphabets.csv": 26,
    "animals.csv": 10,
    "basic_math.csv": 8,
    "colors.csv": 8,
    "fruits.csv": 10,
    "general_knowledge.csv": 8,
    "good_habits.csv": 8,
    "healthy_foods.csv": 6,
    "numbers_counting.csv": 8,
    "shapes.csv": 7,
}


class TestEducationalFilesOnDisk:
    """Validate physical CSV files in data/educational/."""

    def test_directory_exists(self):
        assert DEFAULT_EDUCATIONAL_DIR.exists()
        assert DEFAULT_EDUCATIONAL_DIR.is_dir()

    @pytest.mark.parametrize("filename,expected_rows", EXPECTED_FILES.items())
    def test_csv_file_exists_and_row_count(self, filename, expected_rows):
        file_path = DEFAULT_EDUCATIONAL_DIR / filename
        assert file_path.exists(), f"Missing CSV: {filename}"
        assert file_path.stat().st_size > 0

        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == expected_rows, (
                f"{filename} expected {expected_rows} rows, got {len(reader)}"
            )

    def test_alphabets_csv_headers(self):
        file_path = DEFAULT_EDUCATIONAL_DIR / "alphabets.csv"
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
            assert "letter" in fieldnames
            assert "example_word" in fieldnames
            assert "lesson" in fieldnames

    @pytest.mark.parametrize("filename", [
        "animals.csv", "basic_math.csv", "colors.csv", "fruits.csv",
        "general_knowledge.csv", "good_habits.csv", "healthy_foods.csv",
        "numbers_counting.csv", "shapes.csv"
    ])
    def test_qa_csv_headers(self, filename):
        file_path = DEFAULT_EDUCATIONAL_DIR / filename
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
            assert "question" in fieldnames
            assert "answer" in fieldnames
            assert "category" in fieldnames


class TestEducationalLoader:
    """Validate EducationalContentLoader parsing."""

    def test_loader_availability(self):
        loader = EducationalContentLoader()
        assert loader.is_available()
        csvs = loader.list_csv_files()
        assert len(csvs) == 10
        assert "alphabets.csv" in csvs
        assert "shapes.csv" in csvs

    def test_load_all_items(self):
        loader = EducationalContentLoader()
        items = loader.load_all()
        # Sum of all rows in 10 CSVs: 26 + 10 + 8 + 8 + 10 + 8 + 8 + 6 + 8 + 7 = 99
        assert len(items) == 99

        # Verify all items are ContentItem instances with non-empty text
        for item in items:
            assert isinstance(item, ContentItem)
            assert item.id.startswith("edu_")
            assert len(item.title) > 0
            assert len(item.body) > 0
            assert len(item.tags) > 0

    def test_alphabets_loaded_correctly(self):
        loader = EducationalContentLoader()
        items = loader.load_all()
        alphabet_items = [i for i in items if i.id.startswith("edu_alphabet_")]
        assert len(alphabet_items) == 26
        
        # Check 'a'
        item_a = next((i for i in alphabet_items if i.id == "edu_alphabet_a"), None)
        assert item_a is not None
        assert "Apple" in item_a.body or "apple" in item_a.body.lower()
        assert "a" in item_a.tags
        assert "apple" in item_a.tags

    def test_animals_loaded_correctly(self):
        loader = EducationalContentLoader()
        items = loader.load_all()
        animal_items = [i for i in items if i.category == "animal" and i.id.startswith("edu_animal_")]
        assert len(animal_items) == 10
        assert any("Lion" in i.body for i in animal_items)

    def test_loader_missing_dir(self, tmp_path):
        loader = EducationalContentLoader(data_dir=tmp_path / "nonexistent")
        assert not loader.is_available()
        assert loader.load_all() == []


class TestContentCatalogIntegration:
    """Validate ContentCatalog integration with educational CSVs."""

    def test_catalog_loads_educational_content(self):
        catalog = ContentCatalog()
        assert catalog.educational_count() == 99

    def test_catalog_disable_educational(self):
        catalog = ContentCatalog(load_educational=False)
        assert catalog.educational_count() == 0

    def test_get_alphabet_lesson(self):
        catalog = ContentCatalog()
        lesson_b = catalog.get_alphabet_lesson("B")
        assert lesson_b is not None
        assert "B" in lesson_b.title
        assert "Ball" in lesson_b.body or "ball" in lesson_b.body.lower()

    def test_get_by_tag(self):
        catalog = ContentCatalog()
        shapes = catalog.get_by_tag("shapes")
        assert len(shapes) >= 7

        colors = catalog.get_by_tag("colors")
        assert len(colors) >= 8

        math_items = catalog.get_by_tag("math")
        assert len(math_items) >= 8

    def test_get_by_category_with_hobbies(self):
        catalog = ContentCatalog()
        # Profile preferences including math and shapes
        item = catalog.get_by_category("learn", prefer_tags=["shapes", "colors_shapes"])
        assert item is not None
        assert item.category == "learn"
        assert any(t in ["shapes", "colors_shapes"] for t in item.tags)


class TestIntentRouterIntegration:
    """Validate IntentRouter delivers educational content via voice/keypad."""

    def test_learn_handler_returns_content(self):
        catalog = ContentCatalog()
        profile_service = ProfileService()
        rtc = MockRTC()
        router = IntentRouter(catalog=catalog, profile_service=profile_service, rtc=rtc)

        # Voice route for Intent.LEARN
        result = router.route_intent(Intent.LEARN)
        assert result.intent == Intent.LEARN
        assert result.content_item is not None
        assert len(result.response_text) > 0

    def test_animals_handler_returns_content(self):
        catalog = ContentCatalog()
        profile_service = ProfileService()
        rtc = MockRTC()
        router = IntentRouter(catalog=catalog, profile_service=profile_service, rtc=rtc)

        # Voice route for Intent.ANIMALS
        result = router.route_intent(Intent.ANIMALS)
        assert result.intent == Intent.ANIMALS
        assert result.content_item is not None
        assert len(result.response_text) > 0

    def test_keypad_2_learn_routing(self):
        catalog = ContentCatalog()
        profile_service = ProfileService()
        rtc = MockRTC()
        router = IntentRouter(catalog=catalog, profile_service=profile_service, rtc=rtc)

        # Keypad '2' maps to LEARN
        result = router.route_keypad("2")
        assert result.intent == Intent.LEARN
        assert result.content_item is not None
