/**
 * firmware.ino - ESP8266 Pet Feeder with Wi-Fi Configuration
 *
 * This firmware implements a pet feeder system with Wi-Fi configuration:
 * - Wi-Fi configuration portal with EEPROM storage
 * - RGB LED status indicators (Red: Error/Config, Green: Ready, Blue: Feeding)
 * - MG996R continuous servo motor control for feeding
 * - Manual feed button with debouncing
 * - Modular design with separate LED and motor control
 */

#include <Arduino.h>
#include <time.h>
#include <sys/time.h>
#include <WiFiUdp.h>
#include <NTPClient.h>
#include <EEPROM.h>
#include <ArduinoJson.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP8266WebServer.h>
#include <DNSServer.h>

String nowUtcIso();
extern unsigned long lastFeedCompletionTime;

// Inlined config.h (undo modularization)
// Hardware Pin Definitions - RGB LEDs (D7/D0)
#define RED_LED_PIN 2
#define BLUE_LED_PIN 16

// Hardware Pin Definitions - Servo and Buttons
#define SERVO_PIN 14
#define FEED_NOW_PIN 0
#define ADD_PORTION_PIN 13
#define REDUCE_PORTION_PIN 12
#define BUTTON_PIN FEED_NOW_PIN

// Legacy LED pin for compatibility
#define LED_PIN 2
#define OLED_SDA_PIN 4
#define OLED_SCL_PIN 5
#define OLED_ADDR 0x3C
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_RESET -1
#define OLED_UPDATE_INTERVAL_MS 500

// ═══════════════════════════════════════════════════════════
// DEV / PRODUCTION TOGGLE
// Set DEV_MODE 1 for local development
// Set DEV_MODE 0 before flashing to production device
// ═══════════════════════════════════════════════════════════
#define DEV_MODE 0
// LOCAL DEV SETUP CHECKLIST:
// 1. Set DEV_MODE 1
// 2. Find your PC IP: ipconfig (Windows) / ifconfig (Mac/Linux)
// 3. Update DEFAULT_SERVER_URL with your PC IP
// 4. Run Django: python manage.py runserver 0.0.0.0:8000
// 5. Add to your Django env:
//      DEVICE_LEGACY_KEY_ENABLED=true
//      PETIO_DEVICE_API_KEY=petio-local-dev
// 6. Ensure PC firewall allows port 8000
// 7. ESP8266 and PC must be on the same WiFi network
//
// PRODUCTION DEPLOYMENT STEPS:
// 1. Set DEV_MODE 0 and flash to device
// 2. Device boots → connects to saved WiFi automatically
// 3. If no saved WiFi → connect to "PETio-Setup-XXXX" AP
//    → open browser → 192.168.4.1 → enter home WiFi credentials
// 4. Device restarts → connects to home WiFi
// 5. OLED shows pairing screen with 6-digit PIN and Device ID
// 6. Go to https://petio.site/devices/claim/
// 7. Enter Device ID (ESP-0081CA63) and PIN from OLED
// 8. Click Claim Device
// 9. Device receives provisioned key → saves to EEPROM
// 10. Device exits pairing → OLED shows normal screen
// 11. All features active:
//     - Feed button from UI works
//     - Schedules execute
//     - History records
//     - Device shows online
//
// FUTURE REBOOTS: Device auto-connects and resumes — no re-pairing
// NETWORK CHANGE: Hold FEED button 5s → clears credentials → re-setup
// ACCOUNT CHANGE: Hold FEED button 5s → forces re-pairing
// ═══════════════════════════════════════════════════════════

// Wi-Fi Configuration Settings
#define WIFI_TIMEOUT_MS 30000
#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#define FORCE_PAIR_ON_BOOT 0

// EEPROM Configuration
#define EEPROM_SIZE 512
#define LAST_SCHEDULE_ID_ADDR 65
#define CALIB_FLAG_ADDR 68
#define MS_PER_GRAM_ADDR 69
#define STARTUP_DELAY_ADDR 73
#define API_KEY_FLAG_ADDR 80
#define API_KEY_ADDR 81
#define API_KEY_MAX_LEN 64
#define WIFI_FLAG_ADDR 146
#define WIFI_SSID_ADDR 147
#define WIFI_SSID_MAX_LEN 32
#define WIFI_PASS_ADDR (WIFI_SSID_ADDR + WIFI_SSID_MAX_LEN)
#define WIFI_PASS_MAX_LEN 64

// LED Blink Intervals (milliseconds)
#define LED_BLINK_FAST 200
#define LED_BLINK_SLOW 1000

// Servo Control Constants
#define SERVO_NEUTRAL 1500
#define SERVO_RAMP_MS 800
#define SERVO_FORWARD_CLOCKWISE 1
#if SERVO_FORWARD_CLOCKWISE
  #define SERVO_FORWARD 1520
  #define SERVO_BACKWARD 1460
  #define SERVO_RAMP_START 1510
  #define SERVO_SHORT_FORWARD 1600
  #define SERVO_CAL_FORWARD 1600
  #define SERVO_FEED_SPEED 1550
#else
  #define SERVO_FORWARD 1520
  #define SERVO_BACKWARD 1460
  #define SERVO_RAMP_START 1510
  #define SERVO_SHORT_FORWARD 1600
  #define SERVO_CAL_FORWARD 1600
  #define SERVO_FEED_SPEED 1550
#endif

// Anti-Clog System Constants
#define ANTI_CLOG_PRE_SPIN_MS 400
#define ANTI_CLOG_POST_CLEAR_MS 800
#define ANTI_CLOG_REVERSE_PULSE_MS 250
#define ANTI_CLOG_PAUSE_MS 200
#define SERVO_RAMP_FAST_MS 500
// Map anti-clog forward/reverse speeds to correct direction based on SERVO_FORWARD_CLOCKWISE
#if SERVO_FORWARD_CLOCKWISE
  #define SERVO_ANTI_CLOG_SPEED 1300
  #define SERVO_ANTI_CLOG_REVERSE 1400
#else
  #define SERVO_ANTI_CLOG_SPEED 1440
  #define SERVO_ANTI_CLOG_REVERSE 1400
#endif

#define ANTI_JAM_INTERVAL_MS 2000
#define ANTI_JAM_REVERSE_MS 200
#define REVERSE_CLEAR_FORWARD_MS 800
#define REVERSE_CLEAR_REVERSE_MS 300
#define REVERSE_CLEAR_PAUSE_MS 200
// Button and Feeding Constants
#define BUTTON_DEBOUNCE_MS 20
#define BUTTON_EVENT_SUPPRESS_MS 0
#define MANUAL_OVERRIDE_MS 800
#define FEED_CONFIRM_MS 120
#define OTHER_CONFLICT_THRESHOLD_PCT 60
#define SIMPLE_BUTTON_MODE 1
#define BUTTON_BOOT_IGNORE_MS 2000
#define COOLDOWN_PERIOD_MS 5000
#define DEBUG_BUTTONS 0
#define DEBUG_BUTTONS_RATE_MS 250
#define DEFAULT_FEED_DURATION 1000
// Runtime feed pulse override
unsigned int g_feedPulse = SERVO_FEED_SPEED;

// HTTP Communication Constants
// ── Server URL (controlled by DEV_MODE) ──────────────────
#if DEV_MODE
  // TODO: Update this IP to match your PC's local IP address
  // Run: ipconfig (Windows) or ifconfig (Mac/Linux) to find it
  // Run Django with: python manage.py runserver 0.0.0.0:8000
  #define DEFAULT_SERVER_URL "http://192.168.18.9:8000"
#else
  #define DEFAULT_SERVER_URL "https://petio.site"
#endif
// ─────────────────────────────────────────────────────────
#define DEFAULT_DEVICE_ID "ESP-0081CA63"
// ── API Key (controlled by DEV_MODE) ─────────────────────
#if DEV_MODE
  // Must match PETIO_DEVICE_API_KEY env var on local Django server
  // In your shell: DEVICE_LEGACY_KEY_ENABLED=true
  //                PETIO_DEVICE_API_KEY=petio-local-dev
  #define DEFAULT_API_KEY "petio-local-dev"
#else
  #define DEFAULT_API_KEY "51c1ebc55900af5273e5a43c2ba0c140"
#endif
// ─────────────────────────────────────────────────────────
// ── HTTP Timeout (controlled by DEV_MODE) ────────────────
// Local HTTP needs only 3s — no TLS handshake overhead
// Production HTTPS to petio.site needs more time due to
// TLS handshake latency from Philippines to US servers
#if DEV_MODE
  #define HTTP_TIMEOUT_MS 3000
#else
  #define HTTP_TIMEOUT_MS 8000
#endif
// ─────────────────────────────────────────────────────────
// ── HTTP Max Retries (controlled by DEV_MODE) ────────────
// Local dev: 2 retries is enough — fast local network
// Production: 3 retries handles transient mobile network drops
#if DEV_MODE
  #define HTTP_MAX_RETRIES 2
#else
  #define HTTP_MAX_RETRIES 3
#endif
// ─────────────────────────────────────────────────────────
// ── Legacy auth fallback (controlled by DEV_MODE) ────────
// In DEV_MODE, allows polling without a provisioned device key
// so you can test schedules and commands before pairing.
// In production, device MUST be paired first — no fallback.
#if DEV_MODE
  #define DEV_ALLOW_LEGACY_FOR_POLL 1
#else
  #define DEV_ALLOW_LEGACY_FOR_POLL 0
#endif
// ─────────────────────────────────────────────────────────

// NTP and Time Synchronization Constants
#define NTP_SERVER "pool.ntp.org"
#define NTP_TIMEZONE_OFFSET 0
#define NTP_UPDATE_INTERVAL 3600000

// Wi-Fi Fallback Portal Timing
#define FALLBACK_AP_AFTER_MS 300000

// Schedule Polling Constants
#define SCHEDULE_POLL_INTERVAL 45000
#define SCHEDULE_GRACE_PERIOD 120
#define MS_PER_GRAM 20
// Remote command polling
#define COMMAND_POLL_INTERVAL 10000

// Calibrated dispensing constants
#define STARTUP_DELAY_MS 100
#define MIN_DISPENSE_TIME_MS 50UL
#define MAX_DISPENSE_TIME_MS 30000UL

// EEPROM Addresses for Schedule Tracking
#define LAST_SCHEDULE_IxD_ADDR 65
#define SCHEDULE_ID_SIZE 4

// EEPROM Addresses for Calibration
#define CALIB_FLAG_ADDR 68
#define MS_PER_GRAM_ADDR 69
#define STARTUP_DELAY_ADDR 73

// ── Wheel calibration (replaces ms/gram continuous model) ────
// Wheel has 8 compartments × 45° each.
// Calibrate by: filling all 8, weighing total, dividing by 8.
#define WHEEL_COMPARTMENTS       8
#define MS_PER_COMP_DEFAULT      800UL
#define GRAMS_PER_COMP_DEFAULT   10.0f
// Extra time after last compartment rotates to ensure food fully
// clears the exit aperture before the servo stops.
// Fixes inconsistent 2-compartment dispense on short feeds.
#define POST_COMP_SETTLE_MS      200UL

// Calibrated duration API (wheel-based)
unsigned long calculateFeedingDuration(float targetGrams);
void saveCalibration(float gramsPerComp, unsigned long msPerComp);
void loadCalibration();
void handleCalibrationCommands();

// Manual portion configuration
float manualPortionGrams = 25.0f;
unsigned long manualFeedDurationMs = 0;
const float PORTION_STEP_GRAMS = 5.0f;
const float MANUAL_PORTION_MIN_GRAMS = 5.0f;
const float MANUAL_PORTION_MAX_GRAMS = 240.0f;

// Calibration state (wheel-based)
unsigned long g_msPerComp    = MS_PER_COMP_DEFAULT;
float         g_gramsPerComp = GRAMS_PER_COMP_DEFAULT;
bool calibrationMode = false;
float calibrationTestGrams = 0.0f;
unsigned long calibrationStartTime = 0;
unsigned long calibrationLastDuration = 0;
String calibInput = "";

// Inlined ledcontrol.h/.cpp
enum LedState {
  LED_OFF,
  LED_ERROR,
  LED_READY,
  LED_FEEDING,
  LED_CONFIG_BLINK,
  LED_CONNECTING
};

