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

// Inlined config.h (undo modularization)
// Hardware Pin Definitions - RGB LEDs
#define RED_LED_PIN 5
#define GREEN_LED_PIN 4
#define BLUE_LED_PIN 0

// Hardware Pin Definitions - Servo and Button
#define SERVO_PIN 14
#define BUTTON_PIN 12

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
#define SERVO_FORWARD 2000
#define SERVO_BACKWARD 1000

// Button and Feeding Constants
#define BUTTON_DEBOUNCE_MS 50
#define DEFAULT_FEED_DURATION 3000

// HTTP Communication Constants
#define DEFAULT_SERVER_URL "http://192.168.1.2:8000"
#define DEFAULT_DEVICE_ID "ESP8266_FEEDER_001"
#define DEFAULT_API_KEY "CHANGE_ME"
#define HTTP_TIMEOUT_MS 10000
#define HTTP_MAX_RETRIES 3

// NTP and Time Synchronization Constants
#define NTP_SERVER "pool.ntp.org"
#define NTP_TIMEZONE_OFFSET 0
#define NTP_UPDATE_INTERVAL 3600000

// Schedule Polling Constants
#define SCHEDULE_POLL_INTERVAL 45000
#define SCHEDULE_GRACE_PERIOD 120
#define MS_PER_GRAM 60

// EEPROM Addresses for Schedule Tracking
#define LAST_SCHEDULE_ID_ADDR 65
#define SCHEDULE_ID_SIZE 4

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
  void setGreenLED(bool state) { digitalWrite(GREEN_LED_PIN, state ? HIGH : LOW); }
  void setBlueLED(bool state) { digitalWrite(BLUE_LED_PIN, state ? HIGH : LOW); }
  void turnOffAllLEDs() { setRedLED(false); setGreenLED(false); setBlueLED(false); }

public:
  LedController() : currentState(LED_OFF), blinkState(false), lastBlinkTime(0) {}
  void init() { pinMode(RED_LED_PIN, OUTPUT); pinMode(GREEN_LED_PIN, OUTPUT); pinMode(BLUE_LED_PIN, OUTPUT); turnOffAllLEDs(); Serial.println("LED Controller initialized"); }
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
    if (currentState == LED_CONFIG_BLINK || currentState == LED_CONNECTING) {
      unsigned long blinkInterval = (currentState == LED_CONFIG_BLINK) ? LED_BLINK_FAST : LED_BLINK_SLOW;
      if (currentTime - lastBlinkTime >= blinkInterval) {
        blinkState = !blinkState; lastBlinkTime = currentTime;
        if (currentState == LED_CONFIG_BLINK) { turnOffAllLEDs(); setRedLED(blinkState); }
        else if (currentState == LED_CONNECTING) { turnOffAllLEDs(); setGreenLED(blinkState); }
      }
    }
  }
  void update() { update(millis()); }
  void showError() { turnOffAllLEDs(); setRedLED(true); }
  void showReady() { turnOffAllLEDs(); setGreenLED(true); }
  void showFeeding() { turnOffAllLEDs(); setBlueLED(true); }
  void showConfigMode() { setState(LED_CONFIG_BLINK); }
  void showConnecting() { setState(LED_CONNECTING); }
  void turnOff() { setState(LED_OFF); }
  bool isBlinking() { return (currentState == LED_CONFIG_BLINK || currentState == LED_CONNECTING); }
  void resetBlinkTimer() { lastBlinkTime = millis(); blinkState = false; }
  void flashGreen(unsigned long duration_ms) { setGreenLED(true); delay(duration_ms); setGreenLED(false); }
  void flashRed(unsigned long duration_ms) { setRedLED(true); delay(duration_ms); setRedLED(false); }
};

