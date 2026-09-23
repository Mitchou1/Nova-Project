#!/usr/bin/env bash
# Lance NOVA de bout en bout, sur le PC comme sur la Pi :
#   1. prépare l'environnement Python (venv + dépendances, seulement si
#      les fichiers requirements ont changé depuis la dernière fois) ;
#   2. démarre les services de carte hors ligne (Docker) ;
#   3. lance l'application.
# Aucun service manquant ne bloque le lancement : NOVA démarre toujours et
# retombe sur les services en ligne quand un service local n'est pas prêt.
#
# Usage : ./start_nova.sh                 tout préparer puis lancer NOVA
#         ./start_nova.sh --setup-only    préparer Python sans lancer
#         ./start_nova.sh --no-services   lancer sans démarrer Docker
set -u

# Dossier du projet = dossier de ce script (marche sur le PC ~/Bureau/nova2
# comme sur la Pi ~/nova2, quel que soit l'endroit du clone).
NOVA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAPS_DATA="$NOVA_DIR/maps_data"
VALHALLA_DATA="$NOVA_DIR/valhalla_data"
VENV="$NOVA_DIR/venv"
DEPS_STAMP="$VENV/.nova-requirements.sha256"
DEPS_FAILED_STAMP="$VENV/.nova-requirements.failed"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[nova]${NC} $1"; }
warn()  { echo -e "${YELLOW}[nova]${NC} $1"; }
error() { echo -e "${RED}[nova]${NC} $1"; }
title() {
    echo ""
    info "════════════════════════════════════════"
    info "  $1"
    info "════════════════════════════════════════"
    echo ""
}

SETUP_ONLY=0
NO_SERVICES=0
for arg in "$@"; do
    case "$arg" in
        --setup-only)  SETUP_ONLY=1 ;;
        --no-services) NO_SERVICES=1 ;;
        *) error "Option inconnue : $arg"; exit 2 ;;
    esac
done

cd "$NOVA_DIR"

is_pi() {
    case "$(uname -m)" in aarch64|armv7l) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------------------
# 1. Environnement Python
# ---------------------------------------------------------------------------

requirement_files() {
    echo "requirements.txt"
    if is_pi; then echo "requirements-pi.txt"; fi
}

# Installe paquet par paquet : un paquet qui ne compile pas (fréquent sur Pi)
# n'empêche plus l'installation de tous les autres.
install_requirements_one_by_one() {
    local failed=()
    local file line
    for file in $(requirement_files); do
        while IFS= read -r line || [ -n "$line" ]; do
            line="${line%%#*}"
            line="$(echo "$line" | xargs)"
            [ -z "$line" ] && continue
            if ! pip install -q "$line"; then
                failed+=("$line")
            fi
        done < "$file"
    done
    if [ "${#failed[@]}" -gt 0 ]; then
        warn "Paquets non installés :"
        for line in "${failed[@]}"; do warn "   - $line"; done
        return 1
    fi
    return 0
}

setup_python() {
    if [ ! -x "$VENV/bin/python" ]; then
        info "Création de l'environnement Python (venv)..."
        # Sur la Pi, le venv voit aussi les paquets système (picamera2,
        # libcamera, kivy apt...) qui ne s'installent pas bien via pip.
        local venv_opts=()
        if is_pi; then venv_opts+=(--system-site-packages); fi
        if ! python3 -m venv "${venv_opts[@]}" "$VENV"; then
            error "Impossible de créer le venv. Installe-le avec : sudo apt install python3-venv"
            return 1
        fi
    fi

    # shellcheck disable=SC1091
    source "$VENV/bin/activate"

    local files hash
    files="$(requirement_files)"
    # shellcheck disable=SC2086
    hash="$(cat $files | sha256sum | cut -d' ' -f1)"

    if [ -f "$DEPS_STAMP" ] && [ "$(cat "$DEPS_STAMP")" = "$hash" ]; then
        info "Dépendances Python à jour."
        return 0
    fi
    # Un échec déjà constaté pour ces mêmes fichiers n'est pas retenté à
    # chaque lancement (une compilation ratée sur Pi peut prendre 20 min) :
    # seul --setup-only relance la tentative.
    if [ "$SETUP_ONLY" -eq 0 ] && [ -f "$DEPS_FAILED_STAMP" ] \
            && [ "$(cat "$DEPS_FAILED_STAMP")" = "$hash" ]; then
        warn "Certaines dépendances manquent encore (échec précédent)."
        warn "Pour réessayer : ./start_nova.sh --setup-only"
        return 0
    fi

    # shellcheck disable=SC2086
    info "Installation des dépendances Python ($(echo $files))..."
    info "La première fois, cela peut prendre plusieurs minutes."
    pip install -q --upgrade pip

    local pip_args=()
    local f
    for f in $files; do pip_args+=(-r "$f"); done

    if pip install "${pip_args[@]}" || install_requirements_one_by_one; then
        echo "$hash" > "$DEPS_STAMP"
        rm -f "$DEPS_FAILED_STAMP"
        info "Dépendances Python installées."
    else
        echo "$hash" > "$DEPS_FAILED_STAMP"
        warn "NOVA démarre quand même ; les fonctions liées à ces paquets seront désactivées."
    fi
}

