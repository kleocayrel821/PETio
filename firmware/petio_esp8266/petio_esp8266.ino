// // PETio ESP8266 Unified Firmware (Provisioning + Main)
// // - SoftAP provisioning portal (LittleFS + EEPROM)
// // - Wi-Fi connect and backend communication (HTTP)
// // - LED feedback, button handling, servo feed, offline log buffer

// #include <ESP8266WiFi.h>
// #include <ESP8266HTTPClient.h>
// #include <ESP8266WebServer.h>
// #include <WiFiClient.h>
// #include <ArduinoJson.h>
// #include <EEPROM.h>
// #include <LittleFS.h>
// #include <Servo.h>

// // Pins (NodeMCU mapping)
// const int PIN_LED_RED   = 5;   // D1
// const int PIN_LED_GREEN = 4;   // D2
// const int PIN_LED_BLUE  = 0;   // D3 (GPIO0: only use as LED output; avoid driving LOW at boot)
// const int PIN_SERVO     = 14;  // D5
// const int PIN_BUTTON    = 12;  // D6 (pull-up)

// // SoftAP provisioning credentials
// const char* AP_SSID = "PETio_Config";
// const char* AP_PASS = "petio123";

// // Device/server config
// const char* DEVICE_ID = "petio-esp8266-01"; // change per device
// String BASE_URL = "http://192.168.1.2:8000"; // update to your server IP
// const char* API_KEY = "CHANGE_ME"; // must match Django PETIO_DEVICE_API_KEY

// // EEPROM layout (aligns with provisioning sketch)
// // Byte 0: flag (0x42 means credentials present)
// // Bytes 1-32: SSID (null-terminated)
// // Bytes 33-96: Password (null-terminated)
// const int EEPROM_SIZE = 128;

// // State
// ESP8266WebServer portalServer(80);
// Servo feederServo;
// bool provisioningMode = false;
// bool wifiConnected = false;
// int wifiRSSI = -100;
// unsigned long uptimeSeconds = 0;
// unsigned long lastPoll = 0;
// unsigned long lastLoopMillis = 0;
// unsigned long pollIntervalMs = 30000; // default 30s; server can override

// // Simple local log buffer for sync
// struct LogItem { unsigned long ts; float portion; char source[16]; };
// const int LOG_BUF_MAX = 20;
// LogItem logBuf[LOG_BUF_MAX];
// int logBufCount = 0;

// // LED control
// enum LedColor { RED, GREEN, BLUE, WHITE, OFF };
// void setLEDStatus(LedColor color) {
//   int r=0,g=0,b=0;
//   switch(color){
//     case RED:   r=1; g=0; b=0; break;
//     case GREEN: r=0; g=1; b=0; break;
//     case BLUE:  r=0; g=0; b=1; break;
//     case WHITE: r=1; g=1; b=1; break;
//     case OFF:   r=0; g=0; b=0; break;
//   }
//   digitalWrite(PIN_LED_RED, r);
//   digitalWrite(PIN_LED_GREEN, g);
//   digitalWrite(PIN_LED_BLUE, b);
// }

// // ===== Credential storage helpers =====
// bool saveToLittleFS(const String& ssid, const String& password) {
//   if (!LittleFS.begin()) return false;
//   File f = LittleFS.open("/wifi.json", "w");
//   if (!f) return false;
//   StaticJsonDocument<256> doc;
//   doc["ssid"] = ssid;
//   doc["password"] = password;
//   bool ok = serializeJson(doc, f) > 0;
//   f.close();
//   return ok;
// }

// bool readCredsFromFS(String& ssid, String& pass) {
//   if (!LittleFS.begin()) return false;
//   if (!LittleFS.exists("/wifi.json")) return false;
//   File f = LittleFS.open("/wifi.json", "r");
//   if (!f) return false;
//   StaticJsonDocument<256> doc;
//   DeserializationError err = deserializeJson(doc, f);
//   f.close();
//   if (err) return false;
//   ssid = doc["ssid"].as<String>();
//   pass = doc["password"].as<String>();
//   return ssid.length() > 0;
// }

// void writeEEPROMCreds(const String& ssid, const String& password) {
//   EEPROM.begin(EEPROM_SIZE);
//   EEPROM.write(0, 0x42);
//   for (int i = 0; i < 32; i++) {
//     char c = (i < ssid.length()) ? ssid[i] : '\0';
//     EEPROM.write(1 + i, (uint8_t)c);
//   }
//   for (int i = 0; i < 64; i++) {
//     char c = (i < password.length()) ? password[i] : '\0';
//     EEPROM.write(33 + i, (uint8_t)c);
//   }
//   EEPROM.commit();
//   EEPROM.end();
// }

// bool readCredsFromEEPROM(String& ssid, String& pass) {
//   EEPROM.begin(EEPROM_SIZE);
//   uint8_t flag = EEPROM.read(0);
//   if (flag != 0x42) { EEPROM.end(); return false; }
//   char ssidBuf[33]; char passBuf[65];
//   for (int i=0;i<32;i++) ssidBuf[i] = (char)EEPROM.read(1+i);
//   ssidBuf[32] = '\0';
//   for (int i=0;i<64;i++) passBuf[i] = (char)EEPROM.read(33+i);
//   passBuf[64] = '\0';
//   EEPROM.end();
//   ssid = String(ssidBuf);
//   pass = String(passBuf);
//   return ssid.length() > 0;
// }

