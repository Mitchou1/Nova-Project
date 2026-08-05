# Plan d'intégration JARVIS AI v2.0 — NOVA

**Date :** 2026-08-05 · Cible matérielle confirmée : **Raspberry Pi 5**
(remplace le Pi Zero 2 W visé à l'origine par une partie du code).

7 fonctionnalités demandées. Verdict par fonctionnalité, avec justification —
pas de case cochée en façade sur ce qui n'a pas pu être livré.

---

## Vue d'ensemble

| # | Fonctionnalité | Verdict | Livré cette session |
|---|---|---|---|
| 1 | NLP avancé (intention, entités, contexte, multi-tours) | **CONSTRUIT** (existant durci) | ✅ |
| 2 | Mémoire contextuelle & apprentissage | **ALLÉGÉ** (statistique, pas ML) | ✅ |
| 3 | Multilingue FR/EN/AR | **CONSTRUIT** (allégé, sans code-switching) | ✅ |
| 4 | Reconnaissance de gestes (MPU6050) | **DIFFÉRÉ** — matériel absent | ❌ (architecture prête) |
| 5 | Suggestions prédictives | **ALLÉGÉ** (statistique) | ✅ |
| 6 | Traduction temps réel hors-ligne | **DIFFÉRÉ** — hors budget mémoire | ❌ |
| 7 | Apprentissage hors-ligne (fine-tuning) | **DIFFÉRÉ** — infra absente | ❌ |

---

## 1. NLP avancé — CONSTRUIT (l'existant durci, pas de moteur parallèle)

Le système d'actions (30+ actions, `nova/assistant_actions.py`) + le chemin
rapide déterministe **est** la couche intention/entités du projet : il n'y a
pas eu de moteur NLP séparé à construire, ç'aurait été une duplication.

**Livré :**
- `execute_action()` : filet de sécurité global — une exception inattendue
  dans un handler ne fait plus planter la réponse (durcissement sur JSON
  malformé/argument inattendu du LLM).
- Historique multi-tours (`AssistantEngine.history`) : déjà câblé, désormais
  **persisté** entre redémarrages (voir #2).
- Chemin rapide étendu : langue, effacement d'historique, suggestions.

---

## 2. Mémoire contextuelle & apprentissage — ALLÉGÉ

**Demandé :** cache de préférences, apprentissage de profil, historique
multi-session, mise à jour de modèle hors ligne.

**Livré (`nova/memory_store.py`, nouveau module SQLite) :**
- Historique de conversation persistant entre redémarrages (avant : perdu à
  chaque relance, en mémoire seulement).
- Compteur de fréquence (apps/actions/destinations les plus utilisées) — une
  base **statistique** (SQL `COUNT`), explicitement pas de l'apprentissage
  automatique : aucun modèle entraîné, juste des comptes.

**Différé :** « mise à jour de modèle IA hors ligne » — voir #7, aucune
infrastructure d'entraînement n'existe ni n'est raisonnable à construire dans
une session de code.

---

## 3. Multilingue FR/EN/AR — CONSTRUIT (allégé)

**Livré :**
- `config.language` réellement exploité (existait, était ignoré partout).
- `build_system_prompt()` : l'instruction de langue de réponse a des
  variantes FR/EN/AR. Le schéma d'actions (noms d'action, clés JSON) reste
  en français dans les trois cas — ce sont des identifiants fixes du code,
  pas du texte à traduire.
- `SpeechToText.transcribe()` : la langue passée à Whisper suit la config
  au lieu d'être figée en français.
- Action `changer_langue` (chemin rapide + LLM), persistée.

**Différé, limites documentées honnêtement :**
- **Pas de code-switching** (mélanger FR+EN dans une même phrase) : nécessite
  une détection de langue au niveau du mot, hors de portée d'un ajout de
  configuration.
- **Une seule voix Piper est installée** (`fr_FR-siwis-medium.onnx`). En
  anglais/arabe, NOVA répond par écrit à l'écran plutôt que de forcer une
  synthèse vocale française sur du texte anglais/arabe, ou de prétendre à une
  voix qui n'existe pas. Ajouter une voix EN/AR est un téléchargement de
  fichier, pas un blocage architectural — laissé en travail futur simple.
- **Whisper `small`/`tiny` sur l'arabe** : qualité de transcription
  probablement plus faible qu'en français/anglais (limite du modèle, pas du
  code) — à vérifier en conditions réelles quand un micro/locuteur arabe sera
  disponible pour tester.

---

