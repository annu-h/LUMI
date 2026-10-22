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

void UIManager::nextContentItem() {
    currentContentIndex = (currentContentIndex + 1) % TOTAL_OFFLINE_ITEMS;
    loadOfflineItem(currentContentIndex);
    if (currentState == ScreenState::LEARNING || currentState == ScreenState::QUIZ) {
        setScreenState(currentState);
    }
}

void UIManager::prevContentItem() {
    if (currentContentIndex == 0) {
        currentContentIndex = TOTAL_OFFLINE_ITEMS - 1;
    } else {
        currentContentIndex--;
    }
    loadOfflineItem(currentContentIndex);
    if (currentState == ScreenState::LEARNING || currentState == ScreenState::QUIZ) {
        setScreenState(currentState);
    }
}

void UIManager::setScreenState(ScreenState state) {
    currentState = state;
    tft.fillScreen(COLOR_BG);

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
        drawLumiFace(160, 95, currentFace, animFrame);
    }
}

void UIManager::setContent(const String& title, const String& body, const String& imagePath) {
    currentTitle = title;
    currentBody = body;
    currentImagePath = imagePath;
    if (currentState == ScreenState::LEARNING || currentState == ScreenState::STORY) {
        setScreenState(currentState);
    }
}

void UIManager::setQuiz(const String& question, const String& optA, const String& optB) {
    currentTitle = question;
    quizOptA = optA;
    quizOptB = optB;
    setScreenState(ScreenState::QUIZ);
}

void UIManager::handleInput(KeyCode key) {
    // Navigation for 12-button keypad:
    // [Backward] -> Return to Home or Settings
    // [Forward]  -> Next card or enter Learn mode
    if (key == KeyCode::BTN_BACKWARD) {
        if (currentState == ScreenState::HOME) {
            setScreenState(ScreenState::SETTINGS);
        } else {
            setScreenState(ScreenState::HOME);
        }
        return;
    }

    if (key == KeyCode::BTN_FORWARD) {
        if (currentState == ScreenState::LEARNING) {
            nextContentItem();
        } else {
            setScreenState(ScreenState::LEARNING);
        }
        return;
    }

    switch (currentState) {
        case ScreenState::HOME:
            if (key == KeyCode::NUM_1) setScreenState(ScreenState::LEARNING);
            else if (key == KeyCode::NUM_2) setScreenState(ScreenState::STORY);
            else if (key == KeyCode::NUM_3) setScreenState(ScreenState::QUIZ);
            else if (key == KeyCode::NUM_9) setScreenState(ScreenState::PROGRESS);
            break;

        case ScreenState::LEARNING:
            if (key == KeyCode::NUM_0) nextContentItem();
            else if (key == KeyCode::NUM_3) setScreenState(ScreenState::QUIZ);
            break;

        case ScreenState::QUIZ:
            if (key == KeyCode::NUM_1 || key == KeyCode::NUM_2) {
                uint8_t selected = (key == KeyCode::NUM_1) ? 1 : 2;
                if (selected == currentCorrectOpt) {
                    setContent("Quiz Result", "Correct! You got it right! ⭐", "");
                } else {
                    setContent("Quiz Result", "Nice try! Review and try again!", "");
                }
                setScreenState(ScreenState::LEARNING);
            }
            break;

        default:
            if (key == KeyCode::NUM_0) setScreenState(ScreenState::HOME);
            break;
    }
}

void UIManager::updateAnimation() {
    if (millis() - lastAnimUpdate > 350) {
        lastAnimUpdate = millis();
        animFrame = (animFrame + 1) % 4;

        if (currentState == ScreenState::HOME) {
            drawLumiFace(160, 95, currentFace, animFrame);
        }
    }
}

void UIManager::renderStatusBar(int batteryPct) {
    tft.drawRoundRect(275, 8, 28, 14, 2, TFT_DARKGREY);
    tft.fillRect(303, 12, 2, 6, TFT_DARKGREY);
    int fillW = map(batteryPct, 0, 100, 0, 24);
    tft.fillRect(277, 10, fillW, 10, TFT_GREEN);
}

