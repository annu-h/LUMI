/**
 * LUMI Companion — Integrated Voice Agent & ESP32 Hardware Simulator Client
 * Pure Vanilla JavaScript — Zero External Dependencies or CDNs.
 * Connects UI/UX Developer Canvas & Keypad to Offline Whisper & Piper TTS.
 */

// Screen States (enum class ScreenState matching ui_manager.h)
const ScreenState = {
  HOME: 'HOME',
  LEARNING: 'LEARNING',
  QUIZ: 'QUIZ',
  STORY: 'STORY',
  SETTINGS: 'SETTINGS',
  PROGRESS: 'PROGRESS',
};

// Face States (enum class LumiFaceState matching ui_manager.h)
const LumiFaceState = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  THINKING: 'THINKING',
  SPEAKING: 'SPEAKING',
};

// Key Codes (enum class KeyCode matching keypad_driver.h)
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

// Color Constants (RGB565 converted to Web Colors)
const COLOR_BG        = '#EFFEFE';
const COLOR_TEXT      = '#1E293B';
const COLOR_CARD      = '#FFFFFF';
const COLOR_CYAN      = '#0D9488';
const TFT_DARKGREY    = '#64748B';
const TFT_LIGHTGREY   = '#CBD5E1';
const TFT_GREEN       = '#16A34A';
const TFT_ORANGE      = '#EA580C';
const TFT_BLACK       = '#0F172A';
const TFT_WHITE       = '#FFFFFF';
const FACE_YELLOW     = '#FEF08A';
const BLUSH_PINK      = '#FB7185';

// Default Educational Database (augmented dynamically from /api/educational/catalog)
let OFFLINE_DB = [
  {
    category: "Animal",
    title: "Elephant",
    icon: "🐘",
    imagePath: "/images/animals/elephant.bmp",
    body: "A giant gentle animal with a long trunk!\nSound: Pawoo!\nFact: Elephants wrap trunks to greet.",
    quizQ: "Which animal has a long trunk?",
    optA: "Elephant",
    optB: "Rabbit",
    correctOpt: 1,
    explanation: "Elephants use their long trunks for breathing, drinking water, and picking up food!"
  },
  {
    category: "Animal",
    title: "Lion",
    icon: "🦁",
    imagePath: "/images/animals/lion.bmp",
    body: "King of the jungle with a big golden mane!\nSound: Roar!\nFact: Lions live in groups called prides.",
    quizQ: "What sound does a lion make?",
    optA: "Meow",
    optB: "Roar",
    correctOpt: 2,
    explanation: "Lions roar loudly so their friends can hear them from miles away!"
  },
  {
    category: "Fruit",
    title: "Apple",
    icon: "🍎",
    imagePath: "/images/fruits/apple.bmp",
    body: "Crisp, sweet, and juicy fruit!\nColors: Red, Green, or Yellow.\nFact: Apples can float in water!",
    quizQ: "What color is a ripe apple?",
    optA: "Red",
    optB: "Blue",
    correctOpt: 1,
    explanation: "Apples are delicious and are usually red, yellow, or bright green!"
  },
  {
    category: "Fruit",
    title: "Banana",
    icon: "🍌",
    imagePath: "/images/fruits/banana.bmp",
    body: "Sweet fruit with an easy-to-peel skin!\nPacked with potassium to give you energy.",
    quizQ: "What color is a ripe banana?",
    optA: "Purple",
    optB: "Yellow",
    correctOpt: 2,
    explanation: "Ripe bananas turn bright sunny yellow and are sweet to eat!"
  },
  {
    category: "Shape",
    title: "Circle",
    icon: "⭕",
    imagePath: "/images/shapes/circle.bmp",
    body: "A round curve with zero corners!\nExamples: The Sun, a clock, and a wheel.",
    quizQ: "How many corners does a circle have?",
    optA: "Zero",
    optB: "Four",
    correctOpt: 1,
    explanation: "A circle is perfectly round all the way around with zero corners!"
  },
  {
    category: "Shape",
    title: "Triangle",
    icon: "🔺",
    imagePath: "/images/shapes/triangle.bmp",
    body: "A shape with 3 straight sides & corners!\nExamples: A pizza slice and a pyramid.",
    quizQ: "How many sides does a triangle have?",
    optA: "3",
    optB: "5",
    correctOpt: 1,
    explanation: "Triangles have three straight sides and three pointy corners!"
  },
  {
    category: "Number",
    title: "Number 5",
    icon: "5️⃣",
    imagePath: "/images/numbers/5.bmp",
    body: "High five! You have 5 fingers on each\nhand and 5 toes on each foot to balance.",
    quizQ: "How many fingers on one hand?",
    optA: "5",
    optB: "10",
    correctOpt: 1,
    explanation: "Count them with me: one, two, three, four, five! High five!"
  },
  {
    category: "Alphabet",
    title: "Letter A",
    icon: "🅰️",
    imagePath: "/images/alphabets/a.bmp",
    body: "A is for Apple! Crisp and sweet.\nSay it out loud: 'Ah-Ah-Apple!'",
    quizQ: "What does Letter A stand for?",
    optA: "Apple",
    optB: "Boat",
    correctOpt: 1,
    explanation: "A is the very first letter of the alphabet, and A is for Apple!"
  }
];

// Offline Local Stories
const LOCAL_STORIES = [
  {
    title: "The Clever Fox",
    icon: "🦊",
    body: "Once upon a time in an enchanted forest, a curious fox named Rusty found a magic glowing compass under an old oak tree. The needle didn't point north—it pointed toward friendly adventures and new animal friends!\n\nRusty followed the gentle glow through misty meadows, across singing brooks, until he found a little bear who needed help finding sweet honeycombs. Together, they shared a joyful afternoon of laughter, friendship, and discovery."
  },
  {
    title: "The Lost Puppy",
    icon: "🐶",
    body: "Barnaby was a fluffy puppy with floppy ears and a big tail wag. One sunny morning, he chased a bright blue butterfly into the green meadow and couldn't find his garden gate!\n\nBarnaby sat quietly and listened. Soon, he heard his friend LUMI singing a gentle tune from the porch. Guided by the cheerful melody, Barnaby trotted happily home and snuggled safely into his warm basket."
  },
  {
    title: "The Little Cloud",
    icon: "☁️",
    body: "High in the turquoise sky lived Puffy, a small white cloud who dreamed of painting flowers. One warm summer afternoon, Puffy gathered tiny drops of sparkling rain and showered a sleepy meadow.\n\nSuddenly, red poppies, golden daisies, and purple lavender popped open their petals with joy. Puffy drifted softly across the sunset, happy to bring smiles to the earth below."
  },
  {
    title: "The Brave Squirrel",
    icon: "🐿️",
    body: "Sammy the squirrel loved climbing the tallest pine trees, but today he noticed a lost baby robin shivering on a low branch. Sammy took a deep breath, gathered soft moss, and carefully guided the little bird back up to its cozy nest.\n\nMomma Robin sang a sweet song of gratitude. Sammy learned that bravery isn't about being big—it's about helping others when they need you."
  }
];

// =========================================================================
// API & Audio Utilities
// =========================================================================

async function apiRequest(endpoint, method = "GET", data = null) {
  const options = { method, headers: {} };
  if (data && !(data instanceof FormData)) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(data);
  } else if (data instanceof FormData) {
    options.body = data;
  }

  const response = await fetch(endpoint, options);
  const result = await response.json().catch(() => ({ error: "Invalid JSON response" }));
  if (!response.ok && !result.badge) {
    result.status = "FAILED";
  }
  return result;
}

