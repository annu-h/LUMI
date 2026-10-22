#include "ui_manager.h"

#define COLOR_BG        0xEFFE // Soft Pastel Blue
#define COLOR_TEXT      0x2124 // Dark Slate
#define COLOR_CARD      0xFFFF // White Surface
#define COLOR_CYAN      0x3D7E // Accent Teal

// Embedded dataset aligned with asset folder structures
static const EduItem OFFLINE_DB[] = {
    {"Animal", "Elephant", "/images/animals/elephant.bmp", "A giant gentle animal with a long trunk!\nSound: Pawoo!\nFact: Elephants wrap trunks to greet.", "Which animal has a long trunk?", "Elephant", "Rabbit", 1},
    {"Animal", "Lion", "/images/animals/lion.bmp", "King of the jungle with a big golden mane!\nSound: Roar!\nFact: Lions live in groups called prides.", "What sound does a lion make?", "Meow", "Roar", 2},
    {"Fruit", "Apple", "/images/fruits/apple.bmp", "Crisp, sweet, and juicy fruit!\nColors: Red, Green, or Yellow.\nFact: Apples can float in water!", "What color is a ripe apple?", "Red", "Blue", 1},
    {"Fruit", "Banana", "/images/fruits/banana.bmp", "Sweet fruit with an easy-to-peel skin!\nPacked with potassium to give you energy.", "What color is a ripe banana?", "Purple", "Yellow", 2},
    {"Shape", "Circle", "/images/shapes/circle.bmp", "A round curve with zero corners!\nExamples: The Sun, a clock, and a wheel.", "How many corners does a circle have?", "Zero", "Four", 1},
    {"Shape", "Triangle", "/images/shapes/triangle.bmp", "A shape with 3 straight sides & corners!\nExamples: A pizza slice and a pyramid.", "How many sides does a triangle have?", "3", "5", 1},
    {"Number", "Number 5", "/images/numbers/5.bmp", "High five! You have 5 fingers on each\nhand and 5 toes on each foot to balance.", "How many fingers on one hand?", "5", "10", 1},
    {"Alphabet", "Letter A", "/images/alphabets/a.bmp", "A is for Apple! Crisp and sweet.\nSay it out loud: 'Ah-Ah-Apple!'", "What does Letter A stand for?", "Apple", "Boat", 1}
};
static const uint8_t TOTAL_OFFLINE_ITEMS = sizeof(OFFLINE_DB) / sizeof(EduItem);

UIManager::UIManager()
    : currentState(ScreenState::HOME), currentFace(LumiFaceState::IDLE),
      lastAnimUpdate(0), animFrame(0), currentCorrectOpt(1), currentContentIndex(0) {
    loadOfflineItem(0);
}

void UIManager::begin() {
    tft.init();
    tft.setRotation(1);
    tft.fillScreen(COLOR_BG);
    setScreenState(ScreenState::HOME);
}

void UIManager::loadOfflineItem(uint8_t index) {
    currentContentIndex = index % TOTAL_OFFLINE_ITEMS;
    currentTitle = OFFLINE_DB[currentContentIndex].title;
    currentBody = OFFLINE_DB[currentContentIndex].body;
    currentImagePath = OFFLINE_DB[currentContentIndex].imagePath;
    quizOptA = OFFLINE_DB[currentContentIndex].optA;
    quizOptB = OFFLINE_DB[currentContentIndex].optB;
    currentCorrectOpt = OFFLINE_DB[currentContentIndex].correctOpt;
}

void UIManager::setScreenState(ScreenState state) {
    currentState = state;
    tft.fillScreen(COLOR_BG);
    renderStatusBar(95);

    switch (currentState) {
        case ScreenState::HOME:     renderHomeScreen(); break;
        case ScreenState::LEARNING: renderLearningScreen(); break;
        case ScreenState::QUIZ:     renderQuizScreen(); break;
        case ScreenState::STORY:    renderStoryScreen(); break;
        case ScreenState::SETTINGS: renderSettingsScreen(); break;
        case ScreenState::PROGRESS: renderProgressScreen(); break;
    }
}

void UIManager::setLumiFace(LumiFaceState face) {
    currentFace = face;
    if (currentState == ScreenState::HOME) {
        drawLumiFace(160, 115, currentFace, animFrame);
    }
}

void UIManager::setContent(const String& title, const String& body, const String& imagePath) {
    currentTitle = title;
    currentBody = body;
    currentImagePath = imagePath;
    if (currentState == ScreenState::LEARNING) {
        renderLearningScreen();
    }
}

