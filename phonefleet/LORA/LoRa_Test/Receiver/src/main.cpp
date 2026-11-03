/**********************************************************************************
* LoRa_Test - RECEIVER
*
* Waits for LoRa messages and prints them on the Serial Monitor,
* with the RSSI (signal strength).
*
* Board  : Arduino Mega 2560
* Module : Grove LoRa (RFM95) on Serial1
*          Mega TX1 (pin 18) -> module RX
*          Mega RX1 (pin 19) -> module TX
*          5V -> VCC, GND -> GND
**********************************************************************************/

#include <Arduino.h>
#include <RH_RF95.h>

#define LORA_FREQ   868.0   // MHz, must be the same on both boards

RH_RF95<HardwareSerial> rf95(Serial1);

void setup() {
    Serial.begin(115200);
    Serial.println("LoRa Receiver");

    if (!rf95.init()) {
        Serial.println("LoRa init failed -> check the wiring");
        while (1);  // stop here
    }
    rf95.setFrequency(LORA_FREQ);
    Serial.println("LoRa init OK, waiting for messages...");
}

void loop() {
    if (rf95.available()) {
        uint8_t buf[RH_RF95_MAX_MESSAGE_LEN + 1];  // +1 for the '\0'
        uint8_t len = RH_RF95_MAX_MESSAGE_LEN;

        if (rf95.recv(buf, &len)) {
            buf[len] = '\0';  // turn the bytes into a C string

            Serial.print("Received: ");
            Serial.print((char*) buf);
            Serial.print("   RSSI: ");
            Serial.println(rf95.lastRssi());
        }
    }
}
