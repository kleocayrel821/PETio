# 1.3" OLED Display Troubleshooting Guide

## Common Issues & Solutions

### Problem: Garbled/static display (like in the photo)
**Probable Cause**: Your display is likely using SH1106 controller instead of SSD1306, or needs different initialization parameters.

**Solution**: The updated firmware should auto-detect and work with both. Upload and check Serial Monitor (115200 baud) for initialization details.

---

### Problem: No display at all
**Checklist**:
1. **Wiring** (critical!)
   - VCC → 3.3V or 5V (check your display's specs)
   - GND → GND
   - SCL → D1 (GPIO5)
   - SDA → D2 (GPIO4)
   - Ensure no loose connections!
   
2. **Power Supply**: Make sure your ESP8266 is getting stable power
   
3. **I2C Address**: Run the firmware and check Serial Monitor for I2C scan results
   - Common addresses: 0x3C, 0x3D

---

## Wiring Reference

| Display Pin | ESP8266 Pin | Function |
|-------------|-------------|----------|
| VCC         | 3.3V / 5V   | Power    |
| GND         | GND         | Ground   |
| SCL         | D1 (GPIO5)  | I2C Clock|
| SDA         | D2 (GPIO4)  | I2C Data |
| RES         | (optional)  | Reset    |
| DC          | (not used)  | Data/Command |

---

## Serial Monitor Output

When you run the firmware, you'll see:
```
Scanning I2C bus...
I2C device found at address 0x3C !
Found 1 devices
Trying init at 0x3C as SH1106
OLED initialized at 0x3C as SH1106
Running comprehensive display test...
```

---

## Test Sequence

The firmware will automatically run:
1. I2C bus scan
2. Try both SH1106 and SSD1306 initialization
3. Full display test:
   - Solid white screen
   - Solid black screen
   - Checkerboard pattern
   - Grid lines
   - Text at various sizes
   - Shapes (circles, rectangles)
   - All UI screens

---

## Common 1.3" OLED Variants

### SSD1306 vs SH1106
- **SSD1306**: More common on smaller displays, works with standard Adafruit library
- **SH1106**: Very common on 1.3" displays, similar but needs slightly different init

The firmware automatically tries both!

---

## To Disable Test Mode

Once your display works, change in `Firmware.ino`:
```cpp
#define OLED_DISPLAY_TEST 0
```
