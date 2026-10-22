/**
 * LUMI Companion — Interactive Firmware Simulator & UI/UX Runner
 * Directly executes logic from ui/ui_manager.cpp & input/keypad_driver.cpp
 */

// Color Constants (matching TFT_eSPI RGB565 converted to Web Colors)
const COLOR_BG        = '#EFFEFE'; // 0xEFFE: Soft Pastel Blue
const COLOR_TEXT      = '#1E293B'; // 0x2124: Dark Slate
const COLOR_CARD      = '#FFFFFF'; // 0xFFFF: White Surface
const COLOR_CYAN      = '#0D9488'; // 0x3D7E: Accent Teal
const TFT_DARKGREY    = '#64748B'; // 0x7BEF
const TFT_LIGHTGREY   = '#CBD5E1'; // 0xD69A
const TFT_GREEN       = '#16A34A'; // 0x07E0
const TFT_ORANGE      = '#EA580C'; // 0xFD20
const TFT_BLACK       = '#0F172A'; // 0x0000
const TFT_WHITE       = '#FFFFFF'; // 0xFFFF
const FACE_YELLOW     = '#FEF08A'; // 0xFEE0
const BLUSH_PINK      = '#FB7185'; // 0xFC72
const QUIZ_OPT_A_BG   = '#10B981'; // 0x10B981
const QUIZ_OPT_B_BG   = '#F43F5E'; // 0xF43F5E
const PROGRESS_BAR_BG = '#3B82F6'; // 0x3B82F6
const STAR_GOLD       = '#D97706'; // 0xD977

// Screen States (enum class ScreenState)
const ScreenState = {
  HOME: 'HOME',
  LEARNING: 'LEARNING',
  QUIZ: 'QUIZ',
  STORY: 'STORY',
  SETTINGS: 'SETTINGS',
  PROGRESS: 'PROGRESS',
};

// Face States (enum class LumiFaceState)
const LumiFaceState = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  THINKING: 'THINKING',
  SPEAKING: 'SPEAKING',
};

// Key Codes (enum class KeyCode)
const KeyCode = {
  NONE: 'NONE',
  NUM_0: 'NUM_0',
  NUM_1: 'NUM_1',
  NUM_2: 'NUM_2',
  NUM_3: 'NUM_3',
  NUM_4: 'NUM_4',
  NUM_5: 'NUM_5',
  NUM_6: 'NUM_6',
  NUM_7: 'NUM_7',
  NUM_8: 'NUM_8',
  NUM_9: 'NUM_9',
  BTN_BACKWARD: 'BTN_BACKWARD',
  BTN_FORWARD: 'BTN_FORWARD',
};

// Offline Educational Database (matching OFFLINE_DB in ui_manager.cpp)
const OFFLINE_DB = [
  {
    category: "Animal",
    title: "Elephant",
    imagePath: "/images/animals/elephant.bmp",
    body: "A giant gentle animal with a long trunk!\nSound: Pawoo!\nFact: Elephants wrap trunks to greet.",
    quizQ: "Which animal has a long trunk?",
    optA: "Elephant",
    optB: "Rabbit",
    correctOpt: 1
  },
  {
    category: "Animal",
    title: "Lion",
    imagePath: "/images/animals/lion.bmp",
    body: "King of the jungle with a big golden mane!\nSound: Roar!\nFact: Lions live in groups called prides.",
    quizQ: "What sound does a lion make?",
    optA: "Meow",
    optB: "Roar",
    correctOpt: 2
  },
  {
    category: "Fruit",
    title: "Apple",
    imagePath: "/images/fruits/apple.bmp",
    body: "Crisp, sweet, and juicy fruit!\nColors: Red, Green, or Yellow.\nFact: Apples can float in water!",
    quizQ: "What color is a ripe apple?",
    optA: "Red",
    optB: "Blue",
    correctOpt: 1
  },
  {
    category: "Fruit",
    title: "Banana",
    imagePath: "/images/fruits/banana.bmp",
    body: "Sweet fruit with an easy-to-peel skin!\nPacked with potassium to give you energy.",
    quizQ: "What color is a ripe banana?",
    optA: "Purple",
    optB: "Yellow",
    correctOpt: 2
  },
  {
    category: "Shape",
    title: "Circle",
    imagePath: "/images/shapes/circle.bmp",
    body: "A round curve with zero corners!\nExamples: The Sun, a clock, and a wheel.",
    quizQ: "How many corners does a circle have?",
    optA: "Zero",
    optB: "Four",
    correctOpt: 1
  },
  {
    category: "Shape",
    title: "Triangle",
    imagePath: "/images/shapes/triangle.bmp",
    body: "A shape with 3 straight sides & corners!\nExamples: A pizza slice and a pyramid.",
    quizQ: "How many sides does a triangle have?",
    optA: "3",
    optB: "5",
    correctOpt: 1
  },
  {
    category: "Number",
    title: "Number 5",
    imagePath: "/images/numbers/5.bmp",
    body: "High five! You have 5 fingers on each\nhand and 5 toes on each foot to balance.",
    quizQ: "How many fingers on one hand?",
    optA: "5",
    optB: "10",
    correctOpt: 1
  },
  {
    category: "Alphabet",
    title: "Letter A",
    imagePath: "/images/alphabets/a.bmp",
    body: "A is for Apple! Crisp and sweet.\nSay it out loud: 'Ah-Ah-Apple!'",
    quizQ: "What does Letter A stand for?",
    optA: "Apple",
    optB: "Boat",
    correctOpt: 1
  }
];

