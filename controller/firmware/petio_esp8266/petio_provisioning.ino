// // PETio ESP8266 Provisioning Sketch
// // Purpose: SoftAP config portal to store Wi-Fi credentials in LittleFS and EEPROM

// #include <ESP8266WiFi.h>
// #include <ESP8266WebServer.h>
// #include <LittleFS.h>
// #include <EEPROM.h>
// #include <ArduinoJson.h>

// // SoftAP credentials
// const char* AP_SSID = "PETio_Config";
// const char* AP_PASS = "petio123";

// // Button pin to force provisioning (D6 = GPIO12)
// const int PIN_BUTTON = 12;

// // LED pins for simple feedback (optional visual)
// const int PIN_LED_RED   = 5;   // D1
// const int PIN_LED_GREEN = 4;   // D2
// const int PIN_LED_BLUE  = 0;   // D3 (GPIO0: only use as LED output; avoid input)

// ESP8266WebServer server(80);

// // EEPROM layout
// // Byte 0: flag (0x42 means credentials present)
// // Bytes 1-32: SSID (null-terminated)
// // Bytes 33-96: Password (null-terminated)
// const int EEPROM_SIZE = 128;

// void setLED(bool r, bool g, bool b) {
//   digitalWrite(PIN_LED_RED,   r ? HIGH : LOW);
//   digitalWrite(PIN_LED_GREEN, g ? HIGH : LOW);
//   digitalWrite(PIN_LED_BLUE,  b ? HIGH : LOW);
// }

// void writeEEPROMCreds(const String& ssid, const String& password) {
//   EEPROM.begin(EEPROM_SIZE);
//   EEPROM.write(0, 0x42);
//   // write SSID
//   for (int i = 0; i < 32; i++) {
//     char c = (i < ssid.length()) ? ssid[i] : '\0';
//     EEPROM.write(1 + i, (uint8_t)c);
//   }
//   // write password
//   for (int i = 0; i < 64; i++) {
//     char c = (i < password.length()) ? password[i] : '\0';
//     EEPROM.write(33 + i, (uint8_t)c);
//   }
//   EEPROM.commit();
//   EEPROM.end();
// }

// bool saveToLittleFS(const String& ssid, const String& password) {
//   if (!LittleFS.begin()) {
//     Serial.println("[Provisioning] LittleFS.begin() failed");
//     return false;
//   }
//   File f = LittleFS.open("/wifi.json", "w");
//   if (!f) {
//     Serial.println("[Provisioning] Failed to open /wifi.json for writing");
//     return false;
//   }
//   StaticJsonDocument<256> doc;
//   doc["ssid"] = ssid;
//   doc["password"] = password;
//   if (serializeJson(doc, f) == 0) {
//     Serial.println("[Provisioning] Failed to write JSON");
//     f.close();
//     return false;
//   }
//   f.close();
//   Serial.println("[Provisioning] Saved /wifi.json");
//   return true;
// }

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

// void handleRoot() {
//   server.send(200, "text/html", indexPage());
// }

// void handleSave() {
//   String ssid = server.hasArg("ssid") ? server.arg("ssid") : "";
//   String password = server.hasArg("password") ? server.arg("password") : "";
//   if (ssid.length() == 0) {
//     server.send(400, "text/plain", "Missing SSID");
//     return;
//   }
//   // Persist to LittleFS and EEPROM
//   bool fsOk = saveToLittleFS(ssid, password);
//   writeEEPROMCreds(ssid, password);
//   if (fsOk) {
//     server.send(200, "text/plain", "Credentials saved, rebooting...");
//   } else {
//     server.send(500, "text/plain", "Failed to save to LittleFS, but EEPROM updated. Rebooting...");
//   }
//   Serial.println("Credentials saved, rebooting...");
//   delay(2000);
//   ESP.restart();
// }

// void setup() {
//   Serial.begin(115200);
//   delay(200);
//   pinMode(PIN_LED_RED, OUTPUT);
//   pinMode(PIN_LED_GREEN, OUTPUT);
//   pinMode(PIN_LED_BLUE, OUTPUT);
//   pinMode(PIN_BUTTON, INPUT_PULLUP);
//   setLED(true, false, false); // Red while starting AP

//   // Start SoftAP
//   WiFi.softAP(AP_SSID, AP_PASS);
//   IPAddress ip = WiFi.softAPIP();
//   Serial.print("[Provisioning] AP started: ");
//   Serial.println(ip);

//   // Web server routes
//   server.on("/", HTTP_GET, handleRoot);
//   server.on("/save", HTTP_POST, handleSave);
//   server.begin();
//   Serial.println("[Provisioning] Web server started on 192.168.4.1");
//   setLED(false, false, true); // Blue to indicate AP/portal active
// }

// void loop() {
//   server.handleClient();
// }