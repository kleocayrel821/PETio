# ESP8266 Pet Feeder — Pin Wiring Guide (NodeMCU 1.0)

This document summarizes the physical circuit connections for the ESP8266 (NodeMCU) used by the pet feeder firmware. It maps each firmware function to its corresponding board pin, shows recommended wiring, and highlights boot-strap pin caveats.

## Pin Map (as used in firmware)

Source of truth macros in firmware:
- `d:\PETio\controller\firmware\Firmware\Firmware.ino:31` — `#define RED_LED_PIN 13` (D7)
- `d:\PETio\controller\firmware\Firmware\Firmware.ino:32` — `#define BLUE_LED_PIN 16` (D0)
- `d:\PETio\controller\firmware\Firmware\Firmware.ino:36` — `#define SERVO_PIN 14` (D5)
- `d:\PETio\controller\firmware\Firmware\Firmware.ino:37` — `#define FEED_NOW_PIN 5` (D1)
- `d:\PETio\controller\firmware\Firmware\Firmware\Firmware.ino:38` — `#define ADD_PORTION_PIN 4` (D2)
- `d:\PETio\controller\firmware\Firmware\Firmware.ino:39` — `#define REDUCE_PORTION_PIN 12` (D6)

### Summary Table

| Function            | NodeMCU Pin | GPIO | Direction     | Recommended Wiring                        |
|---------------------|-------------|------|---------------|-------------------------------------------|
| Feed Now Button     | D1          | 5    | `INPUT_PULLUP`| D1 → Button → GND (active LOW)            |
| Add Portion Button  | D2          | 4    | `INPUT_PULLUP`| D2 → Button → GND (active LOW)            |
| Reduce Portion Btn  | D6          | 12   | `INPUT_PULLUP`| D6 → Button → GND (active LOW)            |
| Servo Signal        | D5          | 14   | Output (PWM)  | D5 → Servo signal; Servo GND → Common GND |
| Red LED             | D7          | 13   | Output        | D7 → 220Ω → LED anode; LED cathode → GND  |
| Blue LED            | D0          | 16   | Output        | D0 → 220Ω → LED anode; LED cathode → GND  |

Notes:
- Buttons are active-LOW because the firmware configures `INPUT_PULLUP`. Idle reads HIGH; pressing connects to GND and reads LOW.
- Use short, clean wiring for buttons. Optionally add a 0.1 µF capacitor across each button to reduce contact bounce.
- The Green LED is not used to free pins for safer button wiring; “ready” state shows LEDs OFF.

## Buttons — Recommended Wiring

```
Feed Now (D1):
   D1 (GPIO5) ──[Button]── GND

Add Portion (D2):
   D2 (GPIO4) ──[Button]── GND

Reduce Portion (D6):
   D6 (GPIO12) ──[Button]── GND
```

Behavior:
- Idle: `HIGH` on all three pins.
- Press: Only the corresponding pin goes `LOW`.
- Firmware uses debounce and brief suppression after portion changes to avoid false feed triggers.

## LEDs — Recommended Wiring

Use series resistors (≈220 Ω) to limit current:
```
Red LED (D7/GPIO13):
   D7 ──[220Ω]──► LED anode
                ◄── LED cathode ── GND

Blue LED (D0/GPIO16):
   D0 ──[220Ω]──► LED anode
                ◄── LED cathode ── GND
```

States:
- Error / Config / Connecting: Red solid or blink patterns
- Feeding: Blue solid
- Ready: LEDs OFF

## Servo — Recommended Wiring

Continuous rotation servo (e.g., MG996R):
- Signal: `D5 (GPIO14)` → Servo signal
- Power: External 5–6 V supply (do not power servo from the ESP8266)
- Ground: Common ground between ESP8266 and servo supply

```
LM2596 (5V) ──► Servo +5V
Common GND ──┬─► Servo GND
             └─► ESP8266 GND
D5 (GPIO14) ──► Servo Signal
```

## Power & Ground
- ESP8266 requires stable 3.3 V supply.
- Servo requires its own 5–6 V supply capable of ≥1–2 A bursts.
- Always tie grounds together (ESP8266 GND, servo GND, external supply GND).

## On/Off Switch (Recommended)

Use a simple SPST rocker/toggle switch to cut the 5V supply feeding the system. Place it on the high side of the 5V line coming from the regulator (e.g., LM2596) so both ESP8266 (via VIN/USB 5V) and the servo are powered together.

```
AC/DC 12V → [LM2596 step-down 5V] ──┬── [SWITCH — SPST] ──► 5V BUS
                                   │
                                   └── GND BUS

5V BUS ──► NodeMCU VIN (or USB 5V)
5V BUS ──► Servo +5V
GND BUS ──► NodeMCU GND
GND BUS ──► Servo GND
```

- Place the switch between the regulator’s 5V output and the 5V bus.
- Do not switch the ground; keep a common ground at all times.
- If you power the ESP8266 via USB, you can place the switch only on the servo’s 5V line to create a “motor disable,” but a full system switch is usually preferred.

Alternative: Add a small inline slide switch on the USB 5V lead if you always power the ESP8266 via USB; ensure current rating is sufficient for your servo if the servo also shares that 5V rail.

## Boot-Strap Pin Caveats (ESP8266)
- `GPIO0 (D3)` and `GPIO2 (D4)`: must be HIGH at boot; don’t use as input to GND buttons.
- `GPIO15 (D8)`: must be LOW at boot; avoid using for inputs unless you add external pull-up carefully (not recommended).
- This firmware avoids `D3`, `D4`, and `D8` for buttons to prevent boot issues.

## Quick Diagnostics
- Enable simple monitor by setting `DEBUG_BUTTONS` to `1` in firmware to print:
  - Idle: `Feed=HIGH Add=HIGH Reduce=HIGH`
  - Press feed: `Feed=LOW Add=HIGH Reduce=HIGH`
  - If you see multiple pins LOW at once without pressing, inspect wiring for shorts or swapped connections.

## Reference
- Pin definitions are in `Firmware.ino`:
  - `d:\PETio\controller\firmware\Firmware\Firmware.ino:31–39`
