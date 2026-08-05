# NOVA — Personal AI Wearable Computer

> Un ordinateur portable intelligent porté au bras, entièrement personnalisable et contrôlé par IA locale.

## 🎯 Objectif

Créer un assistant personnel embarqué, autonome (hors ligne), avec interface graphique tactile, capteurs multiples, et intelligence artificielle locale.

## 📋 Architecture

```
┌─────────────────┐
│   Écran tactile │
│   (4" HDMI)      │
└────────┬────────┘
         │
┌────────▼────────┐
│  Raspberry Pi   │
│  Zero 2 W       │
└────────┬────────┘
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
 Capteurs  Comm.        IA
 (I2C)     (BT/WiFi)    (Local)
```

## 🚀 Phases de développement

| Phase | Description | Statut |
|-------|-------------|--------|
| 1 | Prototype matériel | 🔄 En cours |
| 2 | Interface graphique | ⏳ À venir |
| 3 | Système d'apps | ⏳ À venir |
| 4 | IA locale | ⏳ À venir |
| 5 | Calendrier | ⏳ À venir |
| 6 | GPS | ⏳ À venir |
| 7 | Communication | ⏳ À venir |
| 8 | Capteurs | ⏳ À venir |
| 9 | RTL-SDR | ⏳ À venir |
| 10 | Gestion énergie | ⏳ À venir |
| 11 | Boîtier 3D | ⏳ À venir |
| 12 | Version finale | ⏳ À venir |

## 🛠️ Installation

```bash
git clone https://github.com/Mitchou1/Nova-Project.git
cd Nova-Project
chmod +x scripts/install.sh
sudo ./scripts/install.sh
cd software
python3 nova/main.py
```

## 👤 Auteur

**Mitchou** — Étudiant en électronique, ESPRIT Tunisie

## 📄 Licence

MIT License
