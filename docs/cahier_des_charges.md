# Cahier des charges — NOVA

## 1. Présentation

NOVA est un ordinateur portable porté au bras (wearable), autonome,
équipé d'une IA locale fonctionnant sans connexion internet.

## 2. Contraintes

| Contrainte      | Valeur cible                          |
|-----------------|---------------------------------------|
| Autonomie       | ≥ 4 h en usage mixte                  |
| Poids total     | ≤ 350 g                               |
| Écran           | 4" tactile, 800x480                   |
| Démarrage       | ≤ 30 s                                |
| Fonctionnement  | 100 % hors ligne                      |
| Langue          | Français (interface + IA)             |

## 3. Matériel

| Composant       | Référence                    | Rôle                       |
|-----------------|------------------------------|----------------------------|
| Calculateur     | Raspberry Pi Zero 2 W        | OS, UI, IA                 |
| Coprocesseur    | ESP32                        | Capteurs temps réel, BLE   |
| Écran           | Waveshare 4" HDMI tactile    | Interface                  |
| IMU             | MPU-6050                     | Accéléromètre / gyroscope  |
| Environnement   | BME280                       | Temp / hum / pression      |
| GPS             | NEO-6M                       | Position, vitesse          |
| ADC             | MCP3008                      | Mesure batterie            |
| Batterie        | Li-Po 3.7 V 5000 mAh         | Alimentation               |
| Radio           | RTL-SDR v3 (option)          | Scan de fréquences         |

## 4. Logiciel

- OS : Raspberry Pi OS Lite (64 bits)
- UI : Kivy (Python 3)
- STT : Whisper tiny
- LLM : TinyLlama 1.1B quantifié Q4_K_M (llama.cpp)
- TTS : Piper (voix fr_FR-siwis-medium)
- Stockage : SQLite

## 5. Fonctions attendues

1. Écran d'accueil : heure, date, batterie, prochain événement
2. Lanceur d'applications extensible (plugins)
3. Assistant vocal local (écoute → compréhension → réponse vocale)
4. Agenda avec rappels
5. Navigation GPS hors ligne (tuiles pré-téléchargées)
6. Lecture des capteurs en temps réel
7. Scanner radio (RTL-SDR)
8. Gestion d'énergie et mise en veille automatique

## 6. Critères de validation

- [ ] Démarrage automatique au boot
- [ ] Interface tactile réactive (< 100 ms)
- [ ] Réponse vocale complète en < 8 s
- [ ] Aucune requête réseau sortante en usage normal
- [ ] Boîtier imprimé porté confortablement au bras
