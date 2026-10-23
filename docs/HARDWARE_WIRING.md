# Project LUMI — Authoritative Hardware Wiring & Firmware Specification

> **Document Status:** Authoritative Hardware Specification (v3.0 - Final Bring-Up Audit)  
> **Target Microcontroller:** ESP32 DevKit V1 / ESP32-WROOM-32 (original dual-core ESP32-D0WD-V3)  
> **Arduino Core:** ESP32 Arduino Core 3.3.11 / Arduino IDE 2.3.x  
> **Architecture Constraint:** Direct GPIO connections. No external GPIO expander used.  
> **TFT Display Status:** **NOT INSTALLED YET** (`LUMI_ENABLE_TFT 0`). Firmware guards all display operations.  
> **Software References:** [firmware/LumiFirmware/lumi_pins.h](file:///c:/Users/basar/Desktop/LUMI/firmware/LumiFirmware/lumi_pins.h), [firmware/LumiFirmware/lumi_config.h](file:///c:/Users/basar/Desktop/LUMI/firmware/LumiFirmware/lumi_config.h), [config/config.yaml](file:///c:/Users/basar/Desktop/LUMI/config/config.yaml)

---

## 1. Power Distribution & Rail Architecture

### 1.1 Breadboard Power Rail Layout
```
   [ LEFT RAIL (3.3V) ]                             [ RIGHT RAIL (5.0V) ]
   (+)  3.3V  <=== ESP32 3.3V Pin                   (+)  5.0V  <=== ESP32 VIN / V5 Pin
   (-)  GND   <=== ESP32 GND Pin                    (-)  GND   <=== ESP32 GND Pin
         │                                                │
         └───────────── COMMON GROUND BRIDGE ─────────────┘
                (Connect Left (-) directly to Right (-))
```

> [!CAUTION]
> **NEVER CONNECT THE 3.3V AND 5V POSITIVE RAILS TOGETHER!**  
> Bridging the 3.3V rail to the 5V rail will instantly destroy the ESP32 internal silicon and 3.3V peripherals (INMP441, DS3231).  
> **ALWAYS** bridge the two negative (GND) rails together with a solid jumper wire to ensure a single, noise-free common ground reference.

### 1.2 Module Power Source Mapping
| Module / Subsystem | Supply Voltage | Source Rail | Electrical Reason & Regulator Verification |
| :--- | :---: | :---: | :--- |
| **ESP32 DevKit V1** | 5.0V (USB) | USB / VIN | Powered via USB cable; internal AMS1117-3.3 regulates 3.3V for SoC |
| **INMP441 Microphone** | **3.3V** | **Left (+) Rail** | **STRICT 3.3V ONLY.** No onboard regulator. 5V will permanently burn the MEMS sensor! |
| **MAX98357A I2S Amplifier** | **5.0V** | **Right (+) Rail** | Powered from 5V to deliver up to 3.2W into a 4Ω speaker. (3.3V limits output to <0.8W and induces brownout reset on loud peaks). |
| **MicroSD SPI Module** | **5.0V** | **Right (+) Rail** | Standard hobbyist breakout has an onboard 3.3V LDO (XC6206 / 662K). Feeding 3.3V into an LDO outputs ~2.8V, failing SD card init (`CMD0`). |
| **DS3231 RTC Module** | **3.3V** | **Left (+) Rail** | CR2032 coin cell installed. 3.3V rail powers VCC. |
| **Keypad 10kΩ Pull-Ups** | **3.3V** | **Left (+) Rail** | **MUST CONNECT TO 3.3V ONLY.** Connecting column pull-ups to 5V will inject 5V into ESP32 GPIO 35, 13, and 15, damaging the GPIO input stage. |
| **Green Status LED** | 3.3V Logic | GPIO 32 Output | Series 330Ω resistor connected from GPIO 32 to LED Anode; Cathode to GND rail. |
| **TFT Display (Planned)** | 3.3V | Left (+) Rail | *(Deferred — Not physically installed)* |

---

## 2. Authoritative Master Pin Connection Matrix

| Peripheral Subsystem | Signal Name | ESP32 GPIO | Direction | Level | Notes & Strapping Constraints |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Keypad (4x3 Matrix)** | Row 1 (Keys 1, 2, 3) | **GPIO 14** | Output | 3.3V | Driven LOW during scan; High-Z idle |
| | Row 2 (Keys 4, 5, 6) | **GPIO 27** | Output | 3.3V | Driven LOW during scan; High-Z idle |
| | Row 3 (Keys 7, 8, 9) | **GPIO 16** | Output | 3.3V | Driven LOW during scan; High-Z idle |
| | Row 4 (Keys *, 0, #) | **GPIO 12** | Output | 3.3V | ⚠️ **BOOT STRAPPING (MTDI):** Flash LDO voltage select. Must be LOW at reset! Kept High-Z idle. |
| | Column 1 (Keys 1, 4, 7, *) | **GPIO 35** | Input | 3.3V | ⚠️ **INPUT-ONLY (GPI):** No internal pull-up/down. **Physical 10kΩ pull-up to 3.3V is REQUIRED.** |
| | Column 2 (Keys 2, 5, 8, 0) | **GPIO 13** | Input | 3.3V | 10kΩ external pull-up to 3.3V (+ internal pull-up enabled) |
| | Column 3 (Keys 3, 6, 9, #) | **GPIO 15** | Input | 3.3V | ⚠️ **BOOT STRAPPING (MTDO):** 10kΩ pull-up to 3.3V keeps MTDO HIGH (normal boot log output) |
| **Status LED** | LED Drive | **GPIO 32** | Output | 3.3V | Active HIGH. 330Ω in series with Anode, Cathode to GND. |
| **I2S Audio (Shared Clock)** | Bit Clock (BCLK) | **GPIO 26** | Output | 3.3V | Shared clock: INMP441 SCK + MAX98357A BCLK |
| | Word Select (WS/LRC) | **GPIO 25** | Output | 3.3V | Shared word-select: INMP441 WS + MAX98357A LRC |
| | Mic Serial Data (INMP441 SD) | **GPIO 34** | Input | 3.3V | Input-only GPI. INMP441 L/R tied to GND (Left Channel). |
| | Amp Serial Data (MAX98357A DIN)| **GPIO 33** | Output | 3.3V | Transmit data line to MAX98357A DIN. |
| **MicroSD Module (SPI)** | Shared SPI SCK | **GPIO 18** | Output | 3.3V | VSPI Clock |
| | Shared SPI MOSI | **GPIO 23** | Output | 3.3V | VSPI MOSI (Master Out Slave In) |
| | Shared SPI MISO | **GPIO 19** | Input | 3.3V | VSPI MISO (Master In Slave Out) |
| | SD Chip Select (CS) | **GPIO 17** | Output | 3.3V | Dedicated active-LOW SD Card Select |
| **DS3231 RTC (I2C)** | I2C Data (SDA) | **GPIO 21** | I/O | 3.3V | Onboard DS3231 4.7kΩ pull-ups to 3.3V |
| | I2C Clock (SCL) | **GPIO 22** | Output | 3.3V | Onboard DS3231 4.7kΩ pull-ups to 3.3V |
| **TFT Display (Deferred)** | TFT CS | **GPIO 5** | Output | 3.3V | Disabled in firmware (`LUMI_ENABLE_TFT 0`) |
| | TFT DC | **GPIO 2** | Output | 3.3V | ⚠️ Boot strapping pin (kept floating/harmless) |
| | TFT RESET | **GPIO 4** | Output | 3.3V | Disabled in firmware |

---

## 3. Keypad Matrix Electrical Audit & Tactile Switch Connections

### 3.1 Active-LOW Scan with High-Z Idle Architecture
The keypad uses an **Active-LOW** scanning matrix with **external 10kΩ pull-up resistors to the 3.3V rail**:
```
  3.3V Rail
     │
    [10kΩ] (External Pull-Up)
     ├───> ESP32 Column Input (e.g., GPIO 35) [Normal state: HIGH (3.3V)]
     │
   ┌─┴─┐ (Tactile Switch)
   │ O │  When pressed, shorts Column to Row.
   └─┬─┘
     │
     └───> ESP32 Row Output (e.g., GPIO 14) [Driven LOW during scan: 0V]
```

- **Idle State:** All Row pins (GPIO 14, 27, 16, 12) are set to `INPUT` (High-Impedance / High-Z). All Column pins are pulled HIGH (3.3V) by the 10kΩ resistors.
- **Scan Step:** To scan Row $N$, the firmware sets Row $N$ to `OUTPUT` and writes `LOW` (0V). If button $(N, C)$ is pressed, Column $C$ is pulled LOW to 0V.
- **Post-Scan:** Row $N$ is immediately returned to `INPUT` (High-Z).

### 3.2 Tactile Switch Breadboard Node Verification
Standard 4-pin breadboard tactile switches have internal connections:
- Pins A and B on side 1 are **permanently shorted together**.
- Pins C and D on side 2 are **permanently shorted together**.
- Pressing the button bridges (A/B) to (C/D).

> [!IMPORTANT]
> **CRITICAL BREADBOARD NODE CHECK:**  
> The 10kΩ pull-up resistor MUST be connected to the **COLUMN node** (the side of the switch wired to GPIO 35, 13, or 15).  
> **If the resistor is mistakenly placed on the ROW line:**  
> 1. It will pull the Row pin to 3.3V instead of pulling up the Column.  
> 2. When the switch is open, the Column pin (especially GPIO 35) will float, causing random false key presses or no response.  
> 3. If connected to Row 4 (GPIO 12), it will pull GPIO 12 HIGH during reset, triggering the 1.8V flash brownout bootloop!  
>  
> **Verification with Multimeter (Power ON):**  
> With no buttons pressed, measure the voltage on ESP32 pins GPIO 35, GPIO 13, and GPIO 15:  
> Each column pin MUST read **~3.3V**. If any reads 0V or fluctuates, the pull-up resistor is on the wrong terminal!

---

## 4. ESP32 Boot Strapping Pin Hazard Analysis

| Strapping Pin | Assigned Function | Boot Requirement | Risk & Firmware Mitigation |
| :---: | :---: | :---: | :--- |
| **GPIO 12 (MTDI)** | Keypad Row 4 (Keys *, 0, #) | **Must be LOW (0V)** | **CRITICAL:** If GPIO 12 is HIGH at reset, the ESP32 internal flash regulator switches to 1.8V, permanently preventing SPI flash access until reset. Kept in **High-Z** so internal 50kΩ pull-down keeps it LOW. *Do not hold button 0, *, or # during boot!* |
| **GPIO 15 (MTDO)** | Keypad Column 3 (Keys 3, 6, 9, #) | **HIGH (3.3V)** | Controls ROM boot log output. External 10kΩ pull-up to 3.3V holds this pin HIGH during boot, ensuring normal bootloader logging. |
| **GPIO 2** | TFT DC (Uninstalled) | **LOW / Floating** | Connected to onboard LED / strapping on some DevKits. Since TFT is uninstalled and disabled in software (`LUMI_ENABLE_TFT 0`), GPIO 2 remains unasserted during boot. |
| **GPIO 0** | ESP32 Boot Button | **HIGH for SPI Flash** | Standard DevKit circuit has auto-reset capacitor and pull-up. |

---

## 5. Audio Architecture (Full-Duplex I2S with Shared Clocks)

- **Clock Sharing:** BCLK (GPIO 26) and WS/LRC (GPIO 25) are physically wired to both INMP441 and MAX98357A.
- **Independent Diagnostic Modes:**
  - **Diagnostic Mode `[5]` (Mic Test):** Runs continuous INMP441 sampling (16,000 Hz, 32-bit slot, Philips format, Left channel). Calculates real-time sample counts, RMS amplitude, Min/Max waveform peaks, and clipping counts. Speaker is completely silent.
  - **Diagnostic Mode `[6]` (Speaker Test):** Synthesizes a pure 440 Hz sine wave tone, properly shifted by `<< 16` into 32-bit I2S slots and duplicated to both Left and Right channels. Plays for exactly 1.0 second at safe moderate amplitude, then stops cleanly.
- **Audio Routing Precautions:**
  - Never connect speaker terminals directly to ESP32 GPIOs.
  - Never tie MAX98357A output terminals (`OUT+` / `OUT-`) to ground (differential class-D bridge-tied load).

---

## 6. Mandatory Physical Multimeter Checks (Power Disconnected)

Perform these resistance checks using a digital multimeter set to **Resistance / Continuity Mode** with **ALL USB AND POWER DISCONNECTED**:

1. **Rail Isolation Check:**
   - Red probe on **Left (+) Rail (3.3V)**, Black probe on **Right (+) Rail (5.0V)**.
   - **Requirement:** Open circuit / Over-limit ($\mathbf{> 100\text{ k}\Omega}$). If $0\Omega$, **DO NOT APPLY POWER**. The rails are shorted!
2. **Left Rail Short Check:**
   - Red probe on **Left (+) Rail (3.3V)**, Black probe on **Left (-) Rail (GND)**.
   - **Requirement:** Must measure $> 1\text{ k}\Omega$ (charging capacitors may start low and rise). A reading $< 10\Omega$ indicates a dead short.
3. **Right Rail Short Check:**
   - Red probe on **Right (+) Rail (5.0V)**, Black probe on **Right (-) Rail (GND)**.
   - **Requirement:** Must measure $> 1\text{ k}\Omega$.
4. **Common Ground Continuity Check:**
   - Probe between **Left (-) Rail (GND)** and **Right (-) Rail (GND)**.
   - **Requirement:** Must read $\mathbf{0.0\text{ to }0.2\Omega}$ (direct solid connection).
5. **Keypad Pull-Up Resistor Check:**
   - Red probe on **Left (+) Rail (3.3V)**.
   - Black probe on ESP32 pin **GPIO 35** $\rightarrow$ Must read $\approx \mathbf{10\text{ k}\Omega}$.
   - Black probe on ESP32 pin **GPIO 13** $\rightarrow$ Must read $\approx \mathbf{10\text{ k}\Omega}$.
   - Black probe on ESP32 pin **GPIO 15** $\rightarrow$ Must read $\approx \mathbf{10\text{ k}\Omega}$.
   *(If any read $0\Omega$ or open circuit $\infty$, the pull-up resistor is not in the column circuit!)*
6. **Keypad Row Isolation Check:**
   - Red probe on **Left (+) Rail (3.3V)**.
   - Black probe on ESP32 pin **GPIO 12 (Row 4)** with NO keys pressed.
   - **Requirement:** Must read open circuit / infinite resistance. If it reads $10\text{ k}\Omega$, your pull-up is incorrectly attached to the row side of the tactile switch!

---

## 7. Interactive Diagnostic Suite Usage

Once the firmware is flashed using Arduino IDE 2.3.x (`COM3`, 115200 baud), open Serial Monitor (set to **115200 baud**, newline enabled).

The interactive diagnostic suite presents this clean ASCII menu:
```
======================================================================
  ⭐ LUMI ESP32 HARDWARE DIAGNOSTIC SUITE ⭐
======================================================================
  [1] Status LED Test (Blink GPIO 32)
  [2] DS3231 RTC Test (Read I2C Date/Time)
  [3] MicroSD SPI Card Test (Init & Sector Read)
  [4] Keypad 4x3 Matrix Test (Interactive Key Press)
  [5] INMP441 Microphone Audio Test (RMS & Peaks)
  [6] MAX98357A Speaker Audio Test (440Hz Sine Tone)
  [7] ILI9341 TFT Display Status (Disabled Report)
  [8] Host Serial Protocol Framing Check
  [A] Run All Peripheral Smoke Tests (1-3, 7, 8)
  [P] Switch to Production LUMI Binary Protocol Mode
======================================================================
```
Type any number (`1` through `8`, `A`, or `P`) into the Serial Monitor send box and press Enter to execute the test.
