## PETio AP Network Discovery

### Overview
- The feeder now exposes a secure configuration Access Point and automatically scans nearby Wi-Fi networks while the setup portal is open.
- The portal presents a deduplicated list of discovered SSIDs sorted by signal strength, so users select a network instead of typing the SSID manually.
- After a network is selected, the SSID field becomes read-only and the user is prompted only for the password that matches the detected security type.
- Manual SSID entry remains available as a fallback if scanning fails.

### Important Hardware Limitation
- The firmware runs on `ESP8266`, which supports `2.4GHz` Wi-Fi only.
- `5GHz` networks cannot be detected or joined by this hardware, even if they are nearby.
- The portal displays this limitation so users do not attempt to configure a 5GHz-only SSID.

### Setup Flow
1. Power on the feeder.
2. Join the setup AP shown on the OLED.
3. Use the AP password shown on the OLED and in the serial log.
4. Open the captive portal page.
5. Wait for the discovered network list to populate.
6. Select one network from the list.
7. Enter the Wi-Fi password only.
8. Save the configuration and wait for the feeder to restart.

### Security Safeguards
- The setup AP now uses a password instead of remaining open.
- The AP limits connections to a single client during provisioning.
- Wi-Fi passwords are submitted with `POST` and are not echoed to the serial log.
- Password validation follows the selected security mode:
- `Open`: password must be empty.
- `WEP`: `5/13` ASCII characters or `10/26` hexadecimal digits.
- `WPA/WPA2`: `8-63` printable characters.

### Testing Checklist
- Verify the portal discovers visible nearby `2.4GHz` SSIDs and sorts them by RSSI descending.
- Verify duplicate SSIDs appear only once and keep the strongest signal record.
- Verify selecting a discovered network populates the SSID field and prevents manual editing.
- Verify `Open`, `WEP`, and `WPA/WPA2` password validation works as expected.
- Verify the manual entry section becomes usable if scanning fails or if the operator explicitly chooses it.
- Verify the portal layout works on phone and laptop browsers.
- Verify the secure setup AP password is shown correctly on the OLED during configuration mode.

### Troubleshooting
- No networks appear:
- Confirm the target router is broadcasting a `2.4GHz` SSID.
- Tap `Refresh Networks` and wait a few seconds for the async scan to complete.
- Use manual entry if the scan endpoint reports a failure.
- Setup AP cannot be joined:
- Check the OLED for the AP name and password.
- Confirm the device is still in configuration mode and has not timed out.
- Selected network fails after save:
- Re-enter the password and confirm the router uses a supported `2.4GHz` mode.
- If the SSID is hidden, use manual entry.
- Portal is reachable but scan keeps failing:
- Reduce RF interference and move the feeder closer to the router.
- Power-cycle the feeder and retry setup.

### Notes For Maintenance
- The discovered network list is refreshed continuously while configuration mode is active.
- The firmware deduplicates SSIDs on-device and stores only the strongest entry for each name.
- Open networks are now supported because configuration validity is based on SSID presence, not password presence.
