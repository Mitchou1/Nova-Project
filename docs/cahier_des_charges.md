# NOVA — Cahier des charges complet

**Dernière mise à jour :** 2026-08-18

---

## Contexte du projet

Concevoir et fabriquer une machine portable intelligente qui se fixe au bras comme une montre ou une mini-tablette : un ordinateur autonome, personnalisable, contrôlé de bout en bout — matériel et logiciel — par son créateur.

L'objectif est un assistant personnel embarqué capable de fonctionner **hors ligne**, avec une interface graphique personnalisée, des applications ajoutables, des capteurs, une intelligence artificielle locale, et des fonctions utiles au quotidien.

Le projet est réalisé étape par étape, sur Raspberry Pi 5.

---

## Architecture générale du système

Architecture modulaire, pensée pour qu'on puisse ajouter une fonctionnalité sans toucher au système principal.

```
                 Écran tactile
                      |
                      |
              Raspberry Pi 5
                      |
       --------------------------------
       |              |               |
    Capteurs       Communication     IA
       |              |               |
    GPIO/I2C       Bluetooth/WiFi   Agent local
       |
   Modules externes
```

Le système est conçu comme un mini smartphone personnalisé.

---

## PHASE 1 — Prototype matériel de base

### Objectif
Créer une première version fonctionnelle et portable.

### Carte principale

**Raspberry Pi 5** (4 Go ou 8 Go de RAM), quad-core Cortex-A76 @ 2.4 GHz, GPU VideoCore VII.

Fonctions attendues de la carte :
- Linux (Raspberry Pi OS 64 bits) ;
- Python / C++ ;
- WiFi, Bluetooth intégrés ;
- GPIO, I2C, SPI pour les capteurs ;
- USB 3.0 ;
- PCIe 2.0 x1 disponible pour une évolution future (SSD NVMe via HAT, voir Phase 12) ;
- alimentation USB-C PD, jusqu'à 5V/5A.

### Stockage

- microSD 64 Go minimum (classe A2 recommandée pour les IOPS aléatoires — les modèles IA et la base SQLite sollicitent beaucoup de petites lectures/écritures) ;
- SSD NVMe via adaptateur PCIe : optionnel, à garder pour une itération ultérieure si la microSD devient un goulot d'étranglement.

Organisation :
```
/system
/apps
/config
/models
/data
```

---

## PHASE 2 — Écran et interface utilisateur

### Écran tactile

- Prototype : écran tactile 3.5 à 5 pouces, SPI ou HDMI.
- Version finale : écran capacitif AMOLED 4-5 pouces.

### Interface graphique

Framework retenu : **Kivy** (Python). PyQt6 reste une alternative valable si le style « widgets natifs » est préféré, mais Kivy est le choix par défaut pour ce projet — animations fluides gérées nativement, portable sans changement entre PC de développement et Pi.

Écran principal, type smartphone :
```
-------------------
Bonjour utilisateur

Heure
Date

Prochain rendez-vous

Météo

Applications

[AI]
[Maps]
[Agenda]
[Capteurs]
[Radio]
-------------------
```

Exigences d'interface :
- navigation tactile fluide ;
- animations sans lag ;
- thèmes personnalisables ;
- ajout d'applications sans redémarrage du système.

---

## PHASE 3 — Système d'applications modulaires

Architecture de plugins : chaque application est un fichier indépendant, ajoutable sans modifier le système principal.

```
/apps
    calendar.py
    assistant.py
    maps.py
    radio.py
    camera.py
    settings.py
```

---

## PHASE 4 — Agent Intelligence Artificielle local

### Architecture

```
Microphone
    ↓
Speech To Text
    ↓
Agent IA (LLM local)
    ↓
Applications
    ↓
Text To Speech
    ↓
Haut-parleur
```

### Fonctions

