#!/usr/bin/env bash
# Lance NOVA de bout en bout, sur le PC comme sur la Pi :
#   1. prépare l'environnement Python (venv + dépendances, seulement si
#      les fichiers requirements ont changé depuis la dernière fois) ;
#   2. vérifie les modèles d'IA (télécharge Whisper une fois si besoin) ;
#   3. démarre les services de carte hors ligne (Docker), SANS les attendre ;
#   4. sur la Pi : I2C (batterie de l'UPS), groupes, Bluetooth, alimentation ;
#   5. lance l'application, et la relance si on appuie sur « Redémarrer ».
# Aucune étape manquante ne bloque le lancement : NOVA démarre toujours et
# affiche lui-même ce qui est indisponible (pastille LOCAL / DÉMARRAGE /
# INDISPONIBLE dans Maps, état réel dans Paramètres) — sans jamais basculer
# en silence sur des services internet.
#
# Usage : ./start_nova.sh                 tout préparer puis lancer NOVA
#         ./start_nova.sh --setup-only    préparer (Python, modèles, Pi) sans lancer
#         ./start_nova.sh --no-services   lancer sans démarrer Docker
#         ./start_nova.sh --no-sudo       ne jamais demander de mot de passe
#         ./start_nova.sh --autostart     lancer NOVA à l'ouverture de session
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
NO_SUDO=0
AUTOSTART=0
for arg in "$@"; do
    case "$arg" in
        --setup-only)  SETUP_ONLY=1 ;;
        --no-services) NO_SERVICES=1 ;;
        --no-sudo)     NO_SUDO=1 ;;
        --autostart)   AUTOSTART=1 ;;
        -h|--help)     sed -n '2,20p' "$0"; exit 0 ;;
        *) error "Option inconnue : $arg"; exit 2 ;;
    esac
done
LOG_DIR="$NOVA_DIR/data/logs"
CODE_REDEMARRAGE=42       # os._exit(42) : bouton « Redémarrer NOVA »

cd "$NOVA_DIR"

is_pi() {
    case "$(uname -m)" in aarch64|armv7l) return 0 ;; *) return 1 ;; esac
}

# sudo seulement si nécessaire : jamais avec --no-sudo, et jamais sans
# terminal (démarrage automatique) — on signale alors au lieu d'attendre un
# mot de passe que personne ne tapera.
peut_sudo() {
    [ "$NO_SUDO" -eq 0 ] || return 1
    sudo -n true 2>/dev/null && return 0
    [ -t 0 ]
}

dans_groupe() { id -nG "$USER" | tr ' ' '\n' | grep -qx "$1"; }