## 4. Reconnaissance de gestes (MPU6050) — DIFFÉRÉ

**Constat vérifié :** zéro code I2C/smbus2 dans tout le projet. L'app
Capteurs est 100% simulée (`random`). Aucun capteur physique dans cet
environnement de développement.

**Pourquoi différé et pas une version simulée bidon :** un « faux détecteur de
gestes » réagissant à des raccourcis clavier démontrerait un flux UI, mais ne
validerait rien de réel (le vrai problème — filtrer le bruit d'un
accéléromètre, détecter un double-tap fiable, éviter les faux positifs — est
justement ce qu'une simulation ne peut pas tester). Le construire créerait une
fausse impression de fonctionnalité livrée.

**Travail futur, quand le matériel sera branché :**
- Lecture I2C réelle du MPU6050 (`smbus2`, déjà dans `requirements.txt`).
- Détection de gestes simples par seuillage (double-tap = pic d'accélération
  détecté deux fois en <500ms ; rotation de poignet = variation angulaire sur
  l'axe concerné) — **pas du ML** dans un premier temps, un ML léger
  (classification sur fenêtre glissante) seulement si le seuillage s'avère
  insuffisant en pratique, et seulement avec de vraies données d'entraînement
  collectées sur l'appareil réel.
- Point d'intégration déjà prêt : `apps/sensors/app.py::sensor_data["mpu6050"]`
  et les actions `lire_capteur`/`etat_capteurs` existent déjà et seraient
  simplement alimentées par de vraies valeurs au lieu de valeurs simulées.

---

## 5. Suggestions prédictives — ALLÉGÉ

**Livré (`nova/assistant_actions.py::_suggestions`, action `suggestions`) :**
- Prochain événement (`storage.next_event_label()`, déjà existant).
- Destination la plus recherchée (`memory_store.top_usage("destination")`,
  s'appuie sur #2), affichée seulement à partir de 2 occurrences pour éviter
  une « suggestion » basée sur une seule recherche.

**Hors-scope explicite, pas un oubli :**
- **Contacts fréquents** : aucun sous-système contacts n'existe dans le
  projet (pas d'app Contacts, pas de table SQLite dédiée) — l'ajouter serait
  une nouvelle fonctionnalité à part entière, pas un réglage JARVIS.
- **Suggestions météo** : nécessiterait une intégration météo dédiée (comme
  `web_search.py` l'a fait pour la recherche web), pas un ajout mineur à
  empiler dans « suggestions prédictives ».

---

## 6. Traduction temps réel hors ligne — DIFFÉRÉ

Nécessite un modèle de traduction embarqué en plus de Whisper + Qwen2.5-3B +
Piper déjà résidents en mémoire. Même sur Pi 5 (RAM large), c'est un
troisième modèle à charger et maintenir, avec un vrai coût d'intégration
(choix du modèle MT, format d'échange, latence combinée STT→traduction→LLM→
traduction→TTS). Pas un ajout de session de code — nécessiterait son propre
cycle de scoping.

---

## 7. Apprentissage hors ligne — DIFFÉRÉ, sans ambiguïté

**Les 4 sous-demandes (fine-tuning de Qwen2.5-3B, adaptation à l'accent
Whisper, voix Piper adaptative, « amélioration par le feedback utilisateur »)
sont toutes hors de portée, et pas seulement « pour cette session » :**

- `llama-cpp-python` est un runtime d'**inférence uniquement** — pas
  d'entraînement. Fine-tuner un modèle 3B nécessite un framework
  d'entraînement (PyTorch/transformers + LoRA au minimum), des données
  d'entraînement qui n'existent pas, et des ressources de calcul largement
  supérieures à un Pi, même un Pi 5.
- L'adaptation d'accent Whisper et la voix Piper adaptative ont les mêmes
  contraintes fondamentales (entraînement, pas inférence).
- Rien de tout ça n'est une question de temps de développement — c'est une
  architecture différente (entraînement offboard, probablement sur un PC/
  cloud, avec les poids ré-déployés sur l'appareil), à documenter comme une
  direction possible pour une V3 si le projet évolue dans ce sens, pas comme
  un correctif ou une fonctionnalité à ajouter.

**Ce qui a été livré à la place, et qui répond au besoin réel sous-jacent**
(« que NOVA s'améliore avec l'usage ») **:** le cache de fréquence de #2 —
une forme honnête et légère de personnalisation par l'usage, sans prétendre à
de l'apprentissage automatique qui n'est pas construit.
