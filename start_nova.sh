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
            warn "Les tuiles routières sont peut-être toujours en cours de construction — vérifie : sudo docker logs nova-valhalla"
            return 1
        fi
        if [ $((waited % 30)) -eq 0 ]; then
            warn "Valhalla construit encore ses tuiles routières... (${waited}s)"
        fi
    done
}
wait_for_valhalla_routing

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
