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
│       5         │
└────────┬────────┘
    ┌────┴────┬──────────┐
    ▼         ▼          ▼
 Capteurs  Comm.        IA
 (I2C)     (BT/WiFi)    (Local)
```

## 🚀 Phases de développement

Statut détaillé, vérifié critère par critère : voir
[`docs/CONFORMITY_CHECKLIST.md`](docs/CONFORMITY_CHECKLIST.md). Résumé :

| Phase | Description | Statut |
|-------|-------------|--------|
| 1 | Prototype matériel | ⚠️ Logiciel prêt, matériel non testé |
| 2 | Interface graphique | ✅ Fonctionnelle (template Stitch, 3 thèmes) |
| 3 | Système d'apps | ✅ 8 apps, architecture plugin |
| 4 | IA locale (+ JARVIS v2.0) | ✅ Whisper/Qwen2.5-3B/Piper réels, multilingue, mémoire persistante |
| 5 | Calendrier | ✅ SQLite, rappels fiables (bug de minuit corrigé) |
| 6 | GPS | ⚠️ Navigation/routage réels (Valhalla+OSM) ; position GPS 100% simulée |
| 7 | Communication | ⚠️ WiFi/Bluetooth (Pi uniquement) ; pont ESP32 non relié |
| 8 | Capteurs | ❌ 100% simulés (aucun capteur physique disponible) |
| 9 | RTL-SDR | ❌ 100% simulé |
| 10 | Gestion énergie | ✅ Mode économie câblé ; capteur batterie réel (Pi uniquement) |
| 11 | Boîtier 3D | ❌ Non commencé |
| 12 | Version finale | ⚠️ Cible Pi 5 confirmée, non testée sur matériel |

Voir aussi [`docs/RISK_ASSESSMENT.md`](docs/RISK_ASSESSMENT.md) pour l'évaluation
complète (couche logicielle prête, couche matérielle non validée) et
[`docs/JARVIS_INTEGRATION_PLAN.md`](docs/JARVIS_INTEGRATION_PLAN.md) pour le
détail des fonctionnalités IA avancées.

## 🛠️ Installation

```bash
git clone https://github.com/Mitchou1/Nova-Project.git
cd Nova-Project
chmod +x scripts/install.sh
sudo ./scripts/install.sh
./scripts/run.sh
```

`scripts/run.sh` active automatiquement le venv du projet avant de lancer
NOVA — préférez-le à un appel direct de `python3 nova/main.py`, qui échoue si
le Python système ne trouve pas les dépendances du venv.

## 👤 Auteur

**Mitchou** — Étudiant en électronique, ESPRIT Tunisie

## 📄 Licence

MIT License