// Global loadSystemStatus helper retained for test compatibility
async function loadSystemStatus() {
  try {
    return await apiRequest("/api/status");
  } catch (err) {
    console.error("loadSystemStatus error:", err);
    return null;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

class LiveAudioRecorder {
  constructor() {
    this.audioCtx = null;
    this.mediaStream = null;
    this.sourceNode = null;
    this.analyserNode = null;
    this.scriptNode = null;
    this.recordedChunks = [];
    this.isRecording = false;
  }

  async start() {
    if (this.isRecording) return;
    this.recordedChunks = [];

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: { ideal: 16000 },
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.mediaStream = stream;
    const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
    this.audioCtx = new AudioCtxClass();
    if (this.audioCtx.state === "suspended") {
      await this.audioCtx.resume();
    }

    this.sourceNode = this.audioCtx.createMediaStreamSource(stream);
    this.analyserNode = this.audioCtx.createAnalyser();
    this.analyserNode.fftSize = 256;

    const bufferSize = 4096;
    this.scriptNode = this.audioCtx.createScriptProcessor(bufferSize, 1, 1);

    this.scriptNode.onaudioprocess = (e) => {
      if (!this.isRecording) return;
      const channelData = e.inputBuffer.getChannelData(0);
      this.recordedChunks.push(new Float32Array(channelData));
    };

    this.isRecording = true;
    this.muteGain = this.audioCtx.createGain();
    this.muteGain.gain.value = 0;
    this.sourceNode.connect(this.analyserNode);
    this.analyserNode.connect(this.scriptNode);
    this.scriptNode.connect(this.muteGain);
    this.muteGain.connect(this.audioCtx.destination);
  }

  async stop() {
    this.isRecording = false;

    if (this.scriptNode) {
      this.scriptNode.disconnect();
      this.scriptNode.onaudioprocess = null;
    }
    if (this.muteGain) this.muteGain.disconnect();
    if (this.analyserNode) this.analyserNode.disconnect();
    if (this.sourceNode) this.sourceNode.disconnect();
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
    }

    const originalRate = this.audioCtx ? this.audioCtx.sampleRate : 44100;
    if (this.audioCtx && this.audioCtx.state !== "closed") {
      await this.audioCtx.close().catch(() => {});
    }

    let totalSamples = 0;
    for (const chunk of this.recordedChunks) totalSamples += chunk.length;
    const fullBuffer = new Float32Array(totalSamples);
    let offset = 0;
    for (const chunk of this.recordedChunks) {
      fullBuffer.set(chunk, offset);
      offset += chunk.length;
    }

    const targetRate = 16000;
    const resampled = this._resample(fullBuffer, originalRate, targetRate);
    return this._encodeWav(resampled, targetRate);
  }

  _resample(source, srcRate, tgtRate) {
    if (srcRate === tgtRate) return source;
    const ratio = srcRate / tgtRate;
    const newLen = Math.round(source.length / ratio);
    const result = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
      const srcIdx = i * ratio;
      const lower = Math.floor(srcIdx);
      const upper = Math.min(lower + 1, source.length - 1);
      const weight = srcIdx - lower;
      result[i] = source[lower] * (1 - weight) + source[upper] * weight;
    }
    return result;
  }

  _encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeStr = (off, s) => {
      for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
    };

    writeStr(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // Mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, samples.length * 2, true);

    let ptr = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(ptr, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      ptr += 2;
    }

    return new Blob([buffer], { type: "audio/wav" });
  }
}

// =========================================================================
// UI MANAGER SIMULATOR (Executes on 320x240 Canvas)
// =========================================================================

class UIManagerSimulator {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas ? canvas.getContext('2d') : null;
    if (this.ctx) this.ctx.imageSmoothingEnabled = false;

    this.currentState = ScreenState.HOME;
    this.currentFace = LumiFaceState.IDLE;
    this.lastAnimUpdate = Date.now();
    this.animFrame = 0;
    this.batteryPct = 100;
    this.currentContentIndex = 0;

    this.currentTitle = "";
    this.currentBody = "";
    this.currentImagePath = "";
    this.quizOptA = "";
    this.quizOptB = "";
    this.currentCorrectOpt = 1;

    this.soundEnabled = true;
    this.audioCtx = null;