void UIManager::setQuiz(const String& question, const String& optA, const String& optB) {
    currentBody = question;
    quizOptA = optA;
    quizOptB = optB;
    if (currentState == ScreenState::QUIZ) {
        renderQuizScreen();
    }
}

void UIManager::nextContentItem() {
    loadOfflineItem(currentContentIndex + 1);
    if (currentState == ScreenState::LEARNING) renderLearningScreen();
    else if (currentState == ScreenState::QUIZ) renderQuizScreen();
}

void UIManager::prevContentItem() {
    loadOfflineItem(currentContentIndex == 0 ? TOTAL_OFFLINE_ITEMS - 1 : currentContentIndex - 1);
    if (currentState == ScreenState::LEARNING) renderLearningScreen();
    else if (currentState == ScreenState::QUIZ) renderQuizScreen();
}

void UIManager::handleInput(KeyCode key) {
    switch (key) {
        case KeyCode::NUM_1:
            if (currentState == ScreenState::QUIZ) {
                tft.fillRoundRect(20, 140, 130, 45, 8, currentCorrectOpt == 1 ? 0x2DE5 : 0xE986);
                tft.setTextColor(0xFFFF);
                tft.drawString(currentCorrectOpt == 1 ? "GREAT JOB! *" : "TRY AGAIN!", 35, 155, 2);
                delay(800);
                nextContentItem();
            } else {
                setScreenState(ScreenState::LEARNING);
            }
            break;
        case KeyCode::NUM_2:
            if (currentState == ScreenState::QUIZ) {
                tft.fillRoundRect(170, 140, 130, 45, 8, currentCorrectOpt == 2 ? 0x2DE5 : 0xE986);
                tft.setTextColor(0xFFFF);
                tft.drawString(currentCorrectOpt == 2 ? "GREAT JOB! *" : "TRY AGAIN!", 185, 155, 2);
                delay(800);
                nextContentItem();
            } else {
                setScreenState(ScreenState::QUIZ);
            }
            break;
        case KeyCode::NUM_3:
            setScreenState(ScreenState::STORY);
            break;
        case KeyCode::NUM_4:
            setScreenState(ScreenState::PROGRESS);
            break;
        case KeyCode::NUM_0:
            setScreenState(ScreenState::HOME);
            break;
        case KeyCode::BTN_BACKWARD:
            prevContentItem();
            break;
        case KeyCode::BTN_FORWARD:
            nextContentItem();
            break;
        default:
            break;
    }
}

void UIManager::updateAnimation() {
    if (millis() - lastAnimUpdate > 250) {
        lastAnimUpdate = millis();
        animFrame = (animFrame + 1) % 4;

        if (currentState == ScreenState::HOME) {
            drawLumiFace(160, 115, currentFace, animFrame);
        }
    }
}

void UIManager::renderHeader(const char* title) {
    tft.fillRect(0, 0, 320, 26, COLOR_CYAN);
    tft.setTextColor(0xFFFF, COLOR_CYAN);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(title, 160, 13, 2);
}

void UIManager::renderStatusBar(int batteryPct) {
    tft.fillRect(0, 222, 320, 18, 0xCE59);
    tft.setTextColor(0x4208, 0xCE59);
    tft.setTextDatum(ML_DATUM);
    tft.drawString("LUMI Voice Active", 10, 231, 1);

    tft.setTextDatum(MR_DATUM);
    char buf[16];
    snprintf(buf, sizeof(buf), "BAT: %d%%", batteryPct);
    tft.drawString(buf, 310, 231, 1);
}

