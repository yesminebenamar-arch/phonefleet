# Sender

Sends `Hello 0`, `Hello 1`, `Hello 2`, ... over LoRa every 2 seconds.

## Files

| File | Role |
|------|------|
| `platformio.ini` | Project config: board (Mega 2560), serial speed, LoRa library |
| `src/main.cpp`   | The code |

## Wiring (Grove LoRa module -> Mega 2560)

| LoRa module | Mega 2560 |
|-------------|-----------|
| RX  | TX1 (pin 18) |
| TX  | RX1 (pin 19) |
| VCC | 5V  |
| GND | GND |

RX goes to TX, and TX goes to RX (crossed).

## How the code works

1. `setup()`
   - `Serial.begin(115200)`: starts the USB serial link to the PC.
   - `rf95.init()`: talks to the LoRa module over `Serial1`. If it fails, the wiring is wrong and the program stops.
   - `rf95.setFrequency(868.0)`: sets the radio frequency (868 MHz is the EU band).
2. `loop()`
   - Builds the text `"Hello <counter>"` with `sprintf`.
   - `rf95.send(...)` hands the bytes to the radio.
   - `rf95.waitPacketSent()` waits until the radio has finished transmitting.
   - Prints what was sent, adds 1 to the counter, waits 2 s.

## Build / upload (VS Code + PlatformIO)

1. In VS Code: **File > Open Folder** and pick this `Sender` folder.
2. Plug in Mega #1.
3. Click the **→ (Upload)** button in the blue bar at the bottom.
4. Click the **plug (Serial Monitor)** button.

Expected output:

```
LoRa Sender
LoRa init OK
Sent: Hello 0
Sent: Hello 1
```

## Things you can change

- `LORA_FREQ`: must be the **same** on Sender and Receiver.
- `SEND_DELAY`: time between messages, in ms.
- The message: change the `sprintf` line (max ~250 bytes per packet).

## Link with BoxCo_Client

BoxCo_Client does the same thing, but its message is a frame of sensor values:
`HBXCO <tab> serverId <tab> clientId <tab> nbValues <tab> values... <tab> EBXCO`.
Once this test works, you can replace `"Hello %d"` with your own frame.
