# LoRa_Test

Simplest possible LoRa test between two Arduino Mega 2560 boards.

```
Mega #1 (Sender)  ))) LoRa 868 MHz )))  Mega #2 (Receiver)
  "Hello 0"                               prints "Hello 0  RSSI: -45"
```

| Folder | Board | What it does | Details |
|--------|-------|--------------|---------|
| `Sender/`   | Mega #1 | Sends `Hello N` every 2 s | [Sender/README.md](Sender/README.md) |
| `Receiver/` | Mega #2 | Prints what it receives   | [Receiver/README.md](Receiver/README.md) |

Each folder is a separate PlatformIO project: open it on its own in VS Code.

## Test steps

1. Wire the LoRa module the same way on both boards (Serial1, pins 18/19).
2. Upload `Receiver` to Mega #2 and open its Serial Monitor.
3. Upload `Sender` to Mega #1.
4. You should see `Received: Hello ...` on the Receiver every 2 seconds.

## If nothing is received

- `LoRa init failed`: TX/RX not crossed, or the module is not powered.
- Init OK but nothing arrives: check both files use the same `LORA_FREQ`.
- Two boards on one PC: set `upload_port` / `monitor_port` in each `platformio.ini`
  so you don't upload to the wrong board (`pio device list` shows the COM ports).