    this.loadOfflineItem(0);
    this.render();
  }

  initAudio() {
    if (!this.audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) this.audioCtx = new AudioContext();
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
    } catch (e) {}
  }

  playQuizChime(isCorrect) {
    if (!this.soundEnabled) return;
    try {
      this.initAudio();
      if (!this.audioCtx) return;
      const now = this.audioCtx.currentTime;
      if (isCorrect) {
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

  loadOfflineItem(index) {
    if (!OFFLINE_DB.length) return;
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
    this.render();
    window.dispatchEvent(new CustomEvent('lumi-content-changed', { detail: { index: this.currentContentIndex } }));
  }

  prevContentItem() {
    this.loadOfflineItem(this.currentContentIndex - 1);
    this.render();
    window.dispatchEvent(new CustomEvent('lumi-content-changed', { detail: { index: this.currentContentIndex } }));
  }

  setScreenState(state) {
    this.currentState = state;
    this.render();
    window.dispatchEvent(new CustomEvent('lumi-screen-changed', { detail: { state } }));
  }

  setLumiFace(face) {
    this.currentFace = face;
    const badge = document.getElementById('faceExpressionLabel');
    if (badge) badge.textContent = `FACE: ${face}`;
    if (this.currentState === ScreenState.HOME) {
      this.render();
    }
  }

  handleInput(key) {
    this.playKeyBeep(520 + Math.random() * 80);

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
          window.dispatchEvent(new CustomEvent('lumi-quiz-selected', { detail: { selected } }));
        }
        break;

      default:
        if (key === KeyCode.NUM_0) this.setScreenState(ScreenState.HOME);
        break;
    }
  }

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
  // Canvas Graphics Engine (TFT_eSPI Mapping)
  // -------------------------------------------------------------
  clearScreen() {
    if (!this.ctx) return;
    this.ctx.fillStyle = COLOR_BG;
    this.ctx.fillRect(0, 0, 320, 240);
  }

  fillRoundRect(x, y, w, h, r, color) {
    if (!this.ctx) return;
    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.roundRect(x, y, w, h, r);
    this.ctx.fill();
  }

  drawRoundRect(x, y, w, h, r, color) {
    if (!this.ctx) return;
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.roundRect(x, y, w, h, r);
    this.ctx.stroke();
  }

  renderStatusBar(batteryPct) {
    if (!this.ctx) return;
    this.ctx.strokeStyle = TFT_DARKGREY;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(275, 8, 28, 14);
    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.fillRect(303, 12, 2, 6);
    const fillW = Math.max(0, Math.min(24, Math.round((batteryPct / 100) * 24)));
    this.ctx.fillStyle = TFT_GREEN;
    this.ctx.fillRect(277, 10, fillW, 10);
  }

  renderHeader(title) {
    if (!this.ctx) return;
    this.ctx.fillStyle = COLOR_CARD;
    this.ctx.fillRect(0, 0, 320, 32);
    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 15px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    this.ctx.fillText(title, 15, 22);
    this.renderStatusBar(this.batteryPct);
    this.ctx.strokeStyle = TFT_LIGHTGREY;
    this.ctx.lineWidth = 1;
    this.ctx.beginPath();
    this.ctx.moveTo(0, 32);
    this.ctx.lineTo(320, 32);
    this.ctx.stroke();
  }

  drawLumiFace(x, y, state, frame) {
    if (!this.ctx) return;
    // Face Body
    this.ctx.fillStyle = FACE_YELLOW;
    this.ctx.beginPath();
    this.ctx.arc(x, y, 42, 0, Math.PI * 2);
    this.ctx.fill();
    this.ctx.strokeStyle = TFT_ORANGE;
    this.ctx.lineWidth = 2;
    this.ctx.stroke();

    // Eyes
    this.ctx.fillStyle = TFT_BLACK;
    if (state === LumiFaceState.LISTENING) {
      this.ctx.beginPath();
      this.ctx.arc(x - 14, y - 8, 7, 0, Math.PI * 2);
      this.ctx.arc(x + 14, y - 8, 7, 0, Math.PI * 2);
      this.ctx.fill();
      // White highlight
      this.ctx.fillStyle = TFT_WHITE;
      this.ctx.beginPath();
      this.ctx.arc(x - 12, y - 10, 2.5, 0, Math.PI * 2);
      this.ctx.arc(x + 16, y - 10, 2.5, 0, Math.PI * 2);
      this.ctx.fill();
    } else if (state === LumiFaceState.THINKING) {
      this.ctx.beginPath();
      this.ctx.arc(x - 14, y - 12, 5, 0, Math.PI * 2);
      this.ctx.arc(x + 14, y - 12, 5, 0, Math.PI * 2);
      this.ctx.fill();
    } else {
      if (frame === 3) {
        // Blink
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.moveTo(x - 20, y - 8);
        this.ctx.lineTo(x - 8, y - 8);
        this.ctx.moveTo(x + 8, y - 8);
        this.ctx.lineTo(x + 20, y - 8);
        this.ctx.stroke();
      } else {
        this.ctx.beginPath();
        this.ctx.arc(x - 14, y - 8, 5, 0, Math.PI * 2);
        this.ctx.arc(x + 14, y - 8, 5, 0, Math.PI * 2);
        this.ctx.fill();
      }
    }

    // Blush cheeks
    this.ctx.fillStyle = BLUSH_PINK;
    this.ctx.beginPath();
    this.ctx.arc(x - 24, y + 6, 5, 0, Math.PI * 2);
    this.ctx.arc(x + 24, y + 6, 5, 0, Math.PI * 2);
    this.ctx.fill();

    // Mouth
    if (state === LumiFaceState.SPEAKING) {
      const mouthHeight = (frame % 2 === 0) ? 9 : 4;
      this.fillRoundRect(x - 9, y + 10, 18, mouthHeight, 4, TFT_BLACK);
    } else {
      this.ctx.strokeStyle = TFT_BLACK;
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.arc(x, y + 6, 8, 0.1 * Math.PI, 0.9 * Math.PI);
      this.ctx.stroke();
    }
  }

  drawItemImage(x, y, w, h, category) {
    if (!this.ctx) return;
    this.fillRoundRect(x, y, w, h, 8, '#E2E8F0');
    this.drawRoundRect(x, y, w, h, 8, '#94A3B8');

    if (category === "Animal") {
      this.ctx.fillStyle = '#F59E0B';
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2, y + h / 2 - 2, 18, 0, Math.PI * 2);
      this.ctx.arc(x + w / 2 - 14, y + h / 2 - 16, 7, 0, Math.PI * 2);
      this.ctx.arc(x + w / 2 + 14, y + h / 2 - 16, 7, 0, Math.PI * 2);
      this.ctx.fill();
    } else if (category === "Fruit") {
      this.ctx.fillStyle = '#EF4444';
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2, y + h / 2, 16, 0, Math.PI * 2);
      this.ctx.fill();
      this.ctx.fillStyle = '#15803D';
      this.ctx.fillRect(x + w / 2 - 2, y + h / 2 - 20, 4, 6);
    } else if (category === "Shape") {
      this.ctx.strokeStyle = '#3B82F6';
      this.ctx.lineWidth = 3;
      this.ctx.strokeRect(x + 14, y + 14, w - 28, h - 28);
      this.ctx.fillStyle = '#F43F5E';
      this.ctx.beginPath();
      this.ctx.arc(x + w / 2, y + h / 2, 10, 0, Math.PI * 2);
      this.ctx.fill();
    } else {
      this.ctx.fillStyle = '#0284C7';
      this.ctx.font = 'bold 22px monospace';
      this.ctx.fillText("123", x + 12, y + 38);
    }
  }

  render() {
    this.clearScreen();
    switch (this.currentState) {
      case ScreenState.HOME:     this.renderHomeScreen(); break;
      case ScreenState.LEARNING: this.renderLearningScreen(); break;
      case ScreenState.QUIZ:     this.renderQuizScreen(); break;
      case ScreenState.STORY:    this.renderStoryScreen(); break;
      case ScreenState.SETTINGS: this.renderSettingsScreen(); break;
      case ScreenState.PROGRESS: this.renderProgressScreen(); break;
    }
  }

  renderHomeScreen() {
    this.renderHeader("Hi, Friend! :)");
    this.drawLumiFace(160, 95, this.currentFace, this.animFrame);

    this.fillRoundRect(16, 175, 288, 48, 10, COLOR_CARD);
    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 11px monospace';
    this.ctx.fillText("[1] Learn   [2] Story   [3] Quiz   [Fwd] Go", 24, 204);
  }

  renderLearningScreen() {
    this.renderHeader("Learn Mode");
    this.fillRoundRect(12, 42, 296, 188, 8, COLOR_CARD);

    const cat = OFFLINE_DB[this.currentContentIndex]?.category || "Animal";
    this.drawItemImage(22, 52, 60, 60, cat);

    this.ctx.fillStyle = COLOR_CYAN;
    this.ctx.font = 'bold 16px sans-serif';
    this.ctx.fillText(this.currentTitle || "Title", 92, 68);

    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = '11px sans-serif';
    this.ctx.fillText(`Category: ${cat}`, 92, 88);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = '11px sans-serif';
    const lines = (this.currentBody || "").split('\n');
    lines.forEach((l, i) => {
      this.ctx.fillText(l, 22, 130 + i * 16);
    });

    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = 'bold 10px monospace';
    this.ctx.fillText("[Fwd] Next | [3] Quiz | [Back] Home", 22, 218);
  }

  renderQuizScreen() {
    this.renderHeader("Quiz Challenge");
    this.fillRoundRect(12, 42, 296, 188, 8, COLOR_CARD);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 14px sans-serif';
    const q = OFFLINE_DB[this.currentContentIndex]?.quizQ || "Choose the correct answer:";
    this.ctx.fillText(q, 22, 65);

    // Opt 1
    this.fillRoundRect(20, 95, 280, 42, 8, '#10B981');
    this.ctx.fillStyle = TFT_WHITE;
    this.ctx.font = 'bold 14px sans-serif';
    this.ctx.fillText(`1. ${this.quizOptA || "Option 1"}`, 32, 122);

    // Opt 2
    this.fillRoundRect(20, 150, 280, 42, 8, '#F43F5E');
    this.ctx.fillStyle = TFT_WHITE;
    this.ctx.font = 'bold 14px sans-serif';
    this.ctx.fillText(`2. ${this.quizOptB || "Option 2"}`, 32, 177);
  }

  renderStoryScreen() {
    this.renderHeader("Story Time");
    this.fillRoundRect(12, 42, 296, 188, 8, COLOR_CARD);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 16px sans-serif';
    this.ctx.fillText("The Clever Fox", 24, 68);

    this.ctx.font = '11px sans-serif';
    this.ctx.fillText("Once upon a time in an enchanted forest,", 24, 98);
    this.ctx.fillText("a curious fox named Rusty found a magic", 24, 116);
    this.ctx.fillText("glowing compass under an old oak tree...", 24, 134);
    this.ctx.fillText("It pointed to friendly adventures!", 24, 152);

    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = 'bold 10px monospace';
    this.ctx.fillText("Press [Back] to return Home.", 24, 215);
  }

  renderSettingsScreen() {
    this.renderHeader("LUMI Setup");
    this.fillRoundRect(12, 42, 296, 188, 8, COLOR_CARD);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = '11px sans-serif';
    this.ctx.fillText("Battery: 100% (CR2032 Active)", 24, 70);
    this.ctx.fillText("Volume: Normal (MAX98357A I2S)", 24, 92);
    this.ctx.fillText("Keypad: 4x3 Matrix Active-Low", 24, 114);
    this.ctx.fillText("STT: Faster-Whisper base.en (Offline)", 24, 136);
    this.ctx.fillText("TTS: Piper en_US-lessac (Slow 1.15)", 24, 158);

    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = 'bold 10px monospace';
    this.ctx.fillText("Press [Back] to return Home.", 24, 215);
  }

  renderProgressScreen() {
    this.renderHeader("My Learning Stars");
    this.fillRoundRect(12, 42, 296, 188, 8, COLOR_CARD);

    this.ctx.fillStyle = COLOR_TEXT;
    this.ctx.font = 'bold 14px sans-serif';
    this.ctx.fillText("Weekly Progress: 70%", 24, 68);

    this.drawRoundRect(24, 85, 268, 20, 5, TFT_DARKGREY);
    this.fillRoundRect(26, 87, 188, 16, 4, '#3B82F6');

    this.ctx.font = '11px sans-serif';
    this.ctx.fillText("Quizzes Completed: 8 / 10", 24, 128);
    this.ctx.fillText("Stories Listened: 5", 24, 148);

    this.ctx.fillStyle = '#D97706';
    this.ctx.font = 'bold 12px sans-serif';
    this.ctx.fillText("Awesome job! 3 Stars! ⭐⭐⭐", 24, 180);

    this.ctx.fillStyle = TFT_DARKGREY;
    this.ctx.font = 'bold 10px monospace';
    this.ctx.fillText("Press [Back] to return Home.", 24, 215);
  }
}

