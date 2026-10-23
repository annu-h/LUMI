"""
LUMI — Temporary Voice Modules Testing Lab Server

Local-only, zero-external-dependency HTTP server for testing LUMI voice modules:
- Silero VAD (and MockVAD fallback)
- openWakeWord (and MockWakeWordDetector fallback)
- Faster-Whisper STT (Real inference with locally cached base.en)
- Piper TTS (and MockTTS fallback)
- End-to-End Voice Pipeline Integration

Runs exclusively on 127.0.0.1. No cloud services, external network calls, or hardware required.
"""

import hashlib
import http.server
import importlib.util
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

# Ensure LUMI repository root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Import LUMI modules
from src.config import LumiConfig, PROJECT_ROOT
from src.vad import MockVAD, SileroVAD, VADResult, _expand_mask
from src.wake_word import MockWakeWordDetector, OpenWakeWordDetector, WakeWordEvent
from src.stt import MockSTT, FasterWhisperSTT, TranscriptionResult
from src.tts import MockTTS, PiperTTS, TTSResult, _write_wav, _read_wav_as_int16
from src.audio_source import MockAudioSource, FileAudioSource, _load_wav_as_int16
from src.text_normalizer import normalize_text
from src.intent_classifier import classify_intent, Intent
from src.intent_router import IntentRouter
from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService
from src.rtc_service import MockRTC
from src.playback import MockAudioPlayer
from src.jibo_eval import compute_wer, normalize_for_wer

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [VoiceLab] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VoiceLab")

TEMP_DIR = SCRIPT_DIR / "temp_outputs"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Global model cache to avoid re-initializing models across requests
_STT_CACHE: Dict[str, FasterWhisperSTT] = {}
_ROUTER_CACHE: Optional[Tuple[IntentRouter, ContentCatalog]] = None


def get_cached_router() -> IntentRouter:
    global _ROUTER_CACHE
    if _ROUTER_CACHE is None:
        catalog = ContentCatalog()
        profile_svc = ProfileService()
        rtc = MockRTC()
        router = IntentRouter(catalog=catalog, profile_service=profile_svc, rtc=rtc)
        _ROUTER_CACHE = (router, catalog)
    return _ROUTER_CACHE[0]


def get_lumi_conversational_response(
    query: str,
    catalog: ContentCatalog,
    router: IntentRouter,
    classification: Any,
) -> Tuple[str, str]:
    """Smart lookup in educational catalog and LUMI IntentRouter for conversational requests."""
    norm = normalize_text(query).lower()

    # 1. Letter inquiry: e.g. "what is the letter a", "letter b", "tell me about letter c"
    m_letter = re.search(r"\b(?:letter|the letter)\s+([a-z])\b", norm) or re.search(r"\bwhat\s+is\s+([a-z])\b", norm)
    if m_letter:
        letter = m_letter.group(1).lower()
        item = catalog.get_alphabet_lesson(letter)
        if item:
            return item.body, f"Alphabet ({letter.upper()})"

    # 2. Animals inquiry: e.g. "tell me about elephants", "elephants", "lion", "giraffe"
    animal_keywords = [
        "elephant", "lion", "giraffe", "kangaroo", "dog", "cat", "zebra", "cow",
        "parrot", "fish", "tiger", "bear", "rabbit", "monkey", "duck", "frog",
        "turtle", "snake", "whale", "dolphin", "penguin", "owl", "butterfly", "bee"
    ]
    for animal in animal_keywords:
        if animal in norm:
            matched = [i for i in catalog._items if animal in i.body.lower() and i.category == "animal"]
            if not matched:
                matched = [i for i in catalog._items if animal in i.body.lower() or animal in [t.lower() for t in i.tags]]
            if matched:
                return matched[0].body, f"Animal Fact ({animal.capitalize()})"

    # 3. Colors inquiry: e.g. "what color is the sky", "what color is a banana"
    if "color" in norm or "sky" in norm:
        if "sky" in norm:
            matched = [i for i in catalog._items if "sky" in i.body.lower() and ("blue" in i.body.lower() or "colors" in i.tags)]
            if matched:
                return matched[0].body, "Colors (Sky / Blue)"
        elif "banana" in norm:
            matched = [i for i in catalog._items if "banana" in i.body.lower()]
            if matched:
                return matched[0].body, "Colors (Banana / Yellow)"
        elif "leaves" in norm or "leaf" in norm:
            matched = [i for i in catalog._items if "leaves" in i.body.lower()]
            if matched:
                return matched[0].body, "Colors (Leaves / Green)"
        else:
            matched = [i for i in catalog._items if "color" in i.category or "colors" in i.tags]
            if matched:
                return matched[0].body, "Colors"

    # 4. Counting / numbers inquiry: e.g. "can you count from one to ten", "count with me"
    if "count" in norm or "counting" in norm:
        matched = [i for i in catalog._items if i.id == "learn_counting_5"]
        if matched:
            return matched[0].body, "Numbers & Counting"

    # 5. Basic Math: e.g. "what is 2 plus 2", "5 minus 3"
    m_math = re.search(r"(\d+)\s*(plus|\+|\-|minus)\s*(\d+)", norm)
    if m_math:
        for item in catalog._items:
            if m_math.group(1) in item.body and m_math.group(3) in item.body:
                return item.body, "Basic Math"

    # 6. Fall back to LUMI's official IntentRouter
    routing_res = router.route(classification)
    return routing_res.response_text, classification.intent.value


def check_hf_cache(model_name: str) -> bool:
    """Check if model is present in Hugging Face local cache."""
    hf_hub = Path.home() / ".cache" / "huggingface" / "hub"
    if not hf_hub.exists():
        return False
    # Check for direct repo folder matching model name
    pattern = f"*{model_name}*"
    matches = list(hf_hub.glob(pattern))
    return len(matches) > 0


def is_valid_piper_model(model_path: Path, cfg_path: Path) -> bool:
    """Verify that the Piper model and JSON config exist and are genuine binary/json assets, not HTML error pages."""
    if not (model_path.exists() and cfg_path.exists()):
        return False
    try:
        if cfg_path.stat().st_size < 50 or model_path.stat().st_size < 1000:
            return False
        with open(cfg_path, "r", encoding="utf-8") as f:
            c = json.load(f)
            if not isinstance(c, dict) or ("audio" not in c and "num_symbols" not in c and "espeak" not in c):
                return False
        header = model_path.read_bytes()[:64].lower()
        if b"<!doctype" in header or b"<html" in header:
            return False
        return True
    except Exception:
        return False


def _wake_phrase_greeting(phrase: str) -> str:
    """Return an age-appropriate educational greeting prompt when a child says only a wake phrase."""
    p = phrase.lower()
    if "morning" in p:
        return "Good morning! What would you like to learn today?"
    elif "play" in p:
        return "I'm ready to play! What game or story would you like?"
    elif "wake" in p:
        return "I'm awake and ready! What would you like to explore?"
    elif "there" in p:
        return "I'm right here! How can I help you today?"
    elif "lumi!" in p or p == "lumi":
        return "I'm listening! What can I help you with?"
    return "Hello there! What would you like to learn today?"


def _extract_text_wake_word(text: str) -> Tuple[bool, bool, str, str]:
    """Check if typed text starts with or contains any of the 8 LUMI wake phrases or fallback.

    Returns:
        (is_detected, is_genuine_lumi, matched_phrase, remaining_command)
    """
    clean_text = text.strip()
    lower = clean_text.lower()

    # The 8 authoritative LUMI phrases (ordered specific -> general)
    phrase_patterns = [
        ("Good morning, LUMI", r"^good\s+morning[\s,]+lumi[\s,!:?-]*(.*)$"),
        ("Wake up, LUMI", r"^wake\s+up[\s,]+lumi[\s,!:?-]*(.*)$"),
        ("Let's play, LUMI", r"^let(?:'s|\s+us|\s*s)\s+play[\s,]+lumi[\s,!:?-]*(.*)$"),
        ("Are you there, LUMI?", r"^are\s+you\s+there[\s,]+lumi[\s,!:?-]*(.*)$"),
        ("Hello LUMI", r"^hello\s+lumi[\s,!:?-]*(.*)$"),
        ("Hi LUMI", r"^hi\s+lumi[\s,!:?-]*(.*)$"),
        ("Hey LUMI", r"^hey\s+lumi[\s,!:?-]*(.*)$"),
        ("LUMI!", r"^lumi[\s,!:?-]+(.*)$|^lumi$"),
    ]

    for phrase_name, pat in phrase_patterns:
        m = re.match(pat, lower, re.IGNORECASE)
        if m:
            remaining = clean_text[m.start(1):].strip() if m.lastindex and m.group(1) else ""
            remaining = re.sub(r"^[\s,!:?-]+", "", remaining).strip()
            return True, True, phrase_name, remaining

    # Also check generic variations: e.g. "lumi ..."
    m_generic = re.match(r"^(?:hey\s+|hi\s+|hello\s+)?lumi[\s,!:?-]*(.*)$", lower, re.IGNORECASE)
    if m_generic:
        remaining = clean_text[m_generic.start(1):].strip() if m_generic.lastindex and m_generic.group(1) else ""
        remaining = re.sub(r"^[\s,!:?-]+", "", remaining).strip()
        return True, True, "Hey LUMI", remaining

    # Fallback model: hey_jarvis
    jarvis_patterns = [
        r"^(?:hey\s+|hi\s+|hello\s+)?jarvis[\s,!:?-]+(.*)$",
        r"^(?:hey\s+|hi\s+|hello\s+)?jarvis$",
    ]
    for pat in jarvis_patterns:
        m = re.match(pat, lower, re.IGNORECASE)
        if m:
            remaining = clean_text[m.start(1):].strip() if m.lastindex and m.group(1) else ""
            remaining = re.sub(r"^[\s,!:?-]+", "", remaining).strip()
            return True, False, "hey_jarvis", remaining

    return False, False, "", clean_text


def get_available_sample_audios() -> list:
    """Find available sample WAV files from JIBO Kids dataset."""
    jibo_dir = REPO_ROOT / "datasets" / "Jibo_Kids" / "data" / "letters_digits"
    samples = []
    if jibo_dir.exists():
        wav_files = sorted(jibo_dir.rglob("*.wav"))[:15]
        for wav in wav_files:
            txt = wav.with_suffix(".txt")
            ref_snippet = ""
            if txt.exists():
                try:
                    lines = [
                        line.split("\t")[2].strip()
                        for line in txt.read_text(encoding="utf-8").splitlines()
                        if len(line.split("\t")) >= 3
                    ]
                    ref_snippet = " ".join(lines[:8])
                except Exception:
                    ref_snippet = ""
            rel_path = wav.relative_to(REPO_ROOT).as_posix()
            samples.append({
                "id": wav.stem,
                "name": f"JIBO Child Speech ({wav.name})",
                "path": rel_path,
                "ref_text": ref_snippet,
                "category": "JIBO Kids Corpus",
            })
    return samples


