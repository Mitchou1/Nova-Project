#!/bin/bash
# Lance / arrête God's Eye View SANS ouvrir NOVA.
#
# Réutilise le gestionnaire de NOVA (software/nova/gods_eye_manager.py) :
# mêmes vérifications (installation, internet, port), même instance unique.
# Un serveur lancé ici est donc vu par le bouton du Terminal NOVA, et
# inversement — pas de risque d'en avoir deux.
#
# Usage : scripts/gods_eye.sh [demarrer|arreter|etat]   (défaut : demarrer)
#   --pause : attend Entrée en cas d'échec (pour l'icône du bureau, sinon
#             la fenêtre se fermerait avant qu'on puisse lire l'erreur)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

ACTION="demarrer"
PAUSE=0
for arg in "$@"; do
    case "$arg" in
        --pause) PAUSE=1 ;;
        demarrer|start) ACTION="demarrer" ;;
        arreter|stop) ACTION="arreter" ;;
        etat|status) ACTION="etat" ;;
        *) echo "Usage : $0 [demarrer|arreter|etat] [--pause]"; exit 2 ;;
    esac
done

cd "$ROOT_DIR/software" || exit 1
"$PYTHON" - "$ACTION" <<'EOF'
import sys
import threading

from nova.gods_eye_manager import charger_config, get_gods_eye, ouvrir_navigateur

action = sys.argv[1]
gestionnaire = get_gods_eye()

if action == "arreter":
    print("God's Eye View arrêté, mémoire libérée." if gestionnaire.arreter()
          else "God's Eye View ne tournait pas.")
    sys.exit(0)

if action == "etat":
    port = charger_config()["port"]
    if gestionnaire.en_marche():
        print("En marche : http://localhost:{}".format(port))
    else:
        print("Arrêté.")
    sys.exit(0)

# demarrer : attente sans limite ici, le gestionnaire applique déjà
# gods_eye.startup_timeout et renvoie une erreur s'il est dépassé.
fini = threading.Event()
resultat = {}
gestionnaire.demarrer(
    on_progress=lambda msg: None,      # déjà affiché par le journal [gods_eye]
    on_ready=lambda url: (resultat.update(url=url), fini.set()),
    on_error=lambda msg: (resultat.update(erreur=msg), fini.set()))
fini.wait()
if "erreur" in resultat:
    print("\nÉCHEC :", resultat["erreur"])
    sys.exit(1)
erreur = ouvrir_navigateur(resultat["url"])
if erreur:
    print("\n" + erreur)
    sys.exit(1)
print("\nNavigateur ouvert sur {}.".format(resultat["url"]))
print("Globe 3D lourd pour le Pi 5 : chargement long et quelques images/s, "
      "c'est normal.")
print("Pour arrêter le serveur : icône « Arrêter God's Eye » ou "
      "~/nova2/scripts/gods_eye.sh arreter")
EOF
CODE=$?

if [ "$PAUSE" -eq 1 ]; then
    if [ "$CODE" -ne 0 ]; then
        read -r -p "Appuie sur Entrée pour fermer…" _
    else
        sleep 4       # le temps de lire le message avant fermeture
    fi
fi
exit "$CODE"
