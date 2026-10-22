"""
Automated functional verification for LUMI Voice Lab API.
Starts the server in a background thread, tests all endpoints, and verifies responses.
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.voice_lab.server import VoiceLabRequestHandler, http

PORT = 8766
BASE_URL = f"http://127.0.0.1:{PORT}"


def run_tests():
    print(f"Testing Voice Lab Server on {BASE_URL}...")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), VoiceLabRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)

    passed = 0
    total = 0

    def assert_test(name: str, condition: bool, details: str = ""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"  [PASS] {name} {details}")
        else:
            print(f"  [FAIL] {name} {details}")

    # 1. Test Static files
    req = urllib.request.urlopen(f"{BASE_URL}/")
    assert_test("GET / (index.html)", req.status == 200 and "LUMI Voice Lab" in req.read().decode())

    req_css = urllib.request.urlopen(f"{BASE_URL}/style.css")
    assert_test("GET /style.css", req_css.status == 200 and "badge-real" in req_css.read().decode())

    req_js = urllib.request.urlopen(f"{BASE_URL}/app.js")
    assert_test("GET /app.js", req_js.status == 200 and "loadSystemStatus" in req_js.read().decode())

    req_dev = urllib.request.urlopen(f"{BASE_URL}/dev")
    assert_test("GET /dev (dev.html)", req_dev.status == 200 and "Developer Testbed" in req_dev.read().decode())

    # 2. Test /api/status
    req_status = urllib.request.urlopen(f"{BASE_URL}/api/status")
    status_data = json.loads(req_status.read().decode())
    assert_test("GET /api/status", "dependencies" in status_data and "models" in status_data)
    assert_test(
        "Status: Faster-Whisper base.en found",
        status_data["models"]["stt_base_en"]["available"] is True
    )
    assert_test(
        "Status: Wake-word model absent (not fabricated)",
        status_data["models"]["wake_word"]["available"] is False
    )

    def post_json(path: str, data: dict) -> dict:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    # 3. Test VAD native execution (Real Silero VAD Inference)
    vad_native = post_json("/api/vad/test", {
        "source_type": "synthetic",
        "synthetic_type": "tone",
        "use_mock": False,
    })
    assert_test("VAD Native Execution (Real Silero Inference)", vad_native.get("status") == "SUCCESS" and vad_native.get("badge") == "REAL INFERENCE")

    # 4. Test VAD mock (tone -> contains_speech=True)
    vad_mock_tone = post_json("/api/vad/test", {
        "source_type": "synthetic",
        "synthetic_type": "tone",
        "use_mock": True,
    })
    assert_test("VAD Mock Tone Speech Detected", vad_mock_tone.get("contains_speech") is True)

    # 5. Test VAD mock (silence -> contains_speech=False)
    vad_mock_silence = post_json("/api/vad/test", {
        "source_type": "synthetic",
        "synthetic_type": "silence",
        "use_mock": True,
    })
    assert_test("VAD Mock Silence No Speech", vad_mock_silence.get("contains_speech") is False)

    # 6. Test Wake-word Native (should be BLOCKED — MODEL MISSING)
    ww_native = post_json("/api/wake_word/test", {
        "source_type": "synthetic",
        "synthetic_type": "tone",
        "use_mock": False,
    })
    assert_test("Wake-Word Native Blocked — Model Missing", ww_native.get("status") == "BLOCKED" and "hey_lumi.onnx" in ww_native.get("error", ""))

    # 7. Test Wake-word Mock (triggered=True)
    ww_mock = post_json("/api/wake_word/test", {
        "source_type": "synthetic",
        "synthetic_type": "tone",
        "use_mock": True,
    })
    assert_test("Wake-Word Mock Triggered", ww_mock.get("triggered") is True and ww_mock.get("events_count", 0) >= 1)

    # 8. Test Faster-Whisper tiny.en (Real Inference Executed)
    stt_tiny = post_json("/api/stt/test", {
        "source_type": "synthetic",
        "synthetic_type": "silence",
        "synthetic_duration": 1.0,
        "model": "tiny.en",
        "use_mock": False,
    })
    assert_test("STT tiny.en Real Inference Executed", stt_tiny.get("status") == "SUCCESS" and stt_tiny.get("badge") == "REAL INFERENCE")

    # 9. Test Faster-Whisper base.en REAL INFERENCE on synthetic silence
    stt_base = post_json("/api/stt/test", {
        "source_type": "synthetic",
        "synthetic_type": "silence",
        "synthetic_duration": 1.0,
        "model": "base.en",
        "use_mock": False,
    })
    assert_test("STT base.en Real Inference Executed", stt_base.get("status") == "SUCCESS" and stt_base.get("badge") == "REAL INFERENCE")

    # 10. Test Faster-Whisper base.en REAL INFERENCE on JIBO sample with WER
    samples = status_data.get("samples", [])
    if samples:
        sample_path = samples[0]["path"]
        ref_text = samples[0].get("ref_text", "B M U C")
        stt_jibo = post_json("/api/stt/test", {
            "source_type": "sample",
            "sample_path": sample_path,
            "max_duration_s": 5.0,
            "model": "base.en",
            "reference_text": ref_text,
            "use_mock": False,
        })
        assert_test("STT JIBO Audio Transcription", stt_jibo.get("status") == "SUCCESS" and len(stt_jibo.get("transcript", "")) > 0)
        assert_test("STT WER Calculation", "wer" in stt_jibo and stt_jibo["wer"] is not None)

    # 11. Test TTS Native Execution
    tts_native = post_json("/api/tts/test", {
        "text": "Hello Alex!",
        "use_mock": False,
    })
    assert_test("TTS Native Execution (Real Model Synthesis)", tts_native.get("status") == "SUCCESS" and tts_native.get("badge") == "REAL INFERENCE")

    # 12. Test TTS Mock Audio Generation
    tts_mock = post_json("/api/tts/test", {
        "text": "Hello Alex! I am LUMI.",
        "use_mock": True,
    })
    assert_test("TTS Mock WAV Audio Generated", tts_mock.get("status") == "SUCCESS" and tts_mock.get("audio_url") is not None)

    # Check generated audio can be streamed via /api/audio
    if tts_mock.get("audio_url"):
        audio_stream = urllib.request.urlopen(f"{BASE_URL}{tts_mock['audio_url']}")
        assert_test("Audio Streaming /api/audio", audio_stream.status == 200 and audio_stream.headers.get("Content-Type") == "audio/wav")

    # 13. Test End-to-End Pipeline
    pipe_res = post_json("/api/pipeline/test", {
        "source_type": "synthetic",
        "synthetic_type": "tone",
        "allow_mocks": True,
        "skip_wake_word": False,
    })
    assert_test("E2E Pipeline Execution Success", pipe_res.get("status") == "SUCCESS" and len(pipe_res.get("stages", [])) == 6)
    assert_test("E2E Pipeline Response Text", len(pipe_res.get("response_text", "")) > 0)
    assert_test("E2E Pipeline Response Audio URL", pipe_res.get("response_audio_url") is not None)

    # =========================================================================
    # 14. Interactive Turn Tests (Live Conversation, Real Content, Real STT)
    # =========================================================================

    # 14a. Interactive Turn 1: Typed input "What is the letter A?"
    turn1 = post_json("/api/interactive/turn", {
        "text": "What is the letter A?",
        "require_wake_word": False,
        "enable_tts": False,
    })
    assert_test("Interactive Turn 1 (Letter A)", turn1.get("status") == "SUCCESS")
    assert_test("Turn 1 LUMI Response Content", "letter A" in turn1.get("response_text", "") or "apple" in turn1.get("response_text", "").lower())
    assert_test("Turn 1 Diagnostic Stages (9 stages)", len(turn1.get("stages", [])) == 9)

    # 14b. Interactive Turn 2: Follow-up typed input "tell me about elephants"
    turn2 = post_json("/api/interactive/turn", {
        "text": "Hey LUMI, tell me about elephants.",
        "require_wake_word": False,
        "enable_tts": False,
    })
    assert_test("Interactive Turn 2 (Elephants)", turn2.get("status") == "SUCCESS")
    assert_test("Turn 2 LUMI Animal Response", "elephant" in turn2.get("response_text", "").lower() or "animal" in turn2.get("response_text", "").lower() or "trunk" in turn2.get("response_text", "").lower())

    # 14c. Interactive Turn 3: Counting prompt "Can you count from one to ten?"
    turn3 = post_json("/api/interactive/turn", {
        "text": "Can you count from one to ten?",
        "require_wake_word": False,
        "enable_tts": False,
    })
    assert_test("Interactive Turn 3 (Counting)", turn3.get("status") == "SUCCESS")
    assert_test("Turn 3 Counting Response", "1" in turn3.get("response_text", "") or "one" in turn3.get("response_text", "").lower())

    # 14c-1. Interactive Turn with Wake Word in Text: "Hey LUMI, what is the letter A?"
    turn_ww_text = post_json("/api/interactive/turn", {
        "text": "Hey LUMI, what is the letter A?",
        "require_wake_word": True,
        "enable_tts": True,
    })
    assert_test("Interactive Typed Wake Word Confirmed", turn_ww_text.get("status") == "SUCCESS")
    assert_test("Typed Wake Word Stage Passed", any(s.get("id") == "wake_word" and s.get("status") == "Passed" for s in turn_ww_text.get("stages", [])))
    assert_test("Typed Turn TTS Audio URL Generated", bool(turn_ww_text.get("tts_audio_url")))
    assert_test("Typed Turn 9 Stages Present", len(turn_ww_text.get("stages", [])) == 9)

    # 14c-2. Interactive Turn with Wake Word Missing in Text: "What is the letter A?" with require_wake_word=True
    turn_ww_miss = post_json("/api/interactive/turn", {
        "text": "What is the letter A?",
        "require_wake_word": True,
        "enable_tts": False,
    })
    assert_test("Interactive Typed Wake Word Blocked Gracefully", turn_ww_miss.get("status") == "BLOCKED")
    assert_test("Typed Wake Word Stage Blocked", any(s.get("id") == "wake_word" and s.get("status") == "Blocked" for s in turn_ww_miss.get("stages", [])))
    assert_test("Typed Wake Word Missing 9 Stages Present", len(turn_ww_miss.get("stages", [])) == 9)

    # 14c-3. Interactive Turn with Slow Speech Speed (length_scale = 1.15)
    turn_slow = post_json("/api/interactive/turn", {
        "text": "Tell me a story",
        "require_wake_word": False,
        "enable_tts": True,
        "speech_speed": "slow",
    })
    assert_test("Interactive Slow Speech Speed", turn_slow.get("status") == "SUCCESS" and turn_slow.get("speech_speed") == "slow" and bool(turn_slow.get("tts_audio_url")))

    # 14c-4. Interactive Turn with Normal Speech Speed (length_scale = 1.0)
    turn_normal = post_json("/api/interactive/turn", {
        "text": "Tell me a story",
        "require_wake_word": False,
        "enable_tts": True,
        "speech_speed": "normal",
    })
    assert_test("Interactive Normal Speech Speed", turn_normal.get("status") == "SUCCESS" and turn_normal.get("speech_speed") == "normal" and bool(turn_normal.get("tts_audio_url")))

    # 14d. Interactive Turn 4: Audio WAV upload via multipart/form-data
    import io

    import wave
    import numpy as np

    # Generate 16 kHz 16-bit PCM WAV in memory
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio_samples = (np.sin(2 * np.pi * 440.0 * t) * 12000).astype(np.int16)
        wf.writeframes(audio_samples.tobytes())
    wav_bytes = wav_io.getvalue()

    def post_multipart(path: str, fields: dict, files: dict) -> dict:
        boundary = "----WebKitFormBoundary" + os.urandom(16).hex()
        body = bytearray()
        for k, v in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
            body.extend(f"{v}\r\n".encode("utf-8"))
        for k, (fname, fdata, ctype) in files.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'.encode("utf-8"))
            body.extend(f"Content-Type: {ctype}\r\n\r\n".encode("utf-8"))
            body.extend(fdata)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    turn4_audio = post_multipart(
        "/api/interactive/turn",
        fields={"require_wake_word": "false", "enable_tts": "false"},
        files={"audio_file": ("microphone_test.wav", wav_bytes, "audio/wav")},
    )
    assert_test("Interactive Audio Turn Processed", turn4_audio.get("status") in ("SUCCESS", "FAILED"))
    assert_test("Audio Turn 9 Stages Present", len(turn4_audio.get("stages", [])) == 9)
    # Microphone Capture and Audio Validation must be PASSED
    stage_names = {s["name"]: s["status"].upper() for s in turn4_audio.get("stages", [])}
    assert_test("Stage: Microphone Capture Passed", stage_names.get("1. Microphone Capture") == "PASSED")
    assert_test("Stage: Audio Validation Passed", stage_names.get("2. Audio Validation") == "PASSED")

    # 14e. Interactive Turn 5: Real Speech Audio WAV via multipart (Real Faster-Whisper base.en)
    if samples:
        speech_wav_path = REPO_ROOT / samples[0]["path"]
        if speech_wav_path.exists():
            from src.audio_source import _load_wav_as_int16
            audio_raw = _load_wav_as_int16(speech_wav_path)[:16000 * 3]
            speech_io = io.BytesIO()
            with wave.open(speech_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_raw.tobytes())
            speech_bytes = speech_io.getvalue()

            turn5_speech = post_multipart(
                "/api/interactive/turn",
                fields={"require_wake_word": "false", "enable_tts": "false"},
                files={"audio_file": ("microphone_speech.wav", speech_bytes, "audio/wav")},
            )
            assert_test("Interactive Speech Audio Turn Success", turn5_speech.get("status") == "SUCCESS")
            assert_test("Speech Audio Transcribed by Real Whisper", len(turn5_speech.get("transcript", "")) > 0)
            assert_test("Speech Audio LUMI Response Generated", len(turn5_speech.get("response_text", "")) > 0)
            assert_test("Speech Audio Turn 9 Stages Present", len(turn5_speech.get("stages", [])) == 9)

    # 15. Educational Endpoints & Piper TTS Speak API
    req_cat = urllib.request.urlopen(f"{BASE_URL}/api/educational/catalog")
    cat_data = json.loads(req_cat.read().decode())
    assert_test("Educational Catalog API", cat_data.get("status") == "SUCCESS" and len(cat_data.get("items", [])) >= 8)

    req_quiz = urllib.request.urlopen(f"{BASE_URL}/api/educational/quiz")
    quiz_data = json.loads(req_quiz.read().decode())
    assert_test("Educational Quiz API", quiz_data.get("status") == "SUCCESS" and len(quiz_data.get("questions", [])) >= 1)

    req_stories = urllib.request.urlopen(f"{BASE_URL}/api/educational/stories")
    stories_data = json.loads(req_stories.read().decode())
    assert_test("Educational Stories API", stories_data.get("status") == "SUCCESS" and len(stories_data.get("stories", [])) >= 1)

    tts_speak = post_json("/api/tts/speak", {
        "text": "Hello friend! Welcome to LUMI.",
        "speech_speed": "slow",
    })
    assert_test("Piper TTS Speak API (Slow 1.15)", tts_speak.get("status") == "SUCCESS" and bool(tts_speak.get("audio_url")))

    # 16. Multi-Phrase Wake-Word Endpoints & Greeting Verification
    req_phrases = urllib.request.urlopen(f"{BASE_URL}/api/wake_word/phrases")
    phrases_data = json.loads(req_phrases.read().decode())
    assert_test("Wake Phrases GET API Success", phrases_data.get("status") == "SUCCESS")
    assert_test("Wake Phrases Total Exactly 8", phrases_data.get("total_phrases") == 8)
    assert_test("Wake Phrases Truthful Needs Training Status", phrases_data.get("needs_training_count") == 8)

    # Test toggling phrase and updating threshold
    post_phrase = post_json("/api/wake_word/phrases", {
        "phrase": "Good morning, LUMI",
        "enabled": True,
        "threshold": 0.65,
    })
    assert_test("Wake Phrases POST API Success", post_phrase.get("status") == "SUCCESS")

    # Test interactive turn with "Good morning, LUMI"
    turn_gm = post_json("/api/interactive/turn", {
        "text": "Good morning LUMI",
        "require_wake_word": True,
        "enable_tts": False,
    })
    assert_test("Interactive Multi-Phrase Turn (Good Morning)", turn_gm.get("status") == "SUCCESS")
    assert_test("Multi-Phrase Greeting Content", "good morning" in turn_gm.get("response_text", "").lower())

    # 17. Test Clear Temp
    clear_res = post_json("/api/clear_temp", {})
    assert_test("Clear Temp API", clear_res.get("status") == "SUCCESS")


    server.shutdown()
    server.server_close()

    print("\n" + "=" * 50)
    print(f"Voice Lab Verification Summary: {passed}/{total} Passed")
    print("=" * 50)
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    import sys
    sys.exit(0 if success else 1)