def load_audio_from_request(data: dict) -> Tuple[np.ndarray, int, str]:
    """Resolve and load audio array, sample rate, and description from request data."""
    source_type = data.get("source_type", "synthetic")
    sample_rate = 16000

    if source_type == "synthetic":
        synth_type = data.get("synthetic_type", "tone")
        duration_s = float(data.get("synthetic_duration", 1.0))
        if synth_type == "silence":
            num_samples = int(sample_rate * duration_s)
            audio = np.zeros(num_samples, dtype=np.int16)
            desc = f"Synthetic Silence ({duration_s:.1f}s)"
        else:  # Tone (440Hz sine wave)
            t = np.linspace(0.0, duration_s, int(sample_rate * duration_s), endpoint=False)
            audio = (10000 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.int16)
            desc = f"Synthetic 440Hz Sine Tone ({duration_s:.1f}s)"
        return audio, sample_rate, desc

    elif source_type in ("sample", "upload"):
        rel_path = data.get("sample_path", "").strip()
        if not rel_path:
            raise ValueError("No audio file path specified")
        
        # Path traversal prevention
        abs_path = (REPO_ROOT / rel_path).resolve()
        valid_roots = [
            (REPO_ROOT / "datasets").resolve(),
            TEMP_DIR.resolve(),
        ]
        if not any(abs_path.is_relative_to(r) for r in valid_roots):
            raise PermissionError("Access to the specified audio file path is denied.")
        
        if not abs_path.exists():
            raise FileNotFoundError(f"Audio file not found: {rel_path}")
        
        audio = _load_wav_as_int16(abs_path)
        orig_dur = len(audio) / sample_rate
        max_duration = data.get("max_duration_s")
        if max_duration is not None and float(max_duration) > 0:
            limit_samples = int(float(max_duration) * sample_rate)
            if len(audio) > limit_samples:
                audio = audio[:limit_samples]
                desc = f"File: {abs_path.name} (first {float(max_duration):.1f}s of {orig_dur:.1f}s)"
            else:
                desc = f"File: {abs_path.name} ({orig_dur:.2f}s)"
        else:
            desc = f"File: {abs_path.name} ({orig_dur:.2f}s)"
        return audio, sample_rate, desc

    raise ValueError(f"Unknown source_type: {source_type}")


class VoiceLabRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the Voice Lab developer interface."""

    def log_message(self, format, *args):
        # Override standard log to use our logger
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File Not Found")
            return
        file_size = file_path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw_body = self.rfile.read(content_length)
        return json.loads(raw_body.decode("utf-8"))

    # -----------------------------------------------------------------------
    # GET Handlers
    # -----------------------------------------------------------------------

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/index.html"):
            self._send_file(SCRIPT_DIR / "index.html", "text/html; charset=utf-8")
        elif path in ("/dev", "/dev.html"):
            self._send_file(SCRIPT_DIR / "dev.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self._send_file(SCRIPT_DIR / "style.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_file(SCRIPT_DIR / "app.js", "application/javascript; charset=utf-8")
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/audit":
            self._handle_audit()
        elif path == "/api/audio":
            self._handle_audio_stream(parsed_url.query)
        elif path == "/api/synthetic/preview":
            self._handle_synthetic_preview(parsed_url.query)
        elif path == "/api/educational/catalog":
            self._handle_educational_catalog()
        elif path == "/api/educational/quiz":
            self._handle_educational_quiz()
        elif path == "/api/educational/stories":
            self._handle_educational_stories()
        elif path == "/api/wake_word/phrases":
            self._handle_wake_word_phrases_get()
        else:
            self.send_error(404, "Not Found")

    def _handle_audit(self) -> None:
        """Run safe, local-only model & dependency audit."""
        try:
            from tools.voice_lab.audit_models import run_full_audit
            data = run_full_audit()
            self._send_json({"status": "SUCCESS", "audit": data})
        except Exception as exc:
            logger.exception("Audit failed: %s", exc)
            self._send_json({"status": "FAILED", "error": str(exc)}, status=500)

    def _handle_status(self) -> None:
        cfg = LumiConfig.load()

        # Dependencies audit
        def is_module_installed(name: str) -> bool:
            import importlib.util
            return importlib.util.find_spec(name) is not None

        faster_whisper_installed = is_module_installed("faster_whisper")
        torch_installed = is_module_installed("torch")
        silero_vad_installed = is_module_installed("silero_vad")
        openwakeword_installed = is_module_installed("openwakeword")
        piper_installed = is_module_installed("piper")

        # Models audit
        base_en_cached = check_hf_cache("faster-whisper-base.en")
        tiny_en_cached = check_hf_cache("faster-whisper-tiny.en")
        large_v3_turbo_cached = check_hf_cache("faster-whisper-large-v3-turbo")

        ww_model_path = cfg.wake_word.resolve_model_path()
        ww_model_exists = ww_model_path.exists()

        tts_model_path = PROJECT_ROOT / cfg.tts.model_path
        tts_cfg_path = PROJECT_ROOT / cfg.tts.config_path
        tts_model_exists = is_valid_piper_model(tts_model_path, tts_cfg_path)
        tts_cfg_exists = tts_model_exists

        data = {
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
            "config": {
                "vad_threshold": cfg.vad.threshold,
                "vad_min_silence_ms": cfg.vad.min_silence_duration_ms,
                "wake_word_threshold": cfg.wake_word.score_threshold,
                "wake_word_cooldown_ms": cfg.wake_word.cooldown_ms,
                "stt_model": cfg.stt.model,
                "stt_device": cfg.stt.device,
                "stt_compute_type": cfg.stt.compute_type,
                "tts_length_scale": cfg.tts.length_scale,
            },
            "dependencies": {
                "faster_whisper": faster_whisper_installed,
                "torch": torch_installed,
                "silero_vad": silero_vad_installed,
                "openwakeword": openwakeword_installed,
                "piper_tts": piper_installed,
            },
            "models": {
                "stt_base_en": {
                    "available": base_en_cached,
                    "location": "Hugging Face Cache (~/.cache/huggingface/hub)",
                },
                "stt_tiny_en": {
                    "available": tiny_en_cached,
                    "location": "Hugging Face Cache",
                },
                "stt_large_v3_turbo": {
                    "available": large_v3_turbo_cached,
                    "location": "Hugging Face Cache",
                },
                "wake_word": {
                    "model_path": str(ww_model_path.relative_to(REPO_ROOT) if ww_model_path.is_relative_to(REPO_ROOT) else ww_model_path),
                    "available": ww_model_exists,
                    "is_fallback": not ww_model_exists and openwakeword_installed,
                    "is_genuine_lumi": ww_model_exists,
                    "fallback_model": "hey_jarvis" if openwakeword_installed else "none",
                    "status_description": "Genuine Hey LUMI Model" if ww_model_exists else "Fallback: hey_jarvis (Development Testing Only — Hey LUMI Model Absent)",
                },
                "piper_tts": {
                    "model_path": str(tts_model_path.relative_to(REPO_ROOT) if tts_model_path.is_relative_to(REPO_ROOT) else tts_model_path),
                    "model_available": tts_model_exists,
                    "config_available": tts_cfg_exists,
                },
            },
            "samples": get_available_sample_audios(),
        }

        try:
            from src.wake_word import MultiPhraseWakeWordDetector
            mp_detector = MultiPhraseWakeWordDetector()
            data["wake_word_phrases"] = mp_detector.get_phrase_status_matrix()
        except Exception as exc:
            logger.debug("Could not inspect wake word phrases for status: %s", exc)
            data["wake_word_phrases"] = []

        self._send_json(data)

    def _handle_wake_word_phrases_get(self) -> None:
        """Return authoritative status matrix and configuration for all 8 wake phrases."""
        try:
            cfg = LumiConfig.load()
            from src.wake_word import make_wake_word_detector, MultiPhraseWakeWordDetector
            detector = make_wake_word_detector(cfg)

            if isinstance(detector, MultiPhraseWakeWordDetector):
                matrix = detector.get_phrase_status_matrix()
                is_fallback = detector.is_fallback
                active_model = detector.model_name
            else:
                from src.wake_word import MultiPhraseWakeWordDetector as MPD
                mp = MPD()
                matrix = mp.get_phrase_status_matrix()
                is_fallback = True
                active_model = "mock"

            ready_count = sum(1 for p in matrix if p["status"] == "VERIFIED")
            needs_training_count = sum(1 for p in matrix if p["status"] == "NEEDS TRAINING")
            validation_count = sum(1 for p in matrix if p["status"] == "MODEL AVAILABLE — VALIDATION REQUIRED")

            self._send_json({
                "status": "SUCCESS",
                "phrases": matrix,
                "total_phrases": len(matrix),
                "ready_count": ready_count,
                "needs_training_count": needs_training_count,
                "validation_count": validation_count,
                "active_detector": active_model,
                "is_fallback": is_fallback,
            })
        except Exception as exc:
            logger.exception("Failed to get wake phrases: %s", exc)
            self._send_json({"status": "FAILED", "error": str(exc)}, status=500)

    def _handle_wake_word_phrases_post(self, body: dict) -> None:
        """Update settings (enabled/threshold) for one or more wake phrases."""
        try:
            phrase_name = body.get("phrase")
            enabled = body.get("enabled")
            threshold = body.get("threshold")

            cfg = LumiConfig.load()
            from src.wake_word import make_wake_word_detector, MultiPhraseWakeWordDetector
            detector = make_wake_word_detector(cfg)

            updated = False
            if isinstance(detector, MultiPhraseWakeWordDetector) and phrase_name:
                if enabled is not None:
                    detector.enable_phrase(phrase_name, bool(enabled))
                    updated = True
                if threshold is not None:
                    detector.set_phrase_threshold(phrase_name, float(threshold))
                    updated = True

            self._send_json({
                "status": "SUCCESS",
                "updated": updated,
                "message": f"Updated settings for '{phrase_name}'" if phrase_name else "Updated settings",
            })
        except Exception as exc:
            logger.exception("Failed to update wake phrase: %s", exc)
            self._send_json({"status": "FAILED", "error": str(exc)}, status=500)

    def _handle_audio_stream(self, query_str: str) -> None:
        params = urllib.parse.parse_qs(query_str)
        rel_path = params.get("path", [""])[0].strip()
        if not rel_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        abs_path = (REPO_ROOT / rel_path).resolve()
        valid_roots = [
            (REPO_ROOT / "datasets").resolve(),
            TEMP_DIR.resolve(),
        ]
        if not any(abs_path.is_relative_to(r) for r in valid_roots):
            self.send_error(403, "Access to path forbidden")
            return

        if not abs_path.exists():
            self.send_error(404, "Audio file not found")
            return

        self._send_file(abs_path, "audio/wav")

    def _handle_synthetic_preview(self, query_str: str) -> None:
        """Dynamically generate a synthetic tone or silence WAV and stream it."""
        params = urllib.parse.parse_qs(query_str)
        synth_type = params.get("type", ["tone"])[0]
        duration_s = float(params.get("duration", [1.0])[0])
        sample_rate = 16000

        if synth_type == "silence":
            audio = np.zeros(int(sample_rate * duration_s), dtype=np.int16)
        else:
            t = np.linspace(0.0, duration_s, int(sample_rate * duration_s), endpoint=False)
            audio = (10000 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.int16)

        out_path = TEMP_DIR / f"preview_{synth_type}_{int(duration_s*1000)}.wav"
        _write_wav(out_path, audio, sample_rate)
        self._send_file(out_path, "audio/wav")

    def _handle_educational_catalog(self) -> None:
        """Serve real educational content loaded from project CSVs."""
        try:
            from src.educational_loader import EducationalContentLoader
            loader = EducationalContentLoader()
            items = loader.load_all()
            data = []
            for item in items:
                data.append({
                    "id": item.id,
                    "category": item.category,
                    "title": item.title,
                    "body": item.body,
                    "tags": item.tags,
                })
            self._send_json({"status": "SUCCESS", "count": len(data), "items": data})
        except Exception as exc:
            logger.exception("Failed to load educational catalog: %s", exc)
            self._send_json({"status": "FAILED", "error": str(exc)}, status=500)

    def _handle_educational_quiz(self) -> None:
        """Serve structured 2-choice educational quizzes derived from local datasets."""
        try:
            questions = [
                {
                    "category": "Animal",
                    "question": "Which animal has a long trunk?",
                    "optA": "Elephant",
                    "optB": "Rabbit",
                    "correctOpt": 1,
                    "explanation": "Elephants wrap their trunks to greet and drink water!"
                },
                {
                    "category": "Animal",
                    "question": "What sound does a lion make?",
                    "optA": "Meow",
                    "optB": "Roar",
                    "correctOpt": 2,
                    "explanation": "The lion is the king of the jungle and says ROAR!"
                },
                {
                    "category": "Fruit",
                    "question": "What color is a ripe apple?",
                    "optA": "Red",
                    "optB": "Blue",
                    "correctOpt": 1,
                    "explanation": "Apples are delicious and red, green, or yellow!"
                },
                {
                    "category": "Fruit",
                    "question": "What color is a ripe banana?",
                    "optA": "Purple",
                    "optB": "Yellow",
                    "correctOpt": 2,
                    "explanation": "Bananas are yellow and packed with energy!"
                },
                {
                    "category": "Shape",
                    "question": "How many corners does a circle have?",
                    "optA": "Zero",
                    "optB": "Four",
                    "correctOpt": 1,
                    "explanation": "A circle is round with zero corners!"
                },
                {
                    "category": "Shape",
                    "question": "How many sides does a triangle have?",
                    "optA": "3",
                    "optB": "5",
                    "correctOpt": 1,
                    "explanation": "A triangle has 3 straight sides!"
                },
                {
                    "category": "Number",
                    "question": "How many fingers on one hand?",
                    "optA": "5",
                    "optB": "10",
                    "correctOpt": 1,
                    "explanation": "High five! You have 5 fingers on each hand."
                },
                {
                    "category": "Alphabet",
                    "question": "What does Letter A stand for?",
                    "optA": "Apple",
                    "optB": "Boat",
                    "correctOpt": 1,
                    "explanation": "A is for Apple! Ah-Ah-Apple!"
                },
                {
                    "category": "Math",
                    "question": "What is 1 + 1?",
                    "optA": "2",
                    "optB": "4",
                    "correctOpt": 1,
                    "explanation": "1 plus 1 equals 2!"
                },
                {
                    "category": "General Knowledge",
                    "question": "What planet do we live on?",
                    "optA": "Earth",
                    "optB": "Mars",
                    "correctOpt": 1,
                    "explanation": "We live on Planet Earth, our beautiful home!"
                }
            ]
            self._send_json({"status": "SUCCESS", "count": len(questions), "questions": questions})
        except Exception as exc:
            logger.exception("Failed to load educational quiz: %s", exc)
            self._send_json({"status": "FAILED", "error": str(exc)}, status=500)

    def _handle_educational_stories(self) -> None:
        """Serve offline stories from LUMI content catalog."""
        try:
            from src.content_catalog import _build_catalog
            items = _build_catalog()
            stories = [
                {
                    "id": item.id,
                    "title": item.title,
                    "body": item.body,
                    "tags": item.tags
                }
                for item in items if item.category == "story"
            ]
            self._send_json({"status": "SUCCESS", "count": len(stories), "stories": stories})
        except Exception as exc:
            logger.exception("Failed to load stories: %s", exc)
            self._send_json({"status": "FAILED", "error": str(exc)}, status=500)

    def _handle_tts_speak(self, body: dict) -> None:
        """Synthesize arbitrary text with real Piper TTS at specified speed (default slow = 1.15)."""
        text = str(body.get("text", "")).strip()
        speed = str(body.get("speech_speed", "slow")).strip().lower()
        if not text:
            self._send_json({"status": "FAILED", "error": "Empty text for speech synthesis"}, status=400)
            return

        audio_url, stage_tts, stage_playback = self._synthesize_tts(text, enable_tts=True, speech_speed=speed)
        self._send_json({
            "status": "SUCCESS" if audio_url else "FAILED",
            "audio_url": audio_url,
            "tts_audio_url": audio_url,
            "text": text,
            "speech_speed": speed,
            "stage_tts": stage_tts,
        })

    # -----------------------------------------------------------------------
    # POST Handlers
    # -----------------------------------------------------------------------

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/upload":
            self._handle_upload()
            return
        elif path == "/api/interactive/turn":
            self._handle_interactive_turn()
            return

        try:
            body = self._read_json_body()
            if path == "/api/tts/speak":
                self._handle_tts_speak(body)
            elif path == "/api/vad/test":
                self._handle_vad_test(body)
            elif path == "/api/wake_word/test":
                self._handle_wake_word_test(body)
            elif path == "/api/stt/test":
                self._handle_stt_test(body)
            elif path == "/api/tts/test":
                self._handle_tts_test(body)
            elif path == "/api/pipeline/test":
                self._handle_pipeline_test(body)
            elif path == "/api/clear_temp":
                self._handle_clear_temp()
            elif path == "/api/wake_word/phrases":
                self._handle_wake_word_phrases_post(body)
            else:
                self.send_error(404, "Unknown API route")
        except Exception as exc:
            logger.exception("Error handling POST %s: %s", path, exc)
            self._send_json({"error": str(exc), "status": "FAILED"}, status=500)

    def _handle_upload(self) -> None:
        """Handle multipart WAV upload safely."""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(400, "Must be multipart/form-data")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 15 * 1024 * 1024:  # 15 MB limit
            self._send_json({"error": "File size exceeds 15 MB limit", "status": "FAILED"}, status=400)
            return

        raw_body = self.rfile.read(content_length)
        raw_headers = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        msg = BytesParser(policy=default).parsebytes(raw_headers + raw_body)

        file_bytes = None
        raw_filename = "upload.wav"

        for part in msg.iter_parts():
            cd = part.get("Content-Disposition", "")
            name = part.get_param("name", header="content-disposition")
            if name == "file" or part.get_filename():
                raw_filename = part.get_filename() or "upload.wav"
                file_bytes = part.get_payload(decode=True)
                break

        if not file_bytes:
            self._send_json({"error": "No file payload found in upload", "status": "FAILED"}, status=400)
            return

        raw_filename = Path(raw_filename).name
        # Clean filename
        clean_name = "".join(c for c in raw_filename if c.isalnum() or c in "._- ")
        if not clean_name.lower().endswith(".wav"):
            self._send_json({"error": "Only .wav files are supported", "status": "FAILED"}, status=400)
            return

        if len(file_bytes) < 44 or file_bytes[:4] != b"RIFF":
            self._send_json({"error": "Invalid WAV file header", "status": "FAILED"}, status=400)
            return

        # Unique name in temp_outputs
        h = hashlib.sha256(file_bytes).hexdigest()[:8]
        out_name = f"upload_{h}_{clean_name}"
        out_path = TEMP_DIR / out_name
        out_path.write_bytes(file_bytes)

        # Validate with WAV loader
        try:
            audio = _load_wav_as_int16(out_path)
            duration_s = len(audio) / 16000.0
        except Exception as exc:
            out_path.unlink(missing_ok=True)
            self._send_json({"error": f"Failed to parse WAV audio: {exc}", "status": "FAILED"}, status=400)
            return

        rel_path = out_path.relative_to(REPO_ROOT).as_posix()
        self._send_json({
            "status": "SUCCESS",
            "message": "File uploaded successfully",
            "sample_path": rel_path,
            "filename": out_name,
            "duration_s": duration_s,
            "num_samples": len(audio),
            "audio_url": f"/api/audio?path={urllib.parse.quote(rel_path)}",
        })

    def _synthesize_tts(
        self, response_text: str, enable_tts: bool, speech_speed: str = "slow"
    ) -> Tuple[Optional[str], dict, dict]:
        """Synthesize response using genuine Piper TTS, or gracefully handle muting/missing model."""
        s8_t0 = time.perf_counter()
        audio_url = None
        tts_status = "Blocked"
        tts_badge = "BLOCKED — MODEL MISSING"
        tts_output = "Piper model en_US-lessac-medium.onnx not installed; native voice synthesis blocked."

        # Child-friendly speech rate mapping:
        # "slow" -> 1.15 (Default: relaxed, articulated pace for children aged 0-6)
        # "normal" -> 1.00 (Standard adult pace)
        speed_str = str(speech_speed or "slow").lower().strip()
        if speed_str == "normal":
            target_length_scale = 1.0
        elif speed_str == "slow":
            target_length_scale = 1.15
        else:
            try:
                target_length_scale = float(speed_str)
            except ValueError:
                target_length_scale = 1.15

        cfg = LumiConfig.load()
        tts_model_path = PROJECT_ROOT / cfg.tts.model_path
        tts_cfg_path = PROJECT_ROOT / cfg.tts.config_path
        piper_installed = importlib.util.find_spec("piper") is not None
        piper_model_valid = is_valid_piper_model(tts_model_path, tts_cfg_path)

        if piper_model_valid and piper_installed and enable_tts:
            try:
                piper = PiperTTS(str(tts_model_path), str(tts_cfg_path), str(TEMP_DIR), length_scale=target_length_scale)
                tts_res = piper.synthesize(response_text, length_scale=target_length_scale)
                if tts_res.error or len(tts_res.audio) == 0:
                    tts_status = "Failed"
                    tts_badge = "SYNTHESIS FAILED"
                    tts_output = f"Piper synthesis error: {tts_res.error}"
                else:
                    h = hashlib.sha256(f"{response_text}_{target_length_scale:.2f}".encode()).hexdigest()[:8]
                    out_name = f"resp_{h}.wav"
                    out_path = TEMP_DIR / out_name
                    _write_wav(out_path, tts_res.audio, tts_res.sample_rate)
                    rel_p = out_path.relative_to(REPO_ROOT).as_posix()
                    audio_url = f"/api/audio?path={urllib.parse.quote(rel_p)}"
                    tts_status = "Passed"
                    tts_badge = "REAL PIPER TTS"
                    speed_label = "Slow" if target_length_scale > 1.05 else "Normal"
                    tts_output = f"Piper synthesized {tts_res.duration_s:.2f}s audio ({speed_label} pace, length_scale={target_length_scale:.2f})"
            except Exception as exc:
                tts_status = "Failed"
                tts_badge = "SYNTHESIS FAILED"
                tts_output = f"Piper error: {exc}"
        elif not enable_tts:
            tts_status = "Skipped"
            tts_badge = "MUTED"
            tts_output = "Voice output muted by user toggle."
        else:
            tts_status = "Blocked"
            tts_badge = "BLOCKED — MODEL MISSING"
            tts_output = "Piper voice model missing or invalid (HTML error page detected in models/tts/). Spoken response blocked (displaying text response)."
            audio_url = None

        stage_tts = {
            "id": "tts",
            "name": "8. Text-to-Speech (Piper TTS)",
            "status": tts_status,
            "badge": tts_badge,
            "latency_ms": round((time.perf_counter() - s8_t0) * 1000, 2),
            "output": tts_output,
            "details": {"piper_available": piper_model_valid and piper_installed, "audio_url": audio_url},
        }

        if audio_url:
            pb_status = "Passed"
            pb_badge = "PLAYABLE WAV"
            pb_output = "Piper synthesized WAV audio ready for browser playback"
        elif not enable_tts:
            pb_status = "Skipped"
            pb_badge = "MUTED"
            pb_output = "Audio playback muted by user"
        else:
            pb_status = "Blocked"
            pb_badge = "BLOCKED"
            pb_output = "Piper audio unavailable (model missing). Browser voice synthesis fallback enabled."

        stage_playback = {
            "id": "playback",
            "name": "9. Audio Playback",
            "status": pb_status,
            "badge": pb_badge,
            "latency_ms": 0.0,
            "output": pb_output,
            "details": {"audio_url": audio_url},
        }

        return audio_url, stage_tts, stage_playback

    def _handle_interactive_turn(self) -> None:
        """Handle a live conversational turn with real microphone audio or typed input."""
        content_type = self.headers.get("Content-Type", "")
        audio_bytes = None
        user_typed_text = ""
        require_wake_word = False
        model_name = "base.en"
        enable_tts = True
        speech_speed = "slow"

        if "multipart/form-data" in content_type:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 20 * 1024 * 1024:
                self._send_json({"error": "Audio payload exceeds limit", "status": "FAILED"}, status=400)
                return

            raw_body = self.rfile.read(content_length)
            raw_headers = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
            msg = BytesParser(policy=default).parsebytes(raw_headers + raw_body)

            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name in ("file", "audio_file", "audio") or part.get_filename():
                    audio_bytes = part.get_payload(decode=True)
                elif name in ("text", "typed_text", "user_text"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        user_typed_text = payload.decode("utf-8", errors="ignore").strip()
                elif name == "require_wake_word":
                    payload = part.get_payload(decode=True)
                    if payload:
                        require_wake_word = payload.decode().strip().lower() in ("true", "1", "yes")
                elif name == "model":
                    payload = part.get_payload(decode=True)
                    if payload:
                        model_name = payload.decode().strip()
                elif name == "enable_tts":
                    payload = part.get_payload(decode=True)
                    if payload:
                        enable_tts = payload.decode().strip().lower() in ("true", "1", "yes")
                elif name in ("speech_speed", "speed"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        speech_speed = payload.decode().strip().lower()
        else:
            body = self._read_json_body()
            user_typed_text = body.get("text", "").strip()
            require_wake_word = bool(body.get("require_wake_word", False))
            model_name = body.get("model", "base.en")
            enable_tts = bool(body.get("enable_tts", True))
            speech_speed = body.get("speech_speed", "slow").strip().lower()

        stages = []
        overall_t0 = time.perf_counter()
        sample_rate = 16000

        # ------------------------------------------------------------------
        # Stage 1: Microphone Capture / Audio Input
        # ------------------------------------------------------------------
        s1_t0 = time.perf_counter()
        audio = None
        if audio_bytes and len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF":
            h = hashlib.sha256(audio_bytes).hexdigest()[:8]
            mic_path = TEMP_DIR / f"mic_{h}.wav"
            mic_path.write_bytes(audio_bytes)
            try:
                audio = _load_wav_as_int16(mic_path)
                dur_s = len(audio) / sample_rate
                stages.append({
                    "id": "mic_capture",
                    "name": "1. Microphone Capture",
                    "status": "Passed",
                    "badge": "LIVE AUDIO",
                    "latency_ms": round((time.perf_counter() - s1_t0) * 1000, 2),
                    "output": f"Captured {dur_s:.2f}s of live audio from user's microphone ({len(audio)} samples)",
                    "details": {"duration_s": round(dur_s, 2), "samples": len(audio)},
                })
            except Exception as exc:
                stages.append({
                    "id": "mic_capture",
                    "name": "1. Microphone Capture",
                    "status": "Failed",
                    "badge": "FAILED",
                    "latency_ms": round((time.perf_counter() - s1_t0) * 1000, 2),
                    "output": f"Failed to parse captured WAV: {exc}",
                    "details": {},
                })
                self._send_json({"status": "FAILED", "stages": stages, "error": str(exc)}, status=400)
                return
        elif user_typed_text:
            stages.append({
                "id": "mic_capture",
                "name": "1. Microphone Capture",
                "status": "Passed",
                "badge": "TYPED INPUT",
                "latency_ms": 0.0,
                "output": f"Text input provided directly: \"{user_typed_text}\"",
                "details": {"mode": "typed_text"},
            })
        else:
            self._send_json({"error": "No microphone audio or text provided", "status": "FAILED"}, status=400)
            return

        # ------------------------------------------------------------------
        # Stage 2: Audio Validation
        # ------------------------------------------------------------------
        s2_t0 = time.perf_counter()
        rms_energy = 0.0
        if audio is not None:
            if len(audio) == 0:
                stages.append({
                    "id": "audio_validation",
                    "name": "2. Audio Validation",
                    "status": "Failed",
                    "badge": "EMPTY AUDIO",
                    "latency_ms": round((time.perf_counter() - s2_t0) * 1000, 2),
                    "output": "Audio buffer is empty (0 samples recorded)",
                    "details": {},
                })
                self._send_json({
                    "status": "FAILED",
                    "user_transcript": "",
                    "response_text": "I didn't receive any audio from your microphone. Please check your mic and try again!",
                    "stages": stages,
                })
                return
            rms_energy = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
            stages.append({
                "id": "audio_validation",
                "name": "2. Audio Validation",
                "status": "Passed",
                "badge": "VALIDATED",
                "latency_ms": round((time.perf_counter() - s2_t0) * 1000, 2),
                "output": f"Valid 16 kHz 16-bit PCM mono WAV (RMS Energy = {rms_energy:.1f})",
                "details": {"rms": round(rms_energy, 2), "sample_rate": sample_rate},
            })
        else:
            stages.append({
                "id": "audio_validation",
                "name": "2. Audio Validation",
                "status": "Passed",
                "badge": "TEXT VALID",
                "latency_ms": 0.0,
                "output": f"Text query validated: {len(user_typed_text)} chars",
                "details": {},
            })

        # ------------------------------------------------------------------
        # Stage 3: Voice Activity Detection (VAD)
        # ------------------------------------------------------------------
        s3_t0 = time.perf_counter()
        speech_audio = audio

        if audio is not None:
            vad = MockVAD(energy_threshold=80.0)
            vad_res = vad.process(audio)
            is_speech = vad_res.contains_speech
            speech_audio = vad_res.speech_audio if is_speech else audio

            if not is_speech or rms_energy < 50.0:
                stages.append({
                    "id": "vad",
                    "name": "3. Voice Activity Detection (VAD)",
                    "status": "Passed",
                    "badge": "SILENCE / NO SPEECH",
                    "latency_ms": round((time.perf_counter() - s3_t0) * 1000, 2),
                    "output": f"Audio classified as silence (RMS {rms_energy:.1f} < 50). No speech detected.",
                    "details": {"contains_speech": False, "rms": round(rms_energy, 1)},
                })
                for st_id, st_name in [
                    ("wake_word", "4. Wake-Word Detection"),
                    ("stt", "5. Speech-to-Text (Faster-Whisper)"),
                    ("intent", "6. Intent Recognition"),
                    ("response_generation", "7. Response Generation"),
                ]:
                    stages.append({
                        "id": st_id,
                        "name": st_name,
                        "status": "Skipped",
                        "badge": "SKIPPED (SILENCE)",
                        "latency_ms": 0.0,
                        "output": "Stage skipped because no speech was detected.",
                        "details": {},
                    })
                silence_resp = "I didn't hear anything. Please try speaking into your microphone again!"
                audio_url, s_tts, s_pb = self._synthesize_tts(silence_resp, enable_tts, speech_speed=speech_speed)
                stages.append(s_tts)
                stages.append(s_pb)
                total_time_ms = (time.perf_counter() - overall_t0) * 1000.0
                self._send_json({
                    "status": "SUCCESS",
                    "user_transcript": "(Silence detected)",
                    "transcript": "(Silence detected)",
                    "response_text": silence_resp,
                    "topic_tag": "Silence",
                    "intent": "SILENCE",
                    "speech_speed": speech_speed,
                    "audio_url": audio_url,
                    "tts_audio_url": audio_url,
                    "total_time_ms": round(total_time_ms, 2),
                    "stages": stages,
                })
                return

            stages.append({
                "id": "vad",
                "name": "3. Voice Activity Detection (VAD)",
                "status": "Passed",
                "badge": "SPEECH DETECTED",
                "latency_ms": round((time.perf_counter() - s3_t0) * 1000, 2),
                "output": f"Speech active! Speech ratio: {vad_res.speech_ratio*100:.1f}%, RMS: {rms_energy:.1f}",
                "details": {"contains_speech": True, "speech_ratio": round(vad_res.speech_ratio, 2)},
            })
        else:
            stages.append({
                "id": "vad",
                "name": "3. Voice Activity Detection (VAD)",
                "status": "Skipped",
                "badge": "SKIPPED (TEXT)",
                "latency_ms": 0.0,
                "output": "VAD bypassed for direct text input",
                "details": {},
            })

        # ------------------------------------------------------------------
        # Stage 4: Wake-Word Detection
        # ------------------------------------------------------------------
        s4_t0 = time.perf_counter()
        transcript = ""
        stt_inference_s = 0.0
        stt_rtf = 0.0

        if user_typed_text:
            if require_wake_word:
                is_detected, is_genuine, model_lbl, remaining_cmd = _extract_text_wake_word(user_typed_text)
                if is_detected:
                    badge_text = f"WAKE CONFIRMED (TEXT: {model_lbl})"
                    stages.append({
                        "id": "wake_word",
                        "name": "4. Wake-Word Detection",
                        "status": "Passed",
                        "badge": badge_text,
                        "latency_ms": round((time.perf_counter() - s4_t0) * 1000, 2),
                        "output": f"Wake phrase '{model_lbl}' detected in typed text.",
                        "details": {"model": model_lbl, "is_genuine_lumi": is_genuine, "mode": "text"},
                    })

                    if not remaining_cmd:
                        # User typed greeting only e.g. "Hey LUMI"
                        transcript = user_typed_text
                        stages.append({
                            "id": "stt",
                            "name": "5. Speech-to-Text (Faster-Whisper)",
                            "status": "Passed",
                            "badge": "WAKE PHRASE ONLY",
                            "latency_ms": 0.0,
                            "output": "Wake phrase detected with no follow-up question yet.",
                            "details": {},
                        })
                        stages.append({
                            "id": "intent",
                            "name": "6. Intent Recognition",
                            "status": "Passed",
                            "badge": "GREETING",
                            "latency_ms": 0.0,
                            "output": "Routed to wake-up greeting response.",
                            "details": {"intent": "HELLO"},
                        })
                        resp_text = _wake_phrase_greeting(model_lbl)
                        stages.append({
                            "id": "response_generation",
                            "name": "7. Response Generation",
                            "status": "Passed",
                            "badge": "DYNAMIC RESPONSE",
                            "latency_ms": 0.0,
                            "output": f"[Greeting] \"{resp_text}\"",
                            "details": {"topic": "Greeting", "response_text": resp_text},
                        })
                        audio_url, s_tts, s_pb = self._synthesize_tts(resp_text, enable_tts, speech_speed=speech_speed)
                        stages.append(s_tts)
                        stages.append(s_pb)
                        total_time_ms = (time.perf_counter() - overall_t0) * 1000.0
                        self._send_json({
                            "status": "SUCCESS",
                            "transcript": transcript,
                            "user_transcript": transcript,
                            "response_text": resp_text,
                            "topic_tag": "Greeting",
                            "intent": "HELLO",
                            "intent_confidence": 1.0,
                            "speech_speed": speech_speed,
                            "audio_url": audio_url,
                            "tts_audio_url": audio_url,
                            "total_time_ms": round(total_time_ms, 2),
                            "stages": stages,
                        })
                        return
                    else:
                        transcript = remaining_cmd
                        stages.append({
                            "id": "stt",
                            "name": "5. Speech-to-Text (Faster-Whisper)",
                            "status": "Skipped",
                            "badge": "SKIPPED (TYPED)",
                            "latency_ms": 0.0,
                            "output": f"Command extracted after wake phrase: \"{transcript}\"",
                            "details": {"transcript": transcript},
                        })
                else:
                    # Wake phrase not found in typed text
                    stages.append({
                        "id": "wake_word",
                        "name": "4. Wake-Word Detection",
                        "status": "Blocked",
                        "badge": "WAKE NOT DETECTED",
                        "latency_ms": round((time.perf_counter() - s4_t0) * 1000, 2),
                        "output": "Typed text did not start with 'Hey LUMI' (or fallback 'Hey Jarvis').",
                        "details": {"mode": "text"},
                    })
                    for st_id, st_name in [
                        ("stt", "5. Speech-to-Text (Faster-Whisper)"),
                        ("intent", "6. Intent Recognition"),
                        ("response_generation", "7. Response Generation"),
                    ]:
                        stages.append({
                            "id": st_id,
                            "name": st_name,
                            "status": "Skipped",
                            "badge": "SKIPPED (WAKE REQUIRED)",
                            "latency_ms": 0.0,
                            "output": "Stage skipped because wake phrase was not provided.",
                            "details": {},
                        })
                    resp_text = (
                        f"I didn't hear the wake phrase. In text mode, start your message with 'Hey LUMI' "
                        f"(e.g. \"Hey LUMI, {user_typed_text}\") — or uncheck 'Require Wake Word' to chat directly!"
                    )
                    audio_url, s_tts, s_pb = self._synthesize_tts(resp_text, enable_tts, speech_speed=speech_speed)
                    stages.append(s_tts)
                    stages.append(s_pb)
                    total_time_ms = (time.perf_counter() - overall_t0) * 1000.0
                    self._send_json({
                        "status": "BLOCKED",
                        "user_transcript": "",
                        "transcript": "",
                        "response_text": resp_text,
                        "topic_tag": "Wake Required",
                        "intent": "WAKE_WORD_REQUIRED",
                        "intent_confidence": 0.0,
                        "speech_speed": speech_speed,
                        "audio_url": audio_url,
                        "tts_audio_url": audio_url,
                        "total_time_ms": round(total_time_ms, 2),
                        "stages": stages,
                    })
                    return
            else:
                stages.append({
                    "id": "wake_word",
                    "name": "4. Wake-Word Detection",
                    "status": "Skipped",
                    "badge": "SKIPPED (BYPASSED)",
                    "latency_ms": 0.0,
                    "output": "Wake-word check bypassed for direct interactive conversation.",
                    "details": {},
                })
                transcript = user_typed_text
                stages.append({
                    "id": "stt",
                    "name": "5. Speech-to-Text (Faster-Whisper)",
                    "status": "Skipped",
                    "badge": "SKIPPED (TYPED)",
                    "latency_ms": 0.0,
                    "output": f"Typed text used directly: \"{transcript}\"",
                    "details": {"transcript": transcript},
                })
        else:
            # Microphone Audio Input
            if require_wake_word:
                cfg = LumiConfig.load()
                ww_path = cfg.wake_word.resolve_model_path()
                try:
                    from src.wake_word import make_wake_word_detector, MockWakeWordDetector
                    ww_detector = make_wake_word_detector(cfg)
                except Exception:
                    ww_detector = None

                if ww_detector is None or (isinstance(ww_detector, MockWakeWordDetector) and not ww_path.exists()):
                    stages.append({
                        "id": "wake_word",
                        "name": "4. Wake-Word Detection",
                        "status": "Blocked",
                        "badge": "BLOCKED — MODEL MISSING",
                        "latency_ms": round((time.perf_counter() - s4_t0) * 1000, 2),
                        "output": f"Wake-word model hey_lumi.onnx not found at {ww_path}. Never fabricating a model.",
                        "details": {"model_path": str(ww_path)},
                    })
                    for st_id, st_name in [
                        ("stt", "5. Speech-to-Text (Faster-Whisper)"),
                        ("intent", "6. Intent Recognition"),
                        ("response_generation", "7. Response Generation"),
                    ]:
                        stages.append({
                            "id": st_id,
                            "name": st_name,
                            "status": "Skipped",
                            "badge": "SKIPPED (BLOCKED)",
                            "latency_ms": 0.0,
                            "output": "Stage skipped because wake word model is missing.",
                            "details": {},
                        })
                    resp_text = "Wake-word model 'hey_lumi.onnx' is missing. Please uncheck 'Require Wake Word' to talk directly to LUMI!"
                    audio_url, s_tts, s_pb = self._synthesize_tts(resp_text, enable_tts, speech_speed=speech_speed)
                    stages.append(s_tts)
                    stages.append(s_pb)
                    self._send_json({
                        "status": "BLOCKED",
                        "user_transcript": "",
                        "response_text": resp_text,
                        "topic_tag": "Blocked",
                        "intent": "BLOCKED",
                        "speech_speed": speech_speed,
                        "audio_url": audio_url,
                        "tts_audio_url": audio_url,
                        "stages": stages,
                    })
                    return

                ww_frame_size = 1280
                detected_event = None
                detected_frame_idx = -1
                num_frames = len(audio) // ww_frame_size if audio is not None else 0

                for f_idx in range(num_frames):
                    chunk = audio[f_idx * ww_frame_size : (f_idx + 1) * ww_frame_size]
                    evt = ww_detector.process_frame(chunk)
                    if evt:
                        detected_event = evt
                        detected_frame_idx = f_idx
                        break

                is_fallback = getattr(ww_detector, "is_fallback", True)
                is_genuine = getattr(ww_detector, "is_genuine_lumi", False)
                model_lbl = getattr(ww_detector, "model_name", "unknown")

                if detected_event:
                    badge_text = f"WAKE CONFIRMED ({model_lbl})" if is_genuine else f"WAKE CONFIRMED (Fallback: {model_lbl})"
                    stages.append({
                        "id": "wake_word",
                        "name": "4. Wake-Word Detection",
                        "status": "Passed",
                        "badge": badge_text,
                        "latency_ms": round((time.perf_counter() - s4_t0) * 1000, 2),
                        "output": f"Wake phrase confirmed by {model_lbl} at frame {detected_frame_idx} (Score: {detected_event.score:.3f}, {'Genuine Hey LUMI' if is_genuine else 'Fallback Model'}).",
                        "details": {
                            "model": model_lbl,
                            "score": round(detected_event.score, 3),
                            "is_fallback": is_fallback,
                            "is_genuine_lumi": is_genuine,
                            "frame_index": detected_frame_idx,
                        },
                    })
                    command_start_sample = (detected_frame_idx + 1) * ww_frame_size
                    if command_start_sample < len(audio):
                        speech_audio = audio[command_start_sample:]
                    else:
                        stages.append({
                            "id": "stt",
                            "name": "5. Speech-to-Text (Faster-Whisper)",
                            "status": "Passed",
                            "badge": "WAKE PHRASE ONLY",
                            "latency_ms": 0.0,
                            "output": "Wake phrase detected with no follow-up command yet.",
                            "details": {},
                        })
                        stages.append({
                            "id": "intent",
                            "name": "6. Intent Recognition",
                            "status": "Passed",
                            "badge": "GREETING",
                            "latency_ms": 0.0,
                            "output": "Routed to wake-up greeting response.",
                            "details": {"intent": "HELLO"},
                        })
                        resp_text = _wake_phrase_greeting(model_lbl)
                        stages.append({
                            "id": "response_generation",
                            "name": "7. Response Generation",
                            "status": "Passed",
                            "badge": "DYNAMIC RESPONSE",
                            "latency_ms": 0.0,
                            "output": f"[Greeting] \"{resp_text}\"",
                            "details": {"topic": "Greeting", "response_text": resp_text},
                        })
                        audio_url, s_tts, s_pb = self._synthesize_tts(resp_text, enable_tts, speech_speed=speech_speed)
                        stages.append(s_tts)
                        stages.append(s_pb)
                        total_time_ms = (time.perf_counter() - overall_t0) * 1000.0
                        self._send_json({
                            "status": "SUCCESS",
                            "user_transcript": f"{model_lbl}!",
                            "transcript": f"{model_lbl}!",
                            "response_text": resp_text,
                            "topic_tag": "Greeting",
                            "intent": "HELLO",
                            "intent_confidence": 1.0,
                            "speech_speed": speech_speed,
                            "audio_url": audio_url,
                            "tts_audio_url": audio_url,
                            "total_time_ms": round(total_time_ms, 2),
                            "stages": stages,
                        })
                        return
                else:
                    stages.append({
                        "id": "wake_word",
                        "name": "4. Wake-Word Detection",
                        "status": "Blocked",
                        "badge": "WAKE NOT DETECTED",
                        "latency_ms": round((time.perf_counter() - s4_t0) * 1000, 2),
                        "output": f"Audio did not contain the wake phrase (Searched using {model_lbl}{' [Fallback]' if is_fallback else ''}).",
                        "details": {"model": model_lbl, "is_fallback": is_fallback, "threshold": cfg.wake_word.score_threshold},
                    })
                    for st_id, st_name in [
                        ("stt", "5. Speech-to-Text (Faster-Whisper)"),
                        ("intent", "6. Intent Recognition"),
                        ("response_generation", "7. Response Generation"),
                    ]:
                        stages.append({
                            "id": st_id,
                            "name": st_name,
                            "status": "Skipped",
                            "badge": "SKIPPED (WAKE NOT HEARD)",
                            "latency_ms": 0.0,
                            "output": "Stage skipped because wake phrase was not detected in audio.",
                            "details": {},
                        })
                    resp_text = f"I didn't hear the wake phrase. Please start by saying 'Hey LUMI' (or fallback '{model_lbl}')!"
                    audio_url, s_tts, s_pb = self._synthesize_tts(resp_text, enable_tts, speech_speed=speech_speed)
                    stages.append(s_tts)
                    stages.append(s_pb)
                    total_time_ms = (time.perf_counter() - overall_t0) * 1000.0
                    self._send_json({
                        "status": "BLOCKED",
                        "user_transcript": "",
                        "transcript": "",
                        "response_text": resp_text,
                        "topic_tag": "Wake Required",
                        "intent": "WAKE_WORD_REQUIRED",
                        "intent_confidence": 0.0,
                        "speech_speed": speech_speed,
                        "audio_url": audio_url,
                        "tts_audio_url": audio_url,
                        "total_time_ms": round(total_time_ms, 2),
                        "stages": stages,
                    })
                    return
            else:
                stages.append({
                    "id": "wake_word",
                    "name": "4. Wake-Word Detection",
                    "status": "Skipped",
                    "badge": "SKIPPED (BYPASSED)",
                    "latency_ms": 0.0,
                    "output": "Wake-word check bypassed for direct interactive conversation.",
                    "details": {},
                })

            # ------------------------------------------------------------------
            # Stage 5: Speech-to-Text (Faster-Whisper STT) for Audio
            # ------------------------------------------------------------------
            s5_t0 = time.perf_counter()
            if not check_hf_cache(model_name):
                stages.append({
                    "id": "stt",
                    "name": "5. Speech-to-Text (Faster-Whisper)",
                    "status": "Blocked",
                    "badge": "BLOCKED — MODEL NOT DOWNLOADED",
                    "latency_ms": round((time.perf_counter() - s5_t0) * 1000, 2),
                    "output": f"Whisper model '{model_name}' is not cached locally. Auto-downloads are blocked.",
                    "details": {"model": model_name},
                })
                self._send_json({
                    "status": "BLOCKED",
                    "user_transcript": "",
                    "response_text": f"Faster-Whisper model '{model_name}' is not downloaded. Please select the locally cached 'base.en' model.",
                    "topic_tag": "Blocked",
                    "intent": "BLOCKED",
                    "stages": stages,
                })
                return

            cache_key = f"{model_name}_cpu_int8_1"
            if cache_key not in _STT_CACHE:
                _STT_CACHE[cache_key] = FasterWhisperSTT(model=model_name, device="cpu", compute_type="int8", beam_size=1)
                _STT_CACHE[cache_key]._load()
            stt = _STT_CACHE[cache_key]

            stt_t0 = time.perf_counter()
            trans_res = stt.transcribe(speech_audio, sample_rate=sample_rate)
            stt_inference_s = time.perf_counter() - stt_t0
            transcript = trans_res.text.strip()
            dur_s = len(speech_audio) / sample_rate
            stt_rtf = stt_inference_s / dur_s if dur_s > 0 else 0.0

            if not transcript:
                stages.append({
                    "id": "stt",
                    "name": "5. Speech-to-Text (Faster-Whisper)",
                    "status": "Passed",
                    "badge": "NO WORDS RECOGNIZED",
                    "latency_ms": round(stt_inference_s * 1000, 2),
                    "output": f"Faster-Whisper {model_name} completed in {stt_inference_s:.2f}s, but no words were recognized.",
                    "details": {"latency_s": round(stt_inference_s, 2), "rtf": round(stt_rtf, 2)},
                })
                transcript = "(Unintelligible sound)"
            else:
                stages.append({
                    "id": "stt",
                    "name": "5. Speech-to-Text (Faster-Whisper)",
                    "status": "Passed",
                    "badge": "REAL INFERENCE",
                    "latency_ms": round(stt_inference_s * 1000, 2),
                    "output": f"Transcribed: \"{transcript}\" (latency: {stt_inference_s:.2f}s, RTF: {stt_rtf:.2f}x)",
                    "details": {
                        "transcript": transcript,
                        "inference_time_s": round(stt_inference_s, 2),
                        "rtf": round(stt_rtf, 2),
                        "model": model_name,
                    },
                })

        # ------------------------------------------------------------------
        # Stage 6: Intent Recognition
        # ------------------------------------------------------------------
        s6_t0 = time.perf_counter()
        normalized_transcript = normalize_text(transcript)
        classification = classify_intent(normalized_transcript)
        stages.append({
            "id": "intent",
            "name": "6. Intent Recognition",
            "status": "Passed",
            "badge": "REAL CLASSIFIER",
            "latency_ms": round((time.perf_counter() - s6_t0) * 1000, 2),
            "output": f"Intent: {classification.intent.value} (confidence: {classification.confidence:.2f}, pattern: {classification.matched_pattern})",
            "details": {
                "intent": classification.intent.value,
                "confidence": round(classification.confidence, 2),
                "matched_pattern": classification.matched_pattern,
            },
        })

        # ------------------------------------------------------------------
        # Stage 7: Response Generation (Educational Catalog + Intent Router)
        # ------------------------------------------------------------------
        s7_t0 = time.perf_counter()
        router = get_cached_router()
        catalog = _ROUTER_CACHE[1]
        response_text, topic_tag = get_lumi_conversational_response(
            transcript, catalog, router, classification
        )
        stages.append({
            "id": "response_generation",
            "name": "7. Response Generation",
            "status": "Passed",
            "badge": "DYNAMIC RESPONSE",
            "latency_ms": round((time.perf_counter() - s7_t0) * 1000, 2),
            "output": f"[{topic_tag}] \"{response_text[:90]}...\"",
            "details": {"topic": topic_tag, "response_text": response_text},
        })

        # ------------------------------------------------------------------
        # Stages 8 & 9: Text-to-Speech & Playback
        # ------------------------------------------------------------------
        audio_url, stage_tts, stage_playback = self._synthesize_tts(response_text, enable_tts, speech_speed=speech_speed)
        stages.append(stage_tts)
        stages.append(stage_playback)

        total_time_ms = (time.perf_counter() - overall_t0) * 1000.0

        self._send_json({
            "status": "SUCCESS",
            "transcript": transcript,
            "user_transcript": transcript,
            "response_text": response_text,
            "topic_tag": topic_tag,
            "intent": classification.intent.value,
            "intent_confidence": round(classification.confidence, 2),
            "speech_speed": speech_speed,
            "audio_url": audio_url,
            "tts_audio_url": audio_url,
            "total_time_ms": round(total_time_ms, 2),
            "stages": stages,
        })


    def _handle_vad_test(self, body: dict) -> None:
        """Run Silero VAD (or MockVAD) test."""
        audio, sample_rate, desc = load_audio_from_request(body)
        threshold = float(body.get("threshold", 0.5))
        min_silence_ms = int(body.get("min_silence_duration_ms", 700))
        use_mock = bool(body.get("use_mock", False))

        t0 = time.perf_counter()

        if not use_mock:
            # Check for native Silero VAD prerequisites
            try:
                import torch  # noqa: F401
            except ImportError:
                self._send_json({
                    "status": "BLOCKED",
                    "badge": "BLOCKED — DEPENDENCY MISSING",
                    "module": "Silero VAD",
                    "error": (
                        "torch is required for native SileroVAD but is not installed. "
                        "Install silero-vad / torch in your Python environment, or switch to 'Run with Mock Fallback'."
                    ),
                    "audio_desc": desc,
                    "audio_duration_s": len(audio) / sample_rate,
                })
                return

            try:
                vad = SileroVAD(
                    threshold=threshold,
                    min_silence_duration_ms=min_silence_ms,
                    sample_rate=sample_rate,
                )
                vad_result: VADResult = vad.process(audio)
                badge = "REAL INFERENCE"
                is_mock = False
            except Exception as exc:
                self._send_json({
                    "status": "FAILED",
                    "badge": "FAILED",
                    "module": "Silero VAD",
                    "error": str(exc),
                    "audio_desc": desc,
                }, status=500)
                return
        else:
            vad = MockVAD()
            vad_result = vad.process(audio)
            badge = "MOCK TEST"
            is_mock = True

        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Compute speech region intervals if speech was detected
        speech_regions = []
        if vad_result.contains_speech and len(vad_result.speech_audio) > 0:
            speech_dur = len(vad_result.speech_audio) / sample_rate
            speech_regions.append({
                "start_s": 0.0,
                "end_s": round(speech_dur, 3),
                "duration_s": round(speech_dur, 3),
                "samples": len(vad_result.speech_audio),
            })

        self._send_json({
            "status": "SUCCESS",
            "badge": badge,
            "is_mock": is_mock,
            "audio_desc": desc,
            "audio_duration_s": round(len(audio) / sample_rate, 3),
            "contains_speech": vad_result.contains_speech,
            "speech_ratio": round(vad_result.speech_ratio, 4),
            "frames_total": vad_result.frames_total,
            "frames_speech": vad_result.frames_speech,
            "speech_samples": len(vad_result.speech_audio),
            "speech_regions": speech_regions,
            "threshold": threshold,
            "min_silence_ms": min_silence_ms,
            "processing_time_ms": round(latency_ms, 2),
        })

    def _handle_wake_word_test(self, body: dict) -> None:
        """Run Wake-Word detection test."""
        audio, sample_rate, desc = load_audio_from_request(body)
        threshold = float(body.get("threshold", 0.6))
        cooldown_ms = int(body.get("cooldown_ms", 2000))
        use_mock = bool(body.get("use_mock", False))

        cfg = LumiConfig.load()
        model_path = cfg.wake_word.resolve_model_path()
        model_exists = model_path.exists()

        import importlib.util
        oww_installed = importlib.util.find_spec("openwakeword") is not None

        if not use_mock:
            # Strict safety rule: Never fabricate a model or report mocked detection as real wake-word recognition.
            # If the model or library is unavailable, mark the test as BLOCKED — MODEL MISSING.
            if not model_exists or not oww_installed:
                reasons = []
                if not model_exists:
                    reasons.append(f"Model file not found at: {model_path}")
                if not oww_installed:
                    reasons.append("openwakeword package is not installed")
                self._send_json({
                    "status": "BLOCKED",
                    "badge": "BLOCKED — MODEL MISSING",
                    "module": "openWakeWord",
                    "model_path": str(model_path.relative_to(REPO_ROOT) if model_path.is_relative_to(REPO_ROOT) else model_path),
                    "model_exists": model_exists,
                    "library_installed": oww_installed,
                    "error": " & ".join(reasons) + ". Wake-word testing with real audio is not available.",
                    "audio_desc": desc,
                })
                return

            try:
                t0 = time.perf_counter()
                detector = OpenWakeWordDetector(
                    model_path=str(model_path),
                    threshold=threshold,
                    cooldown_ms=cooldown_ms,
                )
                badge = "REAL INFERENCE"
                is_mock = False
            except Exception as exc:
                self._send_json({
                    "status": "FAILED",
                    "badge": "FAILED",
                    "error": str(exc),
                }, status=500)
                return
        else:
            t0 = time.perf_counter()
            detector = MockWakeWordDetector(
                trigger_at_frame=0,
                score=0.95,
                threshold=threshold,
                cooldown_ms=cooldown_ms,
            )
            badge = "MOCK TEST"
            is_mock = True

        # Process audio in 1280-sample (80ms) frames
        chunk_size = 1280
        total_frames = len(audio) // chunk_size
        events = []
        triggered = False

        for f_idx in range(total_frames):
            chunk = audio[f_idx * chunk_size : (f_idx + 1) * chunk_size]
            ev = detector.process_frame(chunk)
            if ev:
                triggered = True
                events.append({
                    "frame_index": f_idx,
                    "time_s": round(f_idx * 0.08, 2),
                    "score": round(ev.score, 4),
                    "model_name": ev.model_name,
                })

        latency_ms = (time.perf_counter() - t0) * 1000.0

        self._send_json({
            "status": "SUCCESS",
            "badge": badge,
            "is_mock": is_mock,
            "audio_desc": desc,
            "audio_duration_s": round(len(audio) / sample_rate, 3),
            "triggered": triggered,
            "total_frames_processed": total_frames,
            "threshold": threshold,
            "cooldown_ms": cooldown_ms,
            "events_count": len(events),
            "events": events,
            "processing_time_ms": round(latency_ms, 2),
        })

    def _handle_stt_test(self, body: dict) -> None:
        """Run Faster-Whisper Speech-to-Text inference."""
        audio, sample_rate, desc = load_audio_from_request(body)
        model_name = body.get("model", "base.en")
        device = body.get("device", "cpu")
        compute_type = body.get("compute_type", "int8")
        beam_size = int(body.get("beam_size", 1))
        reference_text = body.get("reference_text", "").strip()
        use_mock = bool(body.get("use_mock", False))

        if use_mock:
            t0 = time.perf_counter()
            mock_stt = MockSTT(transcript="tell me a story")
            res: TranscriptionResult = mock_stt.transcribe(audio, sample_rate=sample_rate)
            inference_time = time.perf_counter() - t0
            self._send_json({
                "status": "SUCCESS",
                "badge": "MOCK TEST",
                "is_mock": True,
                "model": "mock",
                "transcript": res.text,
                "audio_desc": desc,
                "audio_duration_s": round(res.duration_s, 3),
                "inference_time_s": round(inference_time, 3),
                "rtf": round(inference_time / res.duration_s, 2) if res.duration_s > 0 else 0,
            })
            return

        # Check local model availability
        if not check_hf_cache(model_name):
            self._send_json({
                "status": "BLOCKED",
                "badge": "BLOCKED — MODEL NOT DOWNLOADED",
                "model": model_name,
                "error": (
                    f"Model '{model_name}' is not present in local cache (~/.cache/huggingface/hub). "
                    "Automatic downloads are blocked to respect local-only testing rules. "
                    "Please select the locally cached 'base.en' model."
                ),
                "audio_desc": desc,
            })
            return

        # Load / reuse STT engine
        cache_key = f"{model_name}_{device}_{compute_type}_{beam_size}"
        load_time_s = 0.0

        if cache_key not in _STT_CACHE:
            t_load = time.perf_counter()
            try:
                stt = FasterWhisperSTT(
                    model=model_name,
                    device=device,
                    compute_type=compute_type,
                    beam_size=beam_size,
                )
                stt._load()
                load_time_s = time.perf_counter() - t_load
                _STT_CACHE[cache_key] = stt
            except Exception as exc:
                self._send_json({
                    "status": "FAILED",
                    "badge": "FAILED",
                    "error": f"Failed to load Faster-Whisper model '{model_name}': {exc}",
                }, status=500)
                return
        else:
            stt = _STT_CACHE[cache_key]

        # Run inference
        t0 = time.perf_counter()
        res = stt.transcribe(audio, sample_rate=sample_rate)
        inference_time_s = time.perf_counter() - t0
        rtf = inference_time_s / res.duration_s if res.duration_s > 0 else 0.0

        wer_info = None
        if reference_text:
            wer_score, wer_details = compute_wer(reference_text, res.text)
            wer_info = {
                "score": round(wer_score, 4),
                "percentage": f"{wer_score * 100:.1f}%",
                "details": wer_details,
                "reference": reference_text,
                "normalized_ref": normalize_for_wer(reference_text),
                "normalized_hyp": normalize_for_wer(res.text),
            }

        self._send_json({
            "status": "SUCCESS",
            "badge": "REAL INFERENCE",
            "is_mock": False,
            "model": model_name,
            "device": device,
            "compute_type": compute_type,
            "beam_size": beam_size,
            "transcript": res.text,
            "language": res.language,
            "audio_desc": desc,
            "audio_duration_s": round(res.duration_s, 3),
            "inference_time_s": round(inference_time_s, 3),
            "load_time_s": round(load_time_s, 3) if load_time_s > 0 else None,
            "rtf": round(rtf, 3),
            "segments": res.segments,
            "wer": wer_info,
            "error": res.error,
        })

    def _handle_tts_test(self, body: dict) -> None:
        """Run Piper TTS (or MockTTS) speech synthesis."""
        text = body.get("text", "Hello Alex! I am LUMI.").strip()
        length_scale = float(body.get("length_scale", 1.1))
        use_mock = bool(body.get("use_mock", False))

        cfg = LumiConfig.load()
        model_path = PROJECT_ROOT / cfg.tts.model_path
        cfg_path = PROJECT_ROOT / cfg.tts.config_path
        model_exists = is_valid_piper_model(model_path, cfg_path)

        import importlib.util
        piper_installed = importlib.util.find_spec("piper") is not None

        if not use_mock:
            if not model_exists or not piper_installed:
                reasons = []
                if not model_exists:
                    reasons.append(f"Model/config file missing: {cfg.tts.model_path}")
                if not piper_installed:
                    reasons.append("piper-tts library is not installed")
                self._send_json({
                    "status": "BLOCKED",
                    "badge": "BLOCKED — MODEL / DEPENDENCY MISSING",
                    "module": "Piper TTS",
                    "model_path": cfg.tts.model_path,
                    "error": " & ".join(reasons) + ". Piper TTS synthesis with real voice is not available.",
                    "text": text,
                })
                return

            try:
                t0 = time.perf_counter()
                tts = PiperTTS(
                    model_path=str(model_path),
                    config_path=str(cfg_path),
                    output_dir=str(TEMP_DIR),
                    length_scale=length_scale,
                )
                res: TTSResult = tts.synthesize(text, length_scale=length_scale)
                synth_time_s = time.perf_counter() - t0
                badge = "REAL INFERENCE"
                is_mock = False
            except Exception as exc:
                self._send_json({
                    "status": "FAILED",
                    "badge": "FAILED",
                    "error": str(exc),
                }, status=500)
                return
        else:
            t0 = time.perf_counter()
            tts = MockTTS(duration_s=0.5, use_tone=True)
            res = tts.synthesize(text)
            synth_time_s = time.perf_counter() - t0
            badge = "MOCK TEST"
            is_mock = True

        # Write output to dedicated temporary directory
        h = hashlib.sha256(f"{text}_{badge}_{time.time()}".encode("utf-8")).hexdigest()[:10]
        out_name = f"tts_output_{h}.wav"
        out_path = TEMP_DIR / out_name
        _write_wav(out_path, res.audio, res.sample_rate)

        rel_path = out_path.relative_to(REPO_ROOT).as_posix()
        audio_url = f"/api/audio?path={urllib.parse.quote(rel_path)}"

        self._send_json({
            "status": "SUCCESS",
            "badge": badge,
            "is_mock": is_mock,
            "text": text,
            "sample_rate": res.sample_rate,
            "duration_s": round(res.duration_s, 3),
            "synthesis_time_s": round(synth_time_s, 4),
            "output_file": out_name,
            "audio_url": audio_url,
            "file_size_bytes": out_path.stat().st_size,
            "error": res.error,
        })

    def _handle_pipeline_test(self, body: dict) -> None:
        """Run End-to-End Pipeline test through LUMI modules."""
        audio, sample_rate, desc = load_audio_from_request(body)
        allow_mocks = bool(body.get("allow_mocks", True))
        skip_wake_word = bool(body.get("skip_wake_word", False))
        vad_threshold = float(body.get("vad_threshold", 0.5))

        stages = []
        overall_t0 = time.perf_counter()

        # ------------------------------------------------------------------
        # Stage 1: Audio Input Preparation
        # ------------------------------------------------------------------
        s1_t0 = time.perf_counter()
        dur_s = len(audio) / sample_rate
        stages.append({
            "id": "audio_input",
            "name": "1. Audio Input",
            "status": "REAL",
            "badge": "INPUT AUDIO",
            "latency_ms": round((time.perf_counter() - s1_t0) * 1000, 2),
            "output": f"{desc} ({dur_s:.2f}s, {len(audio)} samples)",
            "details": {
                "duration_s": round(dur_s, 2),
                "sample_rate": sample_rate,
                "samples": len(audio),
            },
        })

        # ------------------------------------------------------------------
        # Stage 2: Wake Word Detection
        # ------------------------------------------------------------------
        s2_t0 = time.perf_counter()
        if skip_wake_word:
            stages.append({
                "id": "wake_word",
                "name": "2. Wake Word Detection",
                "status": "SKIPPED",
                "badge": "SKIPPED (BYPASSED)",
                "latency_ms": 0.0,
                "output": "Wake-word stage skipped by user request",
                "details": {},
            })
        else:
            # Check if real wake word model is available
            cfg = LumiConfig.load()
            ww_path = cfg.wake_word.resolve_model_path()
            if not ww_path.exists() and not allow_mocks:
                stages.append({
                    "id": "wake_word",
                    "name": "2. Wake Word Detection",
                    "status": "BLOCKED",
                    "badge": "BLOCKED — MODEL MISSING",
                    "latency_ms": round((time.perf_counter() - s2_t0) * 1000, 2),
                    "output": f"Missing model: {ww_path}",
                    "details": {},
                })
                self._send_json({"status": "BLOCKED", "stages": stages, "error": "Wake word model missing"})
                return

            ww_detector = MockWakeWordDetector(trigger_at_frame=0, score=0.95, threshold=0.6)
            ww_event = ww_detector.process_frame(audio[:1280] if len(audio) >= 1280 else np.zeros(1280, dtype=np.int16))
            stages.append({
                "id": "wake_word",
                "name": "2. Wake Word Detection",
                "status": "MOCK",
                "badge": "MOCK FALLBACK",
                "latency_ms": round((time.perf_counter() - s2_t0) * 1000, 2),
                "output": f"Triggered: model='{ww_event.model_name}', score={ww_event.score:.2f}",
                "details": {
                    "event": {"model": ww_event.model_name, "score": ww_event.score},
                },
            })

        # ------------------------------------------------------------------
        # Stage 3: Voice Activity Detection (VAD)
        # ------------------------------------------------------------------
        s3_t0 = time.perf_counter()
        # Use MockVAD for fallback when torch is absent
        vad = MockVAD(force_speech=None)
        vad_res = vad.process(audio)
        speech_audio = vad_res.speech_audio if vad_res.contains_speech else audio
        stages.append({
            "id": "vad",
            "name": "3. Voice Activity Detection (VAD)",
            "status": "MOCK",
            "badge": "MOCK FALLBACK",
            "latency_ms": round((time.perf_counter() - s3_t0) * 1000, 2),
            "output": f"contains_speech={vad_res.contains_speech}, speech_ratio={vad_res.speech_ratio:.2f}",
            "details": {
                "contains_speech": vad_res.contains_speech,
                "speech_ratio": round(vad_res.speech_ratio, 2),
                "samples_retained": len(speech_audio),
            },
        })

        # ------------------------------------------------------------------
        # Stage 4: Speech-to-Text (STT) - Faster-Whisper REAL INFERENCE
        # ------------------------------------------------------------------
        s4_t0 = time.perf_counter()
        transcript = ""
        stt_status = "REAL"
        stt_badge = "REAL INFERENCE"

        if check_hf_cache("faster-whisper-base.en"):
            try:
                stt_key = "base.en_cpu_int8_1"
                if stt_key not in _STT_CACHE:
                    _STT_CACHE[stt_key] = FasterWhisperSTT(model="base.en", device="cpu", compute_type="int8")
                    _STT_CACHE[stt_key]._load()
                stt = _STT_CACHE[stt_key]
                trans_res = stt.transcribe(speech_audio, sample_rate=sample_rate)
                transcript = trans_res.text
            except Exception as exc:
                transcript = f"STT failed: {exc}"
                stt_status = "FAILED"
                stt_badge = "FAILED"
        elif allow_mocks:
            mock_stt = MockSTT(transcript="tell me a story")
            trans_res = mock_stt.transcribe(speech_audio)
            transcript = trans_res.text
            stt_status = "MOCK"
            stt_badge = "MOCK FALLBACK"
        else:
            stages.append({
                "id": "stt",
                "name": "4. Speech-to-Text (STT)",
                "status": "BLOCKED",
                "badge": "BLOCKED — MODEL MISSING",
                "latency_ms": 0.0,
                "output": "Faster-Whisper base.en not available in cache",
                "details": {},
            })
            self._send_json({"status": "BLOCKED", "stages": stages, "error": "STT model missing"})
            return

        stages.append({
            "id": "stt",
            "name": "4. Speech-to-Text (STT)",
            "status": stt_status,
            "badge": stt_badge,
            "latency_ms": round((time.perf_counter() - s4_t0) * 1000, 2),
            "output": f"Transcript: \"{transcript}\"",
            "details": {
                "model": "base.en",
                "transcript": transcript,
            },
        })

        # ------------------------------------------------------------------
        # Stage 5: Intent Classification & Routing (REAL Content Catalog)
        # ------------------------------------------------------------------
        s5_t0 = time.perf_counter()
        normalized_transcript = normalize_text(transcript) if transcript else "tell me a story"
        classification = classify_intent(normalized_transcript)
        router = get_cached_router()
        routing_res = router.route(classification)

        stages.append({
            "id": "intent_routing",
            "name": "5. Intent Classification & Routing",
            "status": "REAL",
            "badge": "REAL CLASSIFIER & CATALOG",
            "latency_ms": round((time.perf_counter() - s5_t0) * 1000, 2),
            "output": f"Intent: {classification.intent.value} (conf={classification.confidence:.2f}) -> \"{routing_res.response_text[:80]}...\"",
            "details": {
                "intent": classification.intent.value,
                "confidence": round(classification.confidence, 2),
                "matched_pattern": classification.matched_pattern,
                "response_text": routing_res.response_text,
            },
        })

        # ------------------------------------------------------------------
        # Stage 6: Text-to-Speech (TTS) Response Synthesis
        # ------------------------------------------------------------------
        s6_t0 = time.perf_counter()
        tts_mock = MockTTS(duration_s=0.5, use_tone=True)
        tts_res = tts_mock.synthesize(routing_res.response_text)
        
        # Save response audio
        h = hashlib.sha256(f"pipeline_{time.time()}".encode("utf-8")).hexdigest()[:8]
        out_name = f"pipeline_resp_{h}.wav"
        out_path = TEMP_DIR / out_name
        _write_wav(out_path, tts_res.audio, tts_res.sample_rate)

        rel_path = out_path.relative_to(REPO_ROOT).as_posix()
        audio_url = f"/api/audio?path={urllib.parse.quote(rel_path)}"

        stages.append({
            "id": "tts",
            "name": "6. Text-to-Speech (TTS)",
            "status": "MOCK",
            "badge": "MOCK FALLBACK",
            "latency_ms": round((time.perf_counter() - s6_t0) * 1000, 2),
            "output": f"Synthesized {tts_res.duration_s:.2f}s audio response",
            "details": {
                "audio_url": audio_url,
                "duration_s": tts_res.duration_s,
                "sample_rate": tts_res.sample_rate,
            },
        })

        total_time_ms = (time.perf_counter() - overall_t0) * 1000.0

        self._send_json({
            "status": "SUCCESS",
            "badge": "PIPELINE COMPLETED",
            "total_time_ms": round(total_time_ms, 2),
            "total_time_s": round(total_time_ms / 1000.0, 2),
            "transcript": transcript,
            "intent": classification.intent.value,
            "response_text": routing_res.response_text,
            "response_audio_url": audio_url,
            "stages": stages,
        })

    def _handle_clear_temp(self) -> None:
        """Clear temporary outputs from temp_outputs/ directory."""
        cleared_count = 0
        for f in TEMP_DIR.glob("*.wav"):
            try:
                f.unlink()
                cleared_count += 1
            except Exception:
                pass
        self._send_json({
            "status": "SUCCESS",
            "message": f"Cleared {cleared_count} temporary audio files.",
        })


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server_address = (host, port)
    httpd = http.server.ThreadingHTTPServer(server_address, VoiceLabRequestHandler)
    print("=" * 65)
    print("  LUMI — Temporary Voice Modules Testing Lab")
    print(f"  URL: http://{host}:{port}")
    print(f"  Root Dir: {REPO_ROOT}")
    print(f"  Temp Out: {TEMP_DIR}")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Voice Lab server...")
        httpd.server_close()
        print("Voice Lab server stopped cleanly.")

main = run_server


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LUMI Voice Modules Testing Lab")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
