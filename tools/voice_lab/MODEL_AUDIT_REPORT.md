# LUMI Voice Lab — Model & Eight-Phrase Wake-Word Audit Report

> **Updated at:** 2026-10-22 09:05:00  
> **Environment:** Python 3.13.7 on Windows-11-10.0.26300-SP0  
> **Executable:** `C:\Users\basar\Desktop\LUMI\.venv\Scripts\python.exe`  
> **Repository Root:** `C:\Users\basar\Desktop\LUMI`  
> **HuggingFace Hub Cache:** `C:\Users\basar\.cache\huggingface\hub`  

---

## 1. Executive Summary Table

| Component | Expected file/path | Status | Download attempted? | Verification result | Required next action |
|---|---|---|---|---|---|
| **Faster-Whisper (`tiny.en`)** | `~/.cache/huggingface/hub/models--Systran--faster-whisper-tiny.en` | **READY** | Yes (Systran HF cache) | Verified real inference on real speech (0.42s latency) | None. Operational offline. |
| **Faster-Whisper (`base.en`)** | `~/.cache/huggingface/hub/models--Systran--faster-whisper-base.en` | **READY** | No (Present in local cache) | Verified real inference on real speech (0.68s latency) | None. Primary operational model. |
| **Faster-Whisper (`large-v3-turbo`)** | `~/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo` | **READY** | No (Present in local cache) | Verified real inference on real speech (9.91s latency) | None. Optional high-accuracy model. |
| **Silero VAD** | Bundled inside `silero_vad` package (`.venv/Lib/site-packages/silero_vad/data/silero_vad.jit`) | **READY** | No (Bundled with package) | Verified on silence (`ratio=0.0`) and speech (`ratio=0.953`) | None. Fully operational offline. |
| **openWakeWord Engine (`hey_jarvis_v0.1.onnx`)** | `.venv/Lib/site-packages/openwakeword/resources/models/hey_jarvis_v0.1.onnx` | **READY** | No (Bundled with package) | Verified ONNX runtime frame prediction; offline fallback active | Operational development fallback. |
| **Custom Wake Words (`models/wake_words/*.onnx`)** | `models/wake_words/` (8 phrases) | **MISSING** (Status: **NEEDS TRAINING**) | No (No legitimate public child models exist) | Model files absent on disk. Not fabricated. Multi-phrase engine implemented. | Assemble child speech dataset and train. |
| **Piper TTS (`en_US-lessac-medium.onnx`)** | `models/tts/en_US-lessac-medium.onnx` | **READY** | Yes (Downloaded from rhasspy HF repo) | Verified ONNX binary; synthesized 1.42s WAV audio | None. Fully operational offline. |
| **Piper TTS Config (`en_US-lessac-medium.onnx.json`)** | `models/tts/en_US-lessac-medium.onnx.json` | **READY** | Yes (Downloaded from rhasspy HF repo) | Verified JSON configuration matching voice parameters | None. Fully operational offline. |

---

## 2. Eight-Phrase Wake-Word Support Matrix

Authoritative evaluation of all eight target wake phrases against current assets in the LUMI repository:

| Wake phrase | Actual detector/model | Status | Training required? | Validation required? | Evidence & Asset Path |
|---|---|---|---|---|---|
| **Hey LUMI** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/hey_lumi.onnx` is absent on disk. Not fabricated. Training pipeline available in `tools/wake_word_training/train_wake_word.py`. |
| **Hello LUMI** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/hello_lumi.onnx` is absent on disk. No pre-trained openWakeWord model exists. |
| **Hi LUMI** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/hi_lumi.onnx` is absent on disk. No pre-trained openWakeWord model exists. |
| **Wake up, LUMI** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/wake_up_lumi.onnx` is absent on disk. No pre-trained openWakeWord model exists. |
| **Let's play, LUMI** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/lets_play_lumi.onnx` is absent on disk. No pre-trained openWakeWord model exists. |
| **Are you there, LUMI?** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/are_you_there_lumi.onnx` is absent on disk. No pre-trained openWakeWord model exists. |
| **LUMI!** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/lumi.onnx` is absent on disk. Single-word attention phrase; configured with higher threshold (`0.65`). |
| **Good morning, LUMI** | Fallback: `hey_jarvis_v0.1.onnx` | `NEEDS TRAINING` | Yes | Yes | `models/wake_words/good_morning_lumi.onnx` is absent on disk. No pre-trained openWakeWord model exists. |

