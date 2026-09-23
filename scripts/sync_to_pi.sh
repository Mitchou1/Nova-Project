#!/usr/bin/env bash
# À lancer sur le PC : copie vers la Pi les données lourdes que Git ne
# transporte pas (cartes, itinéraires, modèles IA). rsync ne renvoie que ce
# qui a changé, donc les synchronisations suivantes sont rapides.
#
# Usage : ./scripts/sync_to_pi.sh                     trouve la Pi tout seul
#         ./scripts/sync_to_pi.sh nova@192.168.1.21   adresse donnée à la main
#         ./scripts/sync_to_pi.sh nova@IP autre_dossier   (défaut : nova2)
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_USER="nova"
REMOTE_DIR="${2:-nova2}"
DATA_DIRS=(maps_data valhalla_data models)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[nova]${NC} $1"; }
warn()  { echo -e "${YELLOW}[nova]${NC} $1"; }
error() { echo -e "${RED}[nova]${NC} $1"; }

# L'IP de la Pi change d'un réseau Wi-Fi à l'autre, mais pas son adresse
# MAC : on la cherche par les préfixes attribués à Raspberry Pi.
find_pi() {
    local subnet
    subnet="$(ip -4 route show default | awk '{print $3}' | head -1 | sed 's/\.[0-9]*$/.0\/24/')"
    if [ -n "$subnet" ] && command -v nmap > /dev/null 2>&1; then
        nmap -sn "$subnet" > /dev/null 2>&1
    fi
    ip neigh | grep -iE 'lladdr (2c:cf:67|d8:3a:dd|dc:a6:32|e4:5f:01|b8:27:eb|28:cd:c1)' \
        | grep -v FAILED | awk '{print $1}' | head -1
}

if [ -n "${1:-}" ]; then
    TARGET="$1"
else
    info "Recherche de la Raspberry Pi sur le réseau..."
    PI_IP="$(find_pi)"
    if [ -z "$PI_IP" ]; then
        error "Pi introuvable. Vérifie qu'elle est allumée et sur le même Wi-Fi,"
        error "ou donne son adresse : ./scripts/sync_to_pi.sh nova@ADRESSE_IP"
        exit 1
    fi
    TARGET="$PI_USER@$PI_IP"
    info "Pi trouvée : $TARGET"
fi

# Une seule connexion SSH partagée : le mot de passe n'est demandé qu'une fois.
SSH_SOCKET="/tmp/nova-sync-$$"
SSH_CMD="ssh -o ControlMaster=auto -o ControlPath=$SSH_SOCKET -o ControlPersist=120"
trap 'ssh -o ControlPath="$SSH_SOCKET" -O exit "$TARGET" 2> /dev/null' EXIT

$SSH_CMD "$TARGET" "mkdir -p '$REMOTE_DIR'" || { error "Connexion SSH à $TARGET impossible."; exit 1; }

for dir in "${DATA_DIRS[@]}"; do
    if [ ! -d "$ROOT_DIR/$dir" ]; then
        warn "$dir absent sur ce PC — ignoré."
        continue
    fi
    info "Envoi de $dir..."
    rsync -a --info=progress2 --exclude '.cache/' -e "$SSH_CMD" \
        "$ROOT_DIR/$dir/" "$TARGET:$REMOTE_DIR/$dir/" \
        || { error "Échec de l'envoi de $dir."; exit 1; }
done

info "Données synchronisées. Sur la Pi : cd ~/$REMOTE_DIR && ./start_nova.sh"