// =========================================================================
// MAIN LUMI COMPANION CONTROLLER
// =========================================================================

function initCompanionApp() {
  const canvas = document.getElementById("tftCanvas");
  const uiSim = new UIManagerSimulator(canvas);

  // Animation Loop for Canvas
  setInterval(() => {
    uiSim.updateAnimation();
  }, 100);

  // Elements
  const avatar = document.getElementById("lumiAvatar");
  const statusHeading = document.getElementById("companionStatusHeading");
  const statusSubtext = document.getElementById("companionStatusSubtext");
  const btnHeroMic = document.getElementById("btnHeroMic");
  const heroTimerBadge = document.getElementById("heroTimerBadge");
  const heroTimerText = document.getElementById("heroTimerText");
  const btnStopHero = document.getElementById("btnStopHero");
  const conversationFeed = document.getElementById("conversationFeed");
  const btnClearChatHistory = document.getElementById("btnClearChatHistory");
  const chatTextForm = document.getElementById("chatTextForm");
  const chatTypedInput = document.getElementById("chatTypedInput");
  const btnSpeedSlow = document.getElementById("btnSpeedSlow");
  const btnSpeedNormal = document.getElementById("btnSpeedNormal");
  const btnSoundToggle = document.getElementById("btnSoundToggle");
  const soundToggleIcon = document.getElementById("soundToggleIcon");
  const soundToggleText = document.getElementById("soundToggleText");
  const chkHandsFreeWake = document.getElementById("chkHandsFreeWake");
  const micAlertBanner = document.getElementById("micAlertBanner");
  const micAlertMessage = document.getElementById("micAlertMessage");
  const btnDismissAlert = document.getElementById("btnDismissAlert");
  const speakerGrille = document.getElementById("speakerGrille");

  // Learning Panel Elements
  const carouselCounter = document.getElementById("carouselCounter");
  const learningCatBadge = document.getElementById("learningCatBadge");
  const learningCardIcon = document.getElementById("learningCardIcon");
  const learningCardTitle = document.getElementById("learningCardTitle");
  const learningCardBody = document.getElementById("learningCardBody");
  const btnPrevItem = document.getElementById("btnPrevItem");
  const btnNextItem = document.getElementById("btnNextItem");
  const btnSpeakContent = document.getElementById("btnSpeakContent");
  const catalogGrid = document.getElementById("catalogGrid");

  // Quiz Panel Elements
  const quizCounter = document.getElementById("quizCounter");
  const quizScoreDisplay = document.getElementById("quizScoreDisplay");
  const quizQuestionText = document.getElementById("quizQuestionText");
  const btnQuizOptA = document.getElementById("btnQuizOptA");
  const btnQuizOptB = document.getElementById("btnQuizOptB");
  const quizOptAText = document.getElementById("quizOptAText");
  const quizOptBText = document.getElementById("quizOptBText");
  const quizResultBanner = document.getElementById("quizResultBanner");
  const quizResultIcon = document.getElementById("quizResultIcon");
  const quizResultTitle = document.getElementById("quizResultTitle");
  const quizResultBody = document.getElementById("quizResultBody");
  const btnNextQuiz = document.getElementById("btnNextQuiz");
  const btnRepeatQuizQuestion = document.getElementById("btnRepeatQuizQuestion");

  // Story Panel Elements
  const storyDisplayText = document.getElementById("storyDisplayText");
  const storyDisplayTitle = document.getElementById("storyDisplayTitle");
  const btnReadStoryAloud = document.getElementById("btnReadStoryAloud");
  const btnStopStoryAudio = document.getElementById("btnStopStoryAudio");
  const storyPills = document.querySelectorAll(".story-pill");

  // Progress Stats Elements
  const starsEarnedCount = document.getElementById("starsEarnedCount");
  const progressBarFill = document.getElementById("progressBarFill");
  const progressPctText = document.getElementById("progressPctText");
  const statQuizzesCount = document.getElementById("statQuizzesCount");
  const statStoriesCount = document.getElementById("statStoriesCount");
  const statTurnsCount = document.getElementById("statTurnsCount");
  const statTopicsCount = document.getElementById("statTopicsCount");

  // State
  let currentSpeed = "slow"; // Default Piper length_scale = 1.15 for young children
  let soundEnabled = true;
  let activeAudioPlayer = null;
  let currentTurnState = "ready";
  let liveRecorder = new LiveAudioRecorder();
  let timerInterval = null;
  let recordingStartTime = null;
  let autoStopTimeout = null;

  // Session Progress Tracking
  let sessionStars = 3;
  let sessionQuizzesAnswered = 8;
  let sessionStoriesHeard = 5;
  let sessionSpokenTurns = 0;
  let currentStoryIdx = 0;

  function updateProgressUI() {
    if (starsEarnedCount) starsEarnedCount.textContent = sessionStars;
    if (quizScoreDisplay) quizScoreDisplay.textContent = `Stars: ${sessionStars} ⭐`;
    const pct = Math.min(100, Math.round((sessionStars / 5) * 100));
    if (progressBarFill) progressBarFill.style.width = `${pct}%`;
    if (progressPctText) progressPctText.textContent = `${pct}% Completed`;
    if (statQuizzesCount) statQuizzesCount.textContent = `${sessionQuizzesAnswered} / 10`;
    if (statStoriesCount) statStoriesCount.textContent = `${sessionStoriesHeard}`;
    if (statTurnsCount) statTurnsCount.textContent = `${sessionSpokenTurns}`;
  }

  function setCompanionState(state, heading, subtext) {
    currentTurnState = state;
    if (avatar) avatar.setAttribute("data-state", state);

    // Sync face with hardware canvas
    if (state === "ready") uiSim.setLumiFace(LumiFaceState.IDLE);
    else if (state === "listening") uiSim.setLumiFace(LumiFaceState.LISTENING);
    else if (state === "processing") uiSim.setLumiFace(LumiFaceState.THINKING);
    else if (state === "speaking") uiSim.setLumiFace(LumiFaceState.SPEAKING);

    if (btnHeroMic) {
      btnHeroMic.className = `hero-mic-btn state-${state}`;
    }

    if (statusHeading && heading) statusHeading.textContent = heading;
    if (statusSubtext && subtext) statusSubtext.textContent = subtext;

    if (state === "listening") {
      if (heroTimerBadge) heroTimerBadge.classList.remove("hidden");
      if (btnStopHero) btnStopHero.classList.remove("hidden");
    } else {
      if (heroTimerBadge) heroTimerBadge.classList.add("hidden");
      if (btnStopHero) btnStopHero.classList.add("hidden");
    }
  }

  function showAlert(msg) {
    if (micAlertMessage) micAlertMessage.textContent = msg;
    if (micAlertBanner) micAlertBanner.classList.remove("hidden");
  }

  function dismissAlert() {
    if (micAlertBanner) micAlertBanner.classList.add("hidden");
  }

  if (btnDismissAlert) btnDismissAlert.addEventListener("click", dismissAlert);

  // Speed Toggles
  function setSpeed(speed) {
    currentSpeed = speed;
    if (speed === "slow") {
      btnSpeedSlow.classList.add("active");
      btnSpeedSlow.setAttribute("aria-checked", "true");
      btnSpeedNormal.classList.remove("active");
      btnSpeedNormal.setAttribute("aria-checked", "false");
    } else {
      btnSpeedNormal.classList.add("active");
      btnSpeedNormal.setAttribute("aria-checked", "true");
      btnSpeedSlow.classList.remove("active");
      btnSpeedSlow.setAttribute("aria-checked", "false");
    }
  }
  if (btnSpeedSlow) btnSpeedSlow.addEventListener("click", () => setSpeed("slow"));
  if (btnSpeedNormal) btnSpeedNormal.addEventListener("click", () => setSpeed("normal"));

  // Voice Toggle
  if (btnSoundToggle) {
    btnSoundToggle.addEventListener("click", () => {
      soundEnabled = !soundEnabled;
      uiSim.soundEnabled = soundEnabled;
      if (soundEnabled) {
        btnSoundToggle.classList.remove("muted");
        btnSoundToggle.classList.add("active");
        if (soundToggleIcon) soundToggleIcon.textContent = "🔊";
        if (soundToggleText) soundToggleText.textContent = "Voice On";
      } else {
        btnSoundToggle.classList.add("muted");
        btnSoundToggle.classList.remove("active");
        if (soundToggleIcon) soundToggleIcon.textContent = "🔇";
        if (soundToggleText) soundToggleText.textContent = "Voice Muted";
        if (activeAudioPlayer) {
          activeAudioPlayer.pause();
          activeAudioPlayer = null;
        }
      }
    });
  }

  // Real Piper TTS audio playback
  async function speakWithPiperTTS(text, fallbackText = null) {
    if (!soundEnabled) return;
    if (activeAudioPlayer) {
      activeAudioPlayer.pause();
      activeAudioPlayer = null;
    }

    setCompanionState("speaking", "LUMI is speaking...", "Listening to Piper voice response.");
    if (speakerGrille) speakerGrille.classList.add("speaking");

    try {
      const res = await apiRequest("/api/tts/speak", "POST", {
        text: text,
        speech_speed: currentSpeed,
      });

      if (res && res.status === "SUCCESS" && res.audio_url) {
        const audio = new Audio(res.audio_url);
        activeAudioPlayer = audio;

        audio.onended = () => {
          activeAudioPlayer = null;
          if (speakerGrille) speakerGrille.classList.remove("speaking");
          setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
        };

        audio.onerror = () => {
          console.warn("Audio element failed, falling back to browser speech.");
          browserSpeechFallback(text);
        };

        await audio.play();
        return;
      }
    } catch (err) {
      console.warn("Piper TTS fetch failed, using browser speech fallback:", err);
    }

    browserSpeechFallback(text || fallbackText);
  }

  function browserSpeechFallback(text) {
    if (!('speechSynthesis' in window)) {
      if (speakerGrille) speakerGrille.classList.remove("speaking");
      setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/\[.*?\]/g, '').replace(/⭐/g, 'star').trim());
    u.rate = currentSpeed === "slow" ? 0.85 : 1.0;
    u.onend = () => {
      if (speakerGrille) speakerGrille.classList.remove("speaking");
      setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
    };
    u.onerror = () => {
      if (speakerGrille) speakerGrille.classList.remove("speaking");
      setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
    };
    window.speechSynthesis.speak(u);
  }

  // --- Screen Tabs Switching ---
  const screenTabBtns = document.querySelectorAll(".screen-tab-btn");
  const screenPanels = {
    HOME: document.getElementById("panelHome"),
    LEARNING: document.getElementById("panelLearning"),
    QUIZ: document.getElementById("panelQuiz"),
    STORY: document.getElementById("panelStory"),
    PROGRESS: document.getElementById("panelProgress"),
    SETTINGS: document.getElementById("panelSettings"),
  };

  function switchScreen(state) {
    screenTabBtns.forEach(btn => {
      const match = btn.dataset.screen === state;
      btn.classList.toggle("active", match);
      btn.setAttribute("aria-selected", match ? "true" : "false");
    });

    Object.keys(screenPanels).forEach(k => {
      if (screenPanels[k]) {
        screenPanels[k].classList.toggle("active", k === state);
      }
    });

    uiSim.setScreenState(state);

    if (state === ScreenState.LEARNING) {
      updateLearningCardUI();
    } else if (state === ScreenState.QUIZ) {
      updateQuizUI();
    }
  }

  screenTabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetScreen = btn.dataset.screen;
      if (targetScreen) switchScreen(targetScreen);
    });
  });

  // Listen for screen changes triggered by keypad/keyboard
  window.addEventListener('lumi-screen-changed', (e) => {
    const s = e.detail.state;
    screenTabBtns.forEach(btn => {
      const match = btn.dataset.screen === s;
      btn.classList.toggle("active", match);
      btn.setAttribute("aria-selected", match ? "true" : "false");
    });
    Object.keys(screenPanels).forEach(k => {
      if (screenPanels[k]) {
        screenPanels[k].classList.toggle("active", k === s);
      }
    });
    if (s === ScreenState.LEARNING) updateLearningCardUI();
    else if (s === ScreenState.QUIZ) updateQuizUI();
  });

  // --- Keypad Click and Keyboard Binding ---
  const keyBtns = document.querySelectorAll(".key-btn");
  keyBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.key;
      btn.classList.add("pressed");
      setTimeout(() => btn.classList.remove("pressed"), 120);
      if (key && KeyCode[key]) {
        uiSim.handleInput(KeyCode[key]);
      }
    });
  });

  window.addEventListener("keydown", (e) => {
    // If typing in input box, ignore global keypad shortcuts
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;

    let key = null;
    if (e.key >= '0' && e.key <= '9') {
      key = KeyCode[`NUM_${e.key}`];
    } else if (e.key === 'ArrowLeft' || e.key === 'Backspace') {
      key = KeyCode.BTN_BACKWARD;
    } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
      key = KeyCode.BTN_FORWARD;
    }

    if (key) {
      e.preventDefault();
      const btnId = key === KeyCode.BTN_BACKWARD ? 'key-back' :
                    key === KeyCode.BTN_FORWARD ? 'key-fwd' :
                    `key-${key.replace('NUM_', '')}`;
      const elem = document.getElementById(btnId);
      if (elem) {
        elem.classList.add("pressed");
        setTimeout(() => elem.classList.remove("pressed"), 120);
      }
      uiSim.handleInput(key);
    }
  });

  // --- Educational Catalog Updates ---
  function updateLearningCardUI() {
    const item = OFFLINE_DB[uiSim.currentContentIndex];
    if (!item) return;

    if (carouselCounter) carouselCounter.textContent = `Item ${uiSim.currentContentIndex + 1} of ${OFFLINE_DB.length}`;
    if (learningCatBadge) learningCatBadge.textContent = item.category || "General";
    if (learningCardIcon) learningCardIcon.textContent = item.icon || "🌟";
    if (learningCardTitle) learningCardTitle.textContent = item.title;
    if (learningCardBody) {
      learningCardBody.innerHTML = escapeHtml(item.body).replace(/\n/g, '<br>');
    }

    // Update active thumbnail
    document.querySelectorAll(".catalog-card").forEach((card, idx) => {
      card.classList.toggle("active", idx === uiSim.currentContentIndex);
    });
  }

  function renderCatalogGrid() {
    if (!catalogGrid) return;
    catalogGrid.innerHTML = "";
    OFFLINE_DB.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = `catalog-card ${idx === uiSim.currentContentIndex ? 'active' : ''}`;
      card.innerHTML = `
        <span class="catalog-card-cat">${escapeHtml(item.category)}</span>
        <strong class="catalog-card-title">${item.icon || '⭐'} ${escapeHtml(item.title)}</strong>
      `;
      card.addEventListener("click", () => {
        uiSim.loadOfflineItem(idx);
        uiSim.render();
        updateLearningCardUI();
      });
      catalogGrid.appendChild(card);
    });
  }

  if (btnPrevItem) {
    btnPrevItem.addEventListener("click", () => {
      uiSim.prevContentItem();
      updateLearningCardUI();
    });
  }
  if (btnNextItem) {
    btnNextItem.addEventListener("click", () => {
      uiSim.nextContentItem();
      updateLearningCardUI();
    });
  }
  if (btnSpeakContent) {
    btnSpeakContent.addEventListener("click", () => {
      const item = OFFLINE_DB[uiSim.currentContentIndex];
      if (item) {
        speakWithPiperTTS(`${item.title}. ${item.body}`);
      }
    });
  }

  // Fetch real educational items from backend
  async function loadCatalog() {
    try {
      const res = await apiRequest("/api/educational/catalog");
      if (res && res.status === "SUCCESS" && Array.isArray(res.items) && res.items.length > 0) {
        OFFLINE_DB = res.items.map(it => ({
          category: it.category || "Learning",
          title: it.title || "Topic",
          icon: it.icon || "🌟",
          body: it.body || it.fact || "",
          quizQ: it.quizQ || `What is ${it.title}?`,
          optA: it.optA || it.title,
          optB: it.optB || "Other",
          correctOpt: it.correctOpt || 1,
          explanation: it.explanation || "Great learning!"
        }));
        uiSim.loadOfflineItem(0);
        renderCatalogGrid();
        updateLearningCardUI();
      }
    } catch (e) {
      console.warn("Could not load /api/educational/catalog, using built-in database", e);
    }
  }

  // --- Quiz Handling ---
  function updateQuizUI() {
    const item = OFFLINE_DB[uiSim.currentContentIndex];
    if (!item) return;

    if (quizCounter) quizCounter.textContent = `Question ${uiSim.currentContentIndex + 1}`;
    if (quizQuestionText) quizQuestionText.textContent = item.quizQ || "Choose the correct answer:";
    if (quizOptAText) quizOptAText.textContent = item.optA || "Option 1";
    if (quizOptBText) quizOptBText.textContent = item.optB || "Option 2";

    if (quizResultBanner) quizResultBanner.classList.add("hidden");
  }

  function handleQuizSelection(selected) {
    const item = OFFLINE_DB[uiSim.currentContentIndex];
    if (!item) return;

    const isCorrect = (selected === item.correctOpt);
    uiSim.playQuizChime(isCorrect);

    if (quizResultBanner) {
      quizResultBanner.classList.remove("hidden");
      quizResultBanner.className = `quiz-result-banner ${isCorrect ? '' : 'wrong'}`;
      if (quizResultIcon) quizResultIcon.textContent = isCorrect ? "🌟" : "💡";
      if (quizResultTitle) quizResultTitle.textContent = isCorrect ? "Super Job! Correct! ⭐" : "Nice try! Review and try again!";
      if (quizResultBody) quizResultBody.textContent = item.explanation || (isCorrect ? "You got it right!" : `The correct answer is: ${item.correctOpt === 1 ? item.optA : item.optB}`);
    }

    if (isCorrect) {
      sessionStars += 1;
      sessionQuizzesAnswered += 1;
      updateProgressUI();
      speakWithPiperTTS("Correct! You got it right! Awesome job!");
    } else {
      speakWithPiperTTS(`Nice try! Review and try again!`);
    }
  }

  if (btnQuizOptA) btnQuizOptA.addEventListener("click", () => handleQuizSelection(1));
  if (btnQuizOptB) btnQuizOptB.addEventListener("click", () => handleQuizSelection(2));

  window.addEventListener('lumi-quiz-selected', (e) => {
    handleQuizSelection(e.detail.selected);
  });

  if (btnNextQuiz) {
    btnNextQuiz.addEventListener("click", () => {
      uiSim.nextContentItem();
      updateQuizUI();
    });
  }

  if (btnRepeatQuizQuestion) {
    btnRepeatQuizQuestion.addEventListener("click", () => {
      const item = OFFLINE_DB[uiSim.currentContentIndex];
      if (item) {
        speakWithPiperTTS(`${item.quizQ}. Option 1: ${item.optA}. Or Option 2: ${item.optB}.`);
      }
    });
  }

  // --- Story Time Handling ---
  storyPills.forEach(pill => {
    pill.addEventListener("click", () => {
      storyPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentStoryIdx = parseInt(pill.dataset.storyIdx || "0", 10);
      const story = LOCAL_STORIES[currentStoryIdx];
      if (story) {
        if (storyDisplayTitle) storyDisplayTitle.textContent = story.title;
        if (storyDisplayText) storyDisplayText.innerHTML = escapeHtml(story.body).replace(/\n\n/g, '<br><br>');
      }
    });
  });

  if (btnReadStoryAloud) {
    btnReadStoryAloud.addEventListener("click", () => {
      const story = LOCAL_STORIES[currentStoryIdx];
      if (story) {
        sessionStoriesHeard += 1;
        updateProgressUI();
        speakWithPiperTTS(`${story.title}. ${story.body}`);
      }
    });
  }

  if (btnStopStoryAudio) {
    btnStopStoryAudio.addEventListener("click", () => {
      if (activeAudioPlayer) {
        activeAudioPlayer.pause();
        activeAudioPlayer = null;
      }
      if (speakerGrille) speakerGrille.classList.remove("speaking");
      setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
    });
  }

  // --- Chat & Voice Interaction ---
  function appendUserBubble(text) {
    if (!conversationFeed) return;
    const row = document.createElement("div");
    row.className = "chat-message chat-user";
    row.innerHTML = `
      <div class="chat-avatar" aria-hidden="true">🧒</div>
      <div class="chat-bubble">
        <div class="chat-sender">You</div>
        <div class="chat-text">${escapeHtml(text)}</div>
      </div>
    `;
    conversationFeed.appendChild(row);
    conversationFeed.scrollTop = conversationFeed.scrollHeight;
  }

  function appendLumiBubble(turnData) {
    if (!conversationFeed) return;
    const row = document.createElement("div");
    row.className = "chat-message chat-lumi";

    const audioUrl = turnData.tts_audio_url || turnData.audio_url;
    let audioControlsHtml = "";

    if (audioUrl && soundEnabled) {
      const speedLabel = turnData.speech_speed === "slow" ? "🐢 Slow" : "🐇 Normal";
      audioControlsHtml = `
        <div class="lumi-audio-player">
          <button class="btn-replay-audio" title="Listen again">▶</button>
          <span class="player-label">Listen to LUMI</span>
          <span class="speed-tag">${speedLabel}</span>
        </div>
      `;
    }

    const topic = turnData.topic_tag || (turnData.intent ? `Topic: ${turnData.intent}` : "Answer");

    row.innerHTML = `
      <div class="chat-avatar" aria-hidden="true">🤖</div>
      <div class="chat-bubble">
        <div class="chat-sender">LUMI</div>
        <div class="chat-text">${escapeHtml(turnData.response_text || "I'm here to help you learn!")}</div>
        ${audioControlsHtml}
        <div class="chat-meta">
          <span>${escapeHtml(topic)}</span>
          <span>&bull;</span>
          <span>${turnData.total_time_ms ? `${turnData.total_time_ms} ms` : "On Device"}</span>
        </div>
      </div>
    `;

    const replayBtn = row.querySelector(".btn-replay-audio");
    if (replayBtn && audioUrl) {
      replayBtn.addEventListener("click", () => {
        playTurnAudio(audioUrl, turnData.response_text);
      });
    }

    conversationFeed.appendChild(row);
    conversationFeed.scrollTop = conversationFeed.scrollHeight;

    sessionSpokenTurns += 1;
    updateProgressUI();

    if (audioUrl && soundEnabled) {
      playTurnAudio(audioUrl, turnData.response_text);
    } else {
      setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
    }
  }

  function appendNoticeBubble(msg) {
    if (!conversationFeed) return;
    const row = document.createElement("div");
    row.className = "chat-message chat-lumi";
    row.innerHTML = `
      <div class="chat-avatar" aria-hidden="true">💡</div>
      <div class="chat-bubble" style="border-color: #f59e0b;">
        <div class="chat-sender" style="color: #fbbf24;">LUMI Notice</div>
        <div class="chat-text">${escapeHtml(msg)}</div>
      </div>
    `;
    conversationFeed.appendChild(row);
    conversationFeed.scrollTop = conversationFeed.scrollHeight;
  }

  function playTurnAudio(audioUrl, fallbackText) {
    if (activeAudioPlayer) {
      activeAudioPlayer.pause();
      activeAudioPlayer = null;
    }

    setCompanionState("speaking", "LUMI is speaking...", "Tap the mic again after LUMI finishes to ask another question.");
    if (speakerGrille) speakerGrille.classList.add("speaking");

    const audio = new Audio(audioUrl);
    activeAudioPlayer = audio;

    function finishPlayback() {
      activeAudioPlayer = null;
      if (speakerGrille) speakerGrille.classList.remove("speaking");
      setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");

      // If hands-free continuous listening is enabled, automatically resume listening after playback echo cooldown
      if (chkHandsFreeWake && chkHandsFreeWake.checked) {
        setTimeout(() => {
          if (chkHandsFreeWake && chkHandsFreeWake.checked && currentTurnState === "ready") {
            startRecording();
          }
        }, 900); // 900ms echo suppression cooldown
      }
    }

    audio.onended = finishPlayback;
    audio.onerror = () => {
      console.warn("Audio playback failed, attempting browser speech");
      browserSpeechFallback(fallbackText);
    };

    audio.play().catch((err) => {
      console.log("Audio play blocked by browser policy:", err);
      finishPlayback();
    });
  }

  // --- Microphone Capture Handlers ---
  async function startRecording() {
    dismissAlert();
    if (activeAudioPlayer) {
      activeAudioPlayer.pause();
      activeAudioPlayer = null;
    }

    try {
      await liveRecorder.start();
      recordingStartTime = Date.now();

      if (timerInterval) clearInterval(timerInterval);
      timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
        const m = Math.floor(elapsed / 60);
        const s = String(elapsed % 60).padStart(2, "0");
        if (heroTimerText) heroTimerText.textContent = `${m}:${s}`;
      }, 500);

      setCompanionState("listening", "I'm listening to your voice...", "Speak clearly into your microphone, then tap Stop when finished.");

      // Safety timeout after 15s
      if (autoStopTimeout) clearTimeout(autoStopTimeout);
      autoStopTimeout = setTimeout(() => {
        if (currentTurnState === "listening") {
          stopRecordingAndSubmit();
        }
      }, 15000);

    } catch (err) {
      console.error("Microphone access error:", err);
      showAlert("Could not access your microphone. Please check permissions and try again, or use typed chat below.");
      setCompanionState("error", "Microphone not available", "Check mic permission or type your question in the box below.");
    }
  }

  async function stopRecordingAndSubmit() {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    if (autoStopTimeout) { clearTimeout(autoStopTimeout); autoStopTimeout = null; }

    setCompanionState("processing", "I'm thinking...", "LUMI is listening closely and preparing an answer...");

    try {
      const wavBlob = await liveRecorder.stop();
      if (!wavBlob || wavBlob.size < 100) {
        setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "I didn't catch any audio that time. Let's try again!");
        return;
      }

      const formData = new FormData();
      formData.append("audio_file", wavBlob, "microphone_turn.wav");
      formData.append("require_wake_word", chkHandsFreeWake && chkHandsFreeWake.checked ? "true" : "false");
      formData.append("enable_tts", soundEnabled ? "true" : "false");
      formData.append("speech_speed", currentSpeed);

      const res = await apiRequest("/api/interactive/turn", "POST", formData);

      if (res.transcript) {
        appendUserBubble(res.transcript);
      }

      if (res.status === "BLOCKED") {
        appendNoticeBubble(res.response_text || "I didn't hear a wake phrase. Try saying 'Hey LUMI' or 'Good morning LUMI'!");
        setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Tip: Uncheck 'Hands-Free' if you prefer tap-to-talk!");
        if (chkHandsFreeWake && chkHandsFreeWake.checked) {
          setTimeout(() => {
            if (chkHandsFreeWake && chkHandsFreeWake.checked && currentTurnState === "ready") {
              startRecording();
            }
          }, 1500);
        }
        return;
      }

      if (res.status === "FAILED") {
        showAlert(res.response_text || res.error || "Turn could not be processed.");
        setCompanionState("error", "Oops, let's try again!", "Tap the mic to ask your question again.");
        return;
      }

      appendLumiBubble(res);

    } catch (err) {
      console.error("Turn submission error:", err);
      showAlert("Could not connect to LUMI Voice server. Please verify the server is running.");
      setCompanionState("error", "Connection Error", "Please check the server connection and try again.");
    }
  }

  if (btnHeroMic) {
    btnHeroMic.addEventListener("click", () => {
      if (currentTurnState === "listening") {
        stopRecordingAndSubmit();
      } else if (currentTurnState === "ready" || currentTurnState === "error") {
        startRecording();
      }
    });
  }

  if (btnStopHero) {
    btnStopHero.addEventListener("click", () => {
      if (currentTurnState === "listening") stopRecordingAndSubmit();
    });
  }

  // --- Quick Prompt Chips ---
  const promptChips = document.querySelectorAll(".prompt-chip");
  promptChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const p = chip.dataset.prompt;
      if (p) submitTypedQuestion(p);
    });
  });

  // --- Fallback Typed Text Form ---
  async function submitTypedQuestion(text) {
    if (!text || currentTurnState === "processing") return;
    if (activeAudioPlayer) {
      activeAudioPlayer.pause();
      activeAudioPlayer = null;
    }

    appendUserBubble(text);
    setCompanionState("processing", "I'm thinking...", "LUMI is reading your question and preparing a friendly answer...");

    try {
      const payload = {
        text: text,
        require_wake_word: chkHandsFreeWake && chkHandsFreeWake.checked,
        enable_tts: soundEnabled,
        speech_speed: currentSpeed,
      };

      const res = await apiRequest("/api/interactive/turn", "POST", payload);

      if (res.status === "BLOCKED") {
        appendNoticeBubble(res.response_text || "Please start your question with 'Hey LUMI' or uncheck Hands-Free mode!");
        setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Tip: Uncheck 'Hands-Free' to chat directly without the wake phrase!");
        return;
      }

      if (res.status === "FAILED") {
        showAlert(res.response_text || res.error || "Turn could not be processed.");
        setCompanionState("error", "Oops, let's try again!", "Type another question below or tap the microphone.");
        return;
      }

      appendLumiBubble(res);

    } catch (err) {
      console.error("Typed turn submission error:", err);
      showAlert("Could not send your question. Please ensure the Voice Lab server is running.");
      setCompanionState("error", "Connection Error", "Check local server and try again.");
    }
  }

  if (chatTextForm) {
    chatTextForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = chatTypedInput ? chatTypedInput.value.trim() : "";
      if (text) {
        if (chatTypedInput) chatTypedInput.value = "";
        submitTypedQuestion(text);
      }
    });
  }

  if (btnClearChatHistory) {
    btnClearChatHistory.addEventListener("click", () => {
      if (!conversationFeed) return;
      conversationFeed.innerHTML = `
        <div class="chat-message chat-lumi">
          <div class="chat-avatar" aria-hidden="true">🤖</div>
          <div class="chat-bubble">
            <div class="chat-sender">LUMI</div>
            <div class="chat-text">Chat cleared! What new adventure would you like to explore together?</div>
          </div>
        </div>
      `;
    });
  }

  if (chkHandsFreeWake) {
    chkHandsFreeWake.addEventListener("change", () => {
      if (chkHandsFreeWake.checked) {
        setCompanionState("ready", "Hands-Free Listening Active", "Say any enabled wake phrase (e.g. 'Hey LUMI', 'Good morning LUMI')!");
        startRecording();
      } else {
        if (currentTurnState === "listening") {
          liveRecorder.stop().catch(() => {});
          if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
          if (autoStopTimeout) { clearTimeout(autoStopTimeout); autoStopTimeout = null; }
          setCompanionState("ready", "I'm ready! Tap the mic to talk with me.", "Ask another question anytime!");
        }
      }
    });
  }

  // --- Eight-Phrase Wake-Word Management ---
  async function loadWakePhrases() {
    try {
      const res = await apiRequest("/api/wake_word/phrases");
      if (res && res.phrases) {
        renderWakePhrases(res.phrases);
      }
    } catch (err) {
      console.warn("Could not load wake phrases:", err);
    }
  }

  function renderWakePhrases(phrases) {
    const tbody = document.getElementById("wakePhrasesTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    phrases.forEach(p => {
      const tr = document.createElement("tr");

      // Checkbox
      const tdActive = document.createElement("td");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.checked = p.enabled;
      chk.title = `Enable or disable '${p.phrase}'`;
      chk.addEventListener("change", async () => {
        try {
          await apiRequest("/api/wake_word/phrases", "POST", {
            phrase: p.phrase,
            enabled: chk.checked
          });
        } catch (e) {
          console.error("Failed to toggle phrase:", e);
        }
      });
      tdActive.appendChild(chk);
      tr.appendChild(tdActive);

      // Phrase Name
      const tdPhrase = document.createElement("td");
      tdPhrase.innerHTML = `<strong>${p.phrase}</strong>`;
      tr.appendChild(tdPhrase);

      // Status Badge
      const tdStatus = document.createElement("td");
      let statusClass = "status-needs-training";
      let statusLabel = "Needs Training";

      if (p.status === "VERIFIED") {
        statusClass = "status-ready";
        statusLabel = "Ready";
      } else if (p.status === "MODEL AVAILABLE — VALIDATION REQUIRED") {
        statusClass = "status-needs-validation";
        statusLabel = "Needs Validation";
      } else if (p.status === "UNSUPPORTED") {
        statusClass = "status-unavailable";
        statusLabel = "Unavailable";
      } else {
        statusClass = "status-needs-training";
        statusLabel = "Needs Training";
      }

      tdStatus.innerHTML = `<span class="phrase-status-badge ${statusClass}">${statusLabel}</span>`;
      tr.appendChild(tdStatus);

      // Model Asset
      const tdModel = document.createElement("td");
      tdModel.innerHTML = `<code>${p.model_filename}</code>`;
      tr.appendChild(tdModel);

      // Action / Details
      const tdAction = document.createElement("td");
      tdAction.style.fontSize = "0.76rem";
      tdAction.style.color = "#94a3b8";
      tdAction.textContent = p.details || (p.training_required ? "Training required with multi-speaker audio" : "Ready");
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });

    const badge = document.getElementById("wakePhraseCountBadge");
    if (badge) {
      badge.textContent = `${phrases.length} Phrases`;
    }
  }

  // Initial Data Load
  loadCatalog();
  renderCatalogGrid();
  updateLearningCardUI();
  updateProgressUI();
  loadWakePhrases();

  // Load offline readiness status
  loadSystemStatus().then((status) => {
    const offlinePill = document.getElementById("offlinePill");
    if (offlinePill && status) {
      offlinePill.title = `Faster-Whisper base.en: OK, Piper TTS: ${status.dependencies.piper_tts ? 'OK' : 'Mock'}, PyTorch: OK`;
    }
  });
}

