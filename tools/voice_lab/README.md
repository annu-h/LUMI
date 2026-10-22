# LUMI Voice Modules Testing Lab

A temporary, local-only developer interface for testing and benchmarking LUMI's voice modules independently.

## Features
- **Silero VAD Panel**: Test speech/silence detection, boundary expansion, threshold, and silence duration.
- **Wake-Word Panel**: Test openWakeWord scoring, threshold comparison, and cooldown verification (reports `BLOCKED — MODEL MISSING` when `hey_lumi.onnx` is absent).
- **Faster-Whisper STT Panel**: Run real model inference on CPU `int8` with locally cached `base.en`, inspect inference time, real-time factor (RTF), and compute WER on JIBO Kids corpus samples.
- **Piper TTS Panel**: Test speech synthesis, length scaling, and audio playback (reports `BLOCKED` when Piper voice model is missing; supports MockTTS audio generation).
- **End-to-End Pipeline Panel**: Run the complete voice interaction flow: Audio &rarr; VAD &rarr; Wake Word &rarr; STT &rarr; Intent Classification & Routing &rarr; TTS.

---

## How to Start

Run the following command from the repository root:

```powershell
python tools/voice_lab/server.py
```

Then open your browser and navigate to:
[http://127.0.0.1:8765](http://127.0.0.1:8765)

Optional arguments:
- `--port 8765` (custom port)
- `--host 127.0.0.1` (local interface only)

---

## How to Stop

Press **`Ctrl + C`** in the terminal where `server.py` is running.

---

## Temporary Cleanup Instructions

This interface is completely temporary and isolated. None of LUMI's production codebase or startup flows were altered.

To remove this testing interface in the future, simply delete this directory:

```powershell
Remove-Item -Recurse -Force tools/voice_lab
```
