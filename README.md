# LUMI — Voice Processing System
# Setup and offline operation guide.

## Prerequisites
- Python 3.11+ (tested on 3.13.7)
- pip (bundled with Python)
- Windows, macOS, or Linux

## Install Dependencies

### Core dependencies (always required)
```bash
pip install -r requirements.txt
```

### Stage 3: VAD + Wake Word
```bash
pip install silero-vad openwakeword
```

### Stage 4: STT (already installed)
```bash
# faster-whisper is pre-installed in the dev environment.
```

### Stage 5: TTS
```bash
pip install piper-tts
```

## Model and Voice Asset Locations

| Asset | Location | Notes |
|-------|----------|-------|
| Wake-word model | `models/wake_words/hey_lumi.onnx` | Must be legitimately obtained; not fabricated |
| TTS voice model | `models/tts/en_US-lessac-medium.onnx` | Download from HuggingFace |
| TTS config | `models/tts/en_US-lessac-medium.onnx.json` | Paired with voice model |
| Generated audio | `audio/generated/` | Cached TTS output |

## How to Obtain Models

### Faster-Whisper (STT)
Models are downloaded automatically on first use by the faster-whisper library.
To pre-download:
```bash
python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8')"
```

### Piper TTS (voice models)
Download from: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium
Required files:
- `en_US-lessac-medium.onnx`
- `en_US-lessac-medium.onnx.json`

### Wake-Word (custom model)
The custom `hey_lumi.onnx` model must be trained or legitimately obtained
in openWakeWord format.  Until then, the mock detector is used for tests.
Real wake-word testing is NOT available.

## Verify Assets Are Cached Locally

```bash
# Check for STT model (in HF cache)
python -c "import os; print(os.path.expanduser('~/.cache/huggingface'))"

# Check for TTS model
ls models/tts/

# Check for wake-word model
ls models/wake_words/
```

## Run with Network Access Disabled

After all models are downloaded, run with:
```bash
LUMI_OFFLINE=1 python -m src.main
```

(Not yet implemented — see Stage 7.)

## Test Intent Classification Without AI Models

```bash
python -m pytest tests/test_intent.py -v
```

## Test Transcription with a Local Audio File

```bash
python -c "
from src.audio_source import FileAudioSource
from src.stt import FasterWhisperSTT

with FileAudioSource('audio/test.wav') as src:
    audio = src.read_frames(16000 * 10)
stt = FasterWhisperSTT(model='base.en', device='cpu', compute_type='int8')
result = stt.transcribe(audio)
print(result.text)
"
```

## Measure Transcription and TTS Latency

```bash
python -m pytest tests/test_stt_latency.py -v
python -m pytest tests/test_tts_latency.py -v
```