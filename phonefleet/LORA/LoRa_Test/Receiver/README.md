# Receiver

Listens for LoRa messages and prints each one on the Serial Monitor, with its RSSI.

## Files

| File | Role |
|------|------|
| `platformio.ini` | Project config: board (Mega 2560), serial speed, LoRa library |
| `src/main.cpp`   | The code |

## Wiring (Grove LoRa module -> Mega 2560)

Same as the Sender:

| LoRa module | Mega 2560 |
|-------------|-----------|
| RX  | TX1 (pin 18) |
| TX  | RX1 (pin 19) |
| VCC | 5V  |
| GND | GND |

## How the code works

1. `setup()`: same as the Sender (start serial, `rf95.init()`, set the frequency).
2. `loop()`
   - `rf95.available()` returns true when a packet has arrived.
   - `rf95.recv(buf, &len)` copies the packet into `buf`; `len` becomes the number of bytes received.
   - `buf[len] = '\0'` ends the string so it can be printed as text.
   - `rf95.lastRssi()` gives the signal strength of that packet, in dBm.

## Build / upload (VS Code + PlatformIO)

1. In VS Code: **File > Open Folder** and pick this `Receiver` folder.
2. Plug in Mega #2.
3. Click **→ (Upload)**, then the **plug (Serial Monitor)** button.

Expected output (with the Sender powered on):

```
LoRa Receiver
LoRa init OK, waiting for messages...
Received: Hello 0   RSSI: -45
Received: Hello 1   RSSI: -46
```

## Reading the RSSI

The RSSI tells you how strong the signal is. Closer to 0 means stronger.

| RSSI | Meaning |
|------|---------|
| -30 to -70   | Very good (boards close together) |
| -70 to -100  | OK |
| below -110   | Weak, messages may start to get lost |

## Link with BoxCo_Server

BoxCo_Server does the same receive steps, then also:
checks the frame (`parseFrame`), adds a date from the RTC, and writes it to the SD card.
You can add those steps one at a time once this test works.
