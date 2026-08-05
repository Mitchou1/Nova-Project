# Checklist de conformité — NOVA

**Date :** 2026-08-05 · Met à jour le tableau de phases obsolète de `README.md`
(qui montrait tout à "à venir" sauf la phase 1).

**Légende :**
- ✅ **Vérifié** — testé réellement dans cet environnement de développement
- ⚠️ **Logiciel prêt, matériel non testable** — code présent et cohérent,
  nécessite le vrai Raspberry Pi/capteurs/GPS/RTL-SDR/batterie pour vérifier
- ❌ **Non implémenté**

Cet environnement de développement n'a **aucun** Raspberry Pi physique, capteur
I2C, dongle RTL-SDR, module GPS, ni batterie réelle — seuls une webcam et un
accès réseau existent (déjà exploités : capture photo réelle, recherche web).

---

## Phase 1 — Prototype matériel de base

| Critère | Statut | Détail |
|---|---|---|
| Structure de dossiers (`/config /apps /models /data`) | ✅ | Existe réellement, cohérente avec le code |
| Raspberry Pi Zero 2 W / Pi 5 physique | ⚠️ | Cible confirmée Pi 5 (voir `JARVIS_INTEGRATION_PLAN.md`) ; code testé uniquement sur PC de dev |
| Stockage microSD | ⚠️ | Aucun test possible sans le matériel |

## Phase 2 — Écran et interface utilisateur

| Critère | Statut | Détail |
|---|---|---|
| Interface graphique personnalisée | ✅ | Kivy, template Stitch, 3 thèmes (Classic/Cyberpunk/Undercover) |
| Écran principal (heure/date/RDV/météo/apps) | ✅ | Présent, sauf météo (hors-scope, voir plan JARVIS) |
| Navigation tactile fluide | ✅ | Testée en usage (mouse/touch), animations désactivables (`ui.animations`) |
| Animations sans lag | ✅ | 3 fuites `Clock.schedule_interval` corrigées cette session (voir `AUDIT_REPORT.md`) |
| Thèmes personnalisables | ✅ | 3 thèmes fonctionnels, changement à chaud |
| Écran tactile physique 3.5"-5" | ⚠️ | Jamais testé sur écran réel |

## Phase 3 — Système d'applications modulaires

| Critère | Statut | Détail |
|---|---|---|
| Architecture plugin (`AppLauncher`) | ✅ | Découverte automatique de `software/apps/*/app.py` |
| 8 apps fonctionnelles | ✅ | assistant, calendar, camera, files, maps, radio, sensors, settings |
| Ajout d'app sans modifier le système principal | ✅ | Vérifié par construction (aucune app ne modifie `nova/`) |

## Phase 4 — Agent IA local (+ JARVIS v2.0)

| Critère | Statut | Détail |
|---|---|---|
| Whisper STT hors ligne | ✅ | faster-whisper, réel, taille suit `config.ai.whisper_model` |
| LLM local (Qwen2.5-3B, llama.cpp) | ✅ | Réel, 30+ actions, chemin rapide déterministe |
| Piper TTS hors ligne | ✅ | Réel, voix FR uniquement (EN/AR : réponse écrite, voir plan JARVIS) |
| Commandes vocales avancées | ✅ | Intention/entités via schéma d'actions + LLM |
| Mémoire contextuelle multi-session | ✅ | Persistée cette session (`memory_store.py`) |
| Multilingue FR/EN/AR | ✅ | Allégé — voir `JARVIS_INTEGRATION_PLAN.md` §3 |
| Fonctionne 100% hors ligne | ✅ | Sauf `rechercher_web`/`ouvrir_navigateur`, qui **nécessitent** internet et le disent honnêtement si absent |
| Latence < 500ms | ❌/⚠️ | Non atteint sur le conteneur de dev (≈14s mesurés en session précédente pour une génération LLM complète) ; **non mesurable sur la cible réelle Pi 5** — voir section Performance |

## Phase 5 — Calendrier intelligent

| Critère | Statut | Détail |
|---|---|---|
| Base SQLite fonctionnelle | ✅ | `apps/calendar/storage.py`, index ajouté cette session |
| Créer/modifier/supprimer par la voix | ✅ | Actions `ajouter_evenement`/`modifier_evenement`/`supprimer_evenements` |
| Rappels automatiques | ✅ | Bug de minuit corrigé cette session, testé sur base réelle |
| Notification écran | ✅ | `EventAlert`, plein écran, pulsation |
| Vibration | ⚠️ | Code GPIO réel présent (`assistant_actions.py::_vibrate`), matériel requis pour vérifier |

## Phase 6 — Navigation GPS intelligente

