# Cahier des charges NOVA — état du projet

**Dernière mise à jour :** 2026-08-05

Ce document remplace le stub d'origine (3 lignes, renvoyant vers "le document
original du projet"). Le cahier des charges complet du projet (12 phases,
matériel + logiciel) définit l'objectif : un ordinateur porté au bras,
autonome, hors ligne, personnalisable, contrôlé par IA locale.

## Où trouver quoi

- **Conformité détaillée phase par phase** : `docs/CONFORMITY_CHECKLIST.md`
  (état réel vérifié, pas une reformulation des intentions d'origine).
- **Plan JARVIS AI v2.0** (fonctionnalités IA avancées demandées en plus du
  cahier des charges initial) : `docs/JARVIS_INTEGRATION_PLAN.md`.
- **Audit technique** (bugs trouvés/corrigés) : `docs/AUDIT_REPORT.md`.
- **Sécurité** : `docs/SECURITY_REPORT.md`.
- **Ce qui reste à faire, par priorité** : `docs/OPTIMIZATION_RECOMMENDATIONS.md`.
- **Évaluation de risque / prêt pour la suite ?** : `docs/RISK_ASSESSMENT.md`.

## Résumé de l'état actuel (voir la checklist pour le détail)

**Couche logicielle :** avancée. Interface Kivy complète (template Stitch, 3
thèmes), 8 applications fonctionnelles, IA locale réelle (Whisper + Qwen2.5-3B
+ Piper, 30+ commandes vocales, mémoire persistante, multilingue FR/EN/AR,
recherche web), calendrier SQLite avec rappels fiables, cartographie/routage
offline réels (Valhalla + tuiles OSM).

**Couche matérielle :** au stade initial. Aucun Raspberry Pi physique,
capteur, GPS, RTL-SDR ni batterie réelle n'a été disponible pendant le
développement — ces sous-systèmes existent en code (simulation honnête) mais
n'ont jamais été validés sur le matériel visé. Voir `RISK_ASSESSMENT.md` pour
le détail de ce qui bloque la validation physique.

**Cible matérielle :** Raspberry Pi 5 (confirmé — remplace le Pi Zero 2 W visé
par une partie du code d'origine ; voir `JARVIS_INTEGRATION_PLAN.md` pour les
ajustements liés à ce changement de cible).

## Ordre de réalisation recommandé (mis à jour)

Le cahier des charges d'origine proposait : interface → apps → calendrier →
assistant vocal → GPS → capteurs → communication → RTL-SDR → boîtier 3D →
version finale. Cet ordre reste globalement pertinent, avec un ajustement :
**valider les capteurs et le GPS sur le vrai matériel avant d'itérer
davantage sur le logiciel qui en dépend** (inutile de peaufiner un code qui
lit des capteurs simulés si le comportement réel réserve des surprises —
bruit, étalonnage, latence I2C). Voir `RISK_ASSESSMENT.md` §Stratégie de
mitigation.