// Inlined motorcontrol.h/.cpp
class MotorController {
private:
  Servo feedingServo; bool servoAttached; bool lastButtonState; bool currentButtonState; unsigned long lastDebounceTime; unsigned long buttonPressTime; bool feedingInProgress; unsigned long feedingStartTime; unsigned long feedingDuration; LedController* ledController;
  void attachServo() { if (!servoAttached) { feedingServo.attach(SERVO_PIN); servoAttached = true; feedingServo.writeMicroseconds(SERVO_NEUTRAL); delay(100); Serial.println("Servo attached and set to neutral"); } }
  void detachServo() { if (servoAttached) { feedingServo.detach(); servoAttached = false; Serial.println("Servo detached"); } }
  void startServo() { if (servoAttached) { feedingServo.writeMicroseconds(SERVO_FORWARD); Serial.print("Servo started - Forward rotation ("); Serial.print(SERVO_FORWARD); Serial.println(" µs)"); } }
  void stopServo() { if (servoAttached) { feedingServo.writeMicroseconds(SERVO_NEUTRAL); Serial.print("Servo stopped - Neutral position ("); Serial.print(SERVO_NEUTRAL); Serial.println(" µs)"); } }
  bool readButtonState() { return digitalRead(BUTTON_PIN); }
public:
  MotorController() : servoAttached(false), lastButtonState(HIGH), currentButtonState(HIGH), lastDebounceTime(0), buttonPressTime(0), feedingInProgress(false), feedingStartTime(0), feedingDuration(0), ledController(nullptr) {}
  void init(LedController* ledCtrl) { ledController = ledCtrl; pinMode(BUTTON_PIN, INPUT_PULLUP); attachServo(); Serial.println("Motor Controller initialized"); Serial.print("Servo pin: "); Serial.println(SERVO_PIN); Serial.print("Button pin: "); Serial.println(BUTTON_PIN); }
  void startFeeding(unsigned long duration_ms) {
    if (feedingInProgress) { Serial.println("Feeding already in progress, ignoring request"); return; }
    Serial.print("Starting feeding for "); Serial.print(duration_ms); Serial.println(" ms");
    feedingInProgress = true; feedingStartTime = millis(); feedingDuration = duration_ms; if (ledController) ledController->showFeeding(); startServo();
  }
  void stopFeeding() { if (!feedingInProgress) return; Serial.println("Stopping feeding operation"); stopServo(); feedingInProgress = false; feedingStartTime = 0; feedingDuration = 0; if (ledController) ledController->showReady(); }
  bool isFeedingInProgress() { return feedingInProgress; }
  void updateButton() {
    bool reading = readButtonState(); if (reading != lastButtonState) lastDebounceTime = millis();
    if ((millis() - lastDebounceTime) > BUTTON_DEBOUNCE_MS) {
      if (reading != currentButtonState) { currentButtonState = reading; if (currentButtonState == LOW) { buttonPressTime = millis(); Serial.println("Manual feed button pressed"); if (!feedingInProgress) startFeeding(DEFAULT_FEED_DURATION); } }
    }
    lastButtonState = reading;
  }
  bool isButtonPressed() { return (currentButtonState == LOW); }
  void update() { updateButton(); if (feedingInProgress) { unsigned long elapsed = millis() - feedingStartTime; if (elapsed >= feedingDuration) { Serial.println("Feeding duration completed"); stopFeeding(); } } }
  void emergencyStop() { Serial.println("EMERGENCY STOP activated"); stopFeeding(); detachServo(); }
  unsigned long getRemainingFeedTime() { if (!feedingInProgress) return 0; unsigned long elapsed = millis() - feedingStartTime; if (elapsed >= feedingDuration) return 0; return feedingDuration - elapsed; }
};

