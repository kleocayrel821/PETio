# PETio Device Pairing — Getting Started and Troubleshooting

## Getting Started (Option B: On‑Device PIN)

1) Power on the device
- Device boots and connects to Wi‑Fi (use the configuration flow if not set).
- The OLED shows “PAIRING MODE” with a 6‑digit PIN and your Device ID.

2) Open the web app and log in
- Use the same server base URL the device reaches (typically your LAN IP, not 127.0.0.1).
- Example: http://192.168.18.9:8000/

3) Claim the device
- Go to Devices → Claim Device (http://<server>/devices/claim/).
- Enter your Device ID and the 6‑digit PIN shown on the OLED.
- Submit. On success, the device will receive its key and exit pairing.

4) Done
- The device now authenticates using Device‑ID and X‑Device‑Key on every request.
- You can view it under Devices and use the Control Panel as usual.

## Troubleshooting

- “Device not found” on claim
  - The device must register its PIN first. Ensure it’s on the pairing screen and connected to the same server base URL.
  - You can manually register for quick testing:
    - POST /api/device/pair/register/ with JSON: { "device_id": "<ID>", "pin": "<PIN>", "ttl_seconds": 300 }.
  - After registration, retry the claim with the same device_id and PIN.

- PIN expired
  - PINs are time‑limited (e.g., 5 minutes). The device automatically rolls a new one and updates the OLED. Use the new PIN.

- Claim limit reached / too many attempts (429)
  - The server enforces rate limits and short lockouts after repeated failed claims. Wait a few minutes and try again with the correct PIN.

- 403 errors after device was claimed
  - The per‑device key was rotated or the device was unpaired. Clear the stored device key on the device to re‑enter pairing and claim again.

- Using the wrong server address
  - Do not mix http://127.0.0.1 with a LAN IP when claiming and registering. Use the same base URL that the device uses.

- OLED and LED meanings (pairing)
  - OLED shows “* PAIRING MODE *” with PIN, Device ID, countdown, and a progress bar.
  - After a successful claim, the OLED returns to READY and normal status screens.

- Re‑pairing steps (field support)
  - Unpair in the web admin (or rotate the key), then clear the device’s stored key so it re‑enters pairing mode. Claim again with the new PIN.

