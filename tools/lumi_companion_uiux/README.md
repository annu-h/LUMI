# LUMI Companion — UI/UX Firmware Interface & Simulator

This workspace contains the complete UI/UX implementation and interactive hardware simulator for the **LUMI Educational Companion** device (ESP32 + 320x240 ILI9341 SPI TFT + 12-Button Matrix Keypad).

---

## 🚀 How to Run the Interface

The interactive simulator runs locally with zero external dependencies (pure HTML/CSS/JavaScript + Python HTTP server):

### Option 1: Automatic Launch (Currently Running!)
The local server is already running and opened in your browser at:
👉 **[http://127.0.0.1:8008/](http://127.0.0.1:8008/)**

### Option 2: Quick Windows Runner (One-Click)
Double-click [`run_interface.bat`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/run_interface.bat) in this folder.

### Option 3: Terminal Command
```powershell
python run_interface.py
```

---

## 🎮 Features Simulated

| Component | Code Reference | Simulator Behavior |
|---|---|---|
| **320×240 Color Display** | [`ui/ui_manager.cpp`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/ui/ui_manager.cpp) | Pixel-accurate TFT_eSPI canvas rendering with RGB565 palette matching (`COLOR_BG`, `COLOR_CARD`, `COLOR_CYAN`, `COLOR_TEXT`) |
| **Animated LUMI Face** | `drawLumiFace()` | 350ms frame animation with natural blinking, smiling, squinting (Thinking), wide eyes (Listening), and moving mouth (Speaking) |
| **6 Screen Modes** | `ScreenState` | **Home**, **Learn Mode** (8 catalog items), **Quiz Challenge** (immediate scoring), **Story Time**, **LUMI Setup**, **Learning Stars** |
| **12-Button Keypad** | [`input/keypad_driver.cpp`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/input/keypad_driver.cpp) | 4×3 matrix scanning (`GPIO 14, 27, 16, 12` × `GPIO 35, 13, 15`) with keyboard shortcuts (0-9, Backspace/Left, Enter/Right) |
| **Audio & Speech** | Web Audio & SpeechSynthesis | Tactile keypad click beeps, quiz celebration chime / error buzz, and LUMI voice narration reading out cards |
| **Hardware Diagnostics** | UI Controls Panel | Live battery voltage slider (CR2032 0-100%), expression switcher, and ESP32 GPIO serial telemetry log |

---

## 📂 Source Code Structure

- [`ui/ui_manager.h`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/ui/ui_manager.h) & [`ui/ui_manager.cpp`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/ui/ui_manager.cpp): C++ state machine, TFT rendering routines, and offline educational catalog.
- [`input/keypad_driver.h`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/input/keypad_driver.h) & [`input/keypad_driver.cpp`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/input/keypad_driver.cpp): Active-low 4x3 matrix scanning and debouncing driver.
- [`index.html`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/index.html), [`style.css`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/style.css), [`app.js`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/app.js): High-fidelity browser simulator engine.
- [`run_interface.py`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/run_interface.py) & [`run_interface.bat`](file:///c:/Users/basar/Downloads/lumi-companion-uiux/lumi-companion-main/run_interface.bat): Local web server and browser auto-launchers.