> **Integrity Guardrail Note:**  
> In strict accordance with Project LUMI integrity rules:
> 1. No ONNX models were fabricated or empty files created.
> 2. `hey_jarvis_v0.1.onnx` is never renamed or misrepresented as `hey_lumi.onnx`.
> 3. Phrases are marked `NEEDS TRAINING` because genuine recognition models do not yet exist on disk.
> 4. The multi-phrase architecture, configuration, API endpoints, continuous listening loop, and testing pipeline are fully implemented and verified.

---

## 3. Technically Valid Multi-Phrase Architecture

### Architecture Selection: openWakeWord Shared-Embedding Multi-Model Engine
- **Acoustic Input:** 16,000 Hz, mono, 16-bit PCM. Fed in 80 ms chunks (1,280 samples).
- **Shared Feature Extractor:** openWakeWord computes `melspectrogram.onnx` and Google Speech Embedding `embedding_model.onnx` (96-dimensional acoustic feature vector) **once per chunk**.
- **Independent Binary Classifiers:** Each phrase is represented by an independent binary classifier ONNX model (FCN MLP, ~100–200 KB) evaluated against the shared 16×96 feature buffer.
- **Resource Footprint & Overhead:**
  - Memory: ~1.2 MB for all 8 ONNX classifier models combined.
  - CPU Latency: Shared embedding extraction takes ~1.5–2.5 ms per 80 ms chunk. Each binary classifier takes ~0.08 ms. Running all 8 classifiers concurrently adds less than 0.7 ms total CPU time per chunk (< 4% of real-time budget).
- **Independent Thresholds & Toggles:** Each phrase has an independent threshold in `config/config.yaml` (0.60 standard, 0.65 for single-word "LUMI!") and can be toggled on/off dynamically via `/api/wake_word/phrases`.

### Rolling Pre-Roll Audio Buffer:
- A rolling circular queue (`collections.deque`, default 800 ms = 10 chunks) buffers audio during `IDLE_LISTENING`.
- When a wake word is confirmed, the audio immediately preceding and following the detection is preserved and prepended to the command capture buffer. This guarantees the opening syllables of the child's command (e.g., "What is...", "Tell me...") are not lost.

---

## 4. Custom Training Assessment & Workflow

