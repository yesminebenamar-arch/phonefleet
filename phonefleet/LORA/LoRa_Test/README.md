# LoRa_Test

The simplest possible LoRa test between two Arduino Mega 2560 boards:
one board **sends** a message by radio, the other **receives** it and shows it on the PC.

```
Mega #1 (Sender)  ))) LoRa radio 868 MHz )))  Mega #2 (Receiver)
  sends "Hello 0"                               shows "Received: Hello 0   RSSI: -45"
```

| Folder | Board | What it does | Details |
|--------|-------|--------------|---------|
| `Sender/`   | Mega #1 | Sends `Hello 0`, `Hello 1`, ... every 2 seconds | [Sender/README.md](Sender/README.md) |
| `Receiver/` | Mega #2 | Prints each message it receives               | [Receiver/README.md](Receiver/README.md) |

> **You don't need to change any code.** Follow the steps below in order.
> No electronics knowledge is needed: you only plug in 4 wires per board.

---

## Step-by-step guide (for beginners)

### 1. What you need

**Hardware (x2, one set per board):**
- 1 × Arduino **Mega 2560** board
- 1 × **Grove LoRa** radio module (RFM95, 868 MHz)
- 1 × **USB cable** (USB-A to USB-B, the "printer" cable) to connect the board to the PC
- 4 × jumper wires (or the Grove cable with 4 wires)

**Software (only once, on your PC):**
- **VS Code**: download it from <https://code.visualstudio.com> and install it.
- An **internet connection** for the first build (the tools download automatically).

### 2. Install PlatformIO in VS Code (only once)

PlatformIO is the VS Code extension that compiles the code and sends it to the Arduino.

1. Open VS Code.
2. Click the **Extensions** icon on the left (4 small squares), or press `Ctrl+Shift+X`.
3. Search for **PlatformIO IDE** and click **Install**.
4. Wait until the installation finishes, then **restart VS Code** when asked.
   An **ant-head icon** appears in the left bar: PlatformIO is ready.

> The first install can take several minutes. Wait for it to finish.

### 3. Wire the LoRa module to each board

Do this with the USB cable **unplugged**. Wire **both** boards the same way.

| Wire from the LoRa module | Goes to the Mega 2560 pin | Where to find it on the board |
|---------------------------|---------------------------|-------------------------------|
| **RX**  | **TX1** (pin 18) | Row of pins on the right, labelled `TX1 18` |
| **TX**  | **RX1** (pin 19) | Right next to it, labelled `RX1 19` |
| **VCC** | **5V**           | Power pins, labelled `5V` |
| **GND** | **GND**          | Any pin labelled `GND` |

**Important:** the wires are **crossed**: RX goes to TX, and TX goes to RX.
This is the most common mistake. If the test fails, check this first.

### 4. Upload the Receiver (board #2)

1. Plug **only board #2** into the PC with its USB cable.
   (Plug in **one board at a time** so the code goes to the right board.)
2. In VS Code: **File → Open Folder…** and choose the **`Receiver`** folder
   (inside `LORA/LoRa_Test/`). Do **not** open the whole project folder.
3. Wait a few seconds. The first time, PlatformIO downloads the tools and
   the LoRa library (can take a few minutes; see the bottom bar).
4. In the **blue bar at the bottom** of VS Code, click the **→ (arrow) Upload** button.
   Wait for **`SUCCESS`** in the terminal.
5. Click the **plug icon (Serial Monitor)** in the blue bar. You should see:

   ```
   LoRa Receiver
   LoRa init OK, waiting for messages...
   ```

Keep this window open: this is where messages will appear.

### 5. Upload the Sender (board #1)

1. Open a **second** VS Code window: **File → New Window**.
2. In this new window: **File → Open Folder…** and choose the **`Sender`** folder.
3. **Unplug board #2** and plug in **board #1**. Board #2 keeps its program;
   you will plug it back in at step 6.
4. Click **→ Upload** in the blue bar and wait for **`SUCCESS`**.
5. Click the **plug icon (Serial Monitor)**. You should see:

   ```
   LoRa Sender
   LoRa init OK
   Sent: Hello 0
   Sent: Hello 1
   ```

### 6. Check the result

Power both boards (with USB, on the same PC or two different PCs).
In the **Receiver** Serial Monitor, a new line appears every 2 seconds:

```
Received: Hello 0   RSSI: -45
Received: Hello 1   RSSI: -46
```

**The test works.** The RSSI number shows the signal strength:
closer to 0 means stronger (see [Receiver/README.md](Receiver/README.md)).

To stop the Serial Monitor, click in the terminal and press `Ctrl+C`.

---

## Two boards on the same PC

Each board gets a port name (`COM3`, `COM5`, ...). PlatformIO picks the board
by itself, but with **two** boards plugged in it may pick the wrong one.

The simplest solution: **plug in only the board you are uploading to**,
upload, then plug in the other one.

If you really need both plugged in at the same time, choose the port by hand:
1. Click the **ant-head icon** (PlatformIO) on the left → **Devices**
   to see the ports (`COM...`) of your boards.
2. In the blue bar at the bottom, click **"Auto"** (next to the plug icon)
   and choose the right `COM` port for this window.

---

## If something goes wrong

 What you see | What it means | What to do |
|--------------|---------------|------------|
 `LoRa init failed -> check the wiring` | The board can't talk to the LoRa module | Check that **RX↔TX are crossed**, and that VCC is on 5V and GND on GND |
 Upload error: `can't open device` / `access denied` | The port is busy | Close the **Serial Monitor** (`Ctrl+C`) or any other program using the board, then upload again |
 Upload error: `no device found` / timeout | The PC doesn't see the board | Try another USB cable or port. Some cables only give power, not data |
 Sender says `Sent: ...` but the Receiver shows nothing | Radio problem | Check both boards are powered and wired the same way. Put them 1 m apart to start |
 Strange characters on the Serial Monitor | Wrong speed | The speed must be **115200** (already set in `platformio.ini`); close and reopen the monitor |
 Red underlines in VS Code (`cannot open source file "Arduino.h"`) | You opened the wrong folder | Open the **`Sender`** or **`Receiver`** folder itself, not the whole project. The code is fine |
 The first build is very slow | PlatformIO is downloading the tools | Normal the first time only. Wait |
