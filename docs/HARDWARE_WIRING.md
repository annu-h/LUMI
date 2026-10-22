# Project LUMI — Authoritative Hardware Wiring & Firmware Specification

> **Document Status:** Authoritative Hardware Specification (v2.0)  
> **Target Microcontroller:** ESP32 DevKit V1 / ESP32-WROOM-32 (30-pin or 38-pin module)  
> **Architecture Constraint:** Direct GPIO connection only. **No external GPIO expander** is used.  
> **Software Reference:** [config/config.yaml](file:///c:/Users/basar/Desktop/LUMI/config/config.yaml), [src/config.py](file:///c:/Users/basar/Desktop/LUMI/src/config.py), and [firmware/include/lumi_pins.h](file:///c:/Users/basar/Desktop/LUMI/firmware/include/lumi_pins.h)

---

## 1. Authoritative Master Connection Matrix

| Peripheral Subsystem | Signal Name | ESP32 GPIO | Pin Type | Voltage Level | Electrical / Strapping Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Keypad (4x3 Matrix)** | Row 0 (1, 2, 3) | **GPIO 14** | Output | 3.3V | Standard GPIO |
| | Row 1 (4, 5, 6) | **GPIO 27** | Output | 3.3V | Standard GPIO |
| | Row 2 (7, 8, 9) | **GPIO 16** | Output | 3.3V | Standard GPIO |
| | Row 3 (*, 0, #) | **GPIO 12** | Output | 3.3V | ⚠️ **STRAPPING PIN (MTDI):** Flash voltage select (3.3V vs 1.8V). Must NOT be pulled HIGH at boot! |
| | Column 0 | **GPIO 35** | Input | 3.3V | ⚠️ **INPUT-ONLY (GPI):** No internal pull-up/pull-down! **External 10kΩ pull-down resistor to GND is REQUIRED.** |
| | Column 1 | **GPIO 13** | Input | 3.3V | Standard GPIO with internal pull-down |
| | Column 2 | **GPIO 15** | Input | 3.3V | ⚠️ **STRAPPING PIN (MTDO):** Boot log output & JTAG control |
| **Status LED** | Green LED Anode | **GPIO 32** | Output | 3.3V | Active HIGH (HIGH = ON, LOW = OFF). Requires current-limiting resistor (220Ω–330Ω) to GND. |
| **I2S Audio (Full-Duplex)**| Shared Bit Clock (BCLK) | **GPIO 26** | Output | 3.3V | Shared clock line between INMP441 (SCK) and MAX98357A (BCLK) |
| | Shared Word Select (WS/LRCLK) | **GPIO 25** | Output | 3.3V | Shared word-select line between INMP441 (WS) and MAX98357A (LRCLK) |
| | Mic Serial Data (INMP441 SD) | **GPIO 34** | Input | 3.3V | Input-only GPI pin. Perfect for microphone RX data. L/R pin tied to GND for Left channel. |
| | Amp Serial Data (MAX98357A DIN)| **GPIO 33** | Output | 3.3V | I2S TX data line to amplifier DIN. |
| **SD Card (SPI)** | Shared SPI Clock (SCK) | **GPIO 18** | Output | 3.3V | VSPI SCK (shared with TFT Display) |
| | Shared Master Out (MOSI) | **GPIO 23** | Output | 3.3V | VSPI MOSI (shared with TFT Display) |
| | Shared Master In (MISO) | **GPIO 19** | Input | 3.3V | VSPI MISO (shared with TFT Display) |
| | SD Chip Select (CS) | **GPIO 17** | Output | 3.3V | Dedicated active-LOW SD Card Chip Select |
| **TFT Display (ILI9341 SPI)**| TFT Chip Select (CS) | **GPIO 5** | Output | 3.3V | Dedicated active-LOW TFT Display Chip Select |
| | TFT Data/Command (DC) | **GPIO 2** | Output | 3.3V | ⚠️ **STRAPPING PIN:** Must be LOW/floating for UART download boot mode |
| | TFT Hardware Reset (RESET) | **GPIO 4** | Output | 3.3V | Active-LOW hardware reset |
| | TFT Header Specification | N/A | N/A | N/A | **Use ONLY the main 14-pin header.** Do NOT use the auxiliary 4-pin SD header on the TFT board. |
| **Real-Time Clock (DS3231)**| I2C Data (SDA) | **GPIO 21** | I/O | 3.3V | Standard I2C SDA (requires 4.7kΩ pull-up to 3.3V) |
| | I2C Clock (SCL) | **GPIO 22** | Output | 3.3V | Standard I2C SCL (requires 4.7kΩ pull-up to 3.3V) |

---

## 2. Hardware Safety & Pin-Conflict Review

### 2.1 ESP32 Strapping Pins (Boot Critical)
The ESP32 ROM bootloader checks several pins at reset to determine the boot mode, flash voltage, and console logging. Three assigned pins require strict design awareness:

1. **GPIO 12 (MTDI) — Assigned to Keypad Row 3:**
   - **Boot Hazard:** GPIO 12 selects the internal flash LDO voltage: `0` selects 3.3V, while `1` selects 1.8V. If GPIO 12 is pulled HIGH when the ESP32 resets, the flash voltage drops to 1.8V, preventing the standard 3.3V SPI flash memory from functioning, causing an endless boot loop (`rst:0x10 (RTCWDT_RTC_RESET)`).
   - **Protection Strategy:** Keypad Row 3 must NEVER be held HIGH during power-on reset. In software, matrix scanning drivers must keep row outputs in HIGH-Z (input) or drive them LOW when idle.
2. **GPIO 15 (MTDO) — Assigned to Keypad Column 2:**
   - **Boot Function:** Controls ROM boot logging. If pulled LOW at reset, bootloader logging is suppressed.
   - **Protection Strategy:** Keypad column reading uses pull-down resistors; ensure Column 2 does not pull the line to unexpected state during flashing.
3. **GPIO 2 — Assigned to TFT DC:**
   - **Boot Function:** Connected to the onboard strapping circuit. If pulled HIGH while GPIO 0 is LOW, it can prevent flashing over UART.
   - **Protection Strategy:** Ensure TFT DC line does not fight GPIO 2 during programming.

### 2.2 GPIO 35 (Input-Only / GPI Limitation)
- **ESP32 Silicon Constraint:** GPIO 34, 35, 36 (VP), and 39 (VN) are input-only pins (GPI). **They lack internal pull-up and pull-down resistors.** The software options `INPUT_PULLUP` and `INPUT_PULLDOWN` do NOT exist in the ESP32 silicon for these pins.
- **Hardware Requirement:** Keypad Column 0 is wired to GPIO 35. Therefore, an **external physical 10kΩ pull-down resistor to GND** must be installed on GPIO 35. Without this resistor, GPIO 35 floats, resulting in false key triggers and erratic inputs.

### 2.3 Keypad Row/Column Scan Logic
- **Row Drive / Column Sense:**
  - Rows (GPIO 14, 27, 16, 12) are configured as digital outputs, driven LOW when idle.
  - Columns (GPIO 35, 13, 15) are configured as digital inputs with pull-down resistors (external 10kΩ on GPIO 35; internal or external pull-down on GPIO 13 and 15).
  - To scan, the firmware pulses one row HIGH at a time and reads column states. If a key is pressed, the corresponding column reads HIGH.
  - When idle, all rows are driven LOW, ensuring GPIO 12 (Row 3) is safely grounded at reset.

### 2.4 Full-Duplex Shared Clock I2S Arrangement
- **Topology:** The INMP441 microphone and MAX98357A amplifier share the clock lines:
  - Bit Clock (BCLK): **GPIO 26**
  - Word Select / LRCLK (WS): **GPIO 25**
- **Hardware Compatibility:**
  - Both devices operate concurrently on the single full-duplex I2S0 peripheral of the ESP32.
  - **Sample Rate:** Synchronized to **16,000 Hz** (voice pipeline standard).
  - **Slot Format:** 32-bit slot width, standard Philips I2S format (data delayed by 1 BCLK cycle).
  - **Microphone (INMP441):** Sends 24-bit PCM data left-aligned inside the 32-bit slot on GPIO 34.
  - **Amplifier (MAX98357A):** Automatically decodes 16-bit or 24-bit data from 32-bit slots on GPIO 33.

### 2.5 Shared SPI Bus & TFT MISO Troubleshooting
- **Bus Sharing:** SCK (GPIO 18), MOSI (GPIO 23), and MISO (GPIO 19) are shared between the SD Card module and ILI9341 TFT display.
- **Header Restriction:** The TFT display must be connected **strictly via its main 14-pin header**. Do NOT use the small auxiliary 4-pin header located on the display module for SD card signals.
- **TFT MISO Troubleshooting Step:**
  - Many common ILI9341 breakout modules have an onboard circuit design flaw where the display does not properly release (tri-state) the MISO line when its Chip Select (GPIO 5) is deasserted (HIGH).
  - If the display actively drives MISO, it corrupts the SD card's response packets on GPIO 19 during card initialization (`CMD0`/`CMD8`).
  - **Resolution:** Because Project LUMI firmware only writes graphic buffers to the display and never reads pixel data from the ILI9341, **disconnect the TFT MISO wire** (leave the TFT MISO pin floating) if SD card read/write errors or initialization failures occur.

### 2.6 Power Supply & Voltage Rail Architecture
- **SD Card Module Power:**
  - Standard MicroSD cards operate strictly at **3.3V**.
  - Many hobbyist breakout boards include an onboard 3.3V LDO regulator (e.g. AMS1117-3.3 or XC6206) and level shifter ICs intended for a **5V** supply input.
  - *Inspection Step:* If the breakout board contains an LDO regulator chip, connect its $V_{in}$ to the **5V (VIN)** rail. Powering a 5V-regulated breakout from 3.3V will cause brownouts ($V_{out} \approx 2.8\text{V}-3.0\text{V}$), corrupting file writes. If the breakout board is a direct 3.3V board without an LDO, connect it to the **3.3V** rail.
- **MAX98357A Amplifier Power:**
  - Connect $V_{in}$ to **5V (VIN)** to deliver up to 3.2W of clean audio into a 4Ω speaker. A 3.3V supply limits output power to ~0.8W and causes supply rail dips during audio peaks.
  - Ensure common GND between ESP32 and amplifier.

---

## 3. Keypad Dual-Mode Operation

Project LUMI maintains a strict separation between **Shortcut Mode** and **Numeric-Entry Mode**, while routing all actions through the existing intent architecture:

```
                      ┌────────────────────────────────────┐
                      │        Keypad Key Pressed          │
                      └─────────────────┬──────────────────┘
                                        │
                         Mode == ? ─────┴───── Mode == ?
                        /                               \
         ┌─────────────────────────────┐   ┌─────────────────────────────┐
         │        SHORTCUT MODE        │   │     NUMERIC-ENTRY MODE      │
         └──────────────┬──────────────┘   └──────────────┬──────────────┘
                        │                                 │
           '0'..'6', '*', '#' Keys             '0'..'9' Digits, '*', '#'
                        │                                 │
          ┌─────────────┴─────────────┐         ┌─────────┴─────────┐
          │ Shared Intent Handlers:   │         │ Digits: Buffer += │
          │ 0 -> HELLO                │         │ '*'   : Backspace │
          │ 1 -> STORY                │         │ '#'   : Submit/OK │
          │ 2 -> LEARN                │         └───────────────────┘
          │ 3 -> MUSIC                │
          │ 4 -> HOBBIES              │
          │ 5 -> FAVORITES            │
          │ 6 -> TIME                 │
          │ * -> BACK                 │
          │ # -> NEXT                 │
          └───────────────────────────┘
```

1. **Shortcut Mode (Default):**
   - Direct physical shortcut to core features: `1` = Story, `2` = Learn, `3` = Music, `4` = Hobbies, `5` = Favorites, `6` = Time, `0` = Hello.
   - `*` triggers `Intent.BACK` (or Previous).
   - `#` triggers `Intent.NEXT` (or Forward).
   - Routed through the exact same `IntentRouter` handlers used for voice recognition transcripts.
2. **Numeric-Entry Mode:**
   - Designed for interactive educational quizzes (counting, math problems, age entry).
   - Digits `0`–`9` accumulate in `_numeric_buffer`.
   - `*` acts as Backspace / Clear.
   - `#` acts as Submit / Enter.

---

## 4. Mandatory Physical Safety Verification Checklist

> [!CAUTION]
> Software cannot electrically verify physical connections. A qualified person must perform these steps manually before connecting the ESP32 to power or USB.

### Phase 1: Pre-Power Continuity & Cold Inspection (USB DISCONNECTED)
- [ ] **USB Cable Disconnected:** Ensure no power source is attached to the ESP32.
- [ ] **3.3V-to-GND Short Check:** Measure resistance between 3.3V rail and GND using a multimeter in continuity mode. Resistance must be $> 1\text{ k}\Omega$ (no direct short).
- [ ] **5V-to-GND Short Check:** Measure resistance between 5V/VIN rail and GND. Resistance must be $> 1\text{ k}\Omega$ (no direct short).
- [ ] **GPIO 35 Pull-Down Verification:** Verify that an external 10kΩ resistor is physically installed between GPIO 35 (Column 0) and GND.
- [ ] **TFT Header Verification:** Confirm that connections use the **main 14-pin header only**. Confirm that the auxiliary 4-pin SD header on the display is completely unconnected.
- [ ] **Common Ground:** Verify that all peripheral GND pins (INMP441, MAX98357A, SD Card, TFT, RTC, Keypad, LED) share a single common ground bus connected to ESP32 GND.

### Phase 2: Power Rail Verification (ESP32 ALONE)
- [ ] Disconnect peripheral $V_{cc}$ lines.
- [ ] Connect ESP32 to USB power.
- [ ] Measure voltage at ESP32 3.3V pin: Must read between **3.25V and 3.35V**.
- [ ] Measure voltage at ESP32 VIN/5V pin: Must read between **4.75V and 5.25V**.
- [ ] Disconnect USB power before reconnecting peripheral power rails.

### Phase 3: Peripheral Power-Up & Component Heat Check
- [ ] Reconnect peripheral power rails according to the verified specifications.
- [ ] Reconnect USB power.
- [ ] **10-Second Heat Check:** Immediately place a finger gently near the ESP32 SoC, MAX98357A amplifier, and SD card regulator. If any component becomes hot to the touch, **disconnect USB power immediately**.
- [ ] Verify that the Green LED on GPIO 32 lights up when driven HIGH.
