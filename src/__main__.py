"""
LUMI package __main__ module.

Allows running the pipeline via:
    python -m src
    python -m src --run-once
"""

from .main import run_cli

if __name__ == "__main__":
    import sys

    if "--run-once" in sys.argv:
        run_cli()
    else:
        print("LUMI - Voice Processing System")
        print("Usage:")
        print("  python -m src --run-once   Run a single mocked interaction")
        print("  python -m src               Show this help")
        print("\nEnsure you have a mock audio file 'audio/test.wav' for FileAudioSource.")