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
#include <ESP8266WebServer.h>
#include <DNSServer.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Servo.h>

String nowUtcIso();
extern unsigned long lastFeedCompletionTime;

// Inlined config.h (undo modularization)
// Hardware Pin Definitions - RGB LEDs (D7/D0)
#define RED_LED_PIN 13
#define BLUE_LED_PIN 16

// Hardware Pin Definitions - Servo and Buttons
#define SERVO_PIN 14
#define FEED_NOW_PIN 5
#define ADD_PORTION_PIN 4
#define REDUCE_PORTION_PIN 12
#define BUTTON_PIN FEED_NOW_PIN

// Legacy LED pin for compatibility
#define LED_PIN 2

// Wi-Fi Configuration Settings
#define WIFI_TIMEOUT_MS 30000
#define CONFIG_TIMEOUT_MS 300000

// EEPROM Configuration
#define EEPROM_SIZE 512
#define CONFIG_FLAG_ADDR 0
#define WIFI_SSID_ADDR 1
#define WIFI_PASS_ADDR 33

// Wi-Fi Credential Limits
#define MAX_SSID_LENGTH 32
#define MAX_PASS_LENGTH 64

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
  #define SERVO_ANTI_CLOG_REVERSE 1440
#else
  #define SERVO_ANTI_CLOG_SPEED 1440
  #define SERVO_ANTI_CLOG_REVERSE 1560
#endif
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
#define DEFAULT_SERVER_URL "http://192.168.18.9:8000"
#define DEFAULT_DEVICE_ID "feeder-1"
#define DEFAULT_API_KEY "petio_secure_key_2025"
#define HTTP_TIMEOUT_MS 15000
#define HTTP_MAX_RETRIES 3

// NTP and Time Synchronization Constants
#define NTP_SERVER "pool.ntp.org"
#define NTP_TIMEZONE_OFFSET 0
#define NTP_UPDATE_INTERVAL 3600000

// Schedule Polling Constants
#define SCHEDULE_POLL_INTERVAL 45000
#define SCHEDULE_GRACE_PERIOD 120
#define MS_PER_GRAM 20

// Calibrated dispensing constants
#define STARTUP_DELAY_MS 100
#define MS_PER_GRAM_CALIBRATED 60.0f
#define MIN_DISPENSE_TIME_MS 500UL
#define MAX_DISPENSE_TIME_MS 30000UL

// EEPROM Addresses for Schedule Tracking
#define LAST_SCHEDULE_ID_ADDR 65
#define SCHEDULE_ID_SIZE 4

// EEPROM Addresses for Calibration
#define CALIB_FLAG_ADDR 68
#define MS_PER_GRAM_ADDR 69
#define STARTUP_DELAY_ADDR 73

// Calibrated duration API
unsigned long calculateFeedingDuration(float targetGrams);
void saveCalibration(float msPerGram, unsigned long startupDelay);
void loadCalibration();
void handleCalibrationCommands();

// Manual portion configuration
float manualPortionGrams = 25.0f;
unsigned long manualFeedDurationMs = 0;
const float PORTION_STEP_GRAMS = 5.0f;
const float MANUAL_PORTION_MIN_GRAMS = 5.0f;
const float MANUAL_PORTION_MAX_GRAMS = 100.0f;

// Calibration state
float g_msPerGram = MS_PER_GRAM_CALIBRATED;
unsigned long g_startupDelay = STARTUP_DELAY_MS;
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
  void init() { pinMode(RED_LED_PIN, OUTPUT); pinMode(BLUE_LED_PIN, OUTPUT); turnOffAllLEDs(); Serial.println("LED Controller initialized"); }
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