class UIManagerSimulator {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;

    // Internal State
    this.currentState = ScreenState.HOME;
    this.currentFace = LumiFaceState.IDLE;
    this.lastAnimUpdate = Date.now();
    this.animFrame = 0;
    this.batteryPct = 100;
    this.currentContentIndex = 0;

    // Loaded Content Fields
    this.currentTitle = "";
    this.currentBody = "";
    this.currentImagePath = "";
    this.quizOptA = "";
    this.quizOptB = "";
    this.currentCorrectOpt = 1;

    // Sound enabled flag
    this.soundEnabled = true;

    // Audio Context for beeps
    this.audioCtx = null;

    this.loadOfflineItem(0);
    this.render();
  }

  initAudio() {
    if (!this.audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.audioCtx = new AudioContext();
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
  }

  playKeyBeep(freq = 680, dur = 0.04) {
    if (!this.soundEnabled) return;
    try {
      this.initAudio();
      if (!this.audioCtx) return;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime);
      gain.gain.setValueAtTime(0.08, this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + dur);
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start();
      osc.stop(this.audioCtx.currentTime + dur);
    } catch (e) {
      // Audio autoplay policy fallback
    }
  }

  playQuizChime(isCorrect) {
    if (!this.soundEnabled) return;
    try {
      this.initAudio();
      if (!this.audioCtx) return;
      const now = this.audioCtx.currentTime;
      if (isCorrect) {
        // Happy ascending 3-note chime
        [523.25, 659.25, 783.99].forEach((f, i) => {
          const osc = this.audioCtx.createOscillator();
          const gain = this.audioCtx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(f, now + i * 0.1);
          gain.gain.setValueAtTime(0.12, now + i * 0.1);
          gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.1 + 0.25);
          osc.connect(gain);
          gain.connect(this.audioCtx.destination);
          osc.start(now + i * 0.1);
          osc.stop(now + i * 0.1 + 0.25);
        });
      } else {
        // Low double buzz
        [220, 180].forEach((f, i) => {
          const osc = this.audioCtx.createOscillator();
          const gain = this.audioCtx.createGain();
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(f, now + i * 0.12);
          gain.gain.setValueAtTime(0.1, now + i * 0.12);
          gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.12 + 0.15);
          osc.connect(gain);
          gain.connect(this.audioCtx.destination);
          osc.start(now + i * 0.12);
          osc.stop(now + i * 0.12 + 0.15);
        });
      }
    } catch (e) {}
  }

  speakText(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/\[.*?\]/g, '').replace(/⭐/g, 'star').trim();
    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.05;
    utterance.pitch = 1.15; // friendly, child-appropriate higher pitch

    // Switch face to SPEAKING while speaking
    const prevFace = this.currentFace;
    this.setLumiFace(LumiFaceState.SPEAKING);
    document.getElementById('speakerGrille')?.classList.add('speaking');

    utterance.onend = () => {
      this.setLumiFace(prevFace);
      document.getElementById('speakerGrille')?.classList.remove('speaking');
    };
    utterance.onerror = () => {
      this.setLumiFace(prevFace);
      document.getElementById('speakerGrille')?.classList.remove('speaking');
    };

    window.speechSynthesis.speak(utterance);
  }

  loadOfflineItem(index) {
    this.currentContentIndex = (index + OFFLINE_DB.length) % OFFLINE_DB.length;
    const item = OFFLINE_DB[this.currentContentIndex];
    this.currentTitle = item.title;
    this.currentBody = item.body;
    this.currentImagePath = item.imagePath;
    this.quizOptA = item.optA;
    this.quizOptB = item.optB;
    this.currentCorrectOpt = item.correctOpt;
  }

  nextContentItem() {
    this.loadOfflineItem(this.currentContentIndex + 1);
    this.log(`[CONTENT] Next Item -> [${this.currentContentIndex}] ${this.currentTitle}`);
    if (this.currentState === ScreenState.LEARNING || this.currentState === ScreenState.QUIZ) {
      this.render();
      if (this.soundEnabled && this.currentState === ScreenState.LEARNING) {
        this.speakText(`${this.currentTitle}. ${this.currentBody}`);
      }
    }
  }

  prevContentItem() {
    this.loadOfflineItem(this.currentContentIndex - 1);
    this.log(`[CONTENT] Prev Item -> [${this.currentContentIndex}] ${this.currentTitle}`);
    if (this.currentState === ScreenState.LEARNING || this.currentState === ScreenState.QUIZ) {
      this.render();
      if (this.soundEnabled && this.currentState === ScreenState.LEARNING) {
        this.speakText(`${this.currentTitle}. ${this.currentBody}`);
      }
    }
  }

  setScreenState(state) {
    this.currentState = state;
    this.log(`[UI] ScreenState transition -> ${state}`);
    this.render();

    // Update external UI buttons
    document.querySelectorAll('.btn-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.screen === state);
    });
    const chip = document.getElementById('activeScreenChip');
    if (chip) chip.textContent = `Screen: ${state}`;

    // Read screen aloud if in learning or quiz or story
    if (this.soundEnabled) {
      if (state === ScreenState.LEARNING) {
        this.speakText(`${this.currentTitle}. ${this.currentBody}`);
      } else if (state === ScreenState.QUIZ) {
        const q = OFFLINE_DB[this.currentContentIndex].quizQ || "Choose the answer";
        this.speakText(`${q}. Option 1: ${this.quizOptA}. Or Option 2: ${this.quizOptB}`);
      } else if (state === ScreenState.STORY) {
        this.speakText("The Clever Fox. Once upon a time in an enchanted forest, a curious fox named Rusty found a magic glowing compass under an oak tree...");
      }
    }
  }

  setLumiFace(face) {
    this.currentFace = face;
    const badge = document.getElementById('faceExpressionLabel');
    if (badge) badge.textContent = `FACE: ${face}`;
    document.querySelectorAll('.face-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.face === face);
    });
    if (this.currentState === ScreenState.HOME) {
      this.render();
    }
  }

  setContent(title, body, imagePath = "") {
    this.currentTitle = title;
    this.currentBody = body;
    this.currentImagePath = imagePath;
    if (this.currentState === ScreenState.LEARNING || this.currentState === ScreenState.STORY) {
      this.render();
    }
  }

  setQuiz(question, optA, optB) {
    this.currentTitle = question;
    this.quizOptA = optA;
    this.quizOptB = optB;
    this.setScreenState(ScreenState.QUIZ);
  }

  // Exact reproduction of UIManager::handleInput(KeyCode key)
  handleInput(key) {
    this.playKeyBeep(520 + Math.random() * 80);
    this.log(`[KEYPAD] Key pressed: ${key} (State: ${this.currentState})`);

    // [Backward] -> Return to Home or Settings
    // [Forward]  -> Next card or enter Learn mode
    if (key === KeyCode.BTN_BACKWARD) {
      if (this.currentState === ScreenState.HOME) {
        this.setScreenState(ScreenState.SETTINGS);
      } else {
        this.setScreenState(ScreenState.HOME);
      }
      return;
    }

    if (key === KeyCode.BTN_FORWARD) {
      if (this.currentState === ScreenState.LEARNING) {
        this.nextContentItem();
      } else {
        this.setScreenState(ScreenState.LEARNING);
      }
      return;
    }

    switch (this.currentState) {
      case ScreenState.HOME:
        if (key === KeyCode.NUM_1) this.setScreenState(ScreenState.LEARNING);
        else if (key === KeyCode.NUM_2) this.setScreenState(ScreenState.STORY);
        else if (key === KeyCode.NUM_3) this.setScreenState(ScreenState.QUIZ);
        else if (key === KeyCode.NUM_9) this.setScreenState(ScreenState.PROGRESS);
        break;

      case ScreenState.LEARNING:
        if (key === KeyCode.NUM_0) this.nextContentItem();
        else if (key === KeyCode.NUM_3) this.setScreenState(ScreenState.QUIZ);
        break;

      case ScreenState.QUIZ:
        if (key === KeyCode.NUM_1 || key === KeyCode.NUM_2) {
          const selected = (key === KeyCode.NUM_1) ? 1 : 2;
          const isCorrect = (selected === this.currentCorrectOpt);
          this.playQuizChime(isCorrect);
          if (isCorrect) {
            this.setContent("Quiz Result", "Correct! You got it right! ⭐", "");
            this.speakText("Correct! You got it right! Awesome job!");
          } else {
            const correctText = this.currentCorrectOpt === 1 ? this.quizOptA : this.quizOptB;
            this.setContent("Quiz Result", `Nice try! The correct answer is ${correctText}.`, "");
            this.speakText(`Nice try! Review and try again!`);
          }
          this.setScreenState(ScreenState.LEARNING);
        }
        break;

      default:
        if (key === KeyCode.NUM_0) this.setScreenState(ScreenState.HOME);
        break;
    }
  }

  // Animation update every 350ms (from updateAnimation)
  updateAnimation() {
    const now = Date.now();
    if (now - this.lastAnimUpdate > 350) {
      this.lastAnimUpdate = now;
      this.animFrame = (this.animFrame + 1) % 4;

      if (this.currentState === ScreenState.HOME) {
        this.renderHomeScreen();
      }
    }
  }

  // -------------------------------------------------------------
  // TFT Canvas Graphics Engine (Directly mapping TFT_eSPI calls)
  // -------------------------------------------------------------

  clearScreen() {
    this.ctx.fillStyle = COLOR_BG;
    this.ctx.fillRect(0, 0, 320, 240);
  }

  fillRoundRect(x, y, w, h, r, color) {
    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.roundRect(x, y, w, h, r);
    this.ctx.fill();
  }

  drawRoundRect(x, y, w, h, r, color) {
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.roundRect(x, y, w, h, r);
    this.ctx.stroke();
  }

  renderStatusBar(batteryPct) {
    // tft.drawRoundRect(275, 8, 28, 14, 2, TFT_DARKGREY);
    this.drawRoundRect(275, 8, 28, 14, 2, TFT_DARKGREY);
    // tft.fillRect(303, 12, 2, 6, TFT_DARKGREY);
    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.fillRect(303, 12, 2, 6);
    // int fillW = map(batteryPct, 0, 100, 0, 24);
    const fillW = Math.max(0, Math.min(24, Math.floor((batteryPct / 100) * 24)));
    // tft.fillRect(277, 10, fillW, 10, TFT_GREEN);
    const col = batteryPct > 20 ? TFT_GREEN : '#EF4444';
    this.ctx.fillStyle = col;
    this.ctx.fillRect(277, 10, fillW, 10);
  }

  renderHeader(title) {
    // tft.fillRect(0, 0, 320, 32, COLOR_CARD);
    this.ctx.fillStyle = COLOR_CARD;
    this.ctx.fillRect(0, 0, 320, 32);

    // tft.setTextColor(COLOR_TEXT); tft.setTextSize(2); tft.setCursor(15, 8);
    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 15px "Outfit", sans-serif';
    this.ctx.textBaseline = 'top';
    this.ctx.fillText(title, 15, 8);

    this.renderStatusBar(this.batteryPct);

    // tft.drawFastHLine(0, 32, 320, TFT_LIGHTGREY);
    this.ctx.strokeStyle = TFT_LIGHTGREY;
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(0, 32.5);
    this.ctx.lineTo(320, 32.5);
    this.ctx.stroke();
  }

  drawLumiFace(x, y, state, frame) {
    // tft.fillCircle(x, y, 42, 0xFEE0);
    this.ctx.fillStyle = FACE_YELLOW;
    this.ctx.beginPath();
    this.ctx.arc(x, y, 42, 0, Math.PI * 2);
    this.ctx.fill();

    // tft.drawCircle(x, y, 42, TFT_ORANGE);
    this.ctx.strokeStyle = TFT_ORANGE;
    this.ctx.lineWidth = 2;
    this.ctx.stroke();

    // Eyes
    if (state === LumiFaceState.LISTENING) {
      this.ctx.fillStyle = TFT_BLACK;
      this.ctx.beginPath();
      this.ctx.arc(x - 14, y - 8, 6, 0, Math.PI * 2);
      this.ctx.arc(x + 14, y - 8, 6, 0, Math.PI * 2);
      this.ctx.fill();

      // White shine
      this.ctx.fillStyle = TFT_WHITE;
      this.ctx.beginPath();
      this.ctx.arc(x - 12, y - 10, 2, 0, Math.PI * 2);
      this.ctx.arc(x + 16, y - 10, 2, 0, Math.PI * 2);
      this.ctx.fill();
    } else if (state === LumiFaceState.THINKING) {
      this.ctx.fillStyle = TFT_BLACK;
      this.ctx.beginPath();
      this.ctx.arc(x - 14, y - 12, 5, 0, Math.PI * 2);
      this.ctx.arc(x + 14, y - 12, 5, 0, Math.PI * 2);
      this.ctx.fill();
    } else {
      if (frame === 3) {
        // Blinking lines
        this.ctx.strokeStyle = TFT_BLACK;
        this.ctx.lineWidth = 2.5;
        this.ctx.beginPath();
        this.ctx.moveTo(x - 20, y - 8);
        this.ctx.lineTo(x - 8, y - 8);
        this.ctx.moveTo(x + 8, y - 8);
        this.ctx.lineTo(x + 20, y - 8);
        this.ctx.stroke();
      } else {
        this.ctx.fillStyle = TFT_BLACK;
        this.ctx.beginPath();
        this.ctx.arc(x - 14, y - 8, 5, 0, Math.PI * 2);
        this.ctx.arc(x + 14, y - 8, 5, 0, Math.PI * 2);
        this.ctx.fill();
      }
    }

    // Blush cheeks
    this.ctx.fillStyle = BLUSH_PINK;
    this.ctx.beginPath();
    this.ctx.arc(x - 24, y + 6, 4, 0, Math.PI * 2);
    this.ctx.arc(x + 24, y + 6, 4, 0, Math.PI * 2);
    this.ctx.fill();

    // Mouth area
    if (state === LumiFaceState.SPEAKING) {
      const mouthHeight = (frame % 2 === 0) ? 8 : 4;
      this.fillRoundRect(x - 8, y + 12, 16, mouthHeight, 3, TFT_BLACK);
    } else {
      // Smile curve
      this.ctx.strokeStyle = TFT_BLACK;
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.arc(x, y + 8, 8, 0.1 * Math.PI, 0.9 * Math.PI);
      this.ctx.stroke();
    }
  }

  drawItemImage(x, y, w, h, category, path) {
    // Base card
    this.fillRoundRect(x, y, w, h, 6, '#F8FAFC');
    this.drawRoundRect(x, y, w, h, 6, '#CBD5E1');

    if (category === "Animal") {
      // Cute animal face
      this.ctx.fillStyle = FACE_YELLOW;
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2, y + h / 2 - 2, 18, 0, Math.PI * 2);
      this.ctx.fill();

      // Ears
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2 - 12, y + h / 2 - 16, 6, 0, Math.PI * 2);
      this.ctx.arc(x + w / 2 + 12, y + h / 2 - 16, 6, 0, Math.PI * 2);
      this.ctx.fill();

      // Nose & Eyes
      this.ctx.fillStyle = TFT_BLACK;
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2 - 6, y + h / 2 - 4, 2, 0, Math.PI * 2);
      this.ctx.arc(x + w / 2 + 6, y + h / 2 - 4, 2, 0, Math.PI * 2);
      this.ctx.arc(x + w / 2, y + h / 2 + 2, 3, 0, Math.PI * 2);
      this.ctx.fill();
    } else if (category === "Fruit") {
      // Red apple
      this.ctx.fillStyle = '#EF4444';
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2, y + h / 2 + 2, 16, 0, Math.PI * 2);
      this.ctx.fill();
      // Green stem
      this.ctx.fillStyle = '#16A34A';
      this.ctx.fillRect(x + w / 2 - 2, y + h / 2 - 18, 4, 6);
    } else if (category === "Shape") {
      // Geometry badge
      this.ctx.strokeStyle = '#2563EB';
      this.ctx.lineWidth = 2;
      this.ctx.strokeRect(x + 14, y + 14, w - 28, h - 28);
      this.ctx.fillStyle = '#F472B6';
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2, y + h / 2, 12, 0, Math.PI * 2);
      this.ctx.fill();
    } else {
      this.ctx.fillStyle = TFT_DARKGREY;
      this.ctx.font = 'bold 22px "Outfit", sans-serif';
      this.ctx.textBaseline = 'middle';
      this.ctx.textAlign = 'center';
      this.ctx.fillText("123", x + w / 2, y + h / 2);
      this.ctx.textAlign = 'left';
    }
  }

  renderHomeScreen() {
    this.clearScreen();
    this.renderHeader("Hi, Friend! :)");
    this.drawLumiFace(160, 95, this.currentFace, this.animFrame);

    // tft.fillRoundRect(20, 175, 280, 50, 10, COLOR_CARD);
    this.fillRoundRect(20, 175, 280, 50, 10, COLOR_CARD);
    this.drawRoundRect(20, 175, 280, 50, 10, TFT_LIGHTGREY);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 12px "Outfit", sans-serif';
    this.ctx.textBaseline = 'middle';
    this.ctx.textAlign = 'center';
    this.ctx.fillText("[1] Learn   [2] Story   [3] Quiz   [Fwd] Go", 160, 200);
    this.ctx.textAlign = 'left';
  }

  renderLearningScreen() {
    this.clearScreen();
    this.renderHeader("Learn Mode");
    this.fillRoundRect(15, 42, 290, 188, 8, COLOR_CARD);
    this.drawRoundRect(15, 42, 290, 188, 8, TFT_LIGHTGREY);

    const cat = OFFLINE_DB[this.currentContentIndex].category;
    this.drawItemImage(25, 52, 60, 60, cat, this.currentImagePath);

    // Title
    this.ctx.fillStyle = COLOR_CYAN;
    this.ctx.font = 'bold 16px "Outfit", sans-serif';
    this.ctx.fillText(this.currentTitle, 95, 54);

    // Category
    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = '11px "Outfit", sans-serif';
    this.ctx.fillText("Category: " + cat, 95, 78);

    // Body with newlines
    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = '11px "Outfit", sans-serif';
    const lines = this.currentBody.split('\n');
    lines.forEach((l, idx) => {
      this.ctx.fillText(l, 25, 124 + idx * 17);
    });

    // Navigation hints
    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = '10px "JetBrains Mono", monospace';
    this.ctx.fillText("[Fwd] Next | [3] Quiz | [Back] Home", 25, 212);
  }

  renderQuizScreen() {
    this.clearScreen();
    this.renderHeader("Quiz Challenge");
    this.fillRoundRect(15, 45, 290, 180, 8, COLOR_CARD);
    this.drawRoundRect(15, 45, 290, 180, 8, TFT_LIGHTGREY);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 13px "Outfit", sans-serif';
    const q = OFFLINE_DB[this.currentContentIndex].quizQ || "Choose the answer:";
    this.ctx.fillText(q, 25, 60);

    // Option A button (Green)
    this.fillRoundRect(25, 110, 270, 40, 6, QUIZ_OPT_A_BG);
    this.ctx.fillStyle = TFT_WHITE;
    this.ctx.font = 'bold 13px "Outfit", sans-serif';
    this.ctx.fillText("1. " + this.quizOptA, 35, 122);

    // Option B button (Red)
    this.fillRoundRect(25, 160, 270, 40, 6, QUIZ_OPT_B_BG);
    this.ctx.fillStyle = TFT_WHITE;
    this.ctx.fillText("2. " + this.quizOptB, 35, 172);
  }

  renderStoryScreen() {
    this.clearScreen();
    this.renderHeader("Story Time");
    this.fillRoundRect(15, 45, 290, 175, 8, COLOR_CARD);
    this.drawRoundRect(15, 45, 290, 175, 8, TFT_LIGHTGREY);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 16px "Outfit", sans-serif';
    this.ctx.fillText("The Clever Fox", 30, 65);

    this.ctx.font = '11px "Outfit", sans-serif';
    const storyLines = [
      "Once upon a time in an enchanted forest,",
      "a curious fox named Rusty found a magic",
      "glowing compass under an oak tree...",
      "",
      "Press [Back] to exit."
    ];
    storyLines.forEach((l, idx) => {
      this.ctx.fillText(l, 30, 100 + idx * 18);
    });
  }

  renderSettingsScreen() {
    this.clearScreen();
    this.renderHeader("LUMI Setup");
    this.fillRoundRect(15, 45, 290, 175, 8, COLOR_CARD);
    this.drawRoundRect(15, 45, 290, 175, 8, TFT_LIGHTGREY);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = '11px "JetBrains Mono", monospace';
    const settings = [
      `Battery: ${this.batteryPct}% (CR2032 Active)`,
      "Volume: Normal (MAX98357A)",
      "Keypad: 4x3 Matrix Active-Low",
      "Storage: MicroSD SPI Ready",
      "",
      "Press [Back] to return Home."
    ];
    settings.forEach((l, idx) => {
      this.ctx.fillText(l, 30, 65 + idx * 20);
    });
  }

  renderProgressScreen() {
    this.clearScreen();
    this.renderHeader("My Learning Stars");
    this.fillRoundRect(15, 45, 290, 175, 8, COLOR_CARD);
    this.drawRoundRect(15, 45, 290, 175, 8, TFT_LIGHTGREY);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 15px "Outfit", sans-serif';
    this.ctx.fillText("Weekly Progress: 70%", 30, 60);

    // Progress bar
    this.drawRoundRect(30, 95, 260, 22, 5, TFT_DARKGREY);
    this.fillRoundRect(32, 97, 182, 18, 4, PROGRESS_BAR_BG);

    this.ctx.font = '12px "Outfit", sans-serif';
    this.ctx.fillText("Quizzes Completed: 8 / 10", 30, 130);
    this.ctx.fillText("Stories Listened: 5", 30, 150);

    this.ctx.fillStyle = STAR_GOLD;
    this.ctx.fillText("Awesome job! 3 Stars! ⭐⭐⭐", 30, 175);
  }

  render() {
    switch (this.currentState) {
      case ScreenState.HOME:     this.renderHomeScreen(); break;
      case ScreenState.LEARNING: this.renderLearningScreen(); break;
      case ScreenState.QUIZ:     this.renderQuizScreen(); break;
      case ScreenState.STORY:    this.renderStoryScreen(); break;
      case ScreenState.SETTINGS: this.renderSettingsScreen(); break;
      case ScreenState.PROGRESS: this.renderProgressScreen(); break;
    }
  }

  log(msg) {
    const consoleEl = document.getElementById('serialConsole');
    if (!consoleEl) return;
    const div = document.createElement('div');
    div.className = 'log-line';
    if (msg.includes('KEYPAD')) div.classList.add('warn');
    else if (msg.includes('ScreenState')) div.classList.add('success');
    else if (msg.includes('CONTENT')) div.classList.add('info');

    const time = new Date().toLocaleTimeString();
    div.textContent = `[${time}] ${msg}`;
    consoleEl.appendChild(div);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
}

