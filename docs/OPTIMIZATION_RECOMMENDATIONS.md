# Recommandations d'optimisation — NOVA

**Date :** 2026-08-05. Ce qui a été **corrigé** cette session est dans
`AUDIT_REPORT.md`. Ce document liste ce qui **reste ouvert**, par priorité,
pour un travail futur.

---

## Priorité haute (à traiter avant la prochaine itération)

### Régénérer le venv depuis `requirements.txt`
**Trouvé par :** build-error-resolver

Le venv réel du projet a dérivé des versions épinglées : numpy **2.5.1**
installé vs **1.26.4** épinglé (changement de version majeure 1.x→2.x, risque
de rupture ABI avec `llama-cpp-python`/`faster-whisper`, souvent compilés
contre numpy 1.x), Kivy 2.3.1 vs 2.3.0, `pytest` absent du venv alors qu'il
est dans `requirements.txt`. Recommandation : `pip install -r requirements.txt`
dans un venv propre, et vérifier explicitement la compatibilité numpy 2.x
avant de la figer comme cible.

### Unifier `requirements.txt` et `requirements-pi.txt` sur le GPS
`gps==3.19` (requirements.txt) et `gpsd-py3==0.3.0` (requirements-pi.txt) sont
deux bibliothèques différentes et non interchangeables pour une fonction GPS
qui n'est de toute façon pas encore implémentée (Phase 6). Choisir une seule
approche (`gpsd-py3` + démon `gpsd` est la voie la plus simple sur Pi) avant
d'implémenter la lecture réelle du NEO-6M.

### Ajouter des tests sur le cœur fonctionnel
**Trouvé par :** e2e-runner

Couverture actuelle : `storage.py`, `paths.py`, `launcher.py` — soit 3 modules
utilitaires. **Zéro test** sur `ai_engine.py`, `assistant_actions.py` (30+
actions, chemin rapide, mémoire), `web_search.py`, et les 8 apps métier. Le
risque de régression silencieuse est réel vu le volume de logique ajouté
cette session sans harnais de test dédié (au-delà des vérifications manuelles
effectuées pendant le développement).

---

## Priorité moyenne

### Factoriser `self.children[0]` (11 occurrences dans les 8 apps)
**Trouvé par :** code-reviewer

`BaseApp.build_ui()` construit `self.content` comme zone de contenu
officielle, mais aucune app ne l'utilise — toutes récupèrent `root` via
`self.children[0]` (dépendant de l'ordre d'ajout interne des widgets).
Fragile : un futur changement dans `build_ui()` casserait silencieusement les
8 apps. Recommandation : exposer `self.main` (alias de `root`) dans
`BaseApp.build_ui()` et migrer les 11 occurrences.

### Migrations de schéma SQLite
`apps/calendar/storage.py` et `nova/memory_store.py` utilisent
`CREATE TABLE IF NOT EXISTS` sans mécanisme de version. Un futur ajout de
colonne cassera les bases déjà déployées. Recommandation : `PRAGMA
user_version` + `ALTER TABLE` conditionnels.

### Refactoriser `execute_action` en dict de dispatch
**Trouvé par :** code-reviewer

33 branches `if action == "...":` linéaires dans `nova/assistant_actions.py`
(maintenant ~1200 lignes). Fonctionnellement correct, mais un dict
`{"action_name": handler}` serait plus maintenable si le fichier continue de
grossir. Envisager aussi de scinder le fichier par domaine (agenda, capteurs,
fichiers, radio, langue) au-delà de 1500 lignes.

### `SELECT *` → colonnes explicites
`apps/calendar/storage.py` (`get_events_for`, `due_reminders`). Une colonne
ajoutée plus tard changerait silencieusement la forme des dicts retournés.

### Firmware ESP32 : décider stub ou vraie intégration
`hardware/esp32/esp32_coprocessor.ino` ne lit jamais réellement le MPU6050
(`sendSensorData()` renvoie des zéros codés en dur) et n'est relié à aucun
code Python. Soit l'implémenter réellement en lien avec la Phase 8 (gestes),
soit documenter explicitement qu'il s'agit d'un placeholder pour ne pas
laisser croire à un pont UART fonctionnel (Phase 7).

---

## Priorité basse

- Type hints quasi absents (0 sur ~509 fonctions) — non bloquant vu la taille
  du projet, prioriser `ai_engine.py`/`assistant_actions.py` si du temps est
  investi.
- `id=` masque le builtin dans `apps/calendar/app.py:33` (cosmétique).
- `except Exception: pass` sans trace dans `map_engine.py`, `settings/app.py`
  (incohérent avec le reste du projet qui logge systématiquement).
- `PRAGMA journal_mode=WAL` non configuré sur les connexions SQLite — coût
  quasi nul, améliorerait la résilience aux coupures d'alimentation sur un
  appareil embarqué.

---

## Note sur les objectifs de performance

Le cahier des charges vise `< 512MB` de mémoire pic — cette cible était
dimensionnée pour le Pi Zero 2W. Depuis la confirmation du Pi 5 comme cible
(RAM très supérieure), cette contrainte n'est plus le facteur limitant :
la vraie priorité de performance devient la **latence perçue**, déjà
partiellement traitée cette session (streaming réel des réponses LLM,
chargement paresseux du moteur IA). Une mesure de latence réelle sur Pi 5
physique reste nécessaire avant de considérer la Phase 4 comme conforme aux
objectifs chiffrés.
