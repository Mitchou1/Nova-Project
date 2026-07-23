/*
 * NOVA — ESP32 Coprocesseur
 * Rôle : lecture capteurs temps réel, pont BLE, mode basse consommation.
 * Liaison avec le Raspberry Pi : UART 115200 bauds.
 *
 * Protocole (lignes ASCII terminées par \n) :
 *   Pi -> ESP32 : "SLEEP"        met l'ESP32 en deep sleep
 *                 "PING"         demande un ACK
 *                 "RATE:200"     change la période d'envoi (ms)
 *   ESP32 -> Pi : "SENSOR:ax,ay,az,gx,gy,gz"
 *                 "BT:<données>"
 *                 "ACK"
 */

#include <Wire.h>
#include <BluetoothSerial.h>
#include <esp_sleep.h>

BluetoothSerial SerialBT;

#define MPU6050_ADDR 0x68
#define UART_RX_PIN  16
#define UART_TX_PIN  17

unsigned long sendPeriod = 100;   // ms
unsigned long lastSend   = 0;

void setup() {
    Serial.begin(115200);
    Serial2.begin(115200, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
    SerialBT.begin("NOVA-Coprocessor");

    Wire.begin();
    // Réveil du MPU-6050 (registre PWR_MGMT_1)
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(0x6B);
    Wire.write(0);
    Wire.endTransmission(true);

    Serial.println("NOVA ESP32 coprocesseur demarre");
}

void loop() {
    if (Serial2.available()) {
        String cmd = Serial2.readStringUntil('\n');
        cmd.trim();
        processCommand(cmd);
    }

    if (SerialBT.available()) {
        String btData = SerialBT.readStringUntil('\n');
        btData.trim();
        Serial2.println("BT:" + btData);
    }

    if (millis() - lastSend > sendPeriod) {
        sendSensorData();
        lastSend = millis();
    }
}

void processCommand(String cmd) {
    if (cmd.startsWith("SLEEP")) {
        Serial2.println("ACK");
        esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);
        esp_deep_sleep_start();
    } else if (cmd.startsWith("PING")) {
        Serial2.println("ACK");
    } else if (cmd.startsWith("RATE:")) {
        sendPeriod = cmd.substring(5).toInt();
        if (sendPeriod < 20) sendPeriod = 20;
        Serial2.println("ACK");
    }
}

int16_t readWord(uint8_t reg) {
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom((uint8_t)MPU6050_ADDR, (uint8_t)2, (uint8_t)true);
    int16_t value = (Wire.read() << 8) | Wire.read();
    return value;
}

void sendSensorData() {
    int16_t ax = readWord(0x3B);
    int16_t ay = readWord(0x3D);
    int16_t az = readWord(0x3F);
    int16_t gx = readWord(0x43);
    int16_t gy = readWord(0x45);
    int16_t gz = readWord(0x47);

    Serial2.print("SENSOR:");
    Serial2.print(ax); Serial2.print(",");
    Serial2.print(ay); Serial2.print(",");
    Serial2.print(az); Serial2.print(",");
    Serial2.print(gx); Serial2.print(",");
    Serial2.print(gy); Serial2.print(",");
    Serial2.println(gz);
}