class LedController {
private:
  LedState currentState;
  bool blinkState;
  unsigned long lastBlinkTime;
  void setRedLED(bool state) { digitalWrite(RED_LED_PIN, state ? HIGH : LOW); }
  void setBlueLED(bool state) { digitalWrite(BLUE_LED_PIN, state ? HIGH : LOW); }
  void turnOffAllLEDs() { setRedLED(false); setBlueLED(false); }
  bool overlayActive;
  bool overlayBlue;
  unsigned long overlayLastToggle;
  unsigned long overlayInterval;
  bool overlayOn;
  int overlayCycles;
  int overlayCompleted;
  LedState overlayRestore;

public:
  LedController() : currentState(LED_OFF), blinkState(false), lastBlinkTime(0), overlayActive(false), overlayBlue(false), overlayLastToggle(0), overlayInterval(0), overlayOn(false), overlayCycles(0), overlayCompleted(0), overlayRestore(LED_OFF) {}
  void init() { pinMode(RED_LED_PIN, OUTPUT); pinMode(BLUE_LED_PIN, OUTPUT); turnOffAllLEDs(); }
  void setState(LedState state) {
    currentState = state; resetBlinkTimer();
    switch (currentState) {
      case LED_OFF: turnOffAllLEDs(); break;
      case LED_ERROR: showError(); break;
      case LED_READY: showReady(); break;
      case LED_FEEDING: showFeeding(); break;
      case LED_CONFIG_BLINK: break; // handled in update
      case LED_CONNECTING: break;    // handled in update
    }
  }
  LedState getState() { return currentState; }
  void update(unsigned long currentTime) {
    if (overlayActive) {
      if (currentState == LED_CONFIG_BLINK || currentState == LED_CONNECTING) { /* overlay preempts base blink briefly */ }
      if (currentTime - overlayLastToggle >= overlayInterval) {
        overlayLastToggle = currentTime;
        overlayOn = !overlayOn;
        if (overlayOn) {
          turnOffAllLEDs();
          if (overlayBlue) setBlueLED(true); else setRedLED(true);
        } else {
          if (overlayBlue) setBlueLED(false); else setRedLED(false);
          overlayCompleted++;
          if (overlayCompleted >= overlayCycles) {
            overlayActive = false;
            setState(overlayRestore);
            return;
          }
        }
      }
      return;
    }
    if (currentState == LED_CONFIG_BLINK || currentState == LED_CONNECTING) {
      unsigned long blinkInterval = (currentState == LED_CONFIG_BLINK) ? LED_BLINK_FAST : LED_BLINK_SLOW;
      if (currentTime - lastBlinkTime >= blinkInterval) {
        blinkState = !blinkState; lastBlinkTime = currentTime;
        if (currentState == LED_CONFIG_BLINK) { turnOffAllLEDs(); setRedLED(blinkState); }
        else if (currentState == LED_CONNECTING) { turnOffAllLEDs(); setRedLED(blinkState); }
      }
    }
  }
  void update() { update(millis()); }
  void showError() { currentState = LED_ERROR; turnOffAllLEDs(); setRedLED(true); }
  void showReady() { currentState = LED_READY; turnOffAllLEDs(); setBlueLED(true); }
  void showFeeding() { currentState = LED_FEEDING; turnOffAllLEDs(); setBlueLED(true); }
  void showConfigMode() { setState(LED_CONFIG_BLINK); }
  void showConnecting() { setState(LED_CONNECTING); }
  void turnOff() { setState(LED_OFF); }
  bool isBlinking() { return (currentState == LED_CONFIG_BLINK || currentState == LED_CONNECTING); }
  void resetBlinkTimer() { lastBlinkTime = millis(); blinkState = false; }
  void flashRed(unsigned long duration_ms) { setRedLED(true); delay(duration_ms); setRedLED(false); }
  void flashBlue(unsigned long duration_ms) { setBlueLED(true); delay(duration_ms); setBlueLED(false); }
  void startFeedbackBlinkBlue(int cycles, unsigned long interval_ms) { overlayRestore = currentState; overlayActive = true; overlayBlue = true; overlayInterval = interval_ms; overlayCycles = cycles; overlayCompleted = 0; overlayOn = false; overlayLastToggle = millis(); }
  void startFeedbackBlinkRed(int cycles, unsigned long interval_ms) { overlayRestore = currentState; overlayActive = true; overlayBlue = false; overlayInterval = interval_ms; overlayCycles = cycles; overlayCompleted = 0; overlayOn = false; overlayLastToggle = millis(); }
};



class OledDisplay {
private:
  Adafruit_SSD1306 display;
  unsigned long lastUpdate;
  uint8_t      animFrame;
  bool         initialized;

  void scanI2C() {
    int found = 0;
    for (int addr = 1; addr < 127; addr++) {
      Wire.beginTransmission(addr);
      if (Wire.endTransmission() == 0) {
        found++;
      }
    }
  }

  /** Small WiFi "fan" icon at (x, y). Shows X when disconnected. */
  void drawWifiIcon(int x, int y, bool connected) {
    if (!connected) {
      display.drawLine(x,     y,     x + 9, y + 9, SSD1306_WHITE);
      display.drawLine(x + 9, y,     x,     y + 9, SSD1306_WHITE);
      return;
    }
    for (int r = 8; r >= 2; r -= 3) {
      display.drawCircle(x + 5, y + 10, r, SSD1306_WHITE);
      display.fillRect(x, y + 10, 11, 8, SSD1306_BLACK);
    }
    display.fillCircle(x + 5, y + 10, 1, SSD1306_WHITE);
  }

  /** Horizontal progress bar. pct = 0–100 */
  void drawProgressBar(int x, int y, int w, int h, int pct) {
    display.drawRect(x, y, w, h, SSD1306_WHITE);
    int fill = (int)((w - 2) * pct / 100);
    if (fill > 0)
      display.fillRect(x + 1, y + 1, fill, h - 2, SSD1306_WHITE);
  }

  void drawNormalScreen(bool wifiConnected, float portionGrams) {
    // ── Top bar: WiFi icon + time ─────────────────────────────────────────
    drawWifiIcon(1, 1, wifiConnected);

    time_t nowTs = time(nullptr);
    struct tm* t = localtime(&nowTs);
    char timeBuf[9];
    snprintf(timeBuf, sizeof(timeBuf), "%02d:%02d:%02d",
             t->tm_hour, t->tm_min, t->tm_sec);

    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    int timeX = OLED_WIDTH - (int)strlen(timeBuf) * 6 - 1;
    display.setCursor(timeX, 3);
    display.print(timeBuf);

    // ── Divider ───────────────────────────────────────────────────────────
    display.drawLine(0, 14, OLED_WIDTH - 1, 14, SSD1306_WHITE);

    // ── "PORTION" label ───────────────────────────────────────────────────
    display.setTextSize(1);
    display.setCursor(2, 16);
    display.print("Portion:");

    // ── Big number + unit ─────────────────────────────────────────────────
    int portionInt = (int)(portionGrams + 0.5f);
    char numBuf[6];
    snprintf(numBuf, sizeof(numBuf), "%d", portionInt);

    display.setTextSize(3);
    int numW = (int)strlen(numBuf) * 18 + 12;
    int numX = (OLED_WIDTH - numW) / 2;
    display.setCursor(numX, 20);
    display.print(numBuf);

    display.setTextSize(2);
    display.setCursor(numX + (int)strlen(numBuf) * 18 + 2, 26);
    display.print("g");

    // ── Progress bar + RDY ────────────────────────────────────────────────
    int pct = (int)(portionGrams / MANUAL_PORTION_MAX_GRAMS * 100.0f);
    pct = constrain(pct, 0, 100);
    drawProgressBar(0, 53, OLED_WIDTH - 30, 8, pct);

    display.setTextSize(1);
    display.setCursor(OLED_WIDTH - 28, 54);
    display.print("RDY");
  }

  void drawDispensingScreen(float portionGrams) {
    // ── Marching-block animation ──────────────────────────────────────────
    const int BLOCK_W   = 12;
    const int BLOCK_H   = 7;
    const int BLOCK_GAP = 3;
    const int NUM_BLOCKS = OLED_WIDTH / (BLOCK_W + BLOCK_GAP);
    int offset = (animFrame * 3) % (BLOCK_W + BLOCK_GAP);

    for (int i = 0; i < NUM_BLOCKS + 1; i++) {
      int bx = i * (BLOCK_W + BLOCK_GAP) - offset;
      if (bx + BLOCK_W > 0 && bx < OLED_WIDTH) {
        if (i % 3 != 2)
          display.fillRect(bx, 1, BLOCK_W, BLOCK_H, SSD1306_WHITE);
        else
          display.drawRect(bx, 1, BLOCK_W, BLOCK_H, SSD1306_WHITE);
      }
    }

    // ── "DISPENSING" text ─────────────────────────────────────────────────
    display.setTextSize(2);
    int textW = 10 * 12;
    int textX = (OLED_WIDTH - textW) / 2;
    display.setCursor(textX, 18);
    display.print("DISPENSING");

    // ── Scrolling dot animation ───────────────────────────────────────────
    const int DOT_R    = 3;
    const int DOT_GAPS = 12;
    const int NUM_DOTS = 5;
    int dotStartX = (OLED_WIDTH - (NUM_DOTS * DOT_GAPS)) / 2;
    for (int i = 0; i < NUM_DOTS; i++) {
      int dx  = dotStartX + i * DOT_GAPS;
      bool lit = ((int)(animFrame % NUM_DOTS) == i);
      if (lit)
        display.fillCircle(dx, 43, DOT_R, SSD1306_WHITE);
      else
        display.drawCircle(dx, 43, DOT_R - 1, SSD1306_WHITE);
    }

    // ── Divider + portion reminder ────────────────────────────────────────
    display.drawLine(0, 54, OLED_WIDTH - 1, 54, SSD1306_WHITE);

    int portionInt = (int)(portionGrams + 0.5f);
    char buf[16];
    snprintf(buf, sizeof(buf), "%dg", portionInt);

    display.setTextSize(1);
    int labelW = (int)strlen(buf) * 6;
    display.setCursor((OLED_WIDTH - labelW) / 2, 56);
    display.print(buf);
  }

