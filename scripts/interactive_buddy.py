"""
LUMI — Interactive Learning Buddy Console

Allows testing LUMI's voice intent classifier, educational content catalog,
keypad buttons, and child profile personalization in real time.
"""

import sys
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService
from src.rtc_service import SystemRTC
from src.intent_classifier import classify_intent, Intent
from src.intent_router import IntentRouter, KEYPAD_MAP


def main():
    catalog = ContentCatalog()
    profile_service = ProfileService()
    profile = profile_service.get_profile()
    rtc = SystemRTC()
    router = IntentRouter(catalog=catalog, profile_service=profile_service, rtc=rtc)

    print("=" * 65)
    print("           LUMI -- AI VOICE LEARNING BUDDY (INTERACTIVE)")
    print("=" * 65)
    print(f"Child Profile: {profile.display_name} ({profile.age_group})")
    print(f"Hobbies: {', '.join(profile.hobbies)}")
    print(f"Educational Datasets Loaded: {catalog.educational_count()} items across 10 CSVs")
    print("-" * 65)
    print("Input Modes:")
    print("  - Type any voice phrase (e.g. 'teach me', 'tell me about animals', 'tell a story')")
    print("  - Enter keypad digit (0=Hello, 1=Story, 2=Learn, 3=Music, 4=Hobbies, 5=Favorites, 6=Time)")
    print("  - Type 'catalog' to inspect available categories and counts")
    print("  - Type 'exit' or 'quit' to leave")
    print("=" * 65)

    while True:
        try:
            user_input = input("\n[LUMI Voice/Keypad] > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Lumi: Goodbye! Have a wonderful day of learning!")
            break

        if user_input.lower() == "catalog":
            print("\n--- Content Catalog Status ---")
            print(f"Total Categories: {catalog.categories()}")
            print(f"Total Educational Items: {catalog.educational_count()}")
            print(f"Sample Alphabet Lesson: {catalog.get_alphabet_lesson('A').body}")
            sample_shapes = catalog.get_by_tag('shapes')
            if sample_shapes:
                print(f"Sample Shape Item: {sample_shapes[0].body}")
            continue

        # Check if input is a keypad key
        if user_input.upper() in KEYPAD_MAP or user_input in ("0", "1", "2", "3", "4", "5", "6"):
            key = user_input.upper()
            result = router.route_keypad(key)
            print(f"[Keypad Press: '{key}'] -> Intent: {result.intent.value}")
            print(f"Lumi: \"{result.response_text}\"")
            if result.content_item:
                print(f"  (Source: {result.content_item.title} | Tags: {', '.join(result.content_item.tags[:4])})")
            continue

        # Voice phrase intent classification
        classification = classify_intent(user_input)
        result = router.route(classification)

        print(f"[Voice Recognized] -> Intent: {classification.intent.value} (Confidence: {classification.confidence:.2f})")
        print(f"Lumi: \"{result.response_text}\"")
        if result.content_item:
            print(f"  (Content: {result.content_item.title} | ID: {result.content_item.id})")


if __name__ == "__main__":
    main()
