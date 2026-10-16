"""
LUMI — Child Profile Service

Provides mock child-profile data for development.
No real personal data is used.

Profile fields:
  - display_name: Friendly name shown in responses.
  - age_group: One of "toddler" (0–2), "preschool" (3–4), "early" (5–6).
  - hobbies: List of interest tags driving content selection.
  - favorite_stories: List of story IDs.
  - favorite_songs: List of song IDs.
  - learning_progress: Dict of topic → level.

Personalization rules:
  ANIMALS  → animal stories and quizzes.
  MUSIC    → songs and rhythm activities.
  DRAWING  → colors and shapes.
  VEHICLES → themed counting.
  PUZZLES  → guessing games.
"""

from dataclasses import dataclass, field
from typing import Optional


HOBBY_CONTENT_MAP: dict[str, list[str]] = {
    "animals": ["animal_stories", "animal_quiz"],
    "music": ["songs", "rhythm_activities"],
    "drawing": ["colors_shapes", "art_stories"],
    "vehicles": ["counting_vehicles", "vehicle_stories"],
    "puzzles": ["guessing_games", "riddles"],
}


@dataclass
class ChildProfile:
    display_name: str = "Friend"
    age_group: str = "preschool"          # "toddler" | "preschool" | "early"
    hobbies: list[str] = field(default_factory=list)
    favorite_stories: list[str] = field(default_factory=list)
    favorite_songs: list[str] = field(default_factory=list)
    learning_progress: dict[str, int] = field(default_factory=dict)

    def content_preferences(self) -> list[str]:
        """Return a ranked list of content category IDs based on hobbies."""
        prefs = []
        for hobby in self.hobbies:
            prefs.extend(HOBBY_CONTENT_MAP.get(hobby.lower(), []))
        return prefs

    def preferred_content_for_intent(self, intent_name: str) -> Optional[str]:
        """Return the most relevant content category for a given intent,
        personalized by hobbies.  Returns None if no match.
        """
        prefs = self.content_preferences()
        intent_lower = intent_name.lower()

        for category in prefs:
            if intent_lower in category:
                return category

        # Fallback: map intent directly to a content category.
        fallback: dict[str, str] = {
            "animals": "animal_stories",
            "story": "stories",
            "music": "songs",
            "learn": "learning",
            "hobbies": "hobbies",
            "favorites": "favorites",
        }
        return fallback.get(intent_lower)


class ProfileService:
    """Loads and provides access to a ChildProfile.

    In development, returns a hardcoded mock profile.  A future version
    will read from local encrypted storage.
    """

    # Development mock profile — clearly labeled, no real personal data.
    MOCK_PROFILE = ChildProfile(
        display_name="Alex",
        age_group="preschool",
        hobbies=["animals", "drawing", "puzzles"],
        favorite_stories=["the_brave_bunny", "space_adventure"],
        favorite_songs=["twinkle_twinkle", "wheels_on_the_bus"],
        learning_progress={"colors": 2, "counting": 1, "animals": 3},
    )

    def __init__(self, use_mock: bool = True) -> None:
        self._use_mock = use_mock
        self._profile: Optional[ChildProfile] = None

    def get_profile(self) -> ChildProfile:
        if self._use_mock:
            return self.MOCK_PROFILE
        if self._profile is None:
            raise NotImplementedError("Production profile storage not implemented.")
        return self._profile
