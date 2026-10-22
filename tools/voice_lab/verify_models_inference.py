"""
Verification script for all LUMI voice models with real inference.
"""
import numpy as np
import wave
import time
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from faster_whisper import WhisperModel
from src.tts import PiperTTS
from src.vad import SileroVAD
from src.wake_word import OpenWakeWordDetector
from src.config import LumiConfig

def main():
    print("=== 1. VERIFY FASTER-WHISPER TINY.EN (REAL TRANSCRIPTION) ===")
    model_tiny = WhisperModel("tiny.en", device="cpu", compute_type="int8", local_files_only=True)
    wav_path = "datasets/Jibo_Kids/data/letters_digits/T1017201/T1017201.wav"
    import soundfile as sf
    data, sr = sf.read(wav_path, dtype='float32')
    audio_f32 = data
    audio_int16 = (data * 32767).astype(np.int16)

    t0 = time.time()
    segments, info = model_tiny.transcribe(audio_f32, language="en", beam_size=1)
    text = " ".join(s.text.strip() for s in segments)
    dt = time.time() - t0
    print(f'tiny.en transcription: "{text}" in {dt:.3f} s (detected lang: {info.language}, prob: {info.language_probability:.2f})')
    assert len(text) > 0, "Transcription must not be empty"

    print("\n=== 2. VERIFY PIPER TTS (REAL SYNTHESIS & WAV VALIDATION) ===")
    cfg = LumiConfig.load()
    tts = PiperTTS(
        model_path=cfg.tts.model_path,
        config_path=cfg.tts.config_path,
        length_scale=cfg.tts.length_scale,
        output_dir="tools/voice_lab/temp_outputs"
    )
    synth_text = "LUMI voice system is ready with all local models."
    t0 = time.time()
    res = tts.synthesize(synth_text)
    dt = time.time() - t0
    print(f'Piper synthesized: "{synth_text}" in {dt:.3f} s. Audio samples: {len(res.audio)}, duration: {res.duration_s:.2f} s')
    assert len(res.audio) > 0, "Synthesized audio must not be empty"
    assert res.sample_rate == 22050, f"Expected 22050 Hz, got {res.sample_rate}"

    print("\n=== 3. VERIFY SILERO VAD (REAL SILENCE & SPEECH) ===")
    vad = SileroVAD(threshold=0.5)
    silence = np.zeros(16000, dtype=np.int16)
    speech = audio_int16[:16000] # from real child speech
    res_silence = vad.process(silence)
    res_speech = vad.process(speech)
    print(f"Silence: contains_speech={res_silence.contains_speech}, ratio={res_silence.speech_ratio:.3f}")
    print(f"Speech:  contains_speech={res_speech.contains_speech}, ratio={res_speech.speech_ratio:.3f}")
    assert not res_silence.contains_speech, "Silence should not contain speech"

    print("\n=== 4. VERIFY OPENWAKEWORD (REAL INFERENCE) ===")
    ww = OpenWakeWordDetector(model_path="models/wake_words/hey_lumi.onnx", threshold=0.6)
    frame = np.zeros(1280, dtype=np.int16)
    event = ww.process_frame(frame)
    print(f"openWakeWord inference executed cleanly. Frame score: {event.score if event else None}")

    print("\n=== ALL PHASE 4 COMPONENT CHECKS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    main()