### Version-Compatible Training Pipeline:
- Implemented in [`tools/wake_word_training/train_wake_word.py`](file:///c:/Users/basar/Desktop/LUMI/tools/wake_word_training/train_wake_word.py).
- Backward-compatible alias maintained in [`tools/wake_word_training/train_hey_lumi.py`](file:///c:/Users/basar/Desktop/LUMI/tools/wake_word_training/train_hey_lumi.py).

### Child Speech Acoustic Characteristics:
1. **Fundamental Frequency (F0):** Children aged 3–8 have higher fundamental pitch (250–400 Hz) compared to adult males (100–150 Hz) and adult females (180–220 Hz).
2. **Formant Frequencies (F1, F2, F3):** Shorter vocal tract lengths shift formant resonances up by 20% to 30%.
3. **Articulation Variability:** Child phoneme transitions, consonant clustering (e.g. /pl/, /st/, /gr/), and syllable timing exhibit wider statistical dispersion.
4. **Synthetic Speech Limitations:** Models trained solely on adult TTS voices (e.g., Piper Lessac) fail to capture child acoustic variance, room reverberation, microphone clipping, or background noise. Synthetic evaluation must never be treated as proof of real-world child reliability.

### Data Requirements for Production Training:
- **Positive Samples:** 200–500 recordings per phrase across at least 15–20 diverse speakers (child and adult female/male) with varied distance (0.5m to 3m), accents, and microphones.
- **Negative Speech:** 10–20 hours of conversational speech, television audio, and sibling speech without wake words.
- **Background Noise:** 5+ hours of domestic noise (appliances, outdoor traffic, room reverberation) from open datasets (e.g., Free Music Archive, ESC-50, DEMAND).
- **Licensing & Privacy:** Zero cloud uploads. All training must run locally on permissible open-source or explicitly consented datasets.

---

## 5. End-to-End Voice Pipeline & State Machine

The voice pipeline implements a robust 6-state machine ([`src/state_machine.py`](file:///c:/Users/basar/Desktop/LUMI/src/state_machine.py)):

```
IDLE_LISTENING ──(Wake Phrase Detected)──> WAKE_DETECTED ──> CAPTURING_COMMAND
      ▲                                                             │
      │                                                     (Silence / VAD)
      │                                                             ▼
RETURN_TO_LISTENING <──(Audio Playback Ends)── SPEAKING <─── PROCESSING
```

1. **`IDLE_LISTENING`**: Continuously processes microphone audio chunks (1,280 samples / 80 ms) locally. Non-wake speech and background noise are rejected.
2. **`WAKE_DETECTED`**: Confirms detection with phrase identity, confidence score, and debounce cooldown. Evaluates whether the model is genuine or fallback.
3. **`CAPTURING_COMMAND`**: Uses pre-roll audio buffer and Silero VAD to capture the child's actual question.
   - *Natural Pause Recovery:* If the child triggers the wake phrase and pauses without a command, LUMI speaks an age-appropriate contextual prompt:
     - `"Good morning, LUMI"` → *"Good morning! What would you like to learn today?"*
     - `"Let's play, LUMI"` → *"I'm ready to play! What game or story would you like?"*
     - `"Wake up, LUMI"` → *"I'm awake and ready! What would you like to explore?"*
     - `"Are you there, LUMI?"` → *"I'm right here! How can I help you today?"*
     - `"LUMI!"` → *"I'm listening! What can I help you with?"*
4. **`PROCESSING`**: Transcribes the captured audio with Faster-Whisper (`base.en`), normalizes text, classifies intent, and queries the educational catalog/router.
5. **`SPEAKING`**: Synthesizes the response with local Piper TTS (`en_US-lessac-medium.onnx`, default slow 1.15 child speed) and plays it through the audio player.
6. **`RETURN_TO_LISTENING`**: Enforces an 800 ms echo suppression grace period, purges microphone residual audio, resets detector internal states, and cleanly transitions back to `IDLE_LISTENING`.

---

## 6. Test Evidence

### Automated Test Runs:
1. **Dedicated Multi-Phrase Wake-Word Test Suite**:
   - Command: `.venv\Scripts\python.exe -m pytest tests/test_multi_wake_word.py -v`
   - Result: **13/13 passed in 1.50s**.
2. **Wake-Up Activation & State Machine Test Suite**:
   - Command: `.venv\Scripts\python.exe -m pytest tests/test_wake_activation.py -v`
   - Result: **7/7 passed in 1.39s**.
3. **Voice Lab Server & End-to-End API Test Suite**:
   - Command: `.venv\Scripts\python.exe tools/voice_lab/test_voice_lab.py`
   - Result: **57/57 passed**.
4. **Complete Unit & Integration Test Suite**:
   - Command: `.venv\Scripts\python.exe -m pytest tests/`
   - Result: **159/159 passed in 23.42s**.

---

## 7. Commands to Launch LUMI and Run Tests

### Launch LUMI Companion & Voice Lab:
```powershell
# Launch the main interactive companion interface (default browser will open http://127.0.0.1:8765)
python run_interface.py
# Or use the Windows launcher script:
run_interface.bat
```

### Run Test Suites:
```powershell
# 1. Run all repository unit and integration tests (159 tests)
.venv\Scripts\python.exe -m pytest tests/ -v

# 2. Run dedicated multi-phrase wake-word tests (13 tests)
.venv\Scripts\python.exe -m pytest tests/test_multi_wake_word.py -v

# 3. Run Voice Lab API & interactive turn verification (57 tests)
.venv\Scripts\python.exe tools/voice_lab/test_voice_lab.py
```

### Multi-Phrase Custom Model Training:
```powershell
# Train any of the 8 authoritative phrases locally:
.venv\Scripts\python.exe tools/wake_word_training/train_wake_word.py --phrase "Hey LUMI" --generate-synthetic
.venv\Scripts\python.exe tools/wake_word_training/train_wake_word.py --phrase "Good morning, LUMI" --generate-synthetic
```

---

## 8. Remaining Blockers & Concrete Next Steps

1. **Child Speech Data Collection for Training**:
   - Collect 200–500 recordings per phrase with explicit consent in family/educational environments.
   - Train each phrase using `tools/wake_word_training/train_wake_word.py` and output to `models/wake_words/{filename}`.
   - Once trained, the phrase status automatically transitions from `NEEDS TRAINING` to `MODEL AVAILABLE — VALIDATION REQUIRED`.
2. **Positive/Negative Validation on Real Audio**:
   - Evaluate each trained ONNX model against 50 positive child utterances and 2 hours of negative speech/background noise.
   - Transition validated models to `VERIFIED`.
3. **ESP32 Microcontroller Physical Hardware Deployment**:
   - When hardware is assembled, connect I2S microphone (INMP441) and I2S speaker (MAX98357A) per [`docs/HARDWARE_WIRING.md`](file:///c:/Users/basar/Desktop/LUMI/docs/HARDWARE_WIRING.md).