// =========================================================================
// DEVELOPER TESTBED CONTROLLER (Used when accessing /dev or /dev.html)
// =========================================================================

function initDevApp() {
  const tabs = document.querySelectorAll(".nav-tab");
  const panels = document.querySelectorAll(".tab-panel");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      panels.forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      const targetPanelId = tab.dataset.tab;
      const targetPanel = document.getElementById(targetPanelId);
      if (targetPanel) {
        targetPanel.classList.add("active");
      }
    });
  });

  loadSystemStatus().then((data) => {
    if (!data) return;
    const statRuntime = document.getElementById("statRuntime");
    if (statRuntime) statRuntime.textContent = `Python ${data.python_version} (${data.platform})`;

    const statSTT = document.getElementById("statSTT");
    if (statSTT) {
      statSTT.textContent = data.dependencies.faster_whisper ? "faster-whisper (OK)" : "faster-whisper (Missing)";
      statSTT.className = data.dependencies.faster_whisper ? "status-chip chip-success" : "status-chip chip-blocked";
    }

    const statSTTModel = document.getElementById("statSTTModel");
    if (statSTTModel) {
      statSTTModel.textContent = data.models.stt_base_en.available ? "base.en (Cached)" : "base.en (Missing)";
      statSTTModel.className = data.models.stt_base_en.available ? "status-chip chip-success" : "status-chip chip-blocked";
    }

    const statVAD = document.getElementById("statVAD");
    if (statVAD) {
      statVAD.textContent = (data.dependencies.torch && data.dependencies.silero_vad) ? "Silero VAD (Native)" : "Silero VAD (Mock Fallback)";
      statVAD.className = (data.dependencies.torch && data.dependencies.silero_vad) ? "status-chip chip-success" : "status-chip chip-blocked";
    }

    const statWW = document.getElementById("statWW");
    if (statWW) {
      statWW.textContent = (data.models.wake_word.available && data.dependencies.openwakeword) ? "openWakeWord (OK)" : "openWakeWord (Model Absent)";
      statWW.className = (data.models.wake_word.available && data.dependencies.openwakeword) ? "status-chip chip-success" : "status-chip chip-blocked";
    }

    const statTTS = document.getElementById("statTTS");
    if (statTTS) {
      statTTS.textContent = (data.models.piper_tts.model_available && data.dependencies.piper_tts) ? "Piper TTS (OK)" : "Piper TTS (Mock Fallback)";
      statTTS.className = (data.models.piper_tts.model_available && data.dependencies.piper_tts) ? "status-chip chip-success" : "status-chip chip-blocked";
    }
  });
}

// Global DOM Ready Entry Point
document.addEventListener("DOMContentLoaded", () => {
  const isCompanionPage = document.getElementById("lumiCompanionApp") !== null;
  const isDevPage = document.getElementById("tab-pipeline") !== null || document.querySelector(".nav-tabs") !== null;

  if (isCompanionPage) {
    initCompanionApp();
  }

  if (isDevPage) {
    initDevApp();
  }
});