- comprendre les commandes vocales ;
- répondre aux questions ;
- contrôler les applications (agenda, navigation, réglages, capteurs, radio, fichiers, caméra) ;
- gérer les tâches (créer/lister/modifier/supprimer un rendez-vous, etc.).

Exemple :
> Utilisateur : « Rappelle-moi demain à 8h d'appeler quelqu'un. »
> L'IA doit comprendre la demande, créer l'événement, programmer le rappel, et notifier l'utilisateur au moment voulu.

### Modèles

| Brique | Technologie | Modèle cible |
|---|---|---|
| Speech To Text | Whisper (faster-whisper) | taille **small** |
| Agent IA | llama.cpp | modèle **~3B paramètres**, quantifié (ex. Q5_K_M) |
| Text To Speech | Piper TTS | voix française qualité medium |

Recommandations d'exécution :
- fenêtre de contexte du LLM : **4096 tokens** minimum (l'historique de conversation persistant plus un prompt système détaillé dépasse vite 2048) ;
- `n_threads = 4` (un thread par cœur physique — au-delà, pas de gain réel sur une charge CPU-bound) ;
- chargement des modèles en tâche de fond après l'affichage de l'interface, jamais de façon synchrone au démarrage (sous peine de geler l'UI plusieurs secondes).

### Fiabilité

Un modèle de ~3B paramètres quantifié **ne garantit pas à 100 % un format de sortie structuré** (JSON d'action) à chaque tentative. Pour les commandes fréquentes et non ambiguës (créer un rendez-vous avec une date/heure explicite, rechercher une information, ouvrir une application, régler un paramètre), prévoir un **chemin de reconnaissance déterministe** (expressions régulières, tolérant aux fautes de frappe/transcription courantes) qui court-circuite le LLM et garantit une exécution fiable. Le LLM reste la voie de secours pour tout ce qui sort de ce périmètre — discussion libre, questions ouvertes, formulations imprévues.

### Fonctionnement hors ligne

Le système doit fonctionner sans connexion internet pour toutes ses fonctions cœur (voix, IA, agenda). Une fonctionnalité de recherche web est une extension explicitement **en ligne** (JARVIS-like) : elle doit se dégrader proprement (message clair, aucune fausse réponse inventée) en l'absence de réseau, et ne doit jamais ouvrir un navigateur sans que l'intention en soit explicite.

---

## PHASE 5 — Calendrier intelligent

### Base de données

SQLite.

### Table `event`

| Champ | Type | Rôle |
|---|---|---|
| id | INTEGER PK | identifiant |
| titre | TEXT | intitulé de l'événement |
| date | TEXT (AAAA-MM-JJ) | date de l'événement |
| heure | TEXT (HH:MM) | heure de l'événement |
| priorité | INTEGER | niveau d'importance |
| description | TEXT | détails optionnels |
| rappel | INTEGER | minutes avant l'événement |

### Fonctions

- création d'événement vocale ou tactile ;
- modification, suppression ;
- rappels automatiques (déclenchés une seule fois par événement, avec tolérance aux redémarrages/veilles de l'appareil) ;
- notification écran ;
- vibration.

Matériel : moteur de vibration 3V sur GPIO.

Exemple d'alerte :
```
14:00

Réunion

Dans 10 minutes

[Vibration]
[Message vocal]
```

---

## PHASE 6 — Navigation GPS intelligente

### Module

GPS NEO-6M (UART ou I2C selon le modèle).

### Fonctions capteur

- localisation ;
- vitesse ;
- coordonnées.

### Application Maps

Cartographie **OpenStreetMap**, tuiles hors-ligne. Deux services distincts, chacun avec un chemin local et un repli en ligne :

- **Géocodage** (nom de lieu → coordonnées) : Nominatim (instance locale si possible, sinon service public respectant sa limite de requêtes).
- **Routage** (calcul d'itinéraire) : moteur local (type Valhalla, conteneurisé) en priorité, service en ligne en repli si indisponible.

### Deux modes d'affichage

- **Mode normal** : navigation classique — carte, itinéraire, distance, vue d'ensemble laissée au contrôle de l'utilisateur.
- **Mode personnalisé** : interface minimaliste adaptée au déplacement (zoom et suivi automatique différents en marche vs en conduite).

---

## PHASE 7 — Communication

### Bluetooth

Bluetooth intégré du Pi 5.
- connexion téléphone ;
- transfert de fichiers ;
- écoute audio.

### WiFi

- synchronisation ;
- mises à jour.

### ESP32 secondaire (optionnel)

Utile principalement pour une veille ultra basse consommation (le Pi 5 éteint, l'ESP32 seul actif) :

```
Raspberry Pi 5
      |
    UART
      |
    ESP32
      |
Capteurs temps réel
```

Rôle si implémenté : gestion basse consommation en veille profonde, lecture de capteurs rapides, Bluetooth BLE.

---

## PHASE 8 — Capteurs

### Mouvement — MPU6050

- accélération, gyroscope ;
- reconnaissance de gestes simples : double tap → ouvrir le menu, rotation du poignet → changer d'écran.

### Environnement — BME280

- température, humidité, pression.

### Distance — VL53L0X

- mesure laser (proximité).

### Caméra — Pi Camera

- photos ;
- vision artificielle, reconnaissance d'objets (inférence légère on-device envisageable).

---

## PHASE 9 — Détection radio

### Matériel

- RTL-SDR USB ;
- antenne VHF/UHF.

```
Antenne
   ↓
RTL-SDR
   ↓
USB
   ↓
Raspberry Pi 5
   ↓
Analyse spectre
   ↓
Affichage fréquence
```

### Fonctions

- scanner de fréquences ;
- détection d'activité radio ;
- mesure de puissance du signal.

Exemple :
```
Signal détecté

Fréquence : 446.006 MHz
Puissance : -35 dBm
```

À ajouter :
- alarme sonore ;
- indicateur de proximité dérivé de la puissance du signal.

---

## PHASE 10 — Gestion énergie

Le Pi 5 peut consommer jusqu'à ~12 W en pointe avec accessoires actifs (écran, WiFi, inférence IA simultanés). L'alimentation doit être dimensionnée pour ça, pas pour la seule consommation moyenne.

### Composants

- batterie Li-Po de capacité suffisante (dimensionner pour l'autonomie visée à ~5-8 W de consommation moyenne réelle, pas la consommation crête) ;
- module de charge/protection adapté à un débit de sortie élevé ;
- **circuit d'alimentation capable de délivrer une tension stable sous forte demande de courant** (le Pi 5 est sensible aux chutes de tension — un sous-dimensionnement se traduit par des redémarrages ou une icône d'alimentation instable) ; une carte UPS/PD dédiée au Pi 5 est préférable à un montage boost générique.

```
Batterie Li-Po
      ↓
Charge / protection
      ↓
Régulation 5V (fort courant)
      ↓
Raspberry Pi 5
```

À ajouter :
- indication de niveau de batterie à l'écran ;
- mode économie d'énergie (réduction des animations/effets quand la batterie est basse).

---

## PHASE 11 — Boîtier 3D

Le Pi 5 (85 × 56 mm) doit être pris en compte dans le dimensionnement du boîtier.

### Design

Avant :
```
+----------------+
|                |
| écran tactile  |
|                |
+----------------+
```

Arrière : batterie, Raspberry Pi 5, modules (GPS, capteurs, radio selon la configuration).

### Prévoir

- ventilation ou dissipateur passif — le Pi 5 chauffe sous charge soutenue (IA locale notamment) ; un boîtier porté au bras doit gérer cette chaleur sans devenir inconfortable ;
- accès USB (au moins un port pour le RTL-SDR ou la mise à jour) ;
- boutons physiques (marche/arrêt, action rapide) ;
- bracelet.

---

## PHASE 12 — Au-delà du Pi 5

Évolution ultérieure, à envisager une fois la version Pi 5 stabilisée et ses limites réelles identifiées :

- **Raspberry Pi 5 Compute Module (CM5)** : même puissance de calcul, format nettement plus compact — pertinent pour une version boîtier plus fine, avec carte porteuse sur mesure.
- **Jetson Orin Nano** : à envisager seulement si la vision par ordinateur devient un axe central (détection/reconnaissance d'objets en temps réel plus poussée que ce que le Pi 5 seul permet).
- SSD NVMe via PCIe (déjà anticipé Phase 1) si la microSD devient limitante.
- Écran AMOLED si toujours au stade SPI/HDMI de prototype.

---

## Ordre de réalisation conseillé

| Étape | Contenu |
|---|---|
| 1 | Raspberry Pi 5 + écran tactile — interface graphique de base |
| 2 | Système d'applications (architecture plugin) |
| 3 | Calendrier |
| 4 | Microphone + assistant vocal (STT → LLM → TTS) |
| 5 | GPS + application Maps |
| 6 | Capteurs (MPU6050, BME280, VL53L0X, caméra) |
| 7 | Bluetooth et communication |
| 8 | RTL-SDR |
| 9 | Boîtier 3D |
| 10 | Version finale / évolutions Phase 12 |

---

## Objectif final

Un appareil portable personnel : **NOVA — Personal AI Wearable Computer**.

Une machine :
- conçue et programmée entièrement par son créateur ;
- autonome ;
- personnalisable ;
- évolutive ;
- contrôlée par une IA locale, fonctionnant hors ligne ;
- capable d'aider dans les tâches quotidiennes ;
- équipée de capteurs et modules choisis selon les besoins réels.

---

## Annexe — Où trouver le détail de l'état d'implémentation

Ce cahier des charges décrit l'**intention** du projet. Pour l'état réel vérifié, voir :

- **Conformité détaillée phase par phase** : `docs/CONFORMITY_CHECKLIST.md` (état réel vérifié, pas une reformulation des intentions).
- **Plan JARVIS AI v2.0** (fonctionnalités IA avancées ajoutées au-delà de ce cahier des charges) : `docs/JARVIS_INTEGRATION_PLAN.md`.
- **Audit technique** (bugs trouvés/corrigés) : `docs/AUDIT_REPORT.md`.
- **Sécurité** : `docs/SECURITY_REPORT.md`.
- **Ce qui reste à faire, par priorité** : `docs/OPTIMIZATION_RECOMMENDATIONS.md`.
- **Évaluation de risque / prêt pour la suite ?** : `docs/RISK_ASSESSMENT.md`.

### Résumé de l'état actuel

**Couche logicielle :** avancée. Interface Kivy complète (template Stitch, 3 thèmes), 8 applications fonctionnelles, IA locale réelle (Whisper + Qwen2.5-3B + Piper, 30+ commandes vocales, mémoire persistante, multilingue FR/EN/AR, recherche web avec repli navigateur), calendrier SQLite avec rappels fiables, cartographie/routage offline réels (Valhalla + tuiles OSM). Chemin de reconnaissance déterministe (sans LLM) pour les commandes d'agenda et de recherche les plus fréquentes, pour garantir leur fiabilité indépendamment des aléas du modèle de langage.

**Couche matérielle :** au stade initial. Aucun Raspberry Pi physique, capteur, GPS, RTL-SDR ni batterie réelle n'a été disponible pendant le développement — ces sous-systèmes existent en code (simulation honnête, bascule automatique vers le matériel réel dès qu'il est détecté) mais n'ont jamais été validés sur le matériel visé. Voir `RISK_ASSESSMENT.md` pour le détail de ce qui bloque la validation physique.

**Cible matérielle :** Raspberry Pi 5.

---

*Ce document sert de cahier des charges complet du projet.*
