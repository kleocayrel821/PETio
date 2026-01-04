# ESP8266 Pet Feeder — LED Status Guide

This guide explains how the firmware uses the LEDs to indicate device state and provide user feedback. The current hardware uses two LEDs:
- Red LED (`RED_LED_PIN = D7 / GPIO13`)
- Blue LED (`BLUE_LED_PIN = D0 / GPIO16`)

Green LED is not used to free pins for safer button wiring. “Ready” state is indicated by all LEDs OFF.

## LED States

- Error (Red solid)
  - Meaning: Wi‑Fi failure or a general error
  - Trigger: `ledController.showError()`
- Ready (Off)
  - Meaning: Device is idle and ready
  - Trigger: `ledController.showReady()`
- Feeding (Blue solid)
  - Meaning: Servo is dispensing food
  - Trigger: `ledController.showFeeding()` (called inside `MotorController.startFeeding()`)
- Config Mode (Red fast blink)
  - Meaning: Configuration portal is active
  - Trigger: `ledController.showConfigMode()`; blinking handled in `LedController.update()`
- Connecting (Red slow blink)
  - Meaning: Attempting Wi‑Fi connection
  - Trigger: `ledController.showConnecting()`; blinking handled in `LedController.update()`

## Portion Adjust Feedback (Overlay Blinks)

When you press the portion adjust buttons:
- Add Portion (D2 / GPIO4): Blue LED blinks quickly (3 cycles at ~80 ms)
- Reduce Portion (D6 / GPIO12): Red LED blinks quickly (3 cycles at ~80 ms)

This feedback runs as an overlay that temporarily takes control of the LEDs and then automatically restores the previous base state:
- If the device is feeding (blue solid), the overlay briefly blinks and returns to solid blue.
- If the device is connecting (red blink), the overlay briefly blinks and then the base red blink resumes.
- If the device is ready (off), the overlay blinks and returns to off.

Overlay behavior is non-blocking and does not delay button handling or servo control.

## Behavior Summary

- Base state is managed via `setState(...)` and `update()` in `LedController`.
- Blink rates:
  - Config blink (fast): ~200 ms interval
  - Connecting blink (slow): ~1000 ms interval
- Overlay feedback:
  - 3 cycles
  - ~80 ms per toggle
  - Restores base state automatically after completing cycles

## Typical Sequences

- Boot:
  - Red slow blink while connecting
  - On Wi‑Fi connection: LEDs OFF (ready)
- Manual feed:
  - Blue solid during servo operation
  - On completion: LEDs OFF (ready)
- Add/Reduce during feeding:
  - Brief feedback blinks; returns to blue solid
- Config mode:
  - Red fast blink until configuration completes or restarts

## Troubleshooting

- Red blinking even when connected:
  - Ensure `showReady()` is called after successful Wi‑Fi; firmware sets `currentState=LED_READY` to leave blinking state.
- Blue LED turns off immediately when feeding:
  - Confirm `flashBlue(...)` is not used after `startFeeding(...)`; firmware keeps blue solid during feeding.
- Feedback not visible:
  - Check LED wiring and resistors (≈220 Ω recommended).
  - Verify button press is registered in serial logs (“Manual portion increased/decreased…”).

## References

- LED controller implementation:
  - `d:\PETio\controller\firmware\Firmware\Firmware.ino` (`LedController` class)
  - Methods: `showError`, `showReady`, `showFeeding`, `showConfigMode`, `showConnecting`, `update`
- Portion adjust feedback triggers:
  - `d:\PETio\controller\firmware\Firmware\Firmware.ino` (`handlePortionAdjustButtons`)
  - Calls `ledController.startFeedbackBlinkBlue(3, 80)` and `ledController.startFeedbackBlinkRed(3, 80)`