// Inlined NetworkingModule.h/.cpp with wrappers for firmware method names
class NetworkingManager {
private:
  ESP8266WebServer webServer; DNSServer dnsServer; String wifiSSID; String wifiPassword; String deviceID; bool configurationMode; bool wifiConnected; unsigned long lastConnectionAttempt; unsigned long configModeStartTime; LedController* ledController;
  void generateDeviceID(); void setupConfigServer(); void handleConfigRoot(); void handleConfigSave(); String getConfigPage();
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
  void setupConfigServer() { webServer.on("/", [this]() { handleConfigRoot(); }); webServer.on("/save", HTTP_POST, [this]() { handleConfigSave(); }); webServer.onNotFound([this]() { handleConfigRoot(); }); webServer.begin(); }
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
    for (int attempt = 0; attempt < maxRetries; attempt++) {
      http.begin(wifiClient, fullURL); http.setTimeout(requestTimeout); http.addHeader("Content-Type", "application/json"); http.addHeader("User-Agent", "ESP8266-PetFeeder/1.0");
      if (apiKey.length() > 0) { http.addHeader("X-API-Key", apiKey); }
      int httpCode = -1; if (method == "POST") httpCode = http.POST(payload); else if (method == "GET") httpCode = http.GET();
      if (httpCode > 0) { response = http.getString(); http.end(); if (httpCode >= 200 && httpCode < 300) { lastError = ""; return true; } else { lastError = "HTTP " + String(httpCode) + ": " + response; } }
      else { lastError = "HTTP request failed: " + String(httpCode); }
      http.end(); if (attempt < maxRetries - 1) { Serial.println("Request failed, retrying in 2 seconds..."); delay(2000); }
    }
    return false;
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
  bool sendFeedingLog(int portionSize, const String& feedType, const String& notes = "") { String payload = createFeedingPayload(portionSize, feedType, notes); String response; Serial.println("Sending feeding log to server..."); Serial.println("Payload: " + payload); return makeRequest("/device/logs/", "POST", payload, response); }
  bool sendDeviceStatus(const String& /*status*/, int /*batteryLevel*/ = 100, int wifiSignal = -50) { DynamicJsonDocument doc(512); doc["device_id"] = deviceID; doc["wifi_rssi"] = wifiSignal; doc["uptime"] = (int)(millis()/1000); doc["daily_feeds"] = dailyFeeds; if (lastFeedIso.length() > 0) doc["last_feed"] = lastFeedIso; doc["error_message"] = ""; String payload; serializeJson(doc, payload); String response; bool success = makeRequest("/device/status/", "POST", payload, response); if (success) { Serial.println("Device status sent successfully"); return true; } else { Serial.println("Failed to send device status: " + lastError); return false; } }
  bool getDeviceConfig(String& configResponse) { String endpoint = String("/device/config/?device_id=") + deviceID; Serial.println("Requesting device configuration..."); bool success = makeRequest(endpoint, "GET", "", configResponse); if (success) { Serial.println("Device configuration retrieved successfully"); return true; } else { Serial.println("Failed to get device configuration: " + lastError); return false; } }
  bool getNextSchedule(String& scheduleResponse) { String endpoint = String("/check-schedule/"); return makeRequest(endpoint, "GET", "", scheduleResponse); }
  bool sendFeedingLogWithSchedule(int portionSize, const String& feedType, uint32_t scheduleId, const String& notes = "") { String payload = createScheduledFeedingPayload(portionSize, feedType, scheduleId, notes); String response; return makeRequest("/device/logs/", "POST", payload, response); }
  void setTimeout(unsigned long timeout) { requestTimeout = timeout; }
  void setMaxRetries(int retries) { maxRetries = retries; }
  bool isServerReachable() { String response; return makeRequest(String("/device/config/?device_id=") + deviceID, "GET", "", response); }
  String getLastError() { return lastError; }
  bool getFeedCommand(String& cmdResponse) { String endpoint = String("/device/feed-command/?device_id=") + deviceID; return makeRequest(endpoint, "GET", "", cmdResponse); }
  bool sendAcknowledge(uint32_t commandId, const String& result = "ok") { DynamicJsonDocument doc(256); doc["command_id"] = commandId; doc["device_id"] = deviceID; doc["result"] = result; String payload; serializeJson(doc, payload); String response; return makeRequest("/device/acknowledge/", "POST", payload, response); }
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
  
  // Load last executed schedule ID from EEPROM
  loadLastExecutedScheduleId();

  // Initialize LED controller first
  ledController.init();
  ledController.showError();  // Show red LED during initialization

