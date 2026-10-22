# LUMI — Interactive Voice Companion & Educational Hardware Simulator

LUMI is a privacy-first, 100% offline educational companion robot designed for children aged 0–6. It combines on-device artificial intelligence with an embedded tactile hardware interface.

---

## 🚀 Quick Start — Primary Application

To launch the integrated LUMI Companion interface:

```bash
# Using the project Python virtual environment:
python run_interface.py

# Or on Windows, double-click:
run_interface.bat
```

- **Primary Companion Interface:** [http://127.0.0.1:8765/](http://127.0.0.1:8765/)
- **Developer Testbed & Model Audit:** [http://127.0.0.1:8765/dev](http://127.0.0.1:8765/dev)

---

## 🎨 Dual Presentation Architecture

The application cleanly separates desktop hardware simulation from embedded firmware while preserving full interactive functionality:

1. **Left Column — Physical Chassis & Desktop Hardware Simulator:**
   - **Chassis Shell:** Warm tactile yellow rounded enclosure mimicking the handheld physical toy.
   - **Simulated 320×240 ILI9341 LCD Screen:** Pixel-crisp CRT scanline glass rendering real-time UI state machines, animated LUMI face expressions (`IDLE`, `LISTENING`, `THINKING`, `SPEAKING`), and educational item graphics.
   - **Animated Speaker Grille:** Sound wave bars that react during real Piper TTS speech synthesis.
   - **12-Button Keypad Matrix:** Keys 1–9, `◄` Back, `0` Home/Next, `►` Forward with tactile 3D click animations and keyboard shortcuts (`0`–`9`, `Left`/`Backspace`, `Right`/`Enter`).

2. **Right Column — Interactive Voice Companion & Activity Center:**
   - **🏠 Home & Voice:** Animated LUMI hero character, 5-state tactile microphone button with ripple animations, speed toggle (`🐢 Slow` length_scale 1.15 recommended for young kids vs `🐇 Normal`), sound toggle, hands-free toggle, quick question chips, real-time conversation feed, and fallback typed text input.
   - **📚 Learn Mode:** Real educational cards loaded from `data/educational/*.csv` via `/api/educational/catalog` with category badges, sound descriptions, fun facts, and `"Read Card Aloud"` via Piper TTS.
   - **❓ Quiz Challenge:** Real two-choice educational questions loaded from `/api/educational/quiz` with instant child-friendly feedback, explanation, and star rewards.
   - **📖 Story Time:** Curated local bedtime and adventure stories (`The Clever Fox`, `The Lost Puppy`, etc.) with Piper TTS voice narration.
   - **⭐ My Learning Stars:** Visual achievement tracking for the current session (stars collected, quizzes completed, questions asked, stories heard).
   - **⚙️ Setup:** Audio, voice speed, and offline system diagnostics.

---

## 🧠 Real Offline Voice Pipeline

Project LUMI performs 100% of speech recognition and synthesis offline without internet access or cloud APIs:

```
[Microphone Audio (16kHz PCM WAV)]
             │
             ▼
  [Silero VAD Voice Detection]
             │
             ▼
[Faster-Whisper base.en Transcription]
             │
             ▼
[LUMI Intent & Educational Catalog Logic]
             │
             ▼
[Piper TTS (en_US-lessac-medium.onnx)]
             │  (length_scale = 1.15 slow pace)
             ▼
[Audio Playback / Speaker Grille Animation]
```

### Truthful Wake-Word Integration
- The custom wake-word model `models/wake_words/hey_lumi.onnx` is currently **MISSING** from the repository and has **NOT** been fabricated or simulated.
- Manual tap-to-talk using the primary microphone button (`#btnHeroMic`) is the verified, reliable activation flow.
- A hands-free checkbox is available in the interface; when checked, speech input is validated for `"Hey LUMI"`.

---

## 🔌 Hardware Configuration & Pinout

Project LUMI targets the **ESP32 DevKit V1 / ESP32-WROOM-32** without external GPIO expanders.

- **Authoritative Wiring Documentation:** [`docs/HARDWARE_WIRING.md`](file:///c:/Users/basar/Desktop/LUMI/docs/HARDWARE_WIRING.md)
- **C/C++ Firmware Headers:** [`firmware/include/lumi_pins.h`](file:///c:/Users/basar/Desktop/LUMI/firmware/include/lumi_pins.h) and [`firmware/include/lumi_config.h`](file:///c:/Users/basar/Desktop/LUMI/firmware/include/lumi_config.h)
- **Embedded C++ Drivers:**
  - [`firmware/src/input/keypad_driver.h`](file:///c:/Users/basar/Desktop/LUMI/firmware/src/input/keypad_driver.h) & [`keypad_driver.cpp`](file:///c:/Users/basar/Desktop/LUMI/firmware/src/input/keypad_driver.cpp)
  - [`firmware/src/ui/ui_manager.h`](file:///c:/Users/basar/Desktop/LUMI/firmware/src/ui/ui_manager.h) & [`ui_manager.cpp`](file:///c:/Users/basar/Desktop/LUMI/firmware/src/ui/ui_manager.cpp)

### Authoritative Pin Mapping
| Component | Function | ESP32 GPIO | Electrical Notes |
|-----------|----------|------------|------------------|
| **Keypad Rows** | Matrix Output (Active-Low) | GPIO 14, 27, 16, 12 | GPIO 12: MTDI strapping pin; idle high-Z on boot |
| **Keypad Columns**| Matrix Input (Active-Low) | GPIO 35, 13, 15 | GPIO 35 is input-only; requires external 10kΩ pull-up/down |
| **Status LED** | System Power & Activity | GPIO 32 | HIGH = Active / ON |
| **I2S Audio** | BCLK | GPIO 26 | Shared between mic and amplifier |
| | WS / LRCLK | GPIO 25 | Shared word select clock |
| | INMP441 Data (Mic) | GPIO 34 | Input only |
| | MAX98357A Data (Amp)| GPIO 33 | Output only |
| **TFT Display** | CS, DC, RESET | GPIO 5, 2, 4 | ILI9341 320×240 SPI display |
| | MOSI, SCLK | GPIO 23, 18 | VSPI bus |
| **SD Storage** | CS | GPIO 17 | MicroSD SPI mode |

---

## 🧪 Testing & Verification

Run the automated verification suites:

### 1. Voice Lab Functional & Integration Suite
```bash
python tools/voice_lab/test_voice_lab.py
```
*Results: **51 / 51 tests pass***, verifying:
- Static asset serving (`/`, `/style.css`, `/app.js`, `/dev`)
- Model dependencies & presence audits
- Silero VAD native inference
- Faster-Whisper `base.en` transcription
- Piper TTS voice synthesis & WAV audio streaming
- 5 interactive conversation turns
- Educational catalog (`/api/educational/catalog`), quiz (`/api/educational/quiz`), and stories (`/api/educational/stories`)
- Piper TTS standalone speak endpoint (`/api/tts/speak`)

### 2. Full Repository Pytest Suite
```bash
pytest tests/
```
*Results: **146 / 146 tests pass***, verifying educational catalog loaders, intent classification, JIBO test cases, hardware pinout integrity, and voice modules.

---

## 📁 Repository Structure

```
LUMI/
├── run_interface.py              # Primary application launcher
├── run_interface.bat             # Windows one-click launcher
├── config/
│   └── config.yaml               # Authoritative project configuration
├── data/
│   └── educational/              # 10 Educational CSV datasets
├── docs/
│   └── HARDWARE_WIRING.md        # Authoritative wiring guide
├── firmware/
│   ├── include/
│   │   ├── lumi_pins.h           # Authoritative GPIO definitions
│   │   └── lumi_config.h         # Firmware timing and display settings
│   └── src/
│       ├── input/
│       │   ├── keypad_driver.h   # Adapted C++ 4x3 keypad driver
│       │   └── keypad_driver.cpp
│       └── ui/
│           ├── ui_manager.h      # Adapted C++ ILI9341 UI state machine
│           └── ui_manager.cpp
├── models/
│   ├── tts/
│   │   ├── en_US-lessac-medium.onnx       # Local Piper voice model
│   │   └── en_US-lessac-medium.onnx.json  # Model configuration
│   └── wake_words/
│       └── (hey_lumi.onnx missing)
├── src/                          # Core voice processing & educational modules
├── tools/
│   ├── lumi_companion_uiux/      # Preserved original UI/UX developer prototype
│   └── voice_lab/
│       ├── server.py             # Primary backend server (port 8765)
│       ├── index.html            # Integrated companion UI & simulator
│       ├── style.css             # Unified modern styles & offline font stack
│       ├── app.js                # Integrated canvas, keypad & voice logic
│       ├── dev.html              # Dedicated developer testbed
│       └── test_voice_lab.py     # 51-test verification suite
└── tests/                        # 146-test Pytest suite
```

---

## 🔒 Privacy & Data Policy

- All inference executes locally on device CPU.
- No audio recordings or text transcripts are sent to the cloud.
- Temporary audio files created during processing are purged via the `/api/clear_temp` endpoint.
- Zero tracking, telemetry, or external font/CDN network requests.