// -------------------------------------------------------------
// App Initialization & DOM Binding
// -------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('tftCanvas');
  const sim = new UIManagerSimulator(canvas);

  // Animation Loop (matches updateAnimation)
  setInterval(() => {
    sim.updateAnimation();
  }, 100);

  // Keypad button clicks
  document.querySelectorAll('.key-btn').forEach(btn => {
    const key = btn.dataset.key;
    btn.addEventListener('click', () => {
      btn.classList.add('pressed');
      setTimeout(() => btn.classList.remove('pressed'), 120);
      sim.handleInput(KeyCode[key] || KeyCode.NONE);
    });
  });

  // Screen Tab Buttons
  document.querySelectorAll('.btn-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      sim.setScreenState(ScreenState[btn.dataset.screen]);
    });
  });

  // Face Expression Buttons
  document.querySelectorAll('.face-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      sim.setLumiFace(LumiFaceState[btn.dataset.face]);
    });
  });

  // Battery Slider
  const batterySlider = document.getElementById('batterySlider');
  const batteryVal = document.getElementById('batteryVal');
  if (batterySlider && batteryVal) {
    batterySlider.addEventListener('input', (e) => {
      sim.batteryPct = parseInt(e.target.value, 10);
      batteryVal.textContent = `${sim.batteryPct}%`;
      sim.render();
    });
  }

  // Catalog Browser Grid
  const catalogGrid = document.getElementById('catalogGrid');
  const carouselCounter = document.getElementById('carouselCounter');

  function updateCatalogCards() {
    if (!catalogGrid) return;
    catalogGrid.innerHTML = '';
    OFFLINE_DB.forEach((item, idx) => {
      const card = document.createElement('div');
      card.className = `catalog-card ${idx === sim.currentContentIndex ? 'active' : ''}`;
      card.innerHTML = `
        <span class="catalog-card-cat">${item.category}</span>
        <span class="catalog-card-title">${item.title}</span>
      `;
      card.addEventListener('click', () => {
        sim.loadOfflineItem(idx);
        sim.setScreenState(ScreenState.LEARNING);
        updateCatalogCards();
      });
      catalogGrid.appendChild(card);
    });
    if (carouselCounter) {
      carouselCounter.textContent = `Item ${sim.currentContentIndex + 1} of ${OFFLINE_DB.length}`;
    }
  }
  updateCatalogCards();

  document.getElementById('btnNextItem')?.addEventListener('click', () => {
    sim.nextContentItem();
    updateCatalogCards();
  });
  document.getElementById('btnPrevItem')?.addEventListener('click', () => {
    sim.prevContentItem();
    updateCatalogCards();
  });
  document.getElementById('btnSpeakContent')?.addEventListener('click', () => {
    sim.speakText(`${sim.currentTitle}. ${sim.currentBody}`);
  });

  // Clear log
  document.getElementById('btnClearLog')?.addEventListener('click', () => {
    const consoleEl = document.getElementById('serialConsole');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-line info">[CONSOLE] Log cleared. Ready.</div>';
  });

  // Sound toggle
  const soundBtn = document.getElementById('btnSoundToggle');
  const soundLabel = document.getElementById('soundLabel');
  if (soundBtn && soundLabel) {
    soundBtn.addEventListener('click', () => {
      sim.soundEnabled = !sim.soundEnabled;
      soundBtn.classList.toggle('active', sim.soundEnabled);
      soundLabel.textContent = sim.soundEnabled ? 'Sound ON' : 'Sound OFF';
    });
  }

  // Keyboard Navigation
  window.addEventListener('keydown', (e) => {
    // Prevent scrolling for arrows and space
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space'].includes(e.code)) {
      e.preventDefault();
    }

    let mappedKey = null;
    let buttonId = null;

    if (e.key >= '0' && e.key <= '9') {
      mappedKey = KeyCode[`NUM_${e.key}`];
      buttonId = `key-${e.key}`;
    } else if (e.key === 'ArrowLeft' || e.key === 'Backspace') {
      mappedKey = KeyCode.BTN_BACKWARD;
      buttonId = 'key-back';
    } else if (e.key === 'ArrowRight' || e.key === 'Enter' || e.code === 'Space') {
      mappedKey = KeyCode.BTN_FORWARD;
      buttonId = 'key-fwd';
    }

    if (mappedKey) {
      if (buttonId) {
        const btn = document.getElementById(buttonId);
        if (btn) {
          btn.classList.add('pressed');
          setTimeout(() => btn.classList.remove('pressed'), 120);
        }
      }
      sim.handleInput(mappedKey);
      updateCatalogCards();
    }
  });

  // Canvas click to select Quiz answers if in QUIZ mode
  canvas.addEventListener('click', (e) => {
    if (sim.currentState !== ScreenState.QUIZ) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = 320 / rect.width;
    const scaleY = 240 / rect.height;
    const clickY = (e.clientY - rect.top) * scaleY;

    if (clickY >= 110 && clickY <= 150) {
      sim.handleInput(KeyCode.NUM_1);
      updateCatalogCards();
    } else if (clickY >= 160 && clickY <= 200) {
      sim.handleInput(KeyCode.NUM_2);
      updateCatalogCards();
    }
  });
});
