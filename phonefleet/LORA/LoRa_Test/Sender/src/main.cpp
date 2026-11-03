/**********************************************************************************
* LoRa_Test - SENDER
*
* Sends a short text message ("Hello 0", "Hello 1", ...) every 2 seconds.
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
#define SEND_DELAY  2000    // ms between two messages

RH_RF95<HardwareSerial> rf95(Serial1);

int counter = 0;

void setup() {
    Serial.begin(115200);
    Serial.println("LoRa Sender");

    if (!rf95.init()) {
        Serial.println("LoRa init failed -> check the wiring");
        while (1);  // stop here
    }
    rf95.setFrequency(LORA_FREQ);
    Serial.println("LoRa init OK");
}

void loop() {
    // Build the message
    char message[20];
    sprintf(message, "Hello %d", counter);

    // Send it
    rf95.send((uint8_t*) message, strlen(message));
    rf95.waitPacketSent();

    Serial.print("Sent: ");
    Serial.println(message);

    counter++;
    delay(SEND_DELAY);
}
