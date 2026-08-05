# Rapport d'audit — NOVA

**Date :** 2026-08-05
**Méthode :** 7 personas d'agents ECC (security-reviewer, code-reviewer, python-reviewer,
database-reviewer, cpp-reviewer, e2e-runner, build-error-resolver), lecture seule,
adaptés au projet réel (Python/Kivy/SQLite — les personas ECC sont écrits pour du
JS/TS/React/Postgres ; le harnais utilisé ne les expose pas non plus comme agents
directement invocables, donc chaque persona a été appliqué via un agent générique
nourri de ses instructions réelles, traduites au contexte du projet).
**Portée :** `software/` (Python/Kivy), `hardware/esp32/` (firmware), `config/`,
`scripts/`, base SQLite du calendrier.

Chaque finding indique s'il a été **corrigé** dans la foulée ou **documenté** pour
plus tard (voir `OPTIMIZATION_RECOMMENDATIONS.md` pour ce qui reste ouvert).

---

## Synthèse

| Sévérité | Trouvés | Corrigés | Documentés |
|---|---|---|---|
| CRITIQUE | 2 | 2 | 0 |
| HAUTE | 4 | 4 | 0 |
| MOYENNE | 6 | 4 | 2 |
| BASSE / INFO | ~14 | 2 | ~12 |

Aucun résultat CRITIQUE ou HAUTE n'a été laissé ouvert.

---

## CRITIQUE

### Décharge batterie continue — `Clock.schedule_interval` jamais annulé
**Agent :** code-reviewer · **Statut :** ✅ corrigé

- `software/apps/sensors/app.py` : simulation à 0.5s tournait en continu depuis le
  démarrage de l'app, écran affiché ou non. Déplacée dans `on_enter`/`on_leave`.
- `software/apps/maps/app.py` : simulation de position GPS à 2s, même schéma.
  Même correctif.
- `software/nova/ui/home_screen.py` : 3 des 4 horloges (heure, événement, capteurs,
  statut) n'étaient annulées qu'à la fermeture complète de l'app (`on_cleanup`),
  jamais en quittant l'accueil pour une autre app. Déplacées dans
  `on_pre_enter`/`on_leave`.

Le motif correct existait déjà dans `apps/radio/app.py` — servi de référence pour
les trois correctifs.

---

## HAUTE

### Chargement eager et bloquant des modèles IA au démarrage
**Agent :** python-reviewer · **Statut :** ✅ corrigé

`AppLauncher` instancie toutes les apps sur le thread principal Kivy pendant
`App.build()` (avant même le démarrage de la boucle d'événements). `AssistantApp.__init__`
appelait `get_engine()`, qui charge Whisper + le LLM (2,4 Go) + Piper de façon
synchrone — l'app entière se figeait au lancement. Chargement rendu paresseux
(au premier usage réel, dans le thread déjà utilisé par le pipeline vocal).

### Échecs de chargement/génération IA jamais remontés à l'UI
**Agent :** python-reviewer · **Statut :** ✅ corrigé

`AssistantEngine.status()`/`fully_simulated()` n'étaient appelés nulle part dans
l'UI — un OOM, un fichier GGUF corrompu ou un disque plein produisaient le même
comportement visible qu'« aucun modèle installé », en silence. L'app affiche
désormais un message explicite si le moteur tombe en simulation complète.

### Connexions SQLite jamais fermées
**Agent :** database-reviewer · **Statut :** ✅ corrigé

`software/apps/calendar/storage.py` : `with connect(...) as connection` ne gère
que la transaction en sqlite3, jamais `close()`. `due_reminders()` est interrogé
toutes les 20s en continu → fuite de descripteurs sur un appareil allumé en
permanence. Nouveau helper `_session()` qui ferme réellement la connexion.

### `due_reminders()` perd les rappels à cheval sur minuit
**Agent :** database-reviewer · **Statut :** ✅ corrigé

La requête ne filtrait que sur `event_date = aujourd'hui`. Un événement à 23:58
avec un rappel de 10 min pouvait être définitivement perdu si l'appareil
vérifiait après minuit (la date avait changé). Corrigé pour inclure hier +
aujourd'hui ; la fenêtre temporelle absolue filtre déjà correctement ce qui est
réellement dû. Testé avec une vraie base temporaire.

---

## MOYENNE

| Finding | Agent | Statut |
|---|---|---|
| Index manquant sur `events.event_date` (table scan à chaque lecture) | database-reviewer | ✅ corrigé |
| `AssistantApp.conversation = []` : attribut de **classe** mutable partagé entre instances | python-reviewer | ✅ corrigé |
| Clés API MapTiler/ORS en clair dans `config/system.json`, déjà committées sur GitHub | security-reviewer | ✅ corrigé (surcharge locale) — **rotation manuelle des clés toujours requise, voir SECURITY_REPORT.md** |
| Incohérence GPS : `gps==3.19` (requirements.txt) vs `gpsd-py3==0.3.0` (requirements-pi.txt) pour la même fonction jamais implémentée | build-error-resolver | 📋 documenté |
| Dérive de versions venv vs requirements.txt (numpy 2.x installé vs 1.26.4 épinglé — risque ABI avec llama-cpp-python/faster-whisper) | build-error-resolver | 📋 documenté |
| Duplication structurelle : `self.children[0]` répété 11 fois dans les 8 apps au lieu d'utiliser `BaseApp.content` | code-reviewer | 📋 documenté |

---

## BASSE / INFO (sélection — voir `OPTIMIZATION_RECOMMENDATIONS.md` pour la liste complète)

- Firmware ESP32 (`hardware/esp32/esp32_coprocessor.ino`) : squelette non
  fonctionnel, `sendSensorData()` renvoie des zéros codés en dur au lieu de lire
  le MPU6050. **Aucun lien logiciel réel** avec `software/` (le pont UART
  Pi↔ESP32 de la Phase 7 du cahier des charges est purement documentaire). Pas
  de bug mémoire critique (usage de `String` Arduino non borné en MEDIUM,
  watchdog absent).
- Suite pytest : fonctionne (9/9) mais `pytest` est absent du venv réel du
  projet — la commande documentée (`venv/bin/python -m pytest`) échoue telle
  quelle tant que `pip install -r requirements.txt` n'est pas relancé.
- Couverture de tests quasi nulle en dehors de `storage.py`/`paths.py`/`launcher.py` :
  zéro test sur `ai_engine.py`, `assistant_actions.py`, `web_search.py`, et les
  8 apps métier.
- `nova/assistant_actions.py` (~1150 lignes) : dispatch en 33 `if/elif` linéaires,
  fonctionnellement correct mais gagnerait à devenir un dict de handlers si le
  fichier continue de grossir.
- Pas de mécanisme de migration de schéma SQLite (`CREATE TABLE IF NOT EXISTS`
  seul) ; `SELECT *` au lieu de colonnes explicites ; absence quasi totale de
  type hints (0 sur ~509 fonctions — peu risqué vu la taille du projet et son
  usage mono-développeur).

---

## Vérification

Chaque correctif de ce rapport a été validé par `python3 -m compileall` +
`python3 -m pytest software/tests -q` (9/9), et pour les bugs logiques
(`due_reminders`, secrets, multilingue) par un test direct sur données réelles,
pas seulement une relecture de code.