void UIManager::drawLumiFace(int cx, int cy, LumiFaceState state, int frame) {
    // Face outline capsule
    tft.fillRoundRect(cx - 75, cy - 60, 150, 120, 24, COLOR_CARD);
    tft.drawRoundRect(cx - 75, cy - 60, 150, 120, 24, COLOR_CYAN);

    int eyeY = cy - 12;
    int eyeSpacing = 36;
    int eyeSize = 10;

    switch (state) {
        case LumiFaceState::IDLE:
            if (frame == 3) {
                // Blink
                tft.drawLine(cx - eyeSpacing - 10, eyeY, cx - eyeSpacing + 10, eyeY, COLOR_TEXT);
                tft.drawLine(cx + eyeSpacing - 10, eyeY, cx + eyeSpacing + 10, eyeY, COLOR_TEXT);
            } else {
                tft.fillCircle(cx - eyeSpacing, eyeY, eyeSize, COLOR_CYAN);
                tft.fillCircle(cx + eyeSpacing, eyeY, eyeSize, COLOR_CYAN);
                // Cute white eye glint
                tft.fillCircle(cx - eyeSpacing - 3, eyeY - 3, 3, 0xFFFF);
                tft.fillCircle(cx + eyeSpacing - 3, eyeY - 3, 3, 0xFFFF);
            }
            // Gentle curve mouth
            tft.drawCircle(cx, cy + 18, 14, COLOR_TEXT);
            tft.fillRect(cx - 18, cy + 4, 36, 16, COLOR_CARD);
            break;

        case LumiFaceState::LISTENING:
            // Big open curious eyes
            tft.fillCircle(cx - eyeSpacing, eyeY, eyeSize + 3, 0x2DE5);
            tft.fillCircle(cx + eyeSpacing, eyeY, eyeSize + 3, 0x2DE5);
            // Open 'O' mouth
            tft.drawCircle(cx, cy + 20, 6 + (frame % 2) * 2, COLOR_TEXT);
            break;

        case LumiFaceState::THINKING:
            // Looking up/diagonal eyes
            tft.fillCircle(cx - eyeSpacing + 4, eyeY - 4, eyeSize, 0xFA40);
            tft.fillCircle(cx + eyeSpacing + 4, eyeY - 4, eyeSize, 0xFA40);
            // Squiggly thinking mouth
            tft.drawLine(cx - 12, cy + 20, cx + 12, cy + 20, COLOR_TEXT);
            break;

        case LumiFaceState::SPEAKING:
            tft.fillCircle(cx - eyeSpacing, eyeY, eyeSize, COLOR_CYAN);
            tft.fillCircle(cx + eyeSpacing, eyeY, eyeSize, COLOR_CYAN);
            // Animated talking mouth
            int mouthH = 4 + (frame * 3);
            tft.fillEllipse(cx, cy + 20, 14, mouthH, COLOR_TEXT);
            break;
    }
}

void UIManager::drawItemImage(int x, int y, int w, int h, const char* category, const char* path) {
    (void)path;
    tft.fillRoundRect(x, y, w, h, 8, COLOR_CARD);
    tft.drawRoundRect(x, y, w, h, 8, COLOR_CYAN);

    // Fallback graphical representation when offline without SD images
    if (strcmp(category, "Animal") == 0) {
        tft.fillCircle(x + w / 2, y + h / 2, 22, 0xD67A);
        tft.fillCircle(x + w / 2 - 16, y + h / 2 - 16, 10, 0xD67A);
        tft.fillCircle(x + w / 2 + 16, y + h / 2 - 16, 10, 0xD67A);
    } else if (strcmp(category, "Fruit") == 0) {
        tft.fillCircle(x + w / 2, y + h / 2 + 4, 24, 0xF800);
        tft.fillRect(x + w / 2 - 2, y + h / 2 - 26, 4, 10, 0x7BE0);
    } else if (strcmp(category, "Shape") == 0) {
        tft.drawCircle(x + w / 2, y + h / 2, 24, 0x001F);
    } else if (strcmp(category, "Number") == 0) {
        tft.setTextColor(0xFA40, COLOR_CARD);
        tft.setTextDatum(MC_DATUM);
        tft.drawString("5", x + w / 2, y + h / 2, 4);
    } else {
        tft.setTextColor(0x2DE5, COLOR_CARD);
        tft.setTextDatum(MC_DATUM);
        tft.drawString("Aa", x + w / 2, y + h / 2, 4);
    }
}

