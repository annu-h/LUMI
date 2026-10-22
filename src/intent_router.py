"""
LUMI — Intent Router and Shared Application Handlers

Routes classified intents to appropriate application handlers.
Voice and keypad inputs use the same handlers.

Keypad mapping:
    1 → STORY      5 → FAVORITES
    2 → LEARN      6 → TIME
    3 → MUSIC      7 → (future: ALARMS)
    4 → HOBBIES    8 → (future: PROGRESS)
    0 → HELLO      9 → (future: PROFILE)
    Backward → BACK
    Forward  → NEXT
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .intent_classifier import Intent, ClassificationResult
from .content_catalog import ContentCatalog, ContentItem
from .child_profile import ProfileService
from .rtc_service import RTCService

logger = logging.getLogger(__name__)


class KeypadMode(str, Enum):
    """Operational mode for the physical/virtual keypad."""
    SHORTCUT = "shortcut"  # Single-key triggers direct intent (1=Story, 2=Learn, etc.)
    NUMERIC = "numeric"    # Digits accumulate for math/quiz answers; * clears, # submits


# Keypad digit → Intent mapping (Shortcut Mode)
KEYPAD_MAP: dict[str, Intent] = {
    "0": Intent.HELLO,
    "1": Intent.STORY,
    "2": Intent.LEARN,
    "3": Intent.MUSIC,
    "4": Intent.HOBBIES,
    "5": Intent.FAVORITES,
    "6": Intent.TIME,
    "*": Intent.BACK,
    "#": Intent.NEXT,
    "BACKWARD": Intent.BACK,
    "FORWARD": Intent.NEXT,
}


@dataclass
class RoutingResult:
    """Output from the intent router."""
    intent: Intent
    response_text: str             # TTS-ready response text
    content_item: Optional[ContentItem] = None
    error: Optional[str] = None


class IntentRouter:
    """Routes intents (from voice or keypad) to response text.

    All handlers return a RoutingResult with TTS-ready response_text.
    Supports both SHORTCUT mode (1=Story, 2=Learn, etc.) and NUMERIC entry mode.
    """

    def __init__(self, catalog: ContentCatalog,
                 profile_service: ProfileService,
                 rtc: RTCService,
                 last_response: Optional[str] = None,
                 keypad_mode: KeypadMode = KeypadMode.SHORTCUT) -> None:
        self._catalog = catalog
        self._profile = profile_service
        self._rtc = rtc
        self._last_response: Optional[str] = last_response
        self._keypad_mode: KeypadMode = keypad_mode
        self._numeric_buffer: str = ""

    @property
    def keypad_mode(self) -> KeypadMode:
        """Return the current keypad mode."""
        return self._keypad_mode

    @keypad_mode.setter
    def keypad_mode(self, mode: KeypadMode) -> None:
        self.set_keypad_mode(mode)

    def set_keypad_mode(self, mode: KeypadMode) -> None:
        """Switch between SHORTCUT mode and NUMERIC entry mode."""
        self._keypad_mode = mode
        if mode == KeypadMode.SHORTCUT:
            self._numeric_buffer = ""

    def get_numeric_buffer(self) -> str:
        """Return the accumulated numeric string."""
        return self._numeric_buffer

    def clear_numeric_buffer(self) -> None:
        """Clear the accumulated numeric string."""
        self._numeric_buffer = ""

    def route(self, result: ClassificationResult) -> RoutingResult:
        """Route a ClassificationResult to a RoutingResult."""
        return self.route_intent(result.intent)

    def route_intent(self, intent: Intent) -> RoutingResult:
        """Route a bare Intent value (used by keypad and tests)."""
        profile = self._profile.get_profile()
        preferences = profile.content_preferences()
        name = profile.display_name

        handlers = {
            Intent.HELLO: self._handle_hello,
            Intent.STORY: self._handle_story,
            Intent.MUSIC: self._handle_music,
            Intent.LEARN: self._handle_learn,
            Intent.ANIMALS: self._handle_animals,
            Intent.HOBBIES: self._handle_hobbies,
            Intent.FAVORITES: self._handle_favorites,
            Intent.TIME: self._handle_time,
            Intent.REPEAT: self._handle_repeat,
            Intent.NEXT: self._handle_next,
            Intent.BACK: self._handle_back,
            Intent.STOP: self._handle_stop,
            Intent.HELP: self._handle_help,
            Intent.EXIT: self._handle_exit,
            Intent.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(intent, self._handle_unknown)
        result = handler(name=name, preferences=preferences)
        logger.debug("Router: %s → '%s'", intent.value, result.response_text[:60])
        return result

    def route_keypad(self, key: str, mode: Optional[KeypadMode] = None) -> RoutingResult:
        """Route a keypad key press.

        In SHORTCUT mode (default), keys route directly through the shared intent handlers.
        In NUMERIC mode, digits accumulate into the numeric buffer, '*' clears/backspaces,
        and '#' submits the accumulated number.
        """
        active_mode = mode if mode is not None else self._keypad_mode
        key_upper = key.strip().upper()

        if active_mode == KeypadMode.NUMERIC:
            if key_upper in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                self._numeric_buffer += key_upper
                return RoutingResult(
                    intent=Intent.UNKNOWN,
                    response_text=f"Entered {key_upper}. Current number: {self._numeric_buffer}.",
                )
            elif key_upper in ("*", "BACKWARD", "CLEAR", "BACK"):
                if self._numeric_buffer:
                    removed = self._numeric_buffer[-1]
                    self._numeric_buffer = self._numeric_buffer[:-1]
                    return RoutingResult(
                        intent=Intent.BACK,
                        response_text=f"Cleared {removed}. Current number: {self._numeric_buffer if self._numeric_buffer else 'empty'}.",
                    )
                return RoutingResult(
                    intent=Intent.BACK,
                    response_text="Number buffer is already empty.",
                )
            elif key_upper in ("#", "FORWARD", "ENTER", "SUBMIT"):
                submitted = self._numeric_buffer
                self._numeric_buffer = ""
                if submitted:
                    return RoutingResult(
                        intent=Intent.NEXT,
                        response_text=f"You entered the number {submitted}!",
                    )
                return RoutingResult(
                    intent=Intent.UNKNOWN,
                    response_text="No number entered.",
                )

        # SHORTCUT mode (default)
        intent = KEYPAD_MAP.get(key_upper, Intent.UNKNOWN)
        return self.route_intent(intent)

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_hello(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("greeting")
        text = item.body if item else f"Hi there, {name}! What would you like to do?"
        return RoutingResult(intent=Intent.HELLO, response_text=text,
                             content_item=item)

    def _handle_story(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("story", prefer_tags=preferences)
        if not item:
            return RoutingResult(
                intent=Intent.STORY,
                response_text="I don't have any stories right now. Try again later!",
            )
        self._last_response = item.body
        return RoutingResult(intent=Intent.STORY, response_text=item.body,
                             content_item=item)

    def _handle_music(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("song", prefer_tags=preferences)
        if not item:
            return RoutingResult(
                intent=Intent.MUSIC,
                response_text="I can't find a song right now. Maybe try learning something?",
            )
        self._last_response = item.body
        return RoutingResult(intent=Intent.MUSIC, response_text=item.body,
                             content_item=item)

    def _handle_learn(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("learn", prefer_tags=preferences)
        if not item:
            return RoutingResult(
                intent=Intent.LEARN,
                response_text="I'm not sure what to teach right now. Ask me about animals!",
            )
        self._last_response = item.body
        return RoutingResult(intent=Intent.LEARN, response_text=item.body,
                             content_item=item)

    def _handle_animals(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("animal", prefer_tags=preferences)
        if not item:
            return RoutingResult(
                intent=Intent.ANIMALS,
                response_text="Let me think of an animal fact... Animals are amazing!",
            )
        self._last_response = item.body
        return RoutingResult(intent=Intent.ANIMALS, response_text=item.body,
                             content_item=item)

    def _handle_hobbies(self, name: str, preferences: list) -> RoutingResult:
        text = (
            f"You love {', '.join(preferences[:2]) if preferences else 'lots of fun things'}! "
            "Would you like a story, a song, or something to learn today?"
        )
        self._last_response = text
        return RoutingResult(intent=Intent.HOBBIES, response_text=text)

    def _handle_favorites(self, name: str, preferences: list) -> RoutingResult:
        text = (
            f"Some of your favorites are "
            f"{', '.join(preferences[:3]) if preferences else 'stories and songs'}. "
            "Would you like one of those?"
        )
        self._last_response = text
        return RoutingResult(intent=Intent.FAVORITES, response_text=text)

    def _handle_time(self, name: str, preferences: list) -> RoutingResult:
        time_str = self._rtc.time_string()
        date_str = self._rtc.date_string()
        text = f"It is {time_str}. Today is {date_str}."
        self._last_response = text
        return RoutingResult(intent=Intent.TIME, response_text=text)

    def _handle_repeat(self, name: str, preferences: list) -> RoutingResult:
        if self._last_response:
            return RoutingResult(
                intent=Intent.REPEAT, response_text=self._last_response
            )
        return RoutingResult(
            intent=Intent.REPEAT,
            response_text="There's nothing to repeat yet. Try asking for a story!",
        )

    def _handle_next(self, name: str, preferences: list) -> RoutingResult:
        # In v1 NEXT re-triggers a story/song.  Future versions will track context.
        item = self._catalog.get_by_category("story", prefer_tags=preferences)
        if item:
            self._last_response = item.body
            return RoutingResult(intent=Intent.NEXT, response_text=item.body,
                                 content_item=item)
        return RoutingResult(
            intent=Intent.NEXT,
            response_text="There's nothing else to show. Try asking for a story!",
        )

    def _handle_back(self, name: str, preferences: list) -> RoutingResult:
        if self._last_response:
            return RoutingResult(
                intent=Intent.BACK, response_text=self._last_response
            )
        return RoutingResult(
            intent=Intent.BACK,
            response_text="There's nothing before this. Try asking for something new!",
        )

    def _handle_stop(self, name: str, preferences: list) -> RoutingResult:
        self._last_response = None
        return RoutingResult(
            intent=Intent.STOP, response_text="Okay, I'll stop. Let me know when you need me!"
        )

    def _handle_help(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("help")
        text = item.body if item else (
            "You can ask me for a story, a song, something to learn, "
            "or what time it is!"
        )
        return RoutingResult(intent=Intent.HELP, response_text=text, content_item=item)

    def _handle_exit(self, name: str, preferences: list) -> RoutingResult:
        return RoutingResult(
            intent=Intent.EXIT,
            response_text="Goodbye! See you next time!",
        )

    def _handle_unknown(self, name: str, preferences: list) -> RoutingResult:
        item = self._catalog.get_by_category("unknown")
        text = item.body if item else (
            "I didn't quite understand. Try saying: tell me a story, "
            "play music, or help."
        )
        return RoutingResult(intent=Intent.UNKNOWN, response_text=text,
                             content_item=item)