# Liste les fichiers lourds absents de Git (modèles IA, cartes) pour dire
# tout de suite quoi copier au lieu de laisser l'app échouer plus tard.
check_data_files() {
    local missing
    missing="$(python - <<'EOF'
import json
from pathlib import Path

config = json.loads(Path("config/system.json").read_text())
local = Path("config/system.local.json")
if local.exists():
    try:
        config.setdefault("ai", {}).update(json.loads(local.read_text()).get("ai", {}))
    except ValueError:
        pass
ai = config.get("ai", {})
wanted = [
    Path("models/llm") / ai.get("llm_model", ""),
    Path("models/tts") / ai.get("tts_voice", ""),
    Path("maps_data/tunisia.mbtiles"),
    Path("valhalla_data/tunisia.osm.pbf"),
]
for path in wanted:
    if not path.is_file():
        print(path)
EOF
)"
    if [ -n "$missing" ]; then
        warn "Fichiers lourds absents (non suivis par Git) :"
        echo "$missing" | while read -r path; do warn "   - $path"; done
        warn "Copie-les depuis le PC avec : ./scripts/sync_to_pi.sh"
    fi
}

# ---------------------------------------------------------------------------
# 2. Services de carte hors ligne (Docker)
# ---------------------------------------------------------------------------

DOCKER="docker"

setup_docker() {
    if ! command -v docker > /dev/null 2>&1; then
        warn "Docker n'est pas installé : cartes et itinéraires hors ligne indisponibles."
        warn "Installation : curl -fsSL https://get.docker.com | sudo sh"
        return 1
    fi
    if ! docker info > /dev/null 2>&1; then
        DOCKER="sudo docker"
        warn "Docker demande sudo. Pour ne plus taper le mot de passe :"
        warn "   sudo usermod -aG docker $USER   (puis déconnexion/reconnexion)"
    fi
    return 0
}

# Attend qu'une URL réponde, sans jamais bloquer NOVA au-delà du délai.
wait_for_http() {
    local url="$1" timeout="$2"
    local waited=0
    until curl -s -o /dev/null "$url" 2>/dev/null; do
        if [ "$waited" -ge "$timeout" ]; then
            return 1
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 0
}

# ensure_container NOM "COMMANDE_CREATION" FICHIER_REQUIS URL_TEST DELAI
# Démarre (ou crée) le conteneur. Ne le crée jamais si ses données manquent :
# Docker créerait sinon un dossier vide appartenant à root, et le conteneur
# tournerait en boucle sur une erreur de permission.
ensure_container() {
    local name="$1" create_cmd="$2" required_file="$3" url="$4" timeout="$5"

    if $DOCKER ps --format '{{.Names}}' | grep -qx "$name"; then
        info "$name est déjà en cours d'exécution."
    elif $DOCKER ps -a --format '{{.Names}}' | grep -qx "$name"; then
        info "$name est arrêté — redémarrage..."
        $DOCKER start "$name" > /dev/null
    elif [ ! -f "$required_file" ]; then
        warn "$name non créé : fichier manquant ${required_file#"$NOVA_DIR"/}"
        return 1
    else
        info "$name n'existe pas encore — création..."
        eval "$create_cmd" > /dev/null || { error "Création de $name impossible."; return 1; }
    fi

    # Redémarre tout seul avec la Pi : plus besoin de relancer à la main.
    $DOCKER update --restart unless-stopped "$name" > /dev/null 2>&1

    if [ "$timeout" -eq 0 ]; then
        curl -s -o /dev/null "$url" 2>/dev/null
        return $?
    fi
    info "Attente de $name..."
    if wait_for_http "$url" "$timeout"; then
        info "$name est prêt !"
        return 0
    fi
    warn "$name ne répond pas encore après ${timeout}s — NOVA démarre quand même."
    warn "Détails : $DOCKER logs --tail 20 $name"
    return 1
}