  // Initialize motor controller with LED reference
  motorController.init(&ledController);

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
}

void loop() {
  // Update all controllers
  network.update();
  motorController.update();
  ledController.update();

  // Handle manual button feeding (existing functionality)
  handleManualFeeding();

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

  delay(100);  // Small delay to prevent watchdog issues
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
  
  // Check if schedule exists
  if (doc["schedule"].isNull()) {
    Serial.println("No pending schedules");
    return;
  }
  
  JsonObject schedule = doc["schedule"];
  uint32_t scheduleId = schedule["schedule_id"];
  String scheduledTimeUTC = schedule["scheduled_time_utc"];
  float portionGrams = schedule["portion_g"];
  
  Serial.println("Found schedule ID: " + String(scheduleId));
  Serial.println("Scheduled time: " + scheduledTimeUTC);
  Serial.println("Portion: " + String(portionGrams) + "g");
  
  // Check for duplicate execution
  if (scheduleId == lastExecutedScheduleId) {
    Serial.println("Schedule already executed, skipping");
    return;
  }
  
  // Parse scheduled time and check if it's due
  if (isScheduleDue(scheduledTimeUTC)) {
    executeScheduledFeeding(scheduleId, portionGrams);
  } else {
    Serial.println("Schedule not yet due for execution");
  }
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
    Serial.println("Failed to parse scheduled time");
    return false;
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
  
  return mktime(&tm);
}

/**
 * Execute scheduled feeding
 */
void executeScheduledFeeding(uint32_t scheduleId, float portionGrams) {
  Serial.println("Executing scheduled feeding - Schedule ID: " + String(scheduleId));
  Serial.println("Portion: " + String(portionGrams) + "g");
  
  // Calculate feeding duration based on portion size
  unsigned long feedingDuration = (unsigned long)(portionGrams * MS_PER_GRAM);
  
  // Ensure minimum and maximum feeding durations
  feedingDuration = max(feedingDuration, 1000UL);   // Minimum 1 second
  feedingDuration = min(feedingDuration, 10000UL);  // Maximum 10 seconds
  
  Serial.println("Feeding duration: " + String(feedingDuration) + "ms");
  
  // Start feeding process
  motorController.startFeeding(feedingDuration);
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
    
    ledController.flashGreen(1000);  // Success indication
    
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
  static bool buttonPressed = false;
  static unsigned long lastButtonPress = 0;
  
  bool currentButtonState = !digitalRead(BUTTON_PIN);
  
  if (currentButtonState && !buttonPressed && (millis() - lastButtonPress > BUTTON_DEBOUNCE_MS)) {
    buttonPressed = true;
    lastButtonPress = millis();
    
    Serial.println("Manual feeding button pressed");
    
    motorController.startFeeding(DEFAULT_FEED_DURATION);
    
    if (network.isConnected()) {
      float portionGrams = (float)DEFAULT_FEED_DURATION / (float)MS_PER_GRAM;
      bool success = httpClient.sendFeedingLog((int)portionGrams, "manual", "Button press feeding");
      if (!success) {
        Serial.println("Failed to log feeding to server: " + httpClient.getLastError());
      }
    }
    
    // Update counters for status heartbeat
    dailyFeeds++;
    lastFeedIso = nowUtcIso();
    
    ledController.flashGreen(500);
    
  } else if (!currentButtonState && buttonPressed) {
    buttonPressed = false;
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
          if (cmd == "feed") {
            executeRemoteFeeding(cmdId, portion);
          } else if (cmd == "stop_feeding") {
            motorController.emergencyStop();
            httpClient.sendAcknowledge(cmdId, "ok");
          }
        }
      }
    }
    lastCommandPoll = currentTime;
  }
}

void executeRemoteFeeding(uint32_t commandId, float portionGrams) {
  unsigned long feedingDuration = (unsigned long)(portionGrams * MS_PER_GRAM);
  feedingDuration = max(feedingDuration, 1000UL);
  feedingDuration = min(feedingDuration, 10000UL);
  
  motorController.startFeeding(feedingDuration);
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