void UIManager::renderHeader(const char* title) {
    tft.fillRect(0, 0, 320, 32, COLOR_CARD);
    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(2);
    tft.setCursor(15, 8);
    tft.print(title);
    renderStatusBar(100);
    tft.drawFastHLine(0, 32, 320, TFT_LIGHTGREY);
}

void UIManager::drawLumiFace(int x, int y, LumiFaceState state, int frame) {
    tft.fillCircle(x, y, 42, 0xFEE0);
    tft.drawCircle(x, y, 42, TFT_ORANGE);

    if (state == LumiFaceState::LISTENING) {
        tft.fillCircle(x - 14, y - 8, 6, TFT_BLACK);
        tft.fillCircle(x + 14, y - 8, 6, TFT_BLACK);
        tft.fillCircle(x - 12, y - 10, 2, TFT_WHITE);
        tft.fillCircle(x + 16, y - 10, 2, TFT_WHITE);
    } else if (state == LumiFaceState::THINKING) {
        tft.fillCircle(x - 14, y - 12, 5, TFT_BLACK);
        tft.fillCircle(x + 14, y - 12, 5, TFT_BLACK);
    } else {
        if (frame == 3) {
            tft.drawFastHLine(x - 20, y - 8, 12, TFT_BLACK);
            tft.drawFastHLine(x + 8, y - 8, 12, TFT_BLACK);
        } else {
            tft.fillCircle(x - 14, y - 8, 5, TFT_BLACK);
            tft.fillCircle(x + 14, y - 8, 5, TFT_BLACK);
        }
    }

    tft.fillCircle(x - 24, y + 6, 4, 0xFC72);
    tft.fillCircle(x + 24, y + 6, 4, 0xFC72);

    tft.fillRect(x - 15, y + 10, 30, 15, 0xFEE0);
    if (state == LumiFaceState::SPEAKING) {
        int mouthHeight = (frame % 2 == 0) ? 8 : 4;
        tft.fillRoundRect(x - 8, y + 12, 16, mouthHeight, 3, TFT_BLACK);
    } else {
        tft.drawCircle(x, y + 8, 8, TFT_BLACK);
        tft.fillRect(x - 10, y + 6, 20, 6, 0xFEE0);
    }
}

void UIManager::drawItemImage(int x, int y, int w, int h, const char* category, const char* path) {
    tft.fillRoundRect(x, y, w, h, 6, 0xE79C);
    tft.drawRoundRect(x, y, w, h, 6, 0x9CD3);

    if (strcmp(category, "Animal") == 0) {
        tft.fillCircle(x + w / 2, y + h / 2 - 2, 18, 0xFEE0);
        tft.fillCircle(x + w / 2 - 12, y + h / 2 - 16, 6, 0xFEE0);
        tft.fillCircle(x + w / 2 + 12, y + h / 2 - 16, 6, 0xFEE0);
    } else if (strcmp(category, "Fruit") == 0) {
        tft.fillCircle(x + w / 2, y + h / 2, 16, 0xF800);
        tft.fillRect(x + w / 2 - 2, y + h / 2 - 20, 4, 6, 0x03E0);
    } else if (strcmp(category, "Shape") == 0) {
        tft.drawRect(x + 14, y + 14, w - 28, h - 28, 0x3B82);
        tft.drawCircle(x + w / 2, y + h / 2, 14, 0xFC72);
    } else {
        tft.setTextColor(TFT_DARKGREY);
        tft.setTextSize(2);
        tft.setCursor(x + 22, y + 20);
        tft.print("123");
    }
}

void UIManager::renderHomeScreen() {
    renderHeader("Hi, Friend! :)");
    drawLumiFace(160, 95, currentFace, animFrame);

    tft.fillRoundRect(20, 175, 280, 50, 10, COLOR_CARD);
    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(1);
    tft.setCursor(30, 195);
    tft.print("[1] Learn   [2] Story   [3] Quiz   [Fwd] Go");
}