// bool loadWiFiCredentials(String& ssid, String& pass) {
//   if (readCredsFromFS(ssid, pass)) return true;
//   if (readCredsFromEEPROM(ssid, pass)) return true;
//   return false;
// }

// // ===== Provisioning portal =====
// String indexPage() {
//   String html = "<html><head><title>PETio Config</title></head><body>";
//   html += "<h2>PETio Wi-Fi Provisioning</h2>";
//   html += "<form action=\"/save\" method=\"post\">";
//   html += "<label>WiFi SSID:</label><input name=\"ssid\"><br>";
//   html += "<label>Password:</label><input name=\"password\" type=\"password\"><br>";
//   html += "<input type=\"submit\" value=\"Save\">";
//   html += "</form>";
//   html += "</body></html>";
//   return html;
// }

// void handleRoot() { portalServer.send(200, "text/html", indexPage()); }

// void handleSave() {
//   String ssid = portalServer.hasArg("ssid") ? portalServer.arg("ssid") : "";
//   String password = portalServer.hasArg("password") ? portalServer.arg("password") : "";
//   if (ssid.length() == 0) { portalServer.send(400, "text/plain", "Missing SSID"); return; }
//   bool fsOk = saveToLittleFS(ssid, password);
//   writeEEPROMCreds(ssid, password);
//   if (fsOk) {
//     portalServer.send(200, "text/plain", "Credentials saved, rebooting...");
//   } else {
//     portalServer.send(500, "text/plain", "Failed to save to LittleFS, but EEPROM updated. Rebooting...");
//   }
//   setLEDStatus(GREEN);
//   delay(1500);
//   ESP.restart();
// }

// void startProvisioningPortal() {
//   setLEDStatus(RED);
//   WiFi.mode(WIFI_AP);
//   WiFi.softAP(AP_SSID, AP_PASS);
//   IPAddress ip = WiFi.softAPIP();
//   Serial.print("[Provisioning] AP started: "); Serial.println(ip);
//   portalServer.on("/", HTTP_GET, handleRoot);
//   portalServer.on("/save", HTTP_POST, handleSave);
//   portalServer.begin();
//   setLEDStatus(BLUE);
// }

// bool checkProvisioningTrigger() {
//   pinMode(PIN_BUTTON, INPUT_PULLUP);
//   bool buttonHeldAtBoot = (digitalRead(PIN_BUTTON) == LOW); // hold to force provisioning
//   String ssid, pass;
//   bool haveCreds = loadWiFiCredentials(ssid, pass);
//   return buttonHeldAtBoot || !haveCreds;
// }

// // ===== Wi-Fi and backend =====
// void connectWiFi() {
//   String ssid, pass;
//   if (!loadWiFiCredentials(ssid, pass)) {
//     setLEDStatus(RED);
//     wifiConnected = false;
//     return;
//   }
//   setLEDStatus(BLUE);
//   WiFi.mode(WIFI_STA);
//   WiFi.begin(ssid.c_str(), pass.c_str());
//   unsigned long start = millis();
//   while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
//     delay(250);
//   }
//   wifiConnected = (WiFi.status() == WL_CONNECTED);
//   setLEDStatus(wifiConnected ? GREEN : RED);
//   if (wifiConnected) {
//     Serial.print("[WiFi] Connected: "); Serial.println(WiFi.localIP());
//   } else {
//     Serial.println("[WiFi] Connect failed");
//   }
// }

// bool beginClient(HTTPClient& client, const String& url) {
//   if (!wifiConnected) return false;
//   WiFiClient wifi;
//   if (!client.begin(wifi, url)) return false;
//   client.addHeader("Content-Type", "application/json");
//   client.addHeader("X-API-Key", API_KEY);
//   return true;
// }

// void performFeed(float portion) {
//   setLEDStatus(WHITE);
//   feederServo.attach(PIN_SERVO);
//   feederServo.write(0);
//   delay(400);
//   feederServo.write(90);
//   int ms = (int)(portion * 1000);
//   ms = constrain(ms, 500, 4000);
//   delay(ms);
//   feederServo.write(0);
//   delay(300);
//   feederServo.detach();
//   setLEDStatus(GREEN);
//   if (logBufCount < LOG_BUF_MAX) {
//     logBuf[logBufCount].ts = millis();
//     logBuf[logBufCount].portion = portion;
//     strncpy(logBuf[logBufCount].source, "esp", sizeof(logBuf[logBufCount].source));
//     logBufCount++;
//   }
// }