  void drawPairingScreen(const String& pin, int secondsLeft, const String& devId) {
    display.fillRect(0, 0, OLED_WIDTH, 13, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setTextSize(1);
    const char* header = "* PAIRING MODE *";
    int hW = strlen(header) * 6;
    display.setCursor((OLED_WIDTH - hW) / 2, 3);
    display.print(header);

    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    const char* label = "Enter in app:";
    int lW = strlen(label) * 6;
    display.setCursor((OLED_WIDTH - lW) / 2, 17);
    display.print(label);

    display.setTextSize(2);
    String formatted = pin.substring(0, 3) + String(" ") + pin.substring(3);
    int pW = formatted.length() * 12;
    display.setCursor((OLED_WIDTH - pW) / 2, 27);
    display.print(formatted);

    display.drawLine(10, 47, OLED_WIDTH - 10, 47, SSD1306_WHITE);

    display.setTextSize(1);
    display.setCursor(2, 52);
    display.print("ID:");
    display.print(devId);

    String cStr = String(secondsLeft) + "s";
    int cX = OLED_WIDTH - (int)cStr.length() * 6 - 2;
    display.setCursor(cX, 52);
    display.print(cStr);

    int pct = (secondsLeft * 100) / 300; // 300s TTL
    pct = constrain(pct, 0, 100);
    int barW = OLED_WIDTH - 4;
    display.drawRect(2, 59, barW, 4, SSD1306_WHITE);
    int fill = (barW - 2) * pct / 100;
    if (fill > 0) display.fillRect(3, 60, fill, 2, SSD1306_WHITE);
  }

public:
  OledDisplay()
    : display(OLED_WIDTH, OLED_HEIGHT, &Wire, OLED_RESET),
      lastUpdate(0), animFrame(0), initialized(false) {}

  void init() {
    Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
    Wire.setClock(400000);

    bool ok = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
    if (!ok) {
      uint8_t alt = (OLED_ADDR == 0x3C) ? 0x3D : 0x3C;
      ok = display.begin(SSD1306_SWITCHCAPVCC, alt);
    }
    if (!ok) {
      initialized = false;
      return;
    }

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    display.setCursor(20, 20);
    display.print("PETio");
    display.setTextSize(1);
    display.setCursor(28, 40);
    display.print("Booting...");
    display.display();

    lastUpdate  = millis();
    initialized = true;
  }

  /**
   * Call every loop() iteration.
   * Signature is unchanged from the original — drop-in compatible.
   */
  void update(bool wifiConnected, const String& /*ssid*/,
              float portionGrams, bool isFeeding) {
    if (!initialized) return;
    unsigned long now = millis();
    if (now - lastUpdate < OLED_UPDATE_INTERVAL_MS) return;
    lastUpdate = now;
    animFrame++;

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    if (isFeeding)
      drawDispensingScreen(portionGrams);
    else
      drawNormalScreen(wifiConnected, portionGrams);

    display.display();
  }

  void updatePairing(const String& pin, int secondsLeft, const String& devId) {
    unsigned long now = millis();
    if (now - lastUpdate < OLED_UPDATE_INTERVAL_MS) return;
    lastUpdate = now;
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    drawPairingScreen(pin, secondsLeft, devId);
    display.display();
  }
};

// Inlined motorcontrol.h/.cpp
class MotorController {
private:
  Servo feedingServo; bool servoAttached; bool feedingInProgress; unsigned long feedingStartTime; unsigned long feedingDuration; LedController* ledController; unsigned int lastPulse; unsigned int targetPulse; bool antiClogMode; bool clogDetected;
  unsigned long lastAntiJamTs; bool antiJamActive; unsigned long antiJamStart; int retryAttempts;
  void attachServo() { if (!servoAttached) { feedingServo.attach(SERVO_PIN); servoAttached = true; feedingServo.writeMicroseconds(SERVO_NEUTRAL); delay(100); } }
  void detachServo() { if (servoAttached) { feedingServo.detach(); servoAttached = false; Serial.println("Servo detached"); } }
  void startServo() { if (servoAttached) { lastPulse = SERVO_RAMP_START; feedingServo.writeMicroseconds(lastPulse); Serial.print("Servo started - Forward rotation ("); Serial.print(lastPulse); Serial.println(" µs)"); } }
  void stopServo() { if (servoAttached) { feedingServo.writeMicroseconds(SERVO_NEUTRAL); lastPulse = SERVO_NEUTRAL; Serial.print("Servo stopped - Neutral position ("); Serial.print(SERVO_NEUTRAL); Serial.println(" µs)"); } }
public:
  MotorController() : servoAttached(false), feedingInProgress(false), feedingStartTime(0), feedingDuration(0), ledController(nullptr), lastPulse(SERVO_NEUTRAL), targetPulse(SERVO_FORWARD), antiClogMode(false), clogDetected(false), lastAntiJamTs(0), antiJamActive(false), antiJamStart(0), retryAttempts(0) {}
  void init(LedController* ledCtrl) { ledController = ledCtrl; attachServo(); }
  void waitWithLED(unsigned long duration_ms) {
    unsigned long start = millis();
    while (millis() - start < duration_ms) {
      if (ledController) ledController->update();
      delay(10);
    }
  }
  void startFeeding(unsigned long duration_ms) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring request"); return; }
    Serial.print("Starting feeding for "); Serial.print(duration_ms); Serial.println(" ms");
    antiClogMode = false;
    feedingInProgress = true; feedingStartTime = millis(); feedingDuration = duration_ms; if (duration_ms < 2000UL) targetPulse = 1680; else targetPulse = SERVO_FORWARD; if (ledController) ledController->showFeeding(); startServo(); lastAntiJamTs = millis(); antiJamActive = false; retryAttempts = 0;
  }
  void startCalibrationFeed(unsigned long duration_ms) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring request"); return; }
    Serial.print("Starting calibration feeding for "); Serial.print(duration_ms); Serial.println(" ms");
    antiClogMode = false;
    feedingInProgress = true; 
    feedingStartTime = millis() - SERVO_RAMP_MS; 
    feedingDuration = duration_ms + SERVO_RAMP_MS; 
    targetPulse = g_feedPulse;
    if (ledController) ledController->showFeeding(); 
    feedingServo.writeMicroseconds(targetPulse);
    lastPulse = targetPulse; lastAntiJamTs = millis(); antiJamActive = false; retryAttempts = 0;
    Serial.print("Calibration feed pulse: "); Serial.println(targetPulse);
  }
  void stopFeeding() { if (!feedingInProgress) return; Serial.println("Stopping feeding operation"); stopServo(); feedingInProgress = false; feedingStartTime = 0; feedingDuration = 0; lastFeedCompletionTime = millis(); if (ledController) ledController->showReady(); }
  bool isFeedingInProgress() { return feedingInProgress; }
  void update() { 
    if (feedingInProgress) { 
      unsigned long now = millis(); 
      unsigned long elapsed = now - feedingStartTime; 
      unsigned long rampMs = antiClogMode ? SERVO_RAMP_FAST_MS : SERVO_RAMP_MS;
      if (antiJamActive) {
        if ((now - antiJamStart) >= ANTI_JAM_REVERSE_MS) {
          feedingServo.writeMicroseconds(targetPulse); lastPulse = targetPulse; antiJamActive = false;
        }
      } else if (elapsed < rampMs) { 
        unsigned int rampPulse = SERVO_RAMP_START + (unsigned int)((long)(targetPulse - SERVO_RAMP_START) * (long)elapsed / (long)rampMs); 
        if (rampPulse != lastPulse) { feedingServo.writeMicroseconds(rampPulse); lastPulse = rampPulse; } 
      } else if (lastPulse != targetPulse) { 
        feedingServo.writeMicroseconds(targetPulse); lastPulse = targetPulse; 
      } 
      // Only apply anti-jam to feeds longer than the interval to avoid triggering on short feeds
      if (!antiJamActive &&
          feedingDuration > ANTI_JAM_INTERVAL_MS &&
          (now - lastAntiJamTs) >= ANTI_JAM_INTERVAL_MS) {
        performAntiJamPulse();
        // Removed feedingStartTime += ANTI_JAM_REVERSE_MS; - This was causing the over-dispensing bug
      }
      if (!clogDetected && elapsed > (feedingDuration + 2000UL)) { 
        clogDetected = true; Serial.println("WARNING: Possible clog detected - feeding taking too long"); 
      }
      if (elapsed >= feedingDuration) { 
        if (antiClogMode) { Serial.println("Feeding duration completed, starting clearing phase"); completeFeedingWithClear(); clogDetected = false; } 
        else { Serial.println("Feeding duration completed"); stopFeeding(); } 
      } 
    } 
  }
  void emergencyStop() { Serial.println("EMERGENCY STOP activated"); stopFeeding(); detachServo(); }
  unsigned long getRemainingFeedTime() { if (!feedingInProgress) return 0; unsigned long elapsed = millis() - feedingStartTime; if (elapsed >= feedingDuration) return 0; return feedingDuration - elapsed; }
  void startFeedingWithAntiClog(unsigned long duration_ms) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring request"); return; }
    Serial.print("Starting normal feeding for "); Serial.print(duration_ms); Serial.println(" ms");
    antiClogMode = false;
    feedingInProgress = true; 
    feedingStartTime = millis() - SERVO_RAMP_MS; 
    feedingDuration = duration_ms + SERVO_RAMP_MS; 
    targetPulse = g_feedPulse;
    if (ledController) ledController->showFeeding();
    feedingServo.writeMicroseconds(targetPulse);
    lastPulse = targetPulse; lastAntiJamTs = millis(); antiJamActive = false; retryAttempts = 0;
    Serial.print("Normal feed pulse: "); Serial.println(targetPulse);
  }
  void runMiniAgitation() {
    Serial.println("Mini-agitation disabled");
  }
  bool checkForClog() { return clogDetected; }
  void performAntiJamPulse() {
    Serial.print("Anti-jam pulse at "); Serial.print((float)ANTI_JAM_INTERVAL_MS / 1000.0f, 1); Serial.println("s...");
    feedingServo.writeMicroseconds(SERVO_ANTI_CLOG_REVERSE);
    antiJamActive = true;
    antiJamStart = millis();
    lastAntiJamTs = antiJamStart;
  }
  void startReverseClearFeeding(float totalGrams) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring reverse-clear request"); return; }
    unsigned long totalDuration = calculateFeedingDuration(totalGrams);
    Serial.println("Reverse-clear disabled; performing single continuous feed");
    startFeedingWithAntiClog(totalDuration);
  }
  void testReverseMotion(unsigned long test_ms) {
    Serial.print("Testing reverse motion for "); Serial.print(test_ms); Serial.println(" ms...");
    feedingServo.writeMicroseconds(SERVO_ANTI_CLOG_REVERSE);
    waitWithLED(test_ms);
    feedingServo.writeMicroseconds(SERVO_NEUTRAL);
    Serial.println("Reverse test complete");
  }
  void testForwardMotion(unsigned long test_ms) {
    Serial.print("Testing forward motion for "); Serial.print(test_ms); Serial.println(" ms...");
    feedingServo.writeMicroseconds(g_feedPulse);
    waitWithLED(test_ms);
    feedingServo.writeMicroseconds(SERVO_NEUTRAL);
    Serial.println("Forward test complete");
  }
  void startChunkedFeeding(float totalGrams) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring chunked request"); return; }
    unsigned long totalDuration = calculateFeedingDuration(totalGrams);
    Serial.println("Chunked feeding disabled; performing single continuous feed");
    startFeedingWithAntiClog(totalDuration);
  }
  void completeFeedingWithClear() {
    if (!feedingInProgress) return;
    Serial.println("Phase 3: Post-dispense clearing");
    if (servoAttached) { feedingServo.writeMicroseconds(SERVO_ANTI_CLOG_SPEED); delay(ANTI_CLOG_POST_CLEAR_MS); }
    stopServo(); feedingInProgress = false; feedingStartTime = 0; feedingDuration = 0; lastFeedCompletionTime = millis(); antiClogMode = false;
    if (ledController) ledController->showReady();
    Serial.println("╔════════════════════════════════════╗");
    Serial.println("║   FEEDING COMPLETE                ║");
    Serial.println("╚════════════════════════════════════╝\n");
  }
  void runAgitationCycle() {
    Serial.println("=== AGITATION CYCLE START (FORWARD ONLY) ===");
    for (int i = 0; i < 5; i++) {
      feedingServo.writeMicroseconds(SERVO_CAL_FORWARD); delay(300);
      feedingServo.writeMicroseconds(SERVO_NEUTRAL); delay(300);
    }
    Serial.println("=== AGITATION CYCLE COMPLETE ===");
  }
  bool isDispensePhaseActive() {
    if (!feedingInProgress) return false;
    unsigned long elapsed = millis() - feedingStartTime;
    return elapsed < feedingDuration;
  }
};

bool loadWifiCredentials(String& ssidOut, String& passOut);
void saveWifiCredentials(const String& ssid, const String& pass);
void clearWifiCredentials();

class NetworkingManager {
private:
  String deviceID;
  bool wifiConnected;
  unsigned long lastConnectionAttempt;
  unsigned long lastStatusPrint;
  int lastStatusSeen;
  LedController* ledController;
  bool configMode;
  bool hasCredentialsVal;
  String storedSsid;
  String storedPass;
  ESP8266WebServer* configServer;
  String apSsid;
  unsigned long offlineSince;
  DNSServer* dnsServer;
  IPAddress apIp;
  IPAddress apGw;
  IPAddress apMask;

  void generateDeviceID() {
    uint32_t chipId = ESP.getChipId();
    char id[16];
    sprintf(id, "%08X", chipId);
    deviceID = String(id);
    Serial.print("Device ID: ");
    Serial.println(deviceID);
  }

  static String htmlEscape(const String& in) {
    String out;
    out.reserve(in.length() + 8);
    for (size_t i = 0; i < in.length(); i++) {
      char c = in[i];
      if (c == '&') out += "&amp;";
      else if (c == '<') out += "&lt;";
      else if (c == '>') out += "&gt;";
      else if (c == '\"') out += "&quot;";
      else out += c;
    }
    return out;
  }

  static String urlEncode(const String& in) {
    const char* hex = "0123456789ABCDEF";
    String out;
    for (size_t i = 0; i < in.length(); i++) {
      uint8_t c = (uint8_t)in[i];
      bool safe = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '-' || c == '_' ||
                  c == '.' || c == '~';
      if (safe) out += (char)c;
      else {
        out += '%';
        out += hex[(c >> 4) & 0x0F];
        out += hex[c & 0x0F];
      }
    }
    return out;
  }

  static const char* encTypeStr(uint8_t e) {
    switch (e) {
      case ENC_TYPE_NONE: return "OPEN";
      case ENC_TYPE_WEP: return "WEP";
      case ENC_TYPE_TKIP: return "WPA/TKIP";
      case ENC_TYPE_CCMP: return "WPA2/CCMP";
      case ENC_TYPE_AUTO: return "AUTO";
      default: return "?";
    }
  }

  void startConfigPortal() {
    if (configServer) return;
    configMode = true;
    WiFi.mode(WIFI_OFF);
    delay(100);
    WiFi.mode(WIFI_AP);
    delay(200);
    // Explicit AP IP configuration for better client compatibility
    WiFi.softAPConfig(apIp, apGw, apMask);
    String suffix = deviceID;
    if (suffix.length() > 4) suffix = suffix.substring(suffix.length() - 4);
    apSsid = String("PETio-Setup-") + suffix;
    WiFi.softAP(apSsid.c_str());
    // Start DNS server to capture all hostnames and resolve to our AP IP
    if (!dnsServer) dnsServer = new DNSServer();
    dnsServer->setErrorReplyCode(DNSReplyCode::NoError);
    dnsServer->start(53, "*", apIp);
    configServer = new ESP8266WebServer(80);
    configServer->on("/", [this]() {
      String ssidPref = "";
      if (configServer->hasArg("ssid")) ssidPref = configServer->arg("ssid");
      String ssidVal = htmlEscape(ssidPref);
      String html =
        "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>WiFi Setup</title><style>body{font-family:Arial;margin:20px}input{padding:8px;margin:6px 0;width:100%}"
        "button{padding:10px 14px}</style></head><body>"
        "<h2>WiFi Setup</h2>"
        "<p><a href='/scan'>Scan for networks</a></p>"
        "<form method='POST' action='/save'>"
        "<label>SSID</label><input name='ssid' value='" + ssidVal + "' maxlength='" + String(WIFI_SSID_MAX_LEN - 1) + "' required/>"
        "<label>Password</label><input name='pass' type='password' maxlength='" + String(WIFI_PASS_MAX_LEN - 1) + "'/>"
        "<button type='submit'>Save</button></form>"
        "</body></html>";
      configServer->send(200, "text/html", html);
    });
    // Captive portal helpers for common OS probes
    configServer->on("/generate_204", [this]() {
      String loc = String("http://") + apIp.toString() + String("/");
      configServer->sendHeader("Cache-Control", "no-cache");
      configServer->sendHeader("Location", loc, true);
      configServer->send(302, "text/plain", "");
    });
    configServer->on("/hotspot-detect.html", [this]() {
      configServer->send(200, "text/html", "<html><head><meta http-equiv='refresh' content='0; url=/' /></head><body>OK</body></html>");
    });
    configServer->on("/ncsi.txt", [this]() {
      configServer->send(200, "text/plain", "Microsoft NCSI");
    });
    configServer->on("/connecttest.txt", [this]() {
      configServer->send(200, "text/plain", "OK");
    });
    configServer->onNotFound([this]() {
      String loc = String("http://") + apIp.toString() + String("/");
      configServer->sendHeader("Cache-Control", "no-cache");
      configServer->sendHeader("Location", loc, true);
      configServer->send(302, "text/plain", "");
    });
    configServer->on("/scan", [this]() {
      Serial.println("Scanning for networks...");
      int n = WiFi.scanNetworks();
      String html =
        "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>Network Scan</title><style>body{font-family:Arial;margin:20px}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccc;padding:6px;text-align:left}</style></head><body>"
        "<h2>Nearby Networks</h2>"
        "<p><a href='/'>&larr; Back to setup</a> | <a href='/scan'>Refresh</a></p>"
        "<table><tr><th>SSID</th><th>RSSI</th><th>Security</th><th></th></tr>";
      for (int i = 0; i < n; i++) {
        String ssid = WiFi.SSID(i);
        if (ssid.length() == 0) continue;
        long rssi = WiFi.RSSI(i);
        uint8_t enc = WiFi.encryptionType(i);
        String esc = htmlEscape(ssid);
        String link = String("/?ssid=") + urlEncode(ssid);
        html += "<tr><td>" + esc + "</td><td>" + String(rssi) + " dBm</td><td>" + String(encTypeStr(enc)) + "</td>"
                "<td><a href='" + link + "'>Use</a></td></tr>";
      }
      html += "</table></body></html>";
      configServer->send(200, "text/html", html);
    });
    configServer->on("/save", [this]() {
      if (!configServer->hasArg("ssid")) { configServer->send(400, "text/plain", "Missing ssid"); return; }
      String ssid = configServer->arg("ssid");
      String pass = configServer->arg("pass");
      saveWifiCredentials(ssid, pass);
      storedSsid = ssid;
      storedPass = pass;
      hasCredentialsVal = true;
      String resp = String("Saved. Connecting to ") + ssid + String(" ...");
      configServer->send(200, "text/plain", resp);
      delay(200);
      stopConfigPortal();
      connect();
    });
    configServer->begin();
    if (ledController) ledController->showError();
    Serial.print("AP started: ");
    Serial.println(apSsid);
  }