// Inlined motorcontrol.h/.cpp
class MotorController {
private:
  Servo feedingServo; bool servoAttached; bool feedingInProgress; unsigned long feedingStartTime; unsigned long feedingDuration; LedController* ledController; unsigned int lastPulse; unsigned int targetPulse; bool antiClogMode; bool clogDetected;
  void attachServo() { if (!servoAttached) { feedingServo.attach(SERVO_PIN); servoAttached = true; feedingServo.writeMicroseconds(SERVO_NEUTRAL); delay(100); Serial.println("Servo attached and set to neutral"); } }
  void detachServo() { if (servoAttached) { feedingServo.detach(); servoAttached = false; Serial.println("Servo detached"); } }
  void startServo() { if (servoAttached) { lastPulse = SERVO_RAMP_START; feedingServo.writeMicroseconds(lastPulse); Serial.print("Servo started - Forward rotation ("); Serial.print(lastPulse); Serial.println(" µs)"); } }
  void stopServo() { if (servoAttached) { feedingServo.writeMicroseconds(SERVO_NEUTRAL); lastPulse = SERVO_NEUTRAL; Serial.print("Servo stopped - Neutral position ("); Serial.print(SERVO_NEUTRAL); Serial.println(" µs)"); } }
public:
  MotorController() : servoAttached(false), feedingInProgress(false), feedingStartTime(0), feedingDuration(0), ledController(nullptr), lastPulse(SERVO_NEUTRAL), targetPulse(SERVO_FORWARD), antiClogMode(false), clogDetected(false) {}
  void init(LedController* ledCtrl) { ledController = ledCtrl; attachServo(); Serial.println("Motor Controller initialized"); Serial.print("Servo pin: "); Serial.println(SERVO_PIN); }
  void startFeeding(unsigned long duration_ms) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring request"); return; }
    Serial.print("Starting feeding for "); Serial.print(duration_ms); Serial.println(" ms");
    antiClogMode = false;
    feedingInProgress = true; feedingStartTime = millis(); feedingDuration = duration_ms; if (duration_ms < 2000UL) targetPulse = 1680; else targetPulse = SERVO_FORWARD; if (ledController) ledController->showFeeding(); startServo();
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
    lastPulse = targetPulse;
    Serial.print("Calibration feed pulse: "); Serial.println(targetPulse);
  }
  void stopFeeding() { if (!feedingInProgress) return; Serial.println("Stopping feeding operation"); stopServo(); feedingInProgress = false; feedingStartTime = 0; feedingDuration = 0; lastFeedCompletionTime = millis(); if (ledController) ledController->showReady(); }
  bool isFeedingInProgress() { return feedingInProgress; }
  void update() { 
    if (feedingInProgress) { 
      unsigned long now = millis(); 
      unsigned long elapsed = now - feedingStartTime; 
      unsigned long rampMs = antiClogMode ? SERVO_RAMP_FAST_MS : SERVO_RAMP_MS;
      if (elapsed < rampMs) { 
        unsigned int rampPulse = SERVO_RAMP_START + (unsigned int)((long)(targetPulse - SERVO_RAMP_START) * (long)elapsed / (long)rampMs); 
        if (rampPulse != lastPulse) { feedingServo.writeMicroseconds(rampPulse); lastPulse = rampPulse; } 
      } else if (lastPulse != targetPulse) { 
        feedingServo.writeMicroseconds(targetPulse); lastPulse = targetPulse; 
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
    lastPulse = targetPulse;
    Serial.print("Normal feed pulse: "); Serial.println(targetPulse);
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
};

// Inlined NetworkingModule.h/.cpp with wrappers for firmware method names
class NetworkingManager {
private:
  ESP8266WebServer webServer; DNSServer dnsServer; String wifiSSID; String wifiPassword; String deviceID; bool configurationMode; bool wifiConnected; unsigned long lastConnectionAttempt; unsigned long configModeStartTime; LedController* ledController;
public:
  NetworkingManager() : webServer(80), dnsServer(), wifiSSID(""), wifiPassword(""), deviceID(""), configurationMode(false), wifiConnected(false), lastConnectionAttempt(0), configModeStartTime(0), ledController(nullptr) {}
  void init(LedController* ledCtrl) { Serial.println("Initializing Wi-Fi Configuration Manager..."); ledController = ledCtrl; EEPROM.begin(EEPROM_SIZE); generateDeviceID(); WiFi.mode(WIFI_STA); Serial.print("Device ID: "); Serial.println(deviceID); Serial.println("Wi-Fi Configuration Manager initialized"); }
  void loadConfiguration() { Serial.println("Loading Wi-Fi configuration..."); byte configFlag = EEPROM.read(CONFIG_FLAG_ADDR); if (configFlag != 0xAA) { Serial.println("No saved configuration found"); return; } char ssidBuffer[MAX_SSID_LENGTH + 1]; for (int i = 0; i < MAX_SSID_LENGTH; i++) { ssidBuffer[i] = EEPROM.read(WIFI_SSID_ADDR + i); if (ssidBuffer[i] == 0) break; } ssidBuffer[MAX_SSID_LENGTH] = 0; wifiSSID = String(ssidBuffer); char passBuffer[MAX_PASS_LENGTH + 1]; for (int i = 0; i < MAX_PASS_LENGTH; i++) { passBuffer[i] = EEPROM.read(WIFI_PASS_ADDR + i); if (passBuffer[i] == 0) break; } passBuffer[MAX_PASS_LENGTH] = 0; wifiPassword = String(passBuffer); Serial.print("Loaded SSID: "); Serial.println(wifiSSID); }
  void saveConfiguration() { Serial.println("Saving Wi-Fi configuration..."); for (int i = 0; i < MAX_SSID_LENGTH; i++) { if (i < wifiSSID.length()) EEPROM.write(WIFI_SSID_ADDR + i, wifiSSID[i]); else EEPROM.write(WIFI_SSID_ADDR + i, 0); } for (int i = 0; i < MAX_PASS_LENGTH; i++) { if (i < wifiPassword.length()) EEPROM.write(WIFI_PASS_ADDR + i, wifiPassword[i]); else EEPROM.write(WIFI_PASS_ADDR + i, 0); } EEPROM.write(CONFIG_FLAG_ADDR, 0xAA); EEPROM.commit(); Serial.println("Configuration saved to EEPROM"); }
  bool isConfigured() { return (wifiSSID.length() > 0 && wifiPassword.length() > 0); }
  void connectToWiFi() { Serial.print("Connecting to Wi-Fi: "); Serial.println(wifiSSID); WiFi.mode(WIFI_STA); WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str()); lastConnectionAttempt = millis(); wifiConnected = false; }
  void handleWiFiConnection() { if (WiFi.status() == WL_CONNECTED && !wifiConnected) { wifiConnected = true; Serial.println("Wi-Fi connected successfully!"); Serial.print("IP address: "); Serial.println(WiFi.localIP()); if (ledController) ledController->showReady(); } else if (WiFi.status() != WL_CONNECTED && wifiConnected) { wifiConnected = false; Serial.println("Wi-Fi connection lost"); if (ledController) ledController->showConnecting(); }
    if (!wifiConnected && (millis() - lastConnectionAttempt > WIFI_TIMEOUT_MS)) { Serial.println("Wi-Fi connection timeout, starting configuration mode"); startConfigMode(); }
  }
  bool isConnected() { return wifiConnected; }
  void startConfigMode() { Serial.println("Starting Wi-Fi configuration mode..."); configurationMode = true; configModeStartTime = millis(); WiFi.disconnect(); String apName = String("ESP8266-Config-") + deviceID.substring(0, 6); WiFi.mode(WIFI_AP); WiFi.softAP(apName.c_str()); Serial.print("Configuration AP started: "); Serial.println(apName); Serial.print("AP IP address: "); Serial.println(WiFi.softAPIP()); setupConfigServer(); dnsServer.start(53, "*", WiFi.softAPIP()); Serial.println("Configuration portal ready"); if (ledController) ledController->showConfigMode(); }
  void handleConfigMode() { dnsServer.processNextRequest(); webServer.handleClient(); if (millis() - configModeStartTime > CONFIG_TIMEOUT_MS) { Serial.println("Configuration mode timeout, restarting..."); ESP.restart(); } }
  bool isConfigMode() { return configurationMode; }
  String getDeviceID() { return deviceID; }

  // Wrappers to match firmware.ino usage
  void startConfigurationMode() { startConfigMode(); }
  void handleConfigurationMode() { handleConfigMode(); }
  bool connect() { connectToWiFi(); unsigned long start = millis(); while (millis() - start < WIFI_TIMEOUT_MS) { handleWiFiConnection(); if (isConnected()) return true; delay(100); } return false; }
  void update() { if (isConfigMode()) handleConfigMode(); else handleWiFiConnection(); }

private:
  void setupConfigServer() { webServer.on("/", [this]() { handleConfigRoot(); }); webServer.on("/save", HTTP_POST, [this]() { handleConfigSave(); }); webServer.on("/ping", HTTP_GET, [this]() { webServer.send(200, "text/plain", "OK"); }); webServer.onNotFound([this]() { handleConfigRoot(); }); webServer.begin(); }
  void handleConfigRoot() { webServer.send(200, "text/html", getConfigPage()); }
  void handleConfigSave() { if (webServer.hasArg("ssid") && webServer.hasArg("password")) { wifiSSID = webServer.arg("ssid"); wifiPassword = webServer.arg("password"); Serial.print("Received SSID: "); Serial.println(wifiSSID); saveConfiguration(); webServer.send(200, "text/html", "Configuration saved! Device will restart..."); delay(2000); ESP.restart(); } else { webServer.send(400, "text/plain", "Missing parameters"); } }
  String getConfigPage() {
    String page = "<html><head><title>ESP8266 Config</title></head><body>";
    page += "<h1>ESP8266 Pet Feeder Configuration</h1>";
    page += "<form method=\"POST\" action=\"/save\">";
    page += "SSID: <input type=\"text\" name=\"ssid\"><br>";
    page += "Password: <input type=\"password\" name=\"password\"><br>";
    page += "<input type=\"submit\" value=\"Save\"></form>";
    page += "</body></html>";
    return page;
  }
  void generateDeviceID() {
    uint32_t chipId = ESP.getChipId();
    char id[16];
    sprintf(id, "%08X", chipId);
    deviceID = String(id);
  }
};

extern int dailyFeeds;
extern String lastFeedIso;

// Inlined httpclient.h/.cpp
class HTTPClientManager {
private:
  HTTPClient http; WiFiClient wifiClient; String serverURL; String deviceID; unsigned long requestTimeout; int maxRetries; String lastError; String apiKey;
  bool makeRequest(const String& endpoint, const String& method, const String& payload, String& response) {
    if (!WiFi.isConnected()) { lastError = "WiFi not connected"; return false; }
    String fullURL = serverURL + endpoint;
    Serial.println("HTTP request: " + fullURL);
    for (int attempt = 0; attempt < maxRetries; attempt++) {
      Serial.println("Attempt " + String(attempt + 1) + "/" + String(maxRetries));
      http.begin(wifiClient, fullURL); http.setTimeout(requestTimeout); http.addHeader("Content-Type", "application/json"); http.addHeader("User-Agent", "ESP8266-PetFeeder/1.0");
      if (apiKey.length() > 0) { http.addHeader("X-API-Key", apiKey); }
      int httpCode = -1; if (method == "POST") httpCode = http.POST(payload); else if (method == "GET") httpCode = http.GET();
      if (httpCode > 0) { response = http.getString(); http.end(); if (httpCode >= 200 && httpCode < 300) { lastError = ""; return true; } else { lastError = "HTTP " + String(httpCode) + ": " + response; } }
      else { lastError = "HTTP request failed: " + String(httpCode); }
      http.end(); if (attempt < maxRetries - 1) { Serial.println("Request failed, retrying in 2 seconds..."); delay(2000); }
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
    DynamicJsonDocument doc(512); doc["timestamp"] = nowUtcIso(); doc["portion_dispensed"] = portionSize; doc["source"] = feedType; String payload; serializeJson(doc, payload); return payload;
  }
  String createScheduledFeedingPayload(int portionSize, const String& feedType, uint32_t /*scheduleId*/, const String& /*notes*/ = "") {
    DynamicJsonDocument doc(256); doc["timestamp"] = nowUtcIso(); doc["portion_dispensed"] = portionSize; doc["source"] = "scheduled"; String payload; serializeJson(doc, payload); return payload;
  }
public:
  HTTPClientManager() : requestTimeout(HTTP_TIMEOUT_MS), maxRetries(HTTP_MAX_RETRIES), lastError("") {}
  void init(const String& serverUrl, const String& devID) { serverURL = serverUrl; deviceID = devID; if (!serverURL.endsWith("/api")) { if (!serverURL.endsWith("/")) serverURL += "/"; serverURL += "api"; } Serial.println("HTTP Client initialized:"); Serial.println("Server URL: " + serverURL); Serial.println("Device ID: " + deviceID); }
  void setApiKey(const String& key) { apiKey = key; }
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
};

// Global objects
NetworkingManager network;
LedController ledController;
MotorController motorController;
HTTPClientManager httpClient;  // Added HTTP client for backend communication

// NTP Client for time synchronization
  WiFiUDP ntpUDP;
  NTPClient timeClient(ntpUDP, NTP_SERVER, NTP_TIMEZONE_OFFSET, NTP_UPDATE_INTERVAL);

// Timing variables for periodic tasks
unsigned long lastStatusUpdate = 0;
unsigned long lastSchedulePoll = 0;
unsigned long lastNTPUpdate = 0;
uint32_t lastExecutedScheduleId = 0;
int dailyFeeds = 0;
String lastFeedIso = "";
unsigned long lastFeedCompletionTime = 0;
unsigned long firmwareBootMs = 0;
unsigned long manualSuppressUntil = 0;

// Error handling and retry logic
int consecutiveNetworkErrors = 0;
const int MAX_CONSECUTIVE_ERRORS = 5;
unsigned long lastConfigSync = 0;
const unsigned long STATUS_UPDATE_INTERVAL = 60000;  // Send status every 60 seconds
const unsigned long CONFIG_SYNC_INTERVAL = 300000;   // Sync config every 5 minutes


void setup() {
  Serial.begin(115200);
  Serial.println("ESP8266 Pet Feeder Starting with Step D Features...");

  // Initialize EEPROM for schedule tracking
  EEPROM.begin(EEPROM_SIZE);
  loadCalibration();
  if (isnan(g_msPerGram) || g_msPerGram < 10.0f || g_msPerGram > 200.0f || g_startupDelay > 1000) {
    Serial.println("Auto-resetting calibration to defaults due to unreasonable values");
    saveCalibration(MS_PER_GRAM_CALIBRATED, STARTUP_DELAY_MS);
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
  manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
  #if SERVO_DIRECTION_TEST
    motorController.runAgitationCycle(); // Light motion test; replace with dedicated direction test if needed
  #endif

  // Initialize additional buttons
  pinMode(ADD_PORTION_PIN, INPUT_PULLUP);
  pinMode(REDUCE_PORTION_PIN, INPUT_PULLUP);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Initialize networking with LED reference
  network.init(&ledController);
  network.loadConfiguration();

  // Initialize HTTP client for Django backend communication
  httpClient.init(DEFAULT_SERVER_URL, DEFAULT_DEVICE_ID);
  httpClient.setApiKey(DEFAULT_API_KEY);

  if (!network.isConfigured()) {
    Serial.println("No Wi-Fi credentials found, starting configuration mode");
    network.startConfigurationMode();
    
    while (!network.isConfigured()) {
      network.handleConfigurationMode();
      delay(100);
    }
  }

  // Connect to Wi-Fi
  Serial.println("Connecting to Wi-Fi...");
  ledController.showConnecting();
  
  if (network.connect()) {
    Serial.println("Wi-Fi connected successfully");
    ledController.showReady();
    
    // Initialize NTP time synchronization
    initializeNTP();
    
  } else {
    Serial.println("Failed to connect to Wi-Fi");
    ledController.showError();
  }

  Serial.println("Setup complete - entering main loop");
  firmwareBootMs = millis();
}

void loop() {
  handleCalibrationCommands();
  // Update all controllers
  handleManualFeeding();
  handlePortionAdjustButtons();
  network.update();
  motorController.update();
  ledController.update();
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

  // Manual handling already prioritized above

  // Step D: NTP time synchronization
  updateNTPTime();

  // Step D: Schedule polling and execution
  if (network.isConnected()) {
    pollAndExecuteSchedules();
    pollAndExecuteRemoteCommands();
    consecutiveNetworkErrors = 0;  // Reset error counter on successful connection
  } else {
    consecutiveNetworkErrors++;
    if (consecutiveNetworkErrors > MAX_CONSECUTIVE_ERRORS) {
      Serial.println("Too many consecutive network errors, attempting reconnection...");
      network.connect();
      consecutiveNetworkErrors = 0;
    }
  }

  // Periodic status updates (existing functionality)
  unsigned long currentTime = millis();
  if (currentTime - lastStatusUpdate > STATUS_UPDATE_INTERVAL) {
    if (network.isConnected()) {
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
    Serial.println("Current UTC time: " + timeClient.getFormattedTime());
    
    // Set system time for time() functions
    time_t epochTime = timeClient.getEpochTime();
    struct timeval tv = { epochTime, 0 };
    settimeofday(&tv, NULL);
    
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
        Serial.println("NTP time updated: " + timeClient.getFormattedTime());
        
        // Update system time
        time_t epochTime = timeClient.getEpochTime();
        struct timeval tv = { epochTime, 0 };
        settimeofday(&tv, NULL);
        
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
    Serial.println("Polling for scheduled feedings...");
    
    String scheduleResponse;
    bool success = httpClient.getNextSchedule(scheduleResponse);
    
    if (success) {
      processScheduleResponse(scheduleResponse);
    } else {
      Serial.println("Failed to poll schedules: " + httpClient.getLastError());
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
 * Calibrated duration calculation accounting for startup delay
 */
unsigned long calculateFeedingDuration(float targetGrams) {
  if (targetGrams < 0.0f) targetGrams = 0.0f;
  unsigned long duration = g_startupDelay + (unsigned long)(targetGrams * g_msPerGram);
  duration = max(duration, MIN_DISPENSE_TIME_MS);
  duration = min(duration, MAX_DISPENSE_TIME_MS);
  return duration;
}

/**
 * Persist calibration values (ms/gram and startup delay) to EEPROM
 */
void saveCalibration(float msPerGram, unsigned long startupDelay) {
  g_msPerGram = msPerGram;
  g_startupDelay = startupDelay;
  EEPROM.put(MS_PER_GRAM_ADDR, g_msPerGram);
  EEPROM.put(STARTUP_DELAY_ADDR, g_startupDelay);
  EEPROM.commit();
  Serial.println("Calibration saved: ms_per_g=" + String(g_msPerGram, 4) + " startup_delay_ms=" + String(g_startupDelay));
}

/**
 * Load calibration values from EEPROM, with sane defaults if uninitialized
 */
void loadCalibration() {
  float ms;
  unsigned long sd;
  byte flag = EEPROM.read(CALIB_FLAG_ADDR);
  EEPROM.get(MS_PER_GRAM_ADDR, ms);
  EEPROM.get(STARTUP_DELAY_ADDR, sd);
  if (flag != 0xCC) {
    g_msPerGram = MS_PER_GRAM_CALIBRATED;
    g_startupDelay = STARTUP_DELAY_MS;
    EEPROM.put(MS_PER_GRAM_ADDR, g_msPerGram);
    EEPROM.put(STARTUP_DELAY_ADDR, g_startupDelay);
    EEPROM.write(CALIB_FLAG_ADDR, 0xCC);
    EEPROM.commit();
    Serial.println("Calibration initialized with defaults and saved to EEPROM");
    return;
  }
  if (isnan(ms) || ms < 10.0f || ms > 200.0f || sd > 1000) {
    Serial.println("Calibration values unreasonable, resetting to defaults");
    saveCalibration(MS_PER_GRAM_CALIBRATED, STARTUP_DELAY_MS);
  } else {
    g_msPerGram = ms;
    g_startupDelay = sd;
    Serial.println("Calibration loaded: ms_per_g=" + String(g_msPerGram, 4) + " startup_delay_ms=" + String(g_startupDelay));
  }
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
        Serial.println("CAL Commands:");
        Serial.println("  CAL START <grams>   - Start calibration feed for given grams");
        Serial.println("  CAL RESULT <grams>  - Record actual grams; suggests ms_per_g");
        Serial.println("  CAL SET <ms_per_g>  - Set ms_per_g and save");
        Serial.println("  CAL STATUS          - Show calibration and sample durations");
        return;
      }
      if (line.startsWith("CAL STATUS")) {
        Serial.println("Calibration Status:");
        Serial.println("  ms_per_g=" + String(g_msPerGram, 4) + " startup_delay_ms=" + String(g_startupDelay));
        Serial.println("  feed_pulse_us=" + String(g_feedPulse));
        for (int g = 5; g <= 500; g += 5) {
          unsigned long d = calculateFeedingDuration((float)g);
          Serial.println("  " + String(g) + "g -> " + String(d) + " ms");
        }
        return;
      }
      if (line == "PORTION" || line == "PORTION STATUS") {
        Serial.println("\n=== MANUAL PORTION STATUS ===");
        Serial.print("Current portion: "); Serial.print(manualPortionGrams); Serial.println("g");
        Serial.print("Calculated duration: "); Serial.print(manualFeedDurationMs); Serial.println("ms");
        Serial.print("Startup delay: "); Serial.print(g_startupDelay); Serial.println("ms");
        Serial.print("MS per gram: "); Serial.println(g_msPerGram);
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
  if (line.startsWith("CAL SET")) {
    String rest = line.substring(8);  // Skip past "CAL SET "
    rest.trim();
    float val = rest.toFloat();
    if (val > 0.0f && val < 500.0f) {
      saveCalibration(val, g_startupDelay);
    } else {
      Serial.println("Invalid ms_per_g");
    }
    return;
  }
  if (line.startsWith("CAL RESET")) {
    saveCalibration(MS_PER_GRAM_CALIBRATED, STARTUP_DELAY_MS);
    g_feedPulse = SERVO_FEED_SPEED;
    Serial.println("Calibration reset to defaults and feed pulse set to " + String(g_feedPulse) + " µs");
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
        String rest = line.substring(10);  // Skip past "CAL START "
        rest.trim();
        calibrationTestGrams = rest.toFloat();
        calibrationLastDuration = calculateFeedingDuration(calibrationTestGrams);
        calibrationStartTime = millis();
        calibrationMode = true;
        Serial.println("Calibration START: grams=" + String(calibrationTestGrams) + " duration=" + String(calibrationLastDuration) + " ms");
        if (!motorController.isFeedingInProgress()) motorController.startCalibrationFeed(calibrationLastDuration);
        return;
      }
      if (line.startsWith("CAL RESULT")) {
        int idx = line.indexOf(' ');
        if (idx > 0) {
          String rest = line.substring(idx + 1); rest.trim();
          float actual = rest.toFloat();
          if (actual > 0.0f) {
            float suggested = (float)(calibrationLastDuration > g_startupDelay ? (calibrationLastDuration - g_startupDelay) : 0UL) / actual;
            float errorPct = calibrationTestGrams > 0.0f ? ((actual - calibrationTestGrams) / calibrationTestGrams) * 100.0f : 0.0f;
            Serial.println("Calibration RESULT: actual=" + String(actual, 3) + "g error=" + String(errorPct, 2) + "%");
            Serial.println("Suggested ms_per_g=" + String(suggested, 4) + " (use CAL SET <value> to apply)");
          } else {
            Serial.println("Invalid actual grams");
          }
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
  motorController.startFeedingWithAntiClog(feedingDuration);
  ledController.showFeeding();  // Blue LED during feeding
  
  // Wait for feeding to complete
  while (motorController.isFeedingInProgress()) {
    motorController.update();
    ledController.update();
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
    motorController.startFeedingWithAntiClog(manualFeedDurationMs);
    if (network.isConnected()) {
      bool success = httpClient.sendFeedingLog((int)manualPortionGrams, "manual", "Button press feeding");
      if (!success) { Serial.println("Failed to log feeding to server: " + httpClient.getLastError()); }
    }
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
    motorController.startFeedingWithAntiClog(manualFeedDurationMs);
    manualSuppressUntil = millis() + 800;
    armed = false;
    if (network.isConnected()) {
      bool success = httpClient.sendFeedingLog((int)manualPortionGrams, "manual", "Button press feeding");
      if (!success) { Serial.println("Failed to log feeding to server: " + httpClient.getLastError()); }
    }
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
    manualSuppressUntil = millis() + 800; // 800ms suppression to prevent conflict detection with Feed button
    manualPortionGrams += PORTION_STEP_GRAMS;
    if (manualPortionGrams > MANUAL_PORTION_MAX_GRAMS) manualPortionGrams = MANUAL_PORTION_MAX_GRAMS;
    manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
    Serial.println("\n╔═══════════════════════════╗");
    Serial.println("║   PORTION INCREASED      ║");
    Serial.println("╚═══════════════════════════╝");
    Serial.print("Portion: "); Serial.print(manualPortionGrams); Serial.println("g");
    Serial.print("Duration: "); Serial.print(manualFeedDurationMs); Serial.println("ms");
    Serial.print("Formula: "); Serial.print(g_startupDelay); Serial.print("ms + (");
    Serial.print(manualPortionGrams); Serial.print("g × "); Serial.print(g_msPerGram); Serial.println("ms/g)");
    Serial.println();
    ledController.startFeedbackBlinkBlue(3, 80);
  } else if (!addStatePressed && addPressed) {
    addPressed = false;
  }

  if (reduceStatePressed && !reducePressed && (millis() - lastReducePress > BUTTON_DEBOUNCE_MS)) {
    reducePressed = true;
    lastReducePress = millis();
    manualSuppressUntil = millis() + 800; // 800ms suppression to prevent conflict detection with Feed button
    manualPortionGrams -= PORTION_STEP_GRAMS;
    if (manualPortionGrams < MANUAL_PORTION_MIN_GRAMS) manualPortionGrams = MANUAL_PORTION_MIN_GRAMS;
    manualFeedDurationMs = calculateFeedingDuration(manualPortionGrams);
    Serial.println("\n╔═══════════════════════════╗");
    Serial.println("║   PORTION DECREASED      ║");
    Serial.println("╚═══════════════════════════╝");
    Serial.print("Portion: "); Serial.print(manualPortionGrams); Serial.println("g");
    Serial.print("Duration: "); Serial.print(manualFeedDurationMs); Serial.println("ms");
    Serial.print("Formula: "); Serial.print(g_startupDelay); Serial.print("ms + (");
    Serial.print(manualPortionGrams); Serial.print("g × "); Serial.print(g_msPerGram); Serial.println("ms/g)");
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
#define COMMAND_POLL_INTERVAL 10000
unsigned long lastCommandPoll = 0;

void pollAndExecuteRemoteCommands() {
  unsigned long currentTime = millis();
  if (currentTime - lastCommandPoll > COMMAND_POLL_INTERVAL) {
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
    } else {
      Serial.println("Failed to poll commands: " + httpClient.getLastError());
    }
    lastCommandPoll = currentTime;
  }
}

void executeRemoteFeeding(uint32_t commandId, float portionGrams) {
  if (motorController.isFeedingInProgress()) { httpClient.sendAcknowledge(commandId, "busy"); return; }
  if (firmwareBootMs != 0 && (millis() - firmwareBootMs) < BUTTON_BOOT_IGNORE_MS) { httpClient.sendAcknowledge(commandId, "boot_mute"); return; }
  if (lastFeedCompletionTime > 0 && (millis() - lastFeedCompletionTime) < COOLDOWN_PERIOD_MS) { httpClient.sendAcknowledge(commandId, "cooldown"); return; }
  unsigned long feedingDuration = calculateFeedingDuration(portionGrams);
  // Ensure minimum duration for anti-clog effectiveness
  motorController.startFeedingWithAntiClog(feedingDuration);
  ledController.showFeeding();
  
  while (motorController.isFeedingInProgress()) {
    motorController.update();
    ledController.update();
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