# /status répond dès que le serveur HTTP de Valhalla est lancé, mais ses
# tuiles routières peuvent encore être en cours de construction en arrière
# plan (long avec un extrait pays) : un calcul d'itinéraire pendant cette
# fenêtre renvoie un trajet dégradé à 2 points, affiché comme une ligne
# droite dans l'app — bug reel observe, corrige jusqu'ici en redemarrant le
# conteneur a la main. On attend ici que Valhalla puisse VRAIMENT calculer
# un trajet (test sur deux points proches de Tunis) avant de lancer l'app.
wait_for_valhalla_routing() {
    info "Vérification que Valhalla peut calculer un itinéraire (tuiles chargées)..."
    local test_body='{"locations":[{"lat":36.8065,"lon":10.1815},{"lat":36.815,"lon":10.19}],"costing":"auto"}'
    local waited=0
    while true; do
        local response
        response=$(curl -s -X POST -H "Content-Type: application/json" \
            -d "$test_body" "http://localhost:8002/route" 2>/dev/null)
        if echo "$response" | grep -q '"legs"'; then
            info "Valhalla peut calculer des itinéraires."
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
        if [ "$waited" -ge 600 ]; then
            warn "Valhalla ne calcule toujours pas d'itinéraire après 10 min."
            warn "Les tuiles routières sont peut-être toujours en cours de construction — vérifie : $DOCKER logs nova-valhalla"
            return 1
        fi
        if [ $((waited % 30)) -eq 0 ]; then
            warn "Valhalla construit encore ses tuiles routières... (${waited}s)"
        fi
    done
}

start_services() {
    setup_docker || return 0

    ensure_container \
        "nova-tileserver" \
        "$DOCKER run -d --name nova-tileserver -v '${MAPS_DATA}':/data -p 8080:8080 maptiler/tileserver-gl --config /data/config.json" \
        "$MAPS_DATA/tunisia.mbtiles" \
        "http://localhost:8080/" \
        90

    if ensure_container \
        "nova-valhalla" \
        "$DOCKER run -d --name nova-valhalla -p 8002:8002 -v '${VALHALLA_DATA}':/custom_files -e tile_urls=/custom_files/tunisia.osm.pbf ghcr.io/gis-ops/docker-valhalla/valhalla:latest" \
        "$VALHALLA_DATA/tunisia.osm.pbf" \
        "http://localhost:8002/status" \
        90; then
        wait_for_valhalla_routing
    fi

    # Nominatim est facultatif (navigation.py bascule sur la recherche en
    # ligne s'il ne répond pas) et son premier import peut durer plus d'une
    # heure sur Pi : on le démarre sans jamais l'attendre.
    if ensure_container \
        "nova-nominatim" \
        "$DOCKER run -d --name nova-nominatim -e PBF_PATH=/nominatim/data/tunisia.osm.pbf -p 8088:8080 -v '${MAPS_DATA}':/nominatim/data --shm-size=1g mediagis/nominatim:5.1" \
        "$MAPS_DATA/tunisia.osm.pbf" \
        "http://localhost:8088/search?q=tunis&format=json" \
        0; then
        info "nova-nominatim est prêt (recherche d'adresses hors ligne)."
    else
        warn "nova-nominatim pas encore prêt (1er import : 30 à 90 min sur Pi)."
        warn "En attendant, la recherche d'adresses passe par Internet."
    fi
}

# ---------------------------------------------------------------------------
# 3. Lancement
# ---------------------------------------------------------------------------

title "Préparation de NOVA"
setup_python || exit 1
check_data_files

if [ "$SETUP_ONLY" -eq 1 ]; then
    info "Préparation terminée (--setup-only)."
    exit 0
fi

if [ "$NO_SERVICES" -eq 0 ]; then
    title "Démarrage des services hors ligne"
    start_services
fi

if ! python -c "import kivy" > /dev/null 2>&1; then
    error "Kivy (l'interface graphique) n'est pas installé : NOVA ne peut pas s'afficher."
    error "Réessaie : ./start_nova.sh --setup-only   (ou sur Pi : sudo apt install python3-kivy)"
    exit 1
fi

title "Lancement de NOVA"
exec python software/nova/main.py