  void stopConfigPortal() {
    if (configServer) {
      configServer->stop();
      delete configServer;
      configServer = nullptr;
    }
    if (dnsServer) {
      dnsServer->stop();
      delete dnsServer;
      dnsServer = nullptr;
    }
    WiFi.softAPdisconnect(true);
    configMode = false;
  }

public:
  NetworkingManager()
    : deviceID(""), wifiConnected(false),
      lastConnectionAttempt(0), lastStatusPrint(0), lastStatusSeen(-1), ledController(nullptr),
      configMode(false), hasCredentialsVal(false), storedSsid(""), storedPass(""), configServer(nullptr), apSsid(""), offlineSince(0),
      dnsServer(nullptr), apIp(192,168,4,1), apGw(192,168,4,1), apMask(255,255,255,0) {}

  void init(LedController* ledCtrl) {
    ledController = ledCtrl;
    WiFi.persistent(false);
    WiFi.setAutoConnect(false);
    WiFi.setAutoReconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(100);
    generateDeviceID();
    Serial.println("Networking initialized");
    String ssid, pass;
    if (loadWifiCredentials(ssid, pass)) {
      storedSsid = ssid;
      storedPass = pass;
      hasCredentialsVal = true;
    } else {
      hasCredentialsVal = false;
    }
  }

  void begin() {
    if (hasCredentialsVal) {
      connect();
    } else {
      startConfigPortal();
    }
  }

  void connect() {
    if (!hasCredentialsVal) {
      startConfigPortal();
      return;
    }
    Serial.print("Connecting to saved WiFi: ");
    Serial.println(storedSsid);
    // Ensure any AP is fully shut down before switching to STA-only
    WiFi.softAPdisconnect(true);
    delay(100);
    WiFi.mode(WIFI_STA);  // STA only — never AP/AP_STA here
    delay(100);
    WiFi.disconnect();
    delay(50);
    WiFi.begin(storedSsid.c_str(), storedPass.length() > 0 ? storedPass.c_str() : nullptr);
    lastConnectionAttempt = millis();
    lastStatusPrint = 0;
    lastStatusSeen = -1;
    wifiConnected = false;
  }

  void reconnectNonBlocking() {
    if (!hasCredentialsVal) return;
    Serial.println("Reconnecting to WiFi");
    WiFi.mode(WIFI_STA);
    delay(100);
    WiFi.disconnect();
    delay(50);
    WiFi.begin(storedSsid.c_str(), storedPass.length() > 0 ? storedPass.c_str() : nullptr);
    lastConnectionAttempt = millis();
    lastStatusPrint = 0;
    lastStatusSeen = -1;
    wifiConnected = false;
  }

  void update() {
    if (configMode && configServer) {
      if (dnsServer) dnsServer->processNextRequest();
      configServer->handleClient();
    }
    if (WiFi.status() == WL_CONNECTED && !wifiConnected) {
      wifiConnected = true;
      offlineSince = 0;
      Serial.println("WiFi connected!");
      Serial.print("IP address: ");
      Serial.println(WiFi.localIP());
      if (ledController) ledController->showReady();
      if (configMode) stopConfigPortal();
    } else if (WiFi.status() != WL_CONNECTED && wifiConnected) {
      wifiConnected = false;
      offlineSince = millis();
      Serial.println("WiFi connection lost");
      if (ledController) ledController->showConnecting();
    } else if (WiFi.status() != WL_CONNECTED) {
      unsigned long now = millis();
      int s = WiFi.status();
      if (s != lastStatusSeen || (now - lastStatusPrint) > 3000) {
        lastStatusSeen = s;
        lastStatusPrint = now;
        Serial.print("WiFi status: ");
        switch (s) {
          case WL_CONNECT_FAILED:
            Serial.println("WRONG PASSWORD");
            if (!configMode && hasCredentialsVal) {
              Serial.println("Starting configuration portal due to wrong WiFi password");
              startConfigPortal();
            }
            break;
          case WL_NO_SSID_AVAIL: Serial.println("SSID NOT FOUND"); break;
          case WL_IDLE_STATUS: Serial.println("CONNECTING..."); break;
          case WL_DISCONNECTED: Serial.println("DISCONNECTED"); break;
          default: Serial.println("CODE " + String(s)); break;
        }
      }
      if (!configMode && hasCredentialsVal && (now - lastConnectionAttempt) > WIFI_TIMEOUT_MS) {
        reconnectNonBlocking();
      }
      if (!configMode && hasCredentialsVal && offlineSince != 0) {
        if ((now - offlineSince) > FALLBACK_AP_AFTER_MS) {
          startConfigPortal();
        }
      }
    }
  }

  bool isConnected() { return wifiConnected; }
  bool isConfigured() { return hasCredentialsVal; }
  bool isConfigMode() { return configMode; }
  String getDeviceID() { return deviceID; }
  String getSSID() { return storedSsid; }
  void enterConfigMode() { startConfigPortal(); }
  void clearCredentials() { clearWifiCredentials(); hasCredentialsVal = false; storedSsid = ""; storedPass = ""; }
  int getLastConnectionStatus() { return WiFi.status(); }
};

extern int dailyFeeds;
extern String lastFeedIso;

// Inlined httpclient.h/.cpp
class HTTPClientManager {
private:
  HTTPClient http; WiFiClient wifiClientPlain; WiFiClientSecure wifiClientTLS; String serverURL; String deviceID; unsigned long requestTimeout; int maxRetries; String lastError; String apiKey; String deviceKey;
  String canonicalize(const String& input) { String s = input; s.trim(); return s; }
  bool makeRequest(const String& endpoint, const String& method, const String& payload, String& response) {
    if (!WiFi.isConnected()) { lastError = "WiFi not connected"; return false; }
    String fullURL = serverURL + endpoint;
    Serial.println("HTTP request: " + fullURL);
    for (int attempt = 0; attempt < maxRetries; attempt++) {
      Serial.println("Attempt " + String(attempt + 1) + "/" + String(maxRetries));
      http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
      bool useTLS = fullURL.startsWith("https://");
      if (useTLS) {
        http.begin(wifiClientTLS, fullURL);
      } else {
        http.begin(wifiClientPlain, fullURL);
      }
      http.setTimeout(requestTimeout); http.addHeader("Content-Type", "application/json"); http.addHeader("User-Agent", "ESP8266-PetFeeder/1.0"); http.addHeader("Connection", "close"); http.useHTTP10(true); http.setReuse(false);
      if (deviceID.length() > 0) { http.addHeader("Device-ID", deviceID); }
      if (deviceKey.length() > 0) { http.addHeader("X-Device-Key", deviceKey); }
      if (apiKey.length() > 0) { http.addHeader("X-API-Key", apiKey); }
      int httpCode = -1; if (method == "POST") httpCode = http.POST(payload); else if (method == "GET") httpCode = http.GET();
      if (httpCode > 0) { response = http.getString(); http.end(); if (httpCode >= 200 && httpCode < 300) { lastError = ""; return true; } else { lastError = "HTTP " + String(httpCode) + ": " + response; } }
      else { lastError = "HTTP request failed: " + String(http.errorToString(httpCode)); }
      http.end(); if (attempt < maxRetries - 1) { Serial.println("Request failed, retrying shortly..."); delay(250); }
    }
    return false;
  }
  void printPretty(const String& json) {
    DynamicJsonDocument doc(768);
    DeserializationError err = deserializeJson(doc, json);
    if (!err) {
      String out;
      serializeJsonPretty(doc, out);
      Serial.println("Payload:\n" + out);
    } else {
      Serial.println("Payload: " + json);
    }
  }
  String createFeedingPayload(int portionSize, const String& feedType, const String& notes = "") {
    DynamicJsonDocument doc(512);
    doc["device_id"] = deviceID;
    doc["timestamp"] = nowUtcIso();
    doc["portion_dispensed"] = portionSize;
    doc["source"] = feedType;
    if (notes.length() > 0) doc["notes"] = notes;
    String payload; serializeJson(doc, payload); return payload;
  }
  String createScheduledFeedingPayload(int portionSize, const String& feedType, uint32_t /*scheduleId*/, const String& /*notes*/ = "") {
    DynamicJsonDocument doc(256);
    doc["device_id"] = deviceID;
    doc["timestamp"] = nowUtcIso();
    doc["portion_dispensed"] = portionSize;
    doc["source"] = "scheduled";
    String payload; serializeJson(doc, payload); return payload;
  }
public:
  HTTPClientManager() : requestTimeout(HTTP_TIMEOUT_MS), maxRetries(HTTP_MAX_RETRIES), lastError("") {}
  void init(const String& serverUrl, const String& devID) { serverURL = canonicalize(serverUrl); deviceID = devID; if (!serverURL.endsWith("/api")) { if (!serverURL.endsWith("/")) serverURL += "/"; serverURL += "api"; } wifiClientTLS.setInsecure(); Serial.println("HTTP Client initialized:"); Serial.println("Server URL: " + serverURL); Serial.println("Device ID: " + deviceID); }
  void setApiKey(const String& key) { apiKey = key; Serial.println("API key configured (length): " + String(apiKey.length())); }
  void setDeviceKey(const String& key) { deviceKey = key; Serial.println("Device key configured (length): " + String(deviceKey.length())); }
  bool hasApiKey() const { return apiKey.length() > 0; }
  bool deviceUnpairSelf() {
    DynamicJsonDocument doc(128);
    doc["device_id"] = deviceID;
    String payload; serializeJson(doc, payload);
    String resp;
    return makeRequest("/device/unpair/", "POST", payload, resp);
  }
  bool sendFeedingLog(int portionSize, const String& feedType, const String& notes = "") { String payload = createFeedingPayload(portionSize, feedType, notes); String response; Serial.println("Sending feeding log to server..."); printPretty(payload); return makeRequest("/device/logs/", "POST", payload, response); }
  bool sendDeviceStatus(const String& /*status*/, int /*batteryLevel*/ = 100, int wifiSignal = -50) { DynamicJsonDocument doc(512); doc["device_id"] = deviceID; doc["wifi_rssi"] = wifiSignal; doc["uptime"] = (int)(millis()/1000); doc["daily_feeds"] = dailyFeeds; if (lastFeedIso.length() > 0) doc["last_feed"] = lastFeedIso; doc["error_message"] = ""; String payload; serializeJson(doc, payload); String response; bool success = makeRequest("/device/status/", "POST", payload, response); if (success) { Serial.println("Device status sent successfully"); return true; } else { Serial.println("Failed to send device status: " + lastError); return false; } }
  bool getDeviceConfig(String& configResponse) { String endpoint = String("/device/config/?device_id=") + deviceID; Serial.println("Requesting device configuration..."); bool success = makeRequest(endpoint, "GET", "", configResponse); if (success) { Serial.println("Device configuration retrieved successfully"); return true; } else { Serial.println("Failed to get device configuration: " + lastError); return false; } }
  bool getNextSchedule(String& scheduleResponse) { String endpoint = String("/check-schedule/?device_id=") + deviceID; return makeRequest(endpoint, "GET", "", scheduleResponse); }
  bool sendFeedingLogWithSchedule(int portionSize, const String& feedType, uint32_t scheduleId, const String& notes = "") { String payload = createScheduledFeedingPayload(portionSize, feedType, scheduleId, notes); String response; return makeRequest("/device/logs/", "POST", payload, response); }
  void setTimeout(unsigned long timeout) { requestTimeout = timeout; }
  void setMaxRetries(int retries) { maxRetries = retries; }
  bool isServerReachable() { String response; return makeRequest(String("/device/config/?device_id=") + deviceID, "GET", "", response); }
  String getLastError() { return lastError; }
  bool getFeedCommand(String& cmdResponse) { 
    String endpoint = String("/device/command/?device_id=") + deviceID; 
    if (makeRequest(endpoint, "GET", "", cmdResponse)) return true; 
    endpoint = String("/device/feed-command/?device_id=") + deviceID; 
    return makeRequest(endpoint, "GET", "", cmdResponse); 
  }
  bool sendAcknowledge(uint32_t commandId, const String& result = "ok") { 
    DynamicJsonDocument doc(256); 
    doc["command_id"] = commandId; 
    doc["device_id"] = deviceID; 
    doc["result"] = result; 
    String payload; 
    serializeJson(doc, payload); 
    String response; 
    if (makeRequest("/device/command/ack/", "POST", payload, response)) return true; 
    return makeRequest("/device/acknowledge/", "POST", payload, response); 
  }
  bool pairRegister(const String& pin, int ttl_seconds) {
    DynamicJsonDocument doc(256);
    doc["device_id"] = deviceID;
    doc["pin"] = pin;
    doc["ttl_seconds"] = ttl_seconds;
    String payload; serializeJson(doc, payload);
    String resp;
    bool ok = makeRequest("/device/pair/register/", "POST", payload, resp);
    if (!ok && lastError.indexOf("409") >= 0) {
      Serial.println("Device already paired on server (409) - skipping to claim poll");
      return true;
    }
    return ok;
  }
  bool pairClaimed(const String& pin, String& keyOut) {
    String endpoint = String("/device/pair/claimed/?device_id=") + deviceID + String("&pin=") + pin;
    String resp; if (!makeRequest(endpoint, "GET", "", resp)) return false;
    DynamicJsonDocument doc(256);
    if (deserializeJson(doc, resp)) return false;
    keyOut = String((const char*)doc["api_key"]);
    return keyOut.length() > 0;
  }
};

// Global objects
NetworkingManager network;
LedController ledController;
MotorController motorController;
OledDisplay oledDisplay;
HTTPClientManager httpClient;  // Added HTTP client for backend communication

// NTP Client for time synchronization
  WiFiUDP ntpUDP;
  NTPClient timeClient(ntpUDP, NTP_SERVER, NTP_TIMEZONE_OFFSET, NTP_UPDATE_INTERVAL);

// Timing variables for periodic tasks
unsigned long lastStatusUpdate = 0;
unsigned long lastSchedulePoll = 0;
unsigned long lastNTPUpdate = 0;
bool ntpSynced = false;
uint32_t lastExecutedScheduleId = 0;
int dailyFeeds = 0;
String lastFeedIso = "";
unsigned long lastFeedCompletionTime = 0;
unsigned long firmwareBootMs = 0;
unsigned long manualSuppressUntil = 0;
unsigned long networkBackoffUntil = 0;
bool manualLogPending = false;
int manualLogPortion = 0;
unsigned long networkBackoffMs = 60000;
const unsigned long MIN_NETWORK_BACKOFF_MS = 60000;
const unsigned long MAX_NETWORK_BACKOFF_MS = 300000;
unsigned long lastCommandPoll = 0;
unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL_MS = 30000;
float activeFeedPortionGrams = 0.0f;

