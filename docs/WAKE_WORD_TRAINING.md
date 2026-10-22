# LUMI — Wake-Word Training & Model Integrity Specification

This document details the architectural requirements, training methodology, data provenance, and privacy considerations for creating a production-grade **"Hey LUMI"** custom wake-word model.

---

## 1. Architectural Overview

LUMI uses the **openWakeWord** framework for local, offline, real-time keyword spotting:
* **Acoustic Input:** 16 kHz mono 16-bit PCM audio stream.
* **Feature Extractor:** openWakeWord's pre-trained `embedding_model.onnx` converts raw audio into 96-dimensional acoustic feature vectors every 80 ms (1,280 samples).
* **Classifier Input Shape:** `(batch, 16, 96)` representing an 800 ms context window of 16 consecutive feature vectors.
* **Classifier Architecture:** Fully Connected Network (FCN) with Layer Normalization, ReLU activation, and a single sigmoid output representing the wake-phrase probability.
* **Export Format:** Standard ONNX (`opset_version=13`).

---

## 2. Why `hey_lumi.onnx` is Currently Marked `MISSING`

To ensure model integrity and privacy:
1. **No False Aliasing:** `hey_jarvis_v0.1.onnx` is **not** renamed or claimed to detect "Hey LUMI". It operates strictly as an explicitly labelled development fallback.
2. **Data Integrity & Acoustic Diversity:** Training an accurate, reliable wake-word detector for young children requires diverse acoustic samples:
   * **Multiple Speaker Profiles:** Varied pitch, formants, cadence, and accents. Models trained solely on a single synthetic TTS voice (e.g., Lessac) suffer from acute acoustic overfitting and exhibit high false rejection rates when tested on real human children.
   * **Background Noise & Hard Negatives:** At least 20–50 hours of diverse negative speech (conversations, educational audio, ambient household sounds, music) to prevent false activations.
   * **Acoustic Augmentation:** Room Impulse Responses (RIRs) simulating real classroom/nursery room acoustics.
3. **Child Privacy & Safety:** LUMI strictly adheres to child data safety principles:
   * Private child recordings are **never** uploaded to external clouds, mirrors, or third-party servers.
   * Large background speech datasets are **not** downloaded without explicit user authorization.

Until a verified, diverse multi-speaker dataset is assembled and approved, the custom model `models/wake_words/hey_lumi.onnx` remains accurately cataloged as **`MISSING`**, and exact "Hey LUMI" wake-word activation is cataloged as **`BLOCKED`**.

---

## 3. Reproducible Training Workflow

A complete training utility is provided at [`tools/wake_word_training/train_hey_lumi.py`](file:///c:/Users/basar/Desktop/LUMI/tools/wake_word_training/train_hey_lumi.py).

### How to Run:
```powershell
# 1. Run with synthetic Piper TTS samples (for prototyping/benchmarking)
.venv\Scripts\python.exe tools/wake_word_training/train_hey_lumi.py --generate-synthetic --epochs 15 --output models/wake_words/hey_lumi.onnx

# 2. Verify the generated model with the audit tool
.venv\Scripts\python.exe tools/voice_lab/audit_models.py
```

### Required Datasets for Production Training:
When preparing production training, supply:
* **Positive Samples Directory:** 500+ diverse recordings of "Hey LUMI" spoken by diverse speakers (adults and children), with variations in speed, volume, and distance from microphone.
* **Negative Samples Directory:** 1,000+ recordings of phonetically similar phrases ("Hey Lily", "Hey Loom", "Hello", "Lu-lu", "Look at me") and general household speech.
* **Noise Dataset:** Diverse white noise, babble, music, and home appliance sounds (e.g. from AudioSet or DEMAND).

---

## 4. State Machine & Fallback Operation

The runtime state machine ([`src/state_machine.py`](file:///c:/Users/basar/Desktop/LUMI/src/state_machine.py)) natively decouples wake-word detection from model existence:
1. If `models/wake_words/hey_lumi.onnx` exists on disk:
   * The detector loads `hey_lumi.onnx`.
   * Flags `is_fallback = False` and `is_genuine_lumi = True`.
   * Listens exclusively for "Hey LUMI".
2. If `models/wake_words/hey_lumi.onnx` is absent:
   * The detector automatically loads the pre-packaged `hey_jarvis_v0.1.onnx` model.
   * Flags `is_fallback = True` and `is_genuine_lumi = False`.
   * The system logs a warning and labels the active model in the UI as `Fallback (hey_jarvis)`.
   * Development testing continues without crashing.