void UIManager::renderHomeScreen() {
    renderHeader("PROJECT LUMI");
    drawLumiFace(160, 115, currentFace, animFrame);

    tft.setTextColor(COLOR_TEXT, COLOR_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("Hi Friend! Say 'Hey LUMI' or press 1-4", 160, 195, 2);
}

void UIManager::renderLearningScreen() {
    renderHeader(OFFLINE_DB[currentContentIndex].category);

    // Graphic illustration card
    drawItemImage(15, 36, 100, 95, OFFLINE_DB[currentContentIndex].category, currentImagePath.c_str());

    // Title & details card
    tft.fillRoundRect(125, 36, 180, 140, 8, COLOR_CARD);
    tft.setTextColor(COLOR_CYAN, COLOR_CARD);
    tft.setTextDatum(TL_DATUM);
    tft.drawString(currentTitle.c_str(), 135, 46, 4);

    tft.setTextColor(COLOR_TEXT, COLOR_CARD);
    tft.setCursor(135, 78, 2);
    tft.print(currentBody.c_str());

    // Navigation hints
    tft.setTextColor(0x7BEF, COLOR_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("Press [*] Prev   |   [#] Next   |   [0] Home", 160, 195, 1);
}

void UIManager::renderQuizScreen() {
    renderHeader("INTERACTIVE QUIZ");

    // Question box
    tft.fillRoundRect(20, 40, 280, 85, 8, COLOR_CARD);
    tft.drawRoundRect(20, 40, 280, 85, 8, COLOR_CYAN);
    tft.setTextColor(COLOR_TEXT, COLOR_CARD);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(OFFLINE_DB[currentContentIndex].quizQ, 160, 82, 2);

    // Option A button (Press 1)
    tft.fillRoundRect(20, 140, 130, 45, 8, COLOR_CARD);
    tft.drawRoundRect(20, 140, 130, 45, 8, 0x2DE5);
    tft.setTextColor(0x2DE5, COLOR_CARD);
    tft.setTextDatum(MC_DATUM);
    String optAText = "1: " + quizOptA;
    tft.drawString(optAText.c_str(), 85, 162, 2);

    // Option B button (Press 2)
    tft.fillRoundRect(170, 140, 130, 45, 8, COLOR_CARD);
    tft.drawRoundRect(170, 140, 130, 45, 8, 0xFA40);
    tft.setTextColor(0xFA40, COLOR_CARD);
    tft.setTextDatum(MC_DATUM);
    String optBText = "2: " + quizOptB;
    tft.drawString(optBText.c_str(), 235, 162, 2);

    tft.setTextColor(0x7BEF, COLOR_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("Press Keypad [1] or [2] to Answer", 160, 202, 1);
}

void UIManager::renderStoryScreen() {
    renderHeader("BEDTIME STORY");

    tft.fillRoundRect(20, 36, 280, 155, 8, COLOR_CARD);
    tft.drawRoundRect(20, 36, 280, 155, 8, COLOR_CYAN);

    tft.setTextColor(COLOR_CYAN, COLOR_CARD);
    tft.drawString("The Little Star Who Could", 35, 48, 2);

    tft.setTextColor(COLOR_TEXT, COLOR_CARD);
    tft.setCursor(35, 75, 2);
    tft.print("Once upon a time in the night sky,\na tiny star wondered if it was bright\nenough to guide the travelers home.\nWith a deep breath, it beamed bright!");

    tft.setTextColor(0x7BEF, COLOR_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("Press [0] for Home Menu", 160, 202, 1);
}

void UIManager::renderSettingsScreen() {
    renderHeader("SYSTEM SETTINGS");

    tft.fillRoundRect(20, 36, 280, 155, 8, COLOR_CARD);
    tft.setTextColor(COLOR_TEXT, COLOR_CARD);

    tft.setCursor(35, 48, 2);
    tft.println("ESP32-WROOM-32 Hardware Diagnostic:");
    tft.setCursor(35, 70, 2);
    tft.println("- INMP441 Mic: BCLK 26, WS 25, DIN 34");
    tft.setCursor(35, 90, 2);
    tft.println("- MAX98357A Amp: DOUT 33, BCLK 26");
    tft.setCursor(35, 110, 2);
    tft.println("- ILI9341 SPI: CS 5, DC 2, RST 4");
    tft.setCursor(35, 130, 2);
    tft.println("- Keypad Matrix: 4 Rows x 3 Cols");
    tft.setCursor(35, 150, 2);
    tft.println("- Offline Intelligence: Ready");
}

void UIManager::renderProgressScreen() {
    renderHeader("LEARNING STARS");

    tft.fillRoundRect(20, 36, 280, 155, 8, COLOR_CARD);
    tft.setTextColor(COLOR_TEXT, COLOR_CARD);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("You Have Earned:", 160, 60, 2);

    // Draw 5 gold stars
    for (int i = 0; i < 5; i++) {
        tft.fillCircle(80 + (i * 40), 105, 12, 0xFDE0);
    }

    tft.drawString("5 Gold Stars Today!", 160, 140, 4);
    tft.setTextColor(0x7BEF, COLOR_BG);
    tft.drawString("Keep up the curious questions!", 160, 202, 1);
}