// Error handling and retry logic
int consecutiveNetworkErrors = 0;
const int MAX_CONSECUTIVE_ERRORS = 5;
unsigned long lastConfigSync = 0;
const unsigned long STATUS_UPDATE_INTERVAL = 60000;  // Send status every 60 seconds
const unsigned long CONFIG_SYNC_INTERVAL = 300000;   // Sync config every 5 minutes


String g_deviceKey = "";
bool g_pairingActive = false;
String g_pairPin = "";
unsigned long g_pairExpireMs = 0;
unsigned long g_lastPairPoll = 0;
bool g_pairRegistered = false;

static inline bool hasDeviceAuth() {
  // Always accept provisioned device key (paired device)
  if (g_deviceKey.length() > 0) return true;
  // In DEV_MODE only: fall back to legacy API key so you can
  // test polling endpoints without completing the pairing flow
  #if DEV_ALLOW_LEGACY_FOR_POLL
    if (httpClient.hasApiKey()) {
      return true;
    }
  #endif
  // Production: no device key = not authorized
  return false;
}

String loadDeviceKey() {
  if (EEPROM.read(API_KEY_FLAG_ADDR) != 0xDA) return "";
  char buf[API_KEY_MAX_LEN + 1];
  for (int i = 0; i < API_KEY_MAX_LEN; i++) {
    buf[i] = (char)EEPROM.read(API_KEY_ADDR + i);
  }
  buf[API_KEY_MAX_LEN] = 0;
  String s = String(buf); s.trim(); return s;
}
void saveDeviceKey(const String& key) {
  int n = min((int)key.length(), API_KEY_MAX_LEN - 1);
  for (int i = 0; i < API_KEY_MAX_LEN; i++) {
    char c = (i < n) ? key[i] : 0;
    EEPROM.write(API_KEY_ADDR + i, c);
  }
  EEPROM.write(API_KEY_FLAG_ADDR, 0xDA);
  EEPROM.commit();
}
void clearDeviceKey() {
  for (int i = 0; i < API_KEY_MAX_LEN; i++) EEPROM.write(API_KEY_ADDR + i, 0);
  EEPROM.write(API_KEY_FLAG_ADDR, 0x00);
  EEPROM.commit();
}
String genPin6() {
  unsigned long r = ((unsigned long)ESP.getChipId() ^ micros()) ^ random(0xFFFFFF);
  int v = (int)(r % 1000000UL);
  char b[7]; snprintf(b, sizeof(b), "%06d", v);
  return String(b);
}

String eepromReadString(int baseAddr, int maxLen) {
  char buf[128];
  int n = maxLen;
  if (n > (int)sizeof(buf) - 1) n = sizeof(buf) - 1;
  for (int i = 0; i < n; i++) {
    buf[i] = (char)EEPROM.read(baseAddr + i);
  }
  buf[n] = 0;
  String s = String(buf);
  s.trim();
  return s;
}

void eepromWriteString(int baseAddr, int maxLen, const String& value) {
  int n = min((int)value.length(), maxLen - 1);
  for (int i = 0; i < maxLen; i++) {
    char c = (i < n) ? value[i] : 0;
    EEPROM.write(baseAddr + i, c);
  }
  EEPROM.commit();
}

bool loadWifiCredentials(String& ssidOut, String& passOut) {
  if (EEPROM.read(WIFI_FLAG_ADDR) != 0xA5) return false;
  String ssid = eepromReadString(WIFI_SSID_ADDR, WIFI_SSID_MAX_LEN);
  String pass = eepromReadString(WIFI_PASS_ADDR, WIFI_PASS_MAX_LEN);
  if (ssid.length() == 0) return false;
  ssidOut = ssid;
  passOut = pass;
  return true;
}

void saveWifiCredentials(const String& ssid, const String& pass) {
  eepromWriteString(WIFI_SSID_ADDR, WIFI_SSID_MAX_LEN, ssid);
  eepromWriteString(WIFI_PASS_ADDR, WIFI_PASS_MAX_LEN, pass);
  EEPROM.write(WIFI_FLAG_ADDR, 0xA5);
  EEPROM.commit();
}

void clearWifiCredentials() {
  for (int i = 0; i < WIFI_SSID_MAX_LEN; i++) EEPROM.write(WIFI_SSID_ADDR + i, 0);
  for (int i = 0; i < WIFI_PASS_MAX_LEN; i++) EEPROM.write(WIFI_PASS_ADDR + i, 0);
  EEPROM.write(WIFI_FLAG_ADDR, 0x00);
  EEPROM.commit();
}

void setup() {
  Serial.begin(115200);
  Serial.println("ESP8266 Pet Feeder Starting with Step D Features...");
  #if DEV_MODE
    Serial.println("*** DEV MODE ACTIVE ***");
    Serial.println("Server: " DEFAULT_SERVER_URL);
    Serial.println("Legacy auth: ENABLED");
    Serial.println("To switch to production: set DEV_MODE 0 and reflash");
  #else
    Serial.println("*** PRODUCTION MODE ***");
    Serial.println("Server: " DEFAULT_SERVER_URL);
    Serial.println("Auth: device key only");
  #endif

  // Initialize EEPROM for schedule tracking
  EEPROM.begin(EEPROM_SIZE);
  loadCalibration();
  if (g_msPerComp < 200 || g_msPerComp > 5000 || isnan(g_gramsPerComp) || g_gramsPerComp < 1.0f || g_gramsPerComp > 100.0f) {
    Serial.println("Auto-resetting calibration to defaults due to unreasonable values");
    saveCalibration(GRAMS_PER_COMP_DEFAULT, MS_PER_COMP_DEFAULT);
  }
  // Optional: direction test during development
  #define SERVO_DIRECTION_TEST 0
  
  // Load last executed schedule ID from EEPROM
  loadLastExecutedScheduleId();

  // Initialize LED controller first
  ledController.init();
  ledController.showError();  // Show red LED during initialization

  // Initialize motor controller with LED reference
  motorController.init(&ledController);
  oledDisplay.init();
  // Enforce minimum of exactly one compartment (runtime value)
  float effectiveMin = max(MANUAL_PORTION_MIN_GRAMS, g_gramsPerComp);
  manualPortionGrams = actualPortionGrams(manualPortionGrams);
  manualPortionGrams = constrain(manualPortionGrams, 
    effectiveMin, MANUAL_PORTION_MAX_GRAMS);
  manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
  Serial.println("Boot portion: " + String(manualPortionGrams, 1) + "g"
    + " (" + String(max(1,(int)((manualPortionGrams/g_gramsPerComp)+0.5f)))
    + " comp) " + String(manualFeedDurationMs) + "ms");
  #if SERVO_DIRECTION_TEST
    motorController.runAgitationCycle(); // Light motion test; replace with dedicated direction test if needed
  #endif

  // Initialize additional buttons
  pinMode(ADD_PORTION_PIN, INPUT_PULLUP);
  pinMode(REDUCE_PORTION_PIN, INPUT_PULLUP);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Initialize networking with LED reference
  network.init(&ledController);

  // Initialize HTTP client for Django backend communication
  {
    String devId = network.getDeviceID();
    if (!devId.startsWith("ESP-")) {
      devId = String("ESP-") + devId;
    }
    httpClient.init(DEFAULT_SERVER_URL, devId);
  }
  httpClient.setApiKey(DEFAULT_API_KEY);

  network.begin();

  // Wait up to 30 seconds for initial connection
  unsigned long connectStart = millis();
  while (!network.isConfigMode() && WiFi.status() != WL_CONNECTED &&
         millis() - connectStart < WIFI_TIMEOUT_MS) {
    network.update();
    delay(100);
  }

  if (network.isConnected()) {
    Serial.println("WiFi connected successfully");
    ledController.showReady();
    initializeNTP();
    lastSchedulePoll = millis() - SCHEDULE_POLL_INTERVAL;
    lastCommandPoll = millis() - COMMAND_POLL_INTERVAL;
    lastStatusUpdate = millis() - STATUS_UPDATE_INTERVAL;
#if FORCE_PAIR_ON_BOOT
    clearDeviceKey();
#endif
    g_deviceKey = loadDeviceKey();
    if (g_deviceKey.length() > 0) {
      httpClient.setDeviceKey(g_deviceKey);
      Serial.println("Loaded device key");
    } else {
      g_pairingActive = true;
      g_pairPin = genPin6();
      g_pairExpireMs = millis() + 300000UL;
      g_lastPairPoll = 0;
      g_pairRegistered = false;
      Serial.println("Pairing mode active");
    }
    String cfg;
    bool cfgOk = httpClient.getDeviceConfig(cfg);
    if (cfgOk) {
      Serial.println("Startup HTTP check OK");
    } else {
      Serial.println("Startup HTTP check failed: " + httpClient.getLastError());
      if (g_deviceKey.length() > 0 && httpClient.getLastError().indexOf("HTTP 403") >= 0) {
        Serial.println("Saved device key rejected by server - clearing key and entering pairing mode");
        clearDeviceKey();
        g_deviceKey = "";
        httpClient.setDeviceKey("");
        g_pairingActive = true;
        g_pairPin = genPin6();
        g_pairExpireMs = millis() + 300000UL;
        g_lastPairPoll = 0;
        g_pairRegistered = false;
        Serial.println("Pairing mode active");
      }
    }
  } else if (!network.isConfigMode()) {
    Serial.println("WiFi unavailable at boot - will retry in background");
    ledController.showError();
    consecutiveNetworkErrors = 0;
    lastReconnectAttempt = 0;
  } else {
    Serial.println("WiFi credentials not set - configuration AP active");
  }

  Serial.println("Setup complete - entering main loop");
  firmwareBootMs = millis();
}

