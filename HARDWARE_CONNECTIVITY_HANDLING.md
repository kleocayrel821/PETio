# Hardware Connectivity Handling for Feed Now

This update adds a connectivity check to the "Feed Now" flow so users receive clear feedback if the ESP8266 device is offline or unreachable.

## Connectivity Check Logic
- Backend uses `controller/utils.py::check_device_connection(device_ip, timeout=3)` to query the device at `http://<device_ip>/ping`.
- The `device_ip` is read from `request.data.device_ip` or `settings.PETIO_DEVICE_IP` (fallback to `PETIO_DEVICE_IP` env var).
- If the device does not respond with HTTP 200 within the timeout or a request error occurs, the backend returns a 503 with a clear error.

## API Response Structure
- Success (200):
  ```json
  {
    "success": true,
    "status": "ok",
    "message": "Feed command queued",
    "command_id": 123,
    "portion_size": 100.0
  }
  ```
- Conflict (409) when a command is already pending:
  ```json
  {
    "success": false,
    "status": "warning",
    "message": "Feed command already pending",
    "command_id": 123,
    "portion_size": 100.0
  }
  ```
- Offline (503) when device is not connected:
  ```json
  {
    "success": false,
    "error": "Device not connected. Please check Wi-Fi or power."
  }
  ```
- Error (500) for unexpected issues:
  ```json
  {
    "success": false,
    "error": "Failed to queue feed command: <details>"
  }
  ```

## Firmware /ping Route Requirement
The ESP8266 firmware now serves a `/ping` endpoint on its local web server:
```cpp
webServer.on("/ping", HTTP_GET, [this]() { webServer.send(200, "text/plain", "OK"); });
```
This allows the Django app to verify device connectivity from the local network.

## Frontend Behavior
The Feed Now button’s JavaScript shows alerts for connectivity issues and network errors:
- If the backend responds with `success: false`, an alert is shown with the error.
- On network errors (server unreachable), an alert is shown.
- For normal success or a 409 already-pending condition, a success toast is displayed.

## Testing Scenarios
1. Device connected:
   - Endpoint returns 200 with `success: true` and queues command.
   - UI shows success toast and updates logs.
2. Device disconnected:
   - Endpoint returns 503 with `success: false` and error message.
   - UI shows an alert indicating the device is not connected.
3. Network error:
   - Endpoint returns 500 or the request fails.
   - UI shows a “Server unreachable.” alert and backend logs show the exception.

## Notes
- Configure `settings.PETIO_DEVICE_IP` or env var `PETIO_DEVICE_IP` for connectivity checks.
- No database schema changes were required for this feature.