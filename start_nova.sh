#!/usr/bin/env bash
set -e

NOVA_DIR="$HOME/Bureau/nova2"
MAPS_DATA="$NOVA_DIR/maps_data"
VALHALLA_DATA="$NOVA_DIR/valhalla_data"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[nova]${NC} $1"; }
warn()  { echo -e "${YELLOW}[nova]${NC} $1"; }
error() { echo -e "${RED}[nova]${NC} $1"; }

ensure_container() {
    local name="$1"
    local create_cmd="$2"
    local port="$3"
    local test_path="$4"

    if sudo docker ps --format '{{.Names}}' | grep -qx "$name"; then
        info "$name est déjà en cours d'exécution."
    elif sudo docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
        info "$name existe mais est arrêté — redémarrage..."
        sudo docker start "$name" > /dev/null
    else
        info "$name n'existe pas encore — création..."
        eval "$create_cmd"
    fi

    info "Attente que $name réponde sur le port $port..."
    local waited=0
    until curl -s -o /dev/null "http://localhost:${port}${test_path}" 2>/dev/null; do
        sleep 2
        waited=$((waited + 2))
        if [ "$waited" -ge 90 ]; then
            warn "$name ne répond pas encore après 90s (il continue peut-être de démarrer en arrière-plan)."
            warn "Vérifie avec : sudo docker logs $name"
            return 1
        fi
    done
    info "$name est prêt !"
    return 0
}

echo ""
info "════════════════════════════════════════"
info "  Démarrage des services hors ligne NOVA"
info "════════════════════════════════════════"
echo ""

ensure_container \
    "nova-tileserver" \
    "sudo docker run -d --name nova-tileserver -v '${MAPS_DATA}':/data -p 8080:8080 maptiler/tileserver-gl --config /data/config.json" \
    "8080" \
    "/"

ensure_container \
    "nova-valhalla" \
    "sudo docker run -d --name nova-valhalla -p 8002:8002 -v '${VALHALLA_DATA}':/custom_files -e tile_urls=/custom_files/tunisia.osm.pbf ghcr.io/gis-ops/docker-valhalla/valhalla:latest" \
    "8002" \
    "/status"

ensure_container \
    "nova-nominatim" \
    "sudo docker run -d --name nova-nominatim -e PBF_PATH=/nominatim/data/tunisia.osm.pbf -p 8088:8080 -v '${MAPS_DATA}':/nominatim/data --shm-size=1g mediagis/nominatim:5.1" \
    "8088" \
    "/search?q=tunis&format=json"

echo ""
info "════════════════════════════════════════"
info "  Tous les services sont prêts. Lancement de NOVA..."
info "════════════════════════════════════════"
echo ""

cd "$NOVA_DIR"
source venv/bin/activate
python software/nova/main.py