void UIManager::renderLearningScreen() {
    renderHeader("Learn Mode");
    tft.fillRoundRect(15, 42, 290, 188, 8, COLOR_CARD);

    const char* cat = OFFLINE_DB[currentContentIndex].category;

    drawItemImage(25, 52, 60, 60, cat, currentImagePath.c_str());

    tft.setTextColor(COLOR_CYAN);
    tft.setTextSize(2);
    tft.setCursor(95, 54);
    tft.print(currentTitle);

    tft.setTextColor(TFT_DARKGREY);
    tft.setTextSize(1);
    tft.setCursor(95, 78);
    tft.print("Category: ");
    tft.print(cat);

    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(1);
    tft.setCursor(25, 124);
    tft.print(currentBody);

    tft.setCursor(25, 212);
    tft.setTextColor(TFT_DARKGREY);
    tft.print("[Fwd] Next | [3] Quiz | [Back] Home");
}

void UIManager::renderQuizScreen() {
    renderHeader("Quiz Challenge");
    tft.fillRoundRect(15, 45, 290, 180, 8, COLOR_CARD);

    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(2);
    tft.setCursor(25, 60);
    const char* q = OFFLINE_DB[currentContentIndex].quizQ;
    tft.print(q ? q : "Choose the answer:");

    tft.fillRoundRect(25, 110, 270, 40, 6, 0x10B981);
    tft.setCursor(35, 122);
    tft.setTextColor(TFT_WHITE);
    tft.print("1. ");
    tft.print(quizOptA);

    tft.fillRoundRect(25, 160, 270, 40, 6, 0xF43F5E);
    tft.setCursor(35, 172);
    tft.print("2. ");
    tft.print(quizOptB);
}

void UIManager::renderStoryScreen() {
    renderHeader("Story Time");
    tft.fillRoundRect(15, 45, 290, 175, 8, COLOR_CARD);
    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(2);
    tft.setCursor(30, 65);
    tft.print("The Clever Fox");
    tft.setTextSize(1);
    tft.setCursor(30, 105);
    tft.print("Once upon a time in an enchanted forest,\na curious fox named Rusty found a magic\nglowing compass under an oak tree...\n\nPress [Back] to exit.");
}

void UIManager::renderSettingsScreen() {
    renderHeader("LUMI Setup");
    tft.fillRoundRect(15, 45, 290, 175, 8, COLOR_CARD);
    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(1);
    tft.setCursor(30, 65);
    tft.println("Battery: 100% (CR2032 Active)");
    tft.setCursor(30, 85);
    tft.println("Volume: Normal (MAX98357A)");
    tft.setCursor(30, 105);
    tft.println("Keypad: 4x3 Matrix Active-Low");
    tft.setCursor(30, 125);
    tft.println("Storage: MicroSD SPI Ready");
    tft.setCursor(30, 145);
    tft.println("Press [Back] to return Home.");
}

void UIManager::renderProgressScreen() {
    renderHeader("My Learning Stars");
    tft.fillRoundRect(15, 45, 290, 175, 8, COLOR_CARD);

    tft.setTextColor(COLOR_TEXT);
    tft.setTextSize(2);
    tft.setCursor(30, 60);
    tft.print("Weekly Progress: 70%");

    tft.drawRoundRect(30, 95, 260, 22, 5, TFT_DARKGREY);
    tft.fillRoundRect(32, 97, 182, 18, 4, 0x3B82F6);

    tft.setTextSize(1);
    tft.setCursor(30, 130);
    tft.print("Quizzes Completed: 8 / 10");
    tft.setCursor(30, 150);
    tft.print("Stories Listened: 5");
    tft.setCursor(30, 175);
    tft.setTextColor(0xD977);
    tft.print("Awesome job! 3 Stars! ⭐⭐⭐");
}