# Rapport de sécurité — NOVA

**Date :** 2026-08-05 · **Méthode :** persona security-reviewer (OWASP, secrets,
injection, SSRF), adapté à un projet Python/Kivy hors ligne — pas d'auth,
pas d'API publique, surface d'attaque très différente d'une app web.

## Synthèse

| Sévérité | Nombre | Statut |
|---|---|---|
| CRITIQUE | 0 | — |
| HAUTE | 0 | — |
| MOYENNE | 1 | ✅ corrigé côté code, ⚠️ action manuelle utilisateur requise |
| BASSE | 3 | 📋 documenté, aucun scénario d'exploitation actif |

**Verdict global :** aucune injection SQL, SSRF ou injection de commande
exploitable trouvée. Les requêtes SQL sont systématiquement paramétrées, les
appels `subprocess` utilisent des listes d'arguments avec des valeurs bornées
(jamais de texte libre issu du LLM, jamais `shell=True`), et l'explorateur de
fichiers reste confiné à `data/` en pratique.

---

## [MOYENNE] Clés API tierces en clair, commitées dans l'historique git

**Trouvé dans :** `config/system.json` (`map.api_key` MapTiler, `map.ors_key`
OpenRouteService) — confirmé présent dans le commit baseline du dépôt.

**Scénario :** le dépôt est poussé sur `github.com/Mitchou1/Nova-Project`
(public ou privé selon les réglages du compte). Un scraper de secrets
automatisé (ou un simple accès au dépôt) récupère les deux clés et peut
consommer/épuiser le quota du compte MapTiler/ORS de l'utilisateur. Pas
d'accès à des données utilisateur, pas d'exécution de code — impact limité
à un abus de quota facturable.

**Corrigé côté code :** nouveau mécanisme de surcharge locale —
`config/system.local.json` (jamais suivi par git, voir `.gitignore`), fusionné
par-dessus la config normale par `ConfigLoader`. `config/system.json` ne
contient plus que des clés vides ; `config/system.local.json.example` documente
le format attendu. Un bug a été trouvé et corrigé dans ce mécanisme lui-même
pendant son implémentation : `ConfigLoader.save()` réécrivait initialement le
dict fusionné (donc les secrets) dans le fichier suivi dès le premier
changement de réglage — corrigé et testé explicitement (voir
`JARVIS_INTEGRATION_PLAN.md` / commit associé).

**⚠️ Action restante, seul l'utilisateur peut la faire :** les deux clés sont
déjà exposées dans l'historique git local ET déjà poussées sur GitHub (merge
de la PR #1). Les retirer du fichier ne les efface pas de l'historique.
Recommandation :
1. Faire tourner (régénérer) les deux clés sur les tableaux de bord MapTiler
   et OpenRouteService.
2. Mettre les nouvelles clés dans `config/system.local.json` (jamais commité).
3. La réécriture de l'historique git (`git filter-repo`/BFG) n'a **pas** été
   tentée ici : le dépôt est déjà partagé (poussé, mergé sur `main`), une
   réécriture forcerait un `push --force` sur une branche partagée — action
   destructive hors du périmètre de cet audit, à décider explicitement par
   l'utilisateur s'il la souhaite malgré tout.

---

## [BASSE] Filtrage de nom incomplet dans l'explorateur de fichiers

**Trouvé dans :** `software/apps/files/app.py` (`creer_dossier`, `renommer`)

Le filtre de nom retire les séparateurs (`/\:*?"<>|`) mais pas les composants
spéciaux `.`/`..`. `creer_dossier("..")` ou `renommer(chemin, "..")` ne sont
pas exploitables aujourd'hui (le check `cible.exists()` bloque en pratique dans
la quasi-totalité des cas), mais c'est une protection accidentelle, pas une
validation explicite. Le canal vocal (`assistant_actions.py::_fichiers_*`)
n'est pas affecté : il ne cible que des entrées réellement listées par
`iterdir()`.

**Recommandation (non appliquée, faible priorité) :** rejeter explicitement
`nom in (".", "..")` avant construction du chemin, et vérifier
`cible.resolve().is_relative_to(racine.resolve())` en défense en profondeur.

## [BASSE] `config/wifi_setup.sh` — SSID/mot de passe non échappés

Script d'administration manuelle, **non appelé nulle part** dans le code Python
(vérifié). Un SSID contenant des caractères spéciaux pourrait injecter des
directives dans `wpa_supplicant.conf` — risque réel uniquement si ce script
est un jour intégré à un flux automatisé.

## [BASSE] `start_nova.sh` — `eval` sur une chaîne dérivée de `$HOME`

Anti-pattern (`eval "$create_cmd"`), aucune entrée utilisateur directe
aujourd'hui. Recommandation : remplacer par un tableau bash (`cmd=(...)`).

---

## Aucun résultat sur

- `nova/web_search.py` : timeout 6s partout, URLs construites uniquement via
  `urllib.parse.urlencode`/`quote`, aucune URL arbitraire dérivée de l'entrée
  utilisateur → pas de SSRF.
- `apps/calendar/storage.py` : 100% requêtes paramétrées, aucune concaténation SQL.
- `nova/tileserver_manager.py` : `subprocess` en listes d'arguments fixes.
- `nova/assistant_actions.py` : tous les `subprocess.run` (wifi, bluetooth,
  volume) utilisent des valeurs strictement bornées/coercées, jamais de texte
  libre issu du LLM directement injecté en shell.
