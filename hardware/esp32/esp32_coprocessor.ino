/*
 * NOVA ESP32 Coprocesseur
 * Gestion : capteurs temps réel, BLE, mode basse consommation
 */

#include <BluetoothSerial.h>

BluetoothSerial SerialBT;

#define MPU6050_ADDR 0x68

void setup() {
    Serial.begin(115200);
    Serial2.begin(115200, SERIAL_8N1, 3, 1); // Vers Pi
    SerialBT.begin("NOVA-Coprocessor");
    Wire.begin();

    // Wake up MPU6050
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(0x6B);
    Wire.write(0);
    Wire.endTransmission();

    Serial.println("NOVA ESP32 Coprocesseur démarré");
}

void loop() {
    if (Serial2.available()) {
        String cmd = Serial2.readStringUntil('\n');
        processCommand(cmd);
    }

    if (SerialBT.available()) {
        String btData = SerialBT.readStringUntil('\n');
        Serial2.println("BT:" + btData);
    }

    static unsigned long lastSend = 0;
    if (millis() - lastSend > 100) {
        sendSensorData();
        lastSend = millis();
    }
}

void processCommand(String cmd) {
    if (cmd.startsWith("SLEEP")) {
        esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);
        esp_deep_sleep_start();
    }
}

void sendSensorData() {
    // TODO: Lire MPU6050 et envoyer au Pi
    Serial2.println("SENSOR:0,0,0,0,0,0");
}