// void syncLogsWithServer() {
//   if (!wifiConnected || logBufCount == 0) return;
//   HTTPClient client; String url = BASE_URL + "/api/device/logs/";
//   if (!beginClient(client, url)) return;
//   DynamicJsonDocument doc(1024);
//   JsonArray arr = doc.createNestedArray("logs");
//   for (int i=0; i<logBufCount; i++) {
//     JsonObject o = arr.createNestedObject();
//     o["timestamp"] = String(millis());
//     o["portion_dispensed"] = logBuf[i].portion;
//     o["source"] = logBuf[i].source;
//   }
//   String body; serializeJson(doc, body);
//   int code = client.POST(body);
//   if (code == 200) { logBufCount = 0; }
//   client.end();
// }

// void updateFromServer() {
//   if (!wifiConnected) return;
//   // Config
//   {
//     HTTPClient client; String cfgUrl = BASE_URL + "/api/device/config/?device_id=" + DEVICE_ID;
//     if (beginClient(client, cfgUrl)) {
//       int code = client.GET();
//       if (code == 200) {
//         DynamicJsonDocument doc(2048); DeserializationError err = deserializeJson(doc, client.getString());
//         if (!err && doc["poll_interval_sec"].is<int>()) {
//           int pi = doc["poll_interval_sec"].as<int>();
//           if (pi >= 10 && pi <= 300) pollIntervalMs = (unsigned long)pi * 1000UL;
//         }
//       }
//       client.end();
//     }
//   }
//   // Command
//   {
//     HTTPClient cmd; String cmdUrl = BASE_URL + "/api/device/feed-command/?device_id=" + DEVICE_ID;
//     if (beginClient(cmd, cmdUrl)) {
//       int code = cmd.GET();
//       if (code == 200) {
//         DynamicJsonDocument doc(1024);
//         if (!deserializeJson(doc, cmd.getString())) {
//           bool hasCmd = doc["has_command"].as<bool>();
//           if (hasCmd) {
//             float portion = doc["portion_size"] ? doc["portion_size"].as<float>() : 1.0;
//             performFeed(portion);
//             // Ack
//             HTTPClient ack; String ackUrl = BASE_URL + "/api/device/acknowledge/";
//             if (beginClient(ack, ackUrl)) {
//               DynamicJsonDocument adoc(256);
//               adoc["command_id"] = (int)doc["command_id"].as<int>();
//               adoc["device_id"] = DEVICE_ID;
//               adoc["result"] = "ok";
//               String body; serializeJson(adoc, body);
//               ack.POST(body); ack.end();
//             }
//           }
//         }
//       }
//       cmd.end();
//     }
//   }
// }

// void handleButtonPress() {
//   static bool lastState = true; // pull-up
//   static unsigned long lastChange = 0;
//   const unsigned long debounce = 50;
//   bool curr = digitalRead(PIN_BUTTON) == LOW;
//   unsigned long now = millis();
//   if (curr != lastState && (now - lastChange) > debounce) {
//     lastState = curr; lastChange = now;
//     if (curr) performFeed(1.0);
//   }
// }

// void sendHeartbeat() {
//   if (!wifiConnected) return;
//   HTTPClient client; String url = BASE_URL + "/api/device/status/";
//   if (!beginClient(client, url)) return;
//   wifiRSSI = WiFi.RSSI();
//   DynamicJsonDocument doc(256);
//   doc["device_id"] = DEVICE_ID;
//   doc["wifi_rssi"] = wifiRSSI;
//   doc["uptime"] = uptimeSeconds;
//   doc["daily_feeds"] = (int)logBufCount; // rough proxy unless tracked separately
//   String body; serializeJson(doc, body);
//   client.POST(body); client.end();
// }

// void otaCheckStub() { /* placeholder */ }

// // ===== Arduino lifecycle =====
// void setup() {
//   Serial.begin(115200);
//   delay(200);
//   pinMode(PIN_LED_RED, OUTPUT);
//   pinMode(PIN_LED_GREEN, OUTPUT);
//   pinMode(PIN_LED_BLUE, OUTPUT);
//   pinMode(PIN_BUTTON, INPUT_PULLUP);
//   setLEDStatus(RED);

//   if (checkProvisioningTrigger()) {
//     provisioningMode = true;
//     startProvisioningPortal();
//     return; // loop() will service portal
//   }

//   connectWiFi();
//   lastPoll = millis();
//   lastLoopMillis = millis();
// }

// void loop() {
//   unsigned long now = millis();

//   if (provisioningMode) {
//     portalServer.handleClient();
//     delay(10);
//     return;
//   }

//   // Uptime
//   if (now - lastLoopMillis >= 1000) { uptimeSeconds++; lastLoopMillis = now; }

//   // Wi-Fi maintenance
//   if (WiFi.status() != WL_CONNECTED) {
//     wifiConnected = false; setLEDStatus(RED);
//     static unsigned long lastTry = 0;
//     if (now - lastTry > 5000) { connectWiFi(); lastTry = now; }
//   } else if (!wifiConnected) { wifiConnected = true; setLEDStatus(GREEN); }

//   // Button
//   handleButtonPress();

//   // Backend polling
//   if (now - lastPoll >= pollIntervalMs) {
//     updateFromServer();
//     syncLogsWithServer();
//     sendHeartbeat();
//     otaCheckStub();
//     lastPoll = now;
//   }

//   delay(10);
// }