# Lit une clé de config/system.json : lire_config ai whisper_model <défaut>
lire_config() {
    python3 - "$NOVA_DIR/config/system.json" "$@" <<'EOF' 2>/dev/null
import json, sys
chemin, cles, defaut = sys.argv[1], sys.argv[2:-1], sys.argv[-1]
try:
    v = json.load(open(chemin))
    for c in cles:
        v = v[c]
    print("true" if v is True else "false" if v is False else v)
except Exception:
    print(defaut)
EOF
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

# Whisper est chargé avec local_files_only=True (aucun accès réseau au
# démarrage de NOVA) : il doit donc être dans le cache. Téléchargé une fois.
check_whisper() {
    local modele cache
    modele="$(lire_config ai whisper_model small)"
    cache="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-$modele"
    if [ -d "$cache" ]; then
        info "Whisper « $modele » en cache local."
        return 0
    fi
    if ! python -c "import faster_whisper" > /dev/null 2>&1; then
        warn "faster-whisper non installé : reconnaissance vocale en simulation (scripts/setup_ai.sh)."
        return 0
    fi
    info "Téléchargement unique de Whisper « $modele » (reconnaissance vocale)..."
    if python -c "from faster_whisper import WhisperModel; WhisperModel('$modele', device='cpu', compute_type='int8')" \
            > /dev/null 2>&1; then
        info "Whisper téléchargé."
    else
        warn "Téléchargement de Whisper impossible (pas d'internet ?) : reconnaissance vocale en simulation."
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
        if ! systemctl is-active --quiet docker 2>/dev/null && peut_sudo; then
            sudo systemctl enable --now docker > /dev/null 2>&1 && info "Service Docker démarré."
        fi
    fi
    if ! docker info > /dev/null 2>&1; then
        # NOVA pilote Docker SANS sudo (map_services.py) : sans le groupe
        # docker, il ne pourra ni relancer ni surveiller les conteneurs.
        if peut_sudo && ! dans_groupe docker; then
            sudo usermod -aG docker "$USER" && \
                warn "Ajouté au groupe docker : reconnecte-toi (ou redémarre) pour l'activer."
        else
            warn "Docker demande sudo : NOVA ne pourra pas surveiller les cartes."
            warn "   sudo usermod -aG docker $USER   (puis déconnexion/reconnexion)"
        fi
        peut_sudo || return 1
        DOCKER="sudo docker"
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

    # Délai 0 : on ne fait que constater l'état. NOVA vérifie ensuite lui-
    # même que le service marche vraiment et l'affiche (map_services.py).
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

start_services() {
    setup_docker || return 0

    # Aucun conteneur n'est attendu ici (avant : jusqu'à 90 s pour les
    # tuiles, puis jusqu'à 10 min pour les tuiles routières de Valhalla).
    # NOVA démarre tout de suite ; Maps affiche « DÉMARRAGE » puis « LOCAL »
    # dès que chaque service fonctionne vraiment (map_services.py).
    ensure_container \
        "nova-tileserver" \
        "$DOCKER run -d --restart unless-stopped --name nova-tileserver -v '${MAPS_DATA}':/data -p 8080:8080 maptiler/tileserver-gl --config /data/config.json" \
        "$MAPS_DATA/tunisia.mbtiles" \
        "http://localhost:8080/" \
        0 || info "nova-tileserver démarre (Maps affichera son état)."

    ensure_container \
        "nova-valhalla" \
        "$DOCKER run -d --restart unless-stopped --name nova-valhalla -p 8002:8002 -v '${VALHALLA_DATA}':/custom_files -e tile_urls=/custom_files/tunisia.osm.pbf ghcr.io/gis-ops/docker-valhalla/valhalla:latest" \
        "$VALHALLA_DATA/tunisia.osm.pbf" \
        "http://localhost:8002/status" \
        0 || info "nova-valhalla démarre (itinéraires disponibles dès que ses tuiles sont chargées)."

    # Le premier import de Nominatim peut durer plus d'une heure sur Pi : on
    # le démarre sans l'attendre. Pas de repli internet silencieux : tant
    # qu'il n'est pas prêt, Maps affiche clairement que la recherche est
    # indisponible (sauf si "allow_online_fallback" est activé).
    if ensure_container \
        "nova-nominatim" \
        "$DOCKER run -d --restart unless-stopped --name nova-nominatim -e PBF_PATH=/nominatim/data/tunisia.osm.pbf -p 8088:8080 -v '${MAPS_DATA}':/nominatim/data -v nova-nominatim-db:/var/lib/postgresql/16/main --shm-size=1g mediagis/nominatim:5.1" \
        "$MAPS_DATA/tunisia.osm.pbf" \
        "http://localhost:8088/search?q=tunis&format=json" \
        0; then
        info "nova-nominatim est prêt (recherche d'adresses hors ligne)."
    else
        warn "nova-nominatim pas encore prêt (1er import : 30 à 90 min sur Pi)."
        warn "NE PAS éteindre la Pi pendant l'import : une coupure corrompt la base"
        warn "(NOVA la répare alors tout seul, mais tout l'import est à refaire)."
        warn "En attendant, Maps indique que la recherche d'adresses est indisponible."
    fi
}

# ---------------------------------------------------------------------------
# 3. Matériel de la Pi (UPS HAT, Bluetooth, alimentation, clavier)
# ---------------------------------------------------------------------------

check_pi_hardware() {
    is_pi || return 0
    # I2C : lecture de la batterie de l'UPS HAT (et futurs capteurs)
    if [ -e /dev/i2c-1 ]; then
        info "Bus I2C actif (batterie de l'UPS lisible)."
    elif peut_sudo; then
        if sudo raspi-config nonint do_i2c 0 && sudo modprobe i2c-dev; then
            info "I2C activé."
        else
            warn "Activation de l'I2C impossible : sudo raspi-config → Interface → I2C."
        fi
    else
        warn "I2C désactivé : batterie de l'UPS illisible (sudo raspi-config → Interface → I2C)."
    fi
    if ! dans_groupe i2c; then
        if peut_sudo; then
            sudo usermod -aG i2c "$USER" && warn "Ajouté au groupe i2c : reconnecte-toi pour l'activer."
        else
            warn "« $USER » n'est pas dans le groupe i2c (sudo usermod -aG i2c $USER)."
        fi
    fi
    # Bluetooth : service arrêté = état illisible dans les Paramètres
    if ! systemctl is-active --quiet bluetooth; then
        if peut_sudo && sudo systemctl enable --now bluetooth; then
            info "Service Bluetooth démarré."
        else
            warn "Service Bluetooth arrêté : sudo systemctl enable --now bluetooth"
        fi
    fi
    # Alimentation : avertissement 5V/5A du Pi 5 avec un UPS sans USB-PD
    if command -v vcgencmd > /dev/null 2>&1; then
        local t
        t="$(vcgencmd get_throttled 2>/dev/null | sed 's/.*=//')"
        if [ "$t" = "0x0" ]; then
            info "Alimentation correcte (aucune sous-tension)."
        else
            warn "Alimentation : get_throttled=$t (sous-tension détectée — détail dans Paramètres)."
        fi
    fi
    # Clavier du système affiché en plus de celui de NOVA ?
    if [ "$(lire_config screen virtual_keyboard auto)" != "false" ] && pgrep -x squeekboard > /dev/null; then
        warn "Le clavier du système (squeekboard) tourne : il peut s'afficher en plus de celui de NOVA."
        warn "   Préférences → Configuration du Raspberry Pi → Affichage → Clavier virtuel : désactivé"
    fi
}

setup_autostart() {
    mkdir -p "$HOME/.config/autostart"
    cat > "$HOME/.config/autostart/nova.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=NOVA
Comment=Assistant personnel NOVA
Exec=$NOVA_DIR/start_nova.sh --no-sudo
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
    info "NOVA se lancera à l'ouverture de session (~/.config/autostart/nova.desktop)."
}

# ---------------------------------------------------------------------------
# 4. Lancement
# ---------------------------------------------------------------------------

title "Préparation de NOVA"
setup_python || exit 1
check_data_files
check_whisper
check_pi_hardware
[ "$AUTOSTART" -eq 1 ] && setup_autostart

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
mkdir -p "$LOG_DIR"
# Boucle : le bouton « Redémarrer NOVA » quitte avec le code 42, et NOVA
# est relancé aussitôt. Tout autre code termine le script.
while true; do
    info "Journal : data/logs/nova.log"
    PYTHONUNBUFFERED=1 python software/nova/main.py 2>&1 | tee -a "$LOG_DIR/nova.log"
    code=${PIPESTATUS[0]}
    if [ "$code" -eq "$CODE_REDEMARRAGE" ]; then
        info "Redémarrage demandé depuis NOVA..."
        continue
    fi
    [ "$code" -ne 0 ] && error "NOVA s'est arrêté avec le code $code (voir data/logs/nova.log)."
    exit "$code"
done
