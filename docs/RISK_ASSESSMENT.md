# Évaluation de risque — NOVA

**Date :** 2026-08-05

## Verdict : prêt pour la production ? — Réponse scindée, pas un OUI/NON unique

Un seul verdict global serait trompeur : la couche logicielle/IA et la couche
d'intégration matérielle physique sont à des stades radicalement différents.

### Couche logicielle / IA embarquée : **PRÊTE pour un usage personnel/beta**

- Pipeline IA réel de bout en bout (Whisper → Qwen2.5-3B → Piper), testé sur
  cette session avec de vraies commandes vocales et textuelles.
- 30+ actions vocales fonctionnelles, chemin rapide déterministe, mémoire
  persistante, multilingue, recherche web réelle — testées individuellement
  sur données réelles, pas seulement relues.
- 2 bugs CRITIQUES (décharge batterie continue) et 4 bugs HAUTE (chargement
  bloquant, échecs silencieux, fuite de connexions SQLite, rappels perdus)
  trouvés par audit et corrigés dans la même session, avec vérification.
- Suite de tests automatisés : 9/9 passent, mais couverture faible en dehors
  des utilitaires (voir `OPTIMIZATION_RECOMMENDATIONS.md`).
- Une clé API tierce exposée en clair dans l'historique git — corrigé côté
  code, rotation manuelle des clés encore requise côté utilisateur.

**Recommandation :** utilisable dès maintenant pour un usage personnel sur PC
de développement. Avant un usage prolongé/multi-utilisateur : ajouter des
tests sur `ai_engine.py`/`assistant_actions.py`, régénérer le venv depuis
`requirements.txt` (dérive de versions détectée), et faire tourner les clés
API exposées.

### Couche intégration matérielle physique : **NON PRÊTE — 0% des capteurs réels**

| Sous-système | État réel |
|---|---|
| Capteurs (MPU6050, BME280, VL53L0X) | 100% simulés, zéro code I2C |
| GPS (NEO-6M) | 100% simulé |
| Radio (RTL-SDR) | 100% simulée |
| Coprocesseur ESP32 | Firmware stub, aucun lien logiciel réel |
| Batterie (MCP3008) | Code réel présent mais jamais testé sur matériel |
| Boîtier 3D | Non commencé |

Rien de tout ça n'est un défaut du travail effectué cette session — c'est
l'état de fait d'un projet développé dans un environnement sans le matériel
physique (confirmé : ni Raspberry Pi, ni capteurs, ni RTL-SDR, ni GPS, ni
batterie réelle disponibles ici). Le code est structuré pour recevoir de
vraies implémentations (points d'intégration identifiés dans
`JARVIS_INTEGRATION_PLAN.md`), mais aucune n'a été validée sur matériel réel.

**Recommandation :** ne pas présenter le projet comme "prêt pour le
prototype physique" tant que la Phase 8 (capteurs) et la Phase 6 (GPS) n'ont
pas été testées avec le vrai matériel — le risque n'est pas un bug caché,
c'est simplement l'absence totale de validation sur cet axe.

---

## Blockers identifiés

| Blocker | Bloque quoi | Sévérité |
|---|---|---|
| Aucun matériel Pi/capteurs disponible pour tester | Phases 6, 7, 8, 9, 10, 11 | Structurel — hors du périmètre d'une session de code |
| Clés API déjà exposées sur GitHub | Sécurité (usage de quota tiers) | Moyenne — action manuelle utilisateur requise |
| Couverture de tests quasi nulle sur le cœur IA | Confiance dans les futures modifications | Moyenne |
| Dérive de versions du venv (numpy 2.x) | Reproductibilité, risque ABI avec llama-cpp-python | Moyenne, non vérifiée en pratique (le venv actuel fonctionne, mais un venv frais depuis requirements.txt n'a pas été testé) |

Aucun blocker CRITIQUE ou HAUTE n'a été laissé sans correctif sur la partie
logicielle.

## Stratégie de mitigation

1. **Immédiat :** faire tourner les clés MapTiler/ORS (action utilisateur).
2. **Court terme :** régénérer le venv depuis `requirements.txt` dans un
   environnement propre et vérifier qu'aucune régression numpy 2.x n'apparaît.
3. **Avant le prototype physique :** valider Phase 8 (capteurs) et Phase 6
   (GPS) sur le matériel réel avant d'itérer davantage sur le logiciel qui en
   dépend — inutile de peaufiner du code qui lit des capteurs simulés si le
   comportement réel du MPU6050/BME280 réserve des surprises (bruit,
   étalonnage, latence I2C).
4. **Continu :** étoffer la suite de tests sur `ai_engine.py`/
   `assistant_actions.py` au fur et à mesure des prochains changements, pour
   ne pas accumuler une dette de couverture plus grande encore.