void loop() {
  // Long-press FEED button (5s) to clear device key and force pairing mode
  {
    if (millis() < BUTTON_BOOT_IGNORE_MS) {
      // Ignore long-press logic during boot grace period to prevent accidental resets
      goto after_long_press_block;
    }
    static unsigned long holdStart = 0;
    static bool acted = false;
    bool down = (digitalRead(FEED_NOW_PIN) == LOW);
    if (down) {
      if (holdStart == 0) holdStart = millis();
      unsigned long held = millis() - holdStart;
      if (held > 1000 && held < 5000) {
        ledController.startFeedbackBlinkRed(1, 150);
      }
      if (held >= 5000 && !acted) {
        acted = true;
        Serial.println("=== BUTTON HOLD DETECTED - FORCING PAIRING MODE ===");
        if (network.isConnected() && g_deviceKey.length() > 0) {
          Serial.println("Attempting server-side unpair before local reset...");
          bool up = httpClient.deviceUnpairSelf();
          Serial.println(String("Unpair request result: ") + (up ? "OK" : "FAILED"));
          delay(150);
        }
        clearDeviceKey();
        g_deviceKey = "";
        httpClient.setDeviceKey("");
        clearWifiCredentials();
        network.clearCredentials();
        network.enterConfigMode();
        g_pairingActive = true;
        g_pairPin = genPin6();
        g_pairExpireMs = millis() + 300000UL;
        g_lastPairPoll = 0;
        g_pairRegistered = false;
        Serial.print("Pairing PIN: ");
        Serial.println(g_pairPin);
      }
    } else {
      holdStart = 0;
      acted = false;
    }
  }
after_long_press_block:
  if (g_pairingActive) {
    int secsLeft = (g_pairExpireMs > millis()) ? (int)((g_pairExpireMs - millis()) / 1000UL) : 0;
    {
      String devId = network.getDeviceID();
      if (!devId.startsWith("ESP-")) {
        devId = String("ESP-") + devId;
      }
      oledDisplay.updatePairing(g_pairPin, secsLeft, devId);
    }
    if (network.isConnected()) {
      if (!g_pairRegistered) {
        bool ok = httpClient.pairRegister(g_pairPin, 300);
        if (ok) {
          g_pairRegistered = true;
          g_lastPairPoll = 0;
          Serial.println("Pairing registered - waiting for app claim");
        } else {
          Serial.println("Pairing registration failed - backing off 10s before retry");
          delay(10000);
        }
      } else {
        if (millis() - g_lastPairPoll > 4000UL) {
          String k;
          bool claimed = httpClient.pairClaimed(g_pairPin, k);
          g_lastPairPoll = millis();
          if (claimed && k.length() > 0) {
            g_deviceKey = k;
            saveDeviceKey(k);
            String verify = loadDeviceKey();
            if (verify == k) {
              httpClient.setDeviceKey(g_deviceKey);
              g_pairingActive = false;
              ledController.showReady();
              Serial.println("Device key saved and verified — pairing complete");
              Serial.println("OLED switching to normal screen");
            } else {
              Serial.println("ERROR: EEPROM key write verification failed");
              Serial.println("Will retry saving on next claim poll");
            }
          }
        }
      }
      if (millis() >= g_pairExpireMs) {
        if (!g_pairRegistered) {
          Serial.println("Pairing timed out with no server registration - exiting pairing mode");
          g_pairingActive = false;
          g_deviceKey = loadDeviceKey();
          if (g_deviceKey.length() > 0) {
            httpClient.setDeviceKey(g_deviceKey);
            ledController.showReady();
            Serial.println("Found saved device key - resuming normal operation");
          } else {
            Serial.println("No key found - device needs re-pairing from the app");
            ledController.showError();
          }
          return;
        }
        g_pairPin = genPin6();
        g_pairExpireMs = millis() + 300000UL;
        g_pairRegistered = false;
      }
    }
    // Ensure captive portal and DNS keep responding while pairing is active
    network.update();
    delay(50);
    return;
  }
  handleCalibrationCommands();
  // Update all controllers
  handleManualFeeding();
  handlePortionAdjustButtons();
  network.update();
  if (network.isConnected() && !ntpSynced) {
    Serial.println("WiFi connected - performing initial NTP sync...");
    initializeNTP();
  }
  // Deferred post-connect initialization (if WiFi came up after boot)
  {
    static bool postConnectInitDone = false;
    if (network.isConnected() && !postConnectInitDone) {
      postConnectInitDone = true;
      if (!ntpSynced) {
        Serial.println("WiFi connected - performing deferred NTP sync");
        initializeNTP();
        lastSchedulePoll = millis() - SCHEDULE_POLL_INTERVAL;
        lastCommandPoll  = millis() - COMMAND_POLL_INTERVAL;
        lastStatusUpdate = millis() - STATUS_UPDATE_INTERVAL;
      }
      String freshKey = loadDeviceKey();
      if (freshKey.length() > 0 && g_deviceKey != freshKey) {
        g_deviceKey = freshKey;
        httpClient.setDeviceKey(g_deviceKey);
        Serial.println("Device key loaded from EEPROM");
        if (g_pairingActive) {
          g_pairingActive = false;
          ledController.showReady();
          Serial.println("Pairing cancelled - valid key found in EEPROM");
        }
      } else if (freshKey.length() == 0 && !g_pairingActive) {
        Serial.println("No device key — entering pairing mode");
        g_pairingActive = true;
        g_pairPin = genPin6();
        g_pairExpireMs = millis() + 300000UL;
        g_lastPairPoll = 0;
        g_pairRegistered = false;
      }
    }
    if (!network.isConnected()) {
      postConnectInitDone = false;
    }
  }
  if (network.isConfigured() && !network.isConnected() && !network.isConfigMode()) {
    ledController.showConnecting();
  }
  motorController.update();
  if (activeFeedPortionGrams > 0.0f && !motorController.isFeedingInProgress()) {
    activeFeedPortionGrams = 0.0f;
  }
feature/controller
  float displayPortion = activeFeedPortionGrams > 0.0f ? activeFeedPortionGrams : actualPortionGrams(manualPortionGrams);

  float displayPortion = activeFeedPortionGrams > 0.0f ? activeFeedPortionGrams : manualPortionGrams;
 main
  oledDisplay.update(network.isConnected(), network.getSSID(), displayPortion, motorController.isDispensePhaseActive());
  if (manualLogPending && !motorController.isFeedingInProgress()) {
    if (network.isConnected()) {
      bool success = httpClient.sendFeedingLog(manualLogPortion, "manual", "Button press feeding");
      if (!success) { Serial.println("Failed to log feeding to server: " + httpClient.getLastError()); }
    }
    manualLogPending = false;
  }
  ledController.update();
  bool allowNetworkWork = !motorController.isFeedingInProgress();
  #if DEBUG_BUTTONS
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 500) {
    int feed = digitalRead(FEED_NOW_PIN);
    int add = digitalRead(ADD_PORTION_PIN);
    int reduce = digitalRead(REDUCE_PORTION_PIN);
    Serial.print("BTN States: Feed=");
    Serial.print(feed == HIGH ? "HIGH" : "LOW");
    Serial.print(" Add=");
    Serial.print(add == HIGH ? "HIGH" : "LOW");
    Serial.print(" Reduce=");
    Serial.println(reduce == HIGH ? "HIGH" : "LOW");
    lastDebug = millis();
  }
  #endif

  if (allowNetworkWork) {
    updateNTPTime();
  }

  // Step D: Schedule polling and execution
  if (allowNetworkWork) {
    if (network.isConnected()) {
      // Connected — run normal operations and reset all error state
      pollAndExecuteSchedules();
      pollAndExecuteRemoteCommands();
      consecutiveNetworkErrors = 0;
      networkBackoffUntil = 0;
      lastReconnectAttempt = 0;
    } else if (!network.isConfigMode() && network.isConfigured()) {
      // Not connected, not in AP mode, credentials exist — retry on cooldown
      unsigned long now = millis();
      if (lastReconnectAttempt == 0 ||
          (now - lastReconnectAttempt) >= RECONNECT_INTERVAL_MS) {
        lastReconnectAttempt = now;
        Serial.println("Network unavailable - attempting reconnect...");
        Serial.print("Next retry in ");
        Serial.print(RECONNECT_INTERVAL_MS / 1000);
        Serial.println("s if this fails");
        network.reconnectNonBlocking();
      }
      // Do NOT increment consecutiveNetworkErrors here —
      // that counter is only for HTTP operation failures, not WiFi state
    }
  }

  // Periodic status updates (existing functionality)
  unsigned long currentTime = millis();
  if (currentTime - lastStatusUpdate > STATUS_UPDATE_INTERVAL) {
    if (allowNetworkWork && network.isConnected()) {
      sendDeviceStatus();
    }
    lastStatusUpdate = currentTime;
  }

  delay(1);
}

/**
 * Initialize NTP time synchronization
 */
void initializeNTP() {
  Serial.println("Initializing NTP time synchronization...");
  
  timeClient.begin();
  
  // Force initial time update
  int retries = 0;
  while (!timeClient.update() && retries < 10) {
    Serial.println("Attempting to sync with NTP server...");
    delay(1000);
    retries++;
  }
  
  if (retries < 10) {
    Serial.println("NTP time synchronized successfully");
    Serial.println("Current UTC time (NTP): " + timeClient.getFormattedTime());
    
    // Set system time for time() functions
    time_t epochTime = timeClient.getEpochTime();
    struct timeval tv = { epochTime, 0 };
    settimeofday(&tv, NULL);
    setenv("TZ", "PHT-8", 1);
    tzset();
    time_t nowLocal = time(nullptr);
    struct tm* lt = localtime(&nowLocal);
    char buf[9]; snprintf(buf, sizeof(buf), "%02d:%02d:%02d", lt->tm_hour, lt->tm_min, lt->tm_sec);
    Serial.println("Local time (PHT): " + String(buf));
    ntpSynced = true;
    
  } else {
    Serial.println("Failed to synchronize with NTP server");
  }
}

/**
 * Update NTP time periodically
 */
void updateNTPTime() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastNTPUpdate > NTP_UPDATE_INTERVAL) {
    if (network.isConnected()) {
      Serial.println("Updating NTP time...");
      
      if (timeClient.update()) {
        Serial.println("NTP time updated (UTC): " + timeClient.getFormattedTime());
        
        // Update system time
        time_t epochTime = timeClient.getEpochTime();
        struct timeval tv = { epochTime, 0 };
        settimeofday(&tv, NULL);
        setenv("TZ", "PHT-8", 1);
        tzset();
        time_t nowLocal = time(nullptr);
        struct tm* lt = localtime(&nowLocal);
        char buf[9]; snprintf(buf, sizeof(buf), "%02d:%02d:%02d", lt->tm_hour, lt->tm_min, lt->tm_sec);
        Serial.println("Local time (PHT): " + String(buf));
        
      } else {
        Serial.println("Failed to update NTP time");
      }
    }
    lastNTPUpdate = currentTime;
  }
}

/**
 * Poll for scheduled feedings and execute if due
 */
void pollAndExecuteSchedules() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastSchedulePoll > SCHEDULE_POLL_INTERVAL) {
    if (!hasDeviceAuth()) {
      Serial.println("Skipping schedule poll: device not paired yet (no device key)");
      lastSchedulePoll = currentTime;
      return;
    }
    if (millis() < networkBackoffUntil) {
      Serial.println("Network backoff active; skipping schedule poll");
      lastSchedulePoll = currentTime;
      return;
    }
    Serial.println("Polling for scheduled feedings...");
    
    String scheduleResponse;
    bool success = httpClient.getNextSchedule(scheduleResponse);
    
    if (success) {
      processScheduleResponse(scheduleResponse);
      networkBackoffMs = MIN_NETWORK_BACKOFF_MS;
      networkBackoffUntil = 0;
    } else {
      Serial.println("Failed to poll schedules: " + httpClient.getLastError());
      networkBackoffMs = min(networkBackoffMs * 2, MAX_NETWORK_BACKOFF_MS);
      networkBackoffUntil = millis() + networkBackoffMs;
      Serial.println("Entering network backoff for " + String(networkBackoffMs / 1000) + "s");
    }
    
    lastSchedulePoll = currentTime;
  }
}

/**
 * Process schedule response and execute feeding if due
 */
void processScheduleResponse(const String& response) {
  DynamicJsonDocument doc(1024);
  DeserializationError error = deserializeJson(doc, response);
  
  if (error) {
    Serial.println("Failed to parse schedule response: " + String(error.c_str()));
    return;
  }
  Serial.println("Raw schedule response: " + response);
  
  if (!doc["schedule"].isNull()) {
    JsonObject schedule = doc["schedule"];
    uint32_t scheduleId = schedule["schedule_id"];
    String scheduledTimeUTC = schedule["scheduled_time_utc"];
    float portionGrams = schedule["portion_g"];
    Serial.println("Found schedule ID: " + String(scheduleId));
    Serial.println("Scheduled time: " + scheduledTimeUTC);
    Serial.println("Portion: " + String(portionGrams) + "g");
    if (scheduleId == lastExecutedScheduleId) {
      Serial.println("Schedule already executed, skipping");
      return;
    }
    if (isScheduleDue(scheduledTimeUTC)) {
      executeScheduledFeeding(scheduleId, portionGrams);
    } else {
      Serial.println("Schedule not yet due for execution");
    }
    return;
  }

  if (doc["schedules"].is<JsonArray>()) {
    JsonArray arr = doc["schedules"].as<JsonArray>();
    time_t localEpoch = timeClient.getEpochTime();
    struct tm* lt = gmtime(&localEpoch);
    int curHour = lt->tm_hour;
    int curMin = lt->tm_min;
    static const char* NAMES[] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
    String dow = String(NAMES[lt->tm_wday]);
    for (JsonObject s : arr) {
      bool enabled = s["enabled"] | false;
      if (!enabled) continue;
      String schedTime = s["time"] | "";
      float portionGrams = s["portion_size"] | 0.0;
      uint32_t scheduleId = s["id"] | 0;
      bool dayMatch = false;
      if (s["days_of_week"].is<JsonArray>()) {
        for (JsonVariant v : s["days_of_week"].as<JsonArray>()) {
          if (String(v.as<const char*>()) == dow) { dayMatch = true; break; }
        }
      }
      if (!dayMatch) continue;
      int h = schedTime.length() >= 2 ? schedTime.substring(0,2).toInt() : -1;
      int m = schedTime.length() >= 5 ? schedTime.substring(3,5).toInt() : -1;
      if (h < 0 || m < 0) continue;
      if (h == curHour && abs(m - curMin) <= 1) {
        if (scheduleId == lastExecutedScheduleId) { return; }
        executeScheduledFeeding(scheduleId, portionGrams);
        return;
      }
    }
  }
 
  bool shouldFeed = doc["should_feed"] | false;
  if (!shouldFeed) {
    Serial.println("No pending schedules");
    return;
  }
 
  float portionGrams = doc["portion_size"] | 0.0;
  uint32_t scheduleId = doc["triggered_schedule_id"] | 0;
  String trig = doc["triggered_schedule_time"] | "";
  if (scheduleId == 0) {
    int hour = 0;
    int minute = 0;
    if (trig.length() >= 5) {
      hour = trig.substring(0, 2).toInt();
      minute = trig.substring(3, 5).toInt();
    }
    time_t nowTs = time(nullptr);
    struct tm* nowTm = gmtime(&nowTs);
    int yday = nowTm ? nowTm->tm_yday : 0;
    scheduleId = (uint32_t)(yday * 10000 + hour * 100 + minute);
  }
  if (scheduleId == lastExecutedScheduleId) {
    Serial.println("Schedule already executed, skipping");
    return;
  }
  executeScheduledFeeding(scheduleId, portionGrams);
}

/**
 * Check if a schedule is due for execution based on current time and grace period
 */
bool isScheduleDue(const String& scheduledTimeUTC) {
  // Parse ISO 8601 timestamp (simplified parsing)
  // Format: 2025-01-20T15:30:05Z
  
  time_t currentTime = time(nullptr);
  time_t scheduledTime = parseISOTimestamp(scheduledTimeUTC);
  
  if (scheduledTime == 0) {
    Serial.println("Failed to parse scheduled time, attempting offset-trim parse");
    String trimmed = scheduledTimeUTC;
    if (trimmed.length() >= 19) trimmed = trimmed.substring(0, 19) + "Z";
    scheduledTime = parseISOTimestamp(trimmed);
    if (scheduledTime == 0) {
      Serial.println("Schedule time parsing failed even after trimming");
      return false;
    }
  }
  
  // Check if current time is within grace period of scheduled time
  long timeDiff = currentTime - scheduledTime;
  
  
  Serial.println("Current time: " + String(currentTime));
  Serial.println("Scheduled time: " + String(scheduledTime));
  Serial.println("Time difference: " + String(timeDiff) + " seconds");
  
  // Execute if we're past the scheduled time but within grace period
  return (timeDiff >= 0 && timeDiff <= SCHEDULE_GRACE_PERIOD);
}

/**
 * Parse ISO 8601 timestamp to Unix timestamp
 * Simplified parser for format: YYYY-MM-DDTHH:MM:SSZ
 */
time_t parseISOTimestamp(const String& isoString) {
  struct tm tm;
  memset(&tm, 0, sizeof(tm));
  
  // Extract components using substring
  int year = isoString.substring(0, 4).toInt();
  int month = isoString.substring(5, 7).toInt();
  int day = isoString.substring(8, 10).toInt();
  int hour = isoString.substring(11, 13).toInt();
  int minute = isoString.substring(14, 16).toInt();
  int second = isoString.substring(17, 19).toInt();
  
  tm.tm_year = year - 1900;  // Years since 1900
  tm.tm_mon = month - 1;     // Months since January (0-11)
  tm.tm_mday = day;
  tm.tm_hour = hour;
  tm.tm_min = minute;
  tm.tm_sec = second;
  
  time_t t = mktime(&tm);
  // Handle timezone offsets like +08:00 or -05:00
  int tzSignPos = isoString.indexOf('+');
  if (tzSignPos < 0) tzSignPos = isoString.indexOf('-');
  if (tzSignPos > 19 && tzSignPos < (int)isoString.length()) {
    int sign = (isoString.charAt(tzSignPos) == '-') ? -1 : 1;
    int tzHour = isoString.substring(tzSignPos + 1, tzSignPos + 3).toInt();
    int tzMin = isoString.substring(tzSignPos + 4, tzSignPos + 6).toInt();
    long offsetSec = sign * (tzHour * 3600 + tzMin * 60);
    t -= offsetSec; // Convert to UTC
  }
  return t;
}

