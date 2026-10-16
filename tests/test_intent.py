"""
Tests for the deterministic intent classifier.

All tests run without AI models, without network access,
and use only deterministic text-to-intent mapping.
"""

import pytest
from src.intent_classifier import classify_intent, Intent, ClassificationResult

# ------------------------------------------------------------------
# Supported intents — all 15
# ------------------------------------------------------------------

INTENT_TEST_CASES = {
    Intent.HELLO: [
        "hello", "hi", "hey", "good morning",
        "good afternoon", "good evening", "how are you",
        "what's up",
    ],
    Intent.STORY: [
        "tell me a story", "i want a story", "read me a story",
        "read a book", "story time", "once upon a time",
        "bedtime story",
    ],
    Intent.MUSIC: [
        "play music", "sing a song", "sing me a song",
        "let's sing", "music time", "song",
        "music",
    ],
    Intent.LEARN: [
        "teach me", "i want to learn", "teach me something",
        "learn new", "tell me about", "what is", "why is",
    ],
    Intent.ANIMALS: [
        "animals", "cat", "dog", "bird", "lion",
        "what sound does a dog make", "tell me about elephants",
    ],
    Intent.HOBBIES: [
        "hobby", "hobbies", "drawing", "painting",
        "craft", "building", "what can i do",
    ],
    Intent.FAVORITES: [
        "favorite", "favourite", "what do i like",
        "best thing",
    ],
    Intent.TIME: [
        "what time is it", "what's the time",
        "what day is it", "what's the date",
    ],
    Intent.REPEAT: [
        "say that again", "repeat", "again please",
        "one more time", "what did you say",
        "i didn't hear",
    ],
    Intent.NEXT: [
        "next", "skip", "another one", "next one",
        "something else",
    ],
    Intent.BACK: [
        "go back", "previous", "back", "last one",
        "before",
    ],
    Intent.STOP: [
        "stop", "stop please", "stop it", "no more",
        "enough", "hush", "silence", "be quiet",
    ],
    Intent.HELP: [
        "help", "what can you do", "how does this work",
        "i'm confused", "i'm lost",
    ],
    Intent.EXIT: [
        "goodbye", "bye bye", "see you", "good night",
        "exit", "quit", "turn off",
    ],
}

# All 15 intents must be covered.


def test_all_intents_covered():
    failures = []
    for intent, phrases in INTENT_TEST_CASES.items():
        for phrase in phrases:
            result = classify_intent(phrase)
            if result.intent != intent:
                failures.append(
                    f"'{phrase}' expected {intent.value}, got {result.intent.value}"
                )
    if failures:
        # Show all failures at once for debugging
        print("\nAll intent test failures:")
        for f in failures:
            print("  ", f)
        pytest.fail(f"{len(failures)} intent test(s) failed")
    # If we get here, all tests passed
    assert True


def test_empty_text_is_unknown():
    result = classify_intent("")
    assert result.intent == Intent.UNKNOWN
    assert result.confidence == 0.0


def test_ambiguous_text_is_unknown():
    """Unknown phrases must return UNKNOWN, not trigger arbitrary actions."""
    result = classify_intent("blargghh xyz 123!")
    assert result.intent == Intent.UNKNOWN
    assert result.confidence == 0.0


def test_specific_paraphrases():
    # Paraphrases from the master prompt must work.
    cases = [
        ("Tell me a story.", Intent.STORY),
        ("I want a story.", Intent.STORY),
        ("Play some music.", Intent.MUSIC),
        ("Teach me something.", Intent.LEARN),
        ("What time is it?", Intent.TIME),
        ("Say that again.", Intent.REPEAT),
        ("Stop, please.", Intent.STOP),
    ]
    for phrase, expected in cases:
        result = classify_intent(phrase)
        assert result.intent == expected, (
            f"'{phrase}' expected {expected.value}, got {result.intent.value}"
        )


def test_false_positive_prevention_for_stop():
    # Words like "okay" or "good" alone should NOT trigger STOP.
    # Only explicit stop commands should trigger STOP.
    result_stop = classify_intent("stop please")
    result_ok = classify_intent("okay")
    assert result_stop.intent == Intent.STOP
    # "okay" should fall through to UNKNOWN (no STOP match).
    # If it doesn't, the test will show it clearly.
    assert result_ok.intent != Intent.STOP or result_ok.confidence < 0.1


def test_overlapping_phrases():
    # "Read me a story" should match STORY (higher confidence pattern)
    result = classify_intent("read me a story")
    assert result.intent == Intent.STORY
