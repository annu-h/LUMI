#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>
#include "../input/keypad_driver.h"

enum class ScreenState {
    HOME,
    LEARNING,
    QUIZ,
    STORY,
    SETTINGS,
    PROGRESS
};

enum class LumiFaceState {
    IDLE,
    LISTENING,
    THINKING,
    SPEAKING
};

struct EduItem {
    const char* category;
    const char* title;
    const char* imagePath;
    const char* body;
    const char* quizQ;
    const char* optA;
    const char* optB;
    uint8_t correctOpt;
};

class UIManager {
public:
    UIManager();
    void begin();
    void handleInput(KeyCode key);
    void updateAnimation();

    void setScreenState(ScreenState state);
    void setLumiFace(LumiFaceState face);
    void setContent(const String& title, const String& body, const String& imagePath = "");
    void setQuiz(const String& question, const String& optA, const String& optB);

    void nextContentItem();
    void prevContentItem();

private:
    TFT_eSPI tft;
    ScreenState currentState;
    LumiFaceState currentFace;
    unsigned long lastAnimUpdate;
    int animFrame;

    String currentTitle;
    String currentBody;
    String currentImagePath;
    String quizOptA;
    String quizOptB;
    uint8_t currentCorrectOpt;
    uint8_t currentContentIndex;

    void renderHomeScreen();
    void renderLearningScreen();
    void renderQuizScreen();
    void renderStoryScreen();
    void renderSettingsScreen();
    void renderProgressScreen();
    void renderHeader(const char* title);
    void renderStatusBar(int batteryPct);
    void drawLumiFace(int x, int y, LumiFaceState state, int frame);
    void drawItemImage(int x, int y, int w, int h, const char* category, const char* path);
    void loadOfflineItem(uint8_t index);
};