/**
 * Wheel-based duration calculation: whole compartments only
 */
unsigned long calculateFeedingDuration(float targetGrams) {
  if (targetGrams <= 0.0f) return 0;
  int comps = max(1, (int)((targetGrams / g_gramsPerComp) + 0.5f));
  // Spin time for N compartments + fixed settle so the last
  // compartment always clears the exit aperture before stopping.
  // POST_COMP_SETTLE_MS fixes inconsistent short-feed dispense.
  unsigned long duration = ((unsigned long)comps * g_msPerComp)
                           + POST_COMP_SETTLE_MS;
  duration = min(duration, MAX_DISPENSE_TIME_MS);
  return duration;
}

// Returns the true dispensed grams after snapping to nearest compartment.
// Always use this for display — never show raw manualPortionGrams directly.
float actualPortionGrams(float targetGrams) {
  if (targetGrams <= 0.0f) return 0.0f;
  int comps = max(1, (int)((targetGrams / g_gramsPerComp) + 0.5f));
  return (float)comps * g_gramsPerComp;
}

/**
 * Persist wheel calibration values to EEPROM
 */
void saveCalibration(float gramsPerComp, unsigned long msPerComp) {
  g_gramsPerComp = gramsPerComp;
  g_msPerComp    = msPerComp;
  EEPROM.put(MS_PER_GRAM_ADDR,   g_msPerComp);
  EEPROM.put(STARTUP_DELAY_ADDR, g_gramsPerComp);
  EEPROM.write(CALIB_FLAG_ADDR, 0xCC);
  EEPROM.commit();
  Serial.println("Calibration saved: grams/comp=" + String(g_gramsPerComp, 2) + "  ms/comp=" + String(g_msPerComp));
}

/**
 * Load wheel calibration values from EEPROM, with sane defaults if uninitialized
 */
void loadCalibration() {
  unsigned long ms;
  float gpc;
  byte flag = EEPROM.read(CALIB_FLAG_ADDR);
  EEPROM.get(MS_PER_GRAM_ADDR,   ms);
  EEPROM.get(STARTUP_DELAY_ADDR, gpc);
  if (flag != 0xCC || ms < 200 || ms > 5000 || isnan(gpc) || gpc < 1.0f || gpc > 100.0f) {
    g_msPerComp    = MS_PER_COMP_DEFAULT;
    g_gramsPerComp = GRAMS_PER_COMP_DEFAULT;
    saveCalibration(g_gramsPerComp, g_msPerComp);
    Serial.println("Calibration reset to defaults");
    return;
  }
  g_msPerComp    = ms;
  g_gramsPerComp = gpc;
  Serial.println("Calibration loaded: grams/comp=" + String(g_gramsPerComp, 2) + "  ms/comp=" + String(g_msPerComp));
}

/**
 * Handle interactive calibration commands over Serial
 * Commands:
 *  - CAL HELP
 *  - CAL STATUS
 *  - CAL START <grams>
 *  - CAL RESULT <grams>
 *  - CAL SET <ms_per_g>
 */
void handleCalibrationCommands() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      String line = calibInput; calibInput = "";
      line.trim();
      if (line.length() == 0) return;
      line.toUpperCase();
      if (line.startsWith("CAL HELP")) {
        Serial.println("=== WHEEL CAL COMMANDS ===");
        Serial.println("  CAL STATUS          - Show current calibration + portion table");
        Serial.println("  CAL FILL <g>        - Set grams per compartment");
        Serial.println("                        Measure: fill all 8, weigh total, divide by 8");
        Serial.println("  CAL COMP <ms>       - Set ms per compartment (one 45deg rotation)");
        Serial.println("  CAL START           - Spin 1 compartment for timing check");
        Serial.println("  CAL RESULT <g>      - Record actual grams from 1 compartment");
        Serial.println("  CAL SPEED <us>      - Set servo pulse width (1400..1700 µs)");
        Serial.println("  CAL RESET           - Reset all calibration to defaults");
        Serial.println("==========================");
        return;
      }
      if (line.startsWith("CAL STATUS")) {
        Serial.println("=== WHEEL CALIBRATION STATUS ===");
        Serial.println("  grams/comp = " + String(g_gramsPerComp, 2) + "g");
        Serial.println("  ms/comp    = " + String(g_msPerComp) + "ms");
        Serial.println("  feed pulse = " + String(g_feedPulse) + " µs");
        Serial.println("  Portion table:");
        for (int c = 1; c <= WHEEL_COMPARTMENTS; c++) {
          unsigned long spinMs = c * g_msPerComp;
          unsigned long totalMs = spinMs + POST_COMP_SETTLE_MS;
          Serial.println("  " + String(c) + " comp → " 
            + String((float)c * g_gramsPerComp, 1) + "g  " 
            + String(spinMs) + "ms + " 
            + String(POST_COMP_SETTLE_MS) + "ms settle = " 
            + String(totalMs) + "ms total");
        }
        Serial.println("================================");
        return;
      }
      if (line == "PORTION" || line == "PORTION STATUS") {
        Serial.println("\n=== MANUAL PORTION STATUS ===");
        Serial.print("Current portion: "); Serial.print(manualPortionGrams); Serial.println("g");
        Serial.print("Calculated duration: "); Serial.print(manualFeedDurationMs); Serial.println("ms");
        Serial.print("grams/comp: "); Serial.println(g_gramsPerComp, 2);
        Serial.print("ms/comp: "); Serial.println(g_msPerComp);
        Serial.print("Expected duration: "); Serial.print(calculateFeedingDuration(manualPortionGrams)); Serial.println("ms");
        if (manualFeedDurationMs != calculateFeedingDuration(manualPortionGrams)) {
          Serial.println("WARNING: Stored duration doesn't match calculation!");
        }
        Serial.println("===========================");
        return;
      }
      if (line.startsWith("AGITATE") || line.startsWith("UNCLOG")) {
        motorController.runAgitationCycle();
        return;
      }
      if (line.startsWith("TEST REVERSE")) {
        motorController.testReverseMotion(2000);
        return;
      }
      if (line.startsWith("TEST FORWARD")) {
        motorController.testForwardMotion(2000);
        return;
      }
      if (line.startsWith("CAL COMP")) {
        // Usage: CAL COMP 750   → sets ms per compartment
        String rest = line.substring(8); rest.trim();
        unsigned long ms = (unsigned long)rest.toInt();
        if (ms >= 200 && ms <= 5000) {
          saveCalibration(g_gramsPerComp, ms);
          Serial.println("ms/comp set to " + String(ms));
          manualPortionGrams = actualPortionGrams(manualPortionGrams);
          manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
          Serial.println("manualFeedDurationMs updated to " + String(manualFeedDurationMs) + "ms");
        } else {
          Serial.println("Invalid value — use 200..5000 ms");
        }
        return;
      }
      if (line.startsWith("CAL FILL")) {
        // Usage: CAL FILL 10.5  → sets grams per compartment
        String rest = line.substring(8); rest.trim();
        float gpc = rest.toFloat();
        if (gpc > 1.0f && gpc < 100.0f) {
          saveCalibration(gpc, g_msPerComp);
          Serial.println("grams/comp set to " + String(gpc, 2));
          manualPortionGrams = actualPortionGrams(manualPortionGrams);
          manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
          Serial.println("manualPortionGrams snapped to " + String(manualPortionGrams, 1) + "g");
          Serial.println("manualFeedDurationMs updated to " + String(manualFeedDurationMs) + "ms");
        } else {
          Serial.println("Invalid value — use 1..100 g");
        }
        return;
      }
      if (line.startsWith("CAL RESET")) {
        saveCalibration(GRAMS_PER_COMP_DEFAULT, MS_PER_COMP_DEFAULT);
        g_feedPulse = SERVO_FEED_SPEED;
        manualPortionGrams = actualPortionGrams(manualPortionGrams);
        manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
        Serial.println("Calibration reset to defaults");
        Serial.println("  grams/comp = " + String(GRAMS_PER_COMP_DEFAULT, 2));
        Serial.println("  ms/comp    = " + String(MS_PER_COMP_DEFAULT));
        Serial.println("  manualPortionGrams snapped to " + String(manualPortionGrams, 1) + "g");
        Serial.println("  manualFeedDurationMs = " + String(manualFeedDurationMs) + "ms");
        return;
      }
      if (line.startsWith("CAL SPEED")) {
        String rest = line.substring(10);  // Skip past "CAL SPEED "
        rest.trim();
        int pulse = rest.toInt();
        if (pulse >= 1400 && pulse <= 1700) {
          g_feedPulse = (unsigned int)pulse;
          Serial.println("Feed pulse updated: " + String(g_feedPulse) + " µs");
        } else {
          Serial.println("Invalid pulse; use 1400..1700 µs");
        }
        return;
      }
      if (line.startsWith("CAL START")) {
        Serial.println("Spinning 1 compartment for timing verification...");
        calibrationLastDuration = g_msPerComp;
        calibrationStartTime = millis();
        calibrationMode = true;
        if (!motorController.isFeedingInProgress())
          motorController.startCalibrationFeed(g_msPerComp);
        return;
      }
      if (line.startsWith("CAL RESULT")) {
        String rest = line.substring(10);
        rest.trim();
        float actual = rest.toFloat();
        if (actual > 0.0f) {
          saveCalibration(actual, g_msPerComp);
          Serial.println("grams/comp updated to " + String(actual, 2) + "g");
        } else {
          Serial.println("Invalid grams");
        }
        calibrationMode = false;
        return;
      }
      Serial.println("Unknown CAL command. Type CAL HELP.");
      return;
    } else {
      calibInput += c;
      if (calibInput.length() > 128) calibInput = calibInput.substring(0, 128);
    }
  }
}
/**
 * Execute scheduled feeding
 */
void executeScheduledFeeding(uint32_t scheduleId, float portionGrams) {
  Serial.println("Executing scheduled feeding - Schedule ID: " + String(scheduleId));
  Serial.println("Portion: " + String(portionGrams) + "g");
  
  // Calculate feeding duration based on portion size
  unsigned long feedingDuration = calculateFeedingDuration(portionGrams);
  Serial.println("Feeding duration: " + String(feedingDuration) + "ms");
  if (firmwareBootMs != 0 && (millis() - firmwareBootMs) < BUTTON_BOOT_IGNORE_MS) {
    Serial.println("Scheduled feed skipped: boot mute");
    return;
  }
  if (motorController.isFeedingInProgress()) {
    Serial.println("Scheduled feed rejected: busy");
    return;
  }
  if (lastFeedCompletionTime > 0 && (millis() - lastFeedCompletionTime) < COOLDOWN_PERIOD_MS) {
    Serial.println("Scheduled feed rejected: cooldown");
    return;
  }
  activeFeedPortionGrams = portionGrams;
  Serial.println("Scheduled feed: " + String(actualPortionGrams(portionGrams), 1)
    + "g (" + String(max(1,(int)((portionGrams / g_gramsPerComp) + 0.5f)))
    + " comp) " + String(feedingDuration) + "ms");
  motorController.startFeedingWithAntiClog(feedingDuration);
  ledController.showFeeding();  // Blue LED during feeding
  
  // Wait for feeding to complete
  while (motorController.isFeedingInProgress()) {
    motorController.update();
    ledController.update();
    oledDisplay.update(network.isConnected(), network.getSSID(), activeFeedPortionGrams, motorController.isDispensePhaseActive());
    delay(100);
  }
  
  // Send feeding log to backend
  bool logSuccess = httpClient.sendFeedingLogWithSchedule(
    (int)portionGrams, 
    "scheduled", 
    scheduleId, 
    "Automated scheduled feeding"
  );
  
  if (logSuccess) {
    Serial.println("Feeding log sent successfully");
    
    // Store executed schedule ID in EEPROM to prevent duplicates
    saveLastExecutedScheduleId(scheduleId);
    
    ledController.flashBlue(1000);  // Success indication
    
  } else {
    Serial.println("Failed to send feeding log: " + httpClient.getLastError());
    ledController.flashRed(1000);  // Error indication
    
    // TODO: Implement local retry queue in EEPROM for failed logs
  }
  
  ledController.showReady();  // Return to ready state
}

/**
 * Load last executed schedule ID from EEPROM
 */
void loadLastExecutedScheduleId() {
  EEPROM.get(LAST_SCHEDULE_ID_ADDR, lastExecutedScheduleId);
  
  // Check if EEPROM contains valid data (not 0xFFFFFFFF)
  if (lastExecutedScheduleId == 0xFFFFFFFF) {
    lastExecutedScheduleId = 0;
  }
  
  Serial.println("Loaded last executed schedule ID: " + String(lastExecutedScheduleId));
}

/**
 * Save last executed schedule ID to EEPROM
 */
void saveLastExecutedScheduleId(uint32_t scheduleId) {
  lastExecutedScheduleId = scheduleId;
  EEPROM.put(LAST_SCHEDULE_ID_ADDR, scheduleId);
  EEPROM.commit();
  
  Serial.println("Saved last executed schedule ID: " + String(scheduleId));
}

/**
 * Handle manual feeding button (existing functionality)
 */