| Critère | Statut | Détail |
|---|---|---|
| Module GPS NEO-6M réel | ❌ | 100% simulé (`random.gauss`), aucun code série/gpsd |
| Cartographie OSM hors ligne | ✅ | Valhalla + tuiles réelles (Tunisie), routage testé |
| Mode normal (navigation classique) | ✅ | Implémenté cette session |
| Mode personnalisé (marche/conduite) | ✅ | Implémenté et testé cette session (zoom, suivi position, profil de routage) |

## Phase 7 — Communication

| Critère | Statut | Détail |
|---|---|---|
| Bluetooth (bascule) | ⚠️ | `bluetoothctl` réel côté code, actif seulement sur Pi |
| WiFi (sync/update) | ⚠️ | `nmcli` réel côté code, actif seulement sur Pi |
| ESP32 coprocesseur (UART) | ❌ | Firmware stub non fonctionnel, **aucun lien logiciel** avec `software/` (vérifié par l'audit — le pont Phase 7 est purement documentaire) |

## Phase 8 — Capteurs

| Critère | Statut | Détail |
|---|---|---|
| MPU6050 (accel/gyro, gestes) | ❌ | 100% simulé, zéro code I2C |
| BME280 (temp/humidité/pression) | ❌ | 100% simulé |
| VL53L0X (distance laser) | ❌ | 100% simulé |
| Pi Camera | ⚠️ | Code `libcamera-still` réel (Pi uniquement) |
| Webcam PC (substitut de dev) | ✅ | Capture réelle via ffmpeg, testée cette session sur la machine de dev |

## Phase 9 — Détection radio (RTL-SDR)

| Critère | Statut | Détail |
|---|---|---|
| RTL-SDR détecté et fonctionnel | ❌ | 100% simulé, aucun import `pyrtlsdr`, absent des deux fichiers requirements |
| Scan de fréquences | ❌ | Simulation aléatoire uniquement |
| Alarme sonore / indicateur proximité | ❌ | Non implémenté (dépend du matériel ci-dessus) |

## Phase 10 — Gestion énergie

| Critère | Statut | Détail |
|---|---|---|
| Indicateur batterie | ⚠️ | Code MCP3008/SPI réel (Pi uniquement), simulation honnête sur PC |
| Mode économie d'énergie | ✅ | Câblé (session précédente) : coupe animations/particules sous le seuil configuré |
| Pas de processus fantôme (CPU) | ✅ | 3 fuites `Clock.schedule_interval` corrigées cette session |

## Phase 11 — Boîtier 3D

| Critère | Statut | Détail |
|---|---|---|
| Design CAD | ❌ | Dossiers `hardware/case/` vides (`.gitkeep` uniquement) |
| Ventilation, accès USB, boutons | ❌ | Non commencé |

## Phase 12 — Version finale améliorée

| Critère | Statut | Détail |
|---|---|---|
| Cible Pi 5 / Jetson | ⚠️ | Pi 5 confirmé comme cible (cette session) ; ajustements logiciels faits (`ai_engine.py`), **non testés sur le matériel réel** |

---

## Objectifs de performance chiffrés

La quasi-totalité de ces cibles **ne peut pas être mesurée** dans cet
environnement (pas de Pi 5, pas de batterie réelle, pas de capteurs/GPS/RTL-SDR).
Quand une mesure proxy a été prise, elle est étiquetée comme telle — jamais
présentée comme satisfaisant la cible réelle.

| Cible | Mesurable ici ? | Résultat |
|---|---|---|
| Latence vocale < 500ms | Proxy seulement | ~14s mesurés (génération LLM seule, conteneur de dev, non représentatif du Pi 5) |
| Réponse UI < 200ms | ⚠️ non mesuré formellement | Pas de profiling effectué ; 3 fuites de `Clock` corrigées, ce qui améliore la fluidité perçue |
| Mémoire < 512MB pic | ⚠️ non mesurable | Cible d'origine pour Pi Zero 2W ; obsolète depuis la confirmation Pi 5 (RAM largement supérieure) |
| CPU < 70% idle / < 95% charge | ❌ non mesurable | Nécessite le matériel réel |
| Batterie < 10W / autonomie > 4h | ❌ non mesurable | Aucune batterie réelle disponible |
| Uptime 99% | ❌ non mesurable | Nécessite un déploiement réel de longue durée |
| Reconnaissance vocale > 90% FR/EN/AR | ❌ non mesurable formellement | Pas de jeu de test audio étalonné disponible |
| Précision GPS < 5m | ❌ non applicable | GPS 100% simulé (Phase 6) |
| Reconnaissance de gestes > 85% | ❌ non applicable | Fonctionnalité différée (Phase 8 / plan JARVIS §4) |
| Capacité 100% hors ligne | ✅ vérifié | Vrai pour tout sauf la recherche web (assumé, documenté, échec honnête si hors ligne) |