void handleManualFeeding() {
  static unsigned long lastRecalc = 0;
  if (millis() - lastRecalc > 5000) {
    unsigned long calcDur = calculateFeedingDuration(manualPortionGrams);
    if (calcDur != manualFeedDurationMs) {
      Serial.print("WARNING: Duration mismatch! Stored=");
      Serial.print(manualFeedDurationMs);
      Serial.print("ms, Calculated=");
      Serial.print(calcDur);
      Serial.println("ms - Fixing...");
      manualFeedDurationMs = calcDur;
    }
    lastRecalc = millis();
  }
  static bool buttonPressed = false;
  static unsigned long lastButtonEvent = 0;
  static unsigned long pressStartTime = 0;
  static unsigned long lastIgnoreLog = 0;
  static bool ignoreLoggedOnce = false;
  static bool armed = true;
  static unsigned long sampleStartTime = 0;
  static int conflictSamples = 0;
  static int totalSamples = 0;
  if (manualSuppressUntil > 0) {
    if (millis() < manualSuppressUntil) return;
    manualSuppressUntil = 0;
  }
  bool currentButtonState = (digitalRead(FEED_NOW_PIN) == LOW);
  #if SIMPLE_BUTTON_MODE
  if (currentButtonState && !buttonPressed && (millis() - lastButtonEvent > BUTTON_DEBOUNCE_MS)) {
    buttonPressed = true;
    lastButtonEvent = millis();
    if (motorController.isFeedingInProgress()) { return; }
    if (lastFeedCompletionTime > 0) {
      unsigned long sinceLast = millis() - lastFeedCompletionTime;
      if (sinceLast < COOLDOWN_PERIOD_MS) {
        Serial.print("Feed rejected: cooldown (");
        Serial.print((COOLDOWN_PERIOD_MS - sinceLast) / 1000);
        Serial.println("s remaining)");
        ledController.startFeedbackBlinkRed(2, 100);
        return;
      }
    }
    // CRITICAL FIX: Portion wheel → single continuous feed only
    // Replaced reverse-clear/chunked logic with simple anti-clog feed
    activeFeedPortionGrams = manualPortionGrams;
    Serial.println("Manual feed: " + String(actualPortionGrams(manualPortionGrams), 1)
      + "g (" + String(max(1,(int)((manualPortionGrams / g_gramsPerComp) + 0.5f)))
      + " comp) " + String(manualFeedDurationMs) + "ms");
    motorController.startFeedingWithAntiClog(manualFeedDurationMs);
    manualLogPending = true;
    manualLogPortion = (int)actualPortionGrams(manualPortionGrams);
    dailyFeeds++;
    lastFeedIso = nowUtcIso();
    return;
  } else if (!currentButtonState && buttonPressed) {
    buttonPressed = false;
    return;
  }
  #endif
  if (currentButtonState && !buttonPressed && (millis() - lastButtonEvent > BUTTON_DEBOUNCE_MS)) {
    buttonPressed = true;
    lastButtonEvent = millis();
    pressStartTime = lastButtonEvent;
    ignoreLoggedOnce = false;
    if (!armed) { return; }
    sampleStartTime = millis();
    conflictSamples = 0;
    totalSamples = 0;
    if (motorController.isFeedingInProgress()) { Serial.println("Feed rejected: busy"); return; }
    if (lastFeedCompletionTime > 0) {
      unsigned long sinceLast = millis() - lastFeedCompletionTime;
      if (sinceLast < COOLDOWN_PERIOD_MS) {
        Serial.print("Feed rejected: cooldown (");
        Serial.print((COOLDOWN_PERIOD_MS - sinceLast) / 1000);
        Serial.println("s remaining)");
        ledController.startFeedbackBlinkRed(2, 100);
        manualSuppressUntil = millis() + (COOLDOWN_PERIOD_MS - sinceLast);
        return;
      }
    }
    return;
  } else if (!currentButtonState && buttonPressed) {
    buttonPressed = false;
    pressStartTime = 0;
    ignoreLoggedOnce = false;
    armed = true;
    conflictSamples = 0;
    totalSamples = 0;
  } else if (currentButtonState && buttonPressed) {
    totalSamples++;
    if ((digitalRead(ADD_PORTION_PIN) == LOW) || (digitalRead(REDUCE_PORTION_PIN) == LOW)) conflictSamples++;
    unsigned long elapsedConfirm = millis() - pressStartTime;
    if (elapsedConfirm >= FEED_CONFIRM_MS) {
      int pct = totalSamples > 0 ? (conflictSamples * 100) / totalSamples : 0;
      bool conflict = pct >= OTHER_CONFLICT_THRESHOLD_PCT;
      if (conflict && (elapsedConfirm < MANUAL_OVERRIDE_MS)) {
        if (!ignoreLoggedOnce && (millis() - lastIgnoreLog > 500)) { Serial.println("Manual ignored: other button active"); lastIgnoreLog = millis(); ignoreLoggedOnce = true; }
        return;
      }
      if (motorController.isFeedingInProgress()) { return; }
      if (lastFeedCompletionTime > 0) {
        unsigned long sinceLast = millis() - lastFeedCompletionTime;
        if (sinceLast < COOLDOWN_PERIOD_MS) {
          Serial.print("Feed rejected: cooldown (");
          Serial.print((COOLDOWN_PERIOD_MS - sinceLast) / 1000);
          Serial.println("s remaining)");
          ledController.startFeedbackBlinkRed(2, 100);
          manualSuppressUntil = millis() + (COOLDOWN_PERIOD_MS - sinceLast);
          return;
        }
      }
    // CRITICAL FIX: Portion wheel → single continuous feed only
    activeFeedPortionGrams = manualPortionGrams;
      Serial.println("Manual feed: " + String(actualPortionGrams(manualPortionGrams), 1)
        + "g (" + String(max(1,(int)((manualPortionGrams / g_gramsPerComp) + 0.5f)))
        + " comp) " + String(manualFeedDurationMs) + "ms");
      motorController.startFeedingWithAntiClog(manualFeedDurationMs);
    manualSuppressUntil = millis() + 800;
    armed = false;
    manualLogPending = true;
      manualLogPortion = (int)actualPortionGrams(manualPortionGrams);
    dailyFeeds++;
    lastFeedIso = nowUtcIso();
  }
}
}

void handlePortionAdjustButtons() {
  static bool addPressed = false;
  static bool reducePressed = false;
  static unsigned long lastAddPress = 0;
  static unsigned long lastReducePress = 0;

  bool addStatePressed = (digitalRead(ADD_PORTION_PIN) == LOW);
  bool reduceStatePressed = (digitalRead(REDUCE_PORTION_PIN) == LOW);

  if (addStatePressed && !addPressed && (millis() - lastAddPress > BUTTON_DEBOUNCE_MS)) {
    addPressed = true;
    lastAddPress = millis();
    manualSuppressUntil = millis() + 800;
    // Step up by exactly one compartment
    manualPortionGrams += g_gramsPerComp;
    if (manualPortionGrams > MANUAL_PORTION_MAX_GRAMS) manualPortionGrams = MANUAL_PORTION_MAX_GRAMS;
    // Snap to clean compartment multiple
    manualPortionGrams = actualPortionGrams(manualPortionGrams);
    manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
    Serial.println("\n╔═══════════════════════════╗");
    Serial.println("║   PORTION INCREASED      ║");
    Serial.println("╚═══════════════════════════╝");
    Serial.print("Portion target: "); Serial.print(manualPortionGrams, 1); Serial.println("g");
    Serial.print("Actual output:  "); Serial.print(actualPortionGrams(manualPortionGrams), 1); Serial.println("g");
    Serial.print("Compartments:   "); Serial.println(max(1,(int)((manualPortionGrams / g_gramsPerComp) + 0.5f)));
    Serial.print("Duration:       "); Serial.print(manualFeedDurationMs); Serial.println("ms");
    int compsInc = max(1, (int)((manualPortionGrams / g_gramsPerComp) + 0.5f));
    Serial.print("Wheel: "); Serial.print(compsInc); Serial.print(" comp → ");
    Serial.print((float)compsInc * g_gramsPerComp, 1); Serial.print("g  ");
    Serial.print(compsInc * (unsigned long)g_msPerComp); Serial.println("ms");
    Serial.println();
    ledController.startFeedbackBlinkBlue(3, 80);
  } else if (!addStatePressed && addPressed) {
    addPressed = false;
  }

  if (reduceStatePressed && !reducePressed && (millis() - lastReducePress > BUTTON_DEBOUNCE_MS)) {
    reducePressed = true;
    lastReducePress = millis();
    manualSuppressUntil = millis() + 800;
    float effectiveMin = max(MANUAL_PORTION_MIN_GRAMS, g_gramsPerComp);
    manualPortionGrams -= g_gramsPerComp;
    if (manualPortionGrams < effectiveMin) manualPortionGrams = effectiveMin;
    manualPortionGrams = actualPortionGrams(manualPortionGrams);
    manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
    Serial.println("\n╔═══════════════════════════╗");
    Serial.println("║   PORTION DECREASED      ║");
    Serial.println("╚═══════════════════════════╝");
    Serial.print("Portion target: "); Serial.print(manualPortionGrams, 1); Serial.println("g");
    Serial.print("Actual output:  "); Serial.print(actualPortionGrams(manualPortionGrams), 1); Serial.println("g");
    Serial.print("Compartments:   "); Serial.println(max(1,(int)((manualPortionGrams / g_gramsPerComp) + 0.5f)));
    Serial.print("Duration:       "); Serial.print(manualFeedDurationMs); Serial.println("ms");
    int compsDec = max(1, (int)((manualPortionGrams / g_gramsPerComp) + 0.5f));
    Serial.print("Wheel: "); Serial.print(compsDec); Serial.print(" comp → ");
    Serial.print((float)compsDec * g_gramsPerComp, 1); Serial.print("g  ");
    Serial.print(compsDec * (unsigned long)g_msPerComp); Serial.println("ms");
    Serial.println();
    ledController.startFeedbackBlinkRed(3, 80);
  } else if (!reduceStatePressed && reducePressed) {
    reducePressed = false;
  }
}

/**
 * Send device status to Django backend
 * Includes battery level, WiFi signal strength, and operational status
 */
void sendDeviceStatus() {
  int wifiSignal = WiFi.RSSI();
  int batteryLevel = 100;  // Placeholder - implement actual battery reading if available
  
  if (!hasDeviceAuth()) {
    Serial.println("Skipping status send: device not paired yet (no device key)");
    return;
  }
  bool success = httpClient.sendDeviceStatus("online", batteryLevel, wifiSignal);
  if (success) {
    Serial.println("Device status sent to server successfully");
  } else {
    Serial.println("Failed to send device status: " + httpClient.getLastError());
  }
}

/**
 * Sync device configuration with Django backend
 * Retrieves feeding schedules and device settings
 */
void syncDeviceConfiguration() {
  String configResponse;
  bool success = httpClient.getDeviceConfig(configResponse);
  
  if (success) {
    Serial.println("Configuration synced with server");
    Serial.println("Config: " + configResponse);
    
    // TODO: Parse configuration and update device settings
    // This would include feeding schedules, portion sizes, etc.
    
  } else {
    Serial.println("Failed to sync configuration: " + httpClient.getLastError());
  }
}

// Remote command polling and execution

void pollAndExecuteRemoteCommands() {
  unsigned long currentTime = millis();
  if (currentTime - lastCommandPoll > COMMAND_POLL_INTERVAL) {
    if (!hasDeviceAuth()) {
      // Avoid hammering auth-protected endpoints before pairing
      lastCommandPoll = currentTime;
      Serial.println("Skipping command poll: device not paired yet (no device key)");
      return;
    }
    if (millis() < networkBackoffUntil) {
      Serial.println("Network backoff active; skipping command poll");
      lastCommandPoll = currentTime;
      return;
    }
    String cmdResponse;
    bool ok = httpClient.getFeedCommand(cmdResponse);
    if (ok) {
      DynamicJsonDocument doc(512);
      DeserializationError err = deserializeJson(doc, cmdResponse);
      if (!err) {
        bool has = doc["has_command"];
        if (has) {
          String cmd = doc["command"] | "";
          uint32_t cmdId = doc["command_id"] | 0;
          float portion = doc["portion_size"] | 0.0;
          if (cmd == "feed" || cmd == "feed_now") {
            executeRemoteFeeding(cmdId, portion);
          } else if (cmd == "stop_feeding") {
            motorController.emergencyStop();
            httpClient.sendAcknowledge(cmdId, "ok");
          }
        }
      }
      networkBackoffMs = MIN_NETWORK_BACKOFF_MS;
      networkBackoffUntil = 0;
    } else {
      Serial.println("Failed to poll commands: " + httpClient.getLastError());
      networkBackoffMs = min(networkBackoffMs * 2, MAX_NETWORK_BACKOFF_MS);
      networkBackoffUntil = millis() + networkBackoffMs;
      Serial.println("Entering network backoff for " + String(networkBackoffMs / 1000) + "s");
    }
    lastCommandPoll = currentTime;
  }
}

void executeRemoteFeeding(uint32_t commandId, float portionGrams) {
  if (motorController.isFeedingInProgress()) { httpClient.sendAcknowledge(commandId, "busy"); return; }
  if (firmwareBootMs != 0 && (millis() - firmwareBootMs) < BUTTON_BOOT_IGNORE_MS) { httpClient.sendAcknowledge(commandId, "boot_mute"); return; }
  if (lastFeedCompletionTime > 0 && (millis() - lastFeedCompletionTime) < COOLDOWN_PERIOD_MS) { httpClient.sendAcknowledge(commandId, "cooldown"); return; }
  unsigned long feedingDuration = calculateFeedingDuration(portionGrams);
  activeFeedPortionGrams = portionGrams;
  Serial.println("Remote feed: " + String(actualPortionGrams(portionGrams), 1)
    + "g (" + String(max(1,(int)((portionGrams / g_gramsPerComp) + 0.5f)))
    + " comp) " + String(feedingDuration) + "ms");
  motorController.startFeedingWithAntiClog(feedingDuration);
  ledController.showFeeding();
  
  while (motorController.isFeedingInProgress()) {
    motorController.update();
    ledController.update();
    oledDisplay.update(network.isConnected(), network.getSSID(), activeFeedPortionGrams, motorController.isDispensePhaseActive());
    delay(100);
  }
  
  bool logOk = httpClient.sendFeedingLog((int)portionGrams, "remote_command", "Remote command feed");
  dailyFeeds++;
  lastFeedIso = nowUtcIso();
  
  httpClient.sendAcknowledge(commandId, logOk ? "ok" : "failed");
  ledController.showReady();
}

/**
 * Helper to format current UTC time in ISO 8601
 */
String nowUtcIso() {
  time_t now = time(nullptr);
  struct tm* utc_tm = gmtime(&now);
  char timestamp[32];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", utc_tm);
  return String(timestamp);
}
