#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════
#  NOVA — lanceur unique : vérifie, répare ce qui peut l'être, puis démarre.
#
#  Usage :
#    ./start_nova.sh               vérifications + réparations + lancement
#    ./start_nova.sh --check       vérifications seulement (ne lance rien)
#    ./start_nova.sh --no-sudo     ne demande jamais de mot de passe
#    ./start_nova.sh --autostart   lancer NOVA à l'ouverture de session
#
#  Toutes les étapes sont idempotentes : relancer le script ne refait que
#  ce qui manque. Une étape qui échoue est signalée mais ne bloque pas le
#  démarrage (NOVA affiche lui-même ce qui est indisponible).
#
#  Ce qui n'est PLUS fait ici : attendre les serveurs de carte (jusqu'à
#  10 min avant). NOVA les vérifie, les relance et les recrée lui-même en
#  arrière-plan (software/nova/map_services.py) sans bloquer l'interface.
# ══════════════════════════════════════════════════════════════════════════
set -u

# Dossier du projet = dossier de ce script (plus de chemin codé en dur)
NOVA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$NOVA_DIR/venv"
PY="$VENV/bin/python"
CONFIG="$NOVA_DIR/config/system.json"
LOG_DIR="$NOVA_DIR/data/logs"
CODE_REDEMARRAGE=42       # os._exit(42) : bouton « Redémarrer NOVA »

CHECK_ONLY=0
NO_SUDO=0
AUTOSTART=0
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        --no-sudo) NO_SUDO=1 ;;
        --autostart) AUTOSTART=1 ;;
        -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "Option inconnue : $arg (voir --help)"; exit 2 ;;
    esac
done

VERT='\033[0;32m'; JAUNE='\033[1;33m'; ROUGE='\033[0;31m'; GRIS='\033[0;90m'; NC='\033[0m'
AVERTISSEMENTS=0
ERREURS=0
ok()    { echo -e "  ${VERT}✓${NC} $1"; }
info()  { echo -e "  ${GRIS}·${NC} $1"; }
warn()  { echo -e "  ${JAUNE}!${NC} $1"; AVERTISSEMENTS=$((AVERTISSEMENTS + 1)); }
err()   { echo -e "  ${ROUGE}✗${NC} $1"; ERREURS=$((ERREURS + 1)); }
titre() { echo -e "\n${VERT}▸ $1${NC}"; }

EST_PI=0
grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null && EST_PI=1

EN_LIGNE=0
timeout 3 bash -c 'exec 3<>/dev/tcp/pypi.org/443' 2>/dev/null && EN_LIGNE=1

dans_groupe() { id -nG "$USER" | tr ' ' '\n' | grep -qx "$1"; }

# sudo seulement si nécessaire, jamais en mode --check / --no-sudo, et
# jamais sans terminal (démarrage automatique : on signale au lieu
# d'attendre un mot de passe que personne ne tapera).
peut_sudo() {
    [ "$CHECK_ONLY" -eq 0 ] && [ "$NO_SUDO" -eq 0 ] || return 1
    sudo -n true 2>/dev/null && return 0
    [ -t 0 ]
}

# Lit une clé de la config JSON : lire_config ai whisper_model <défaut>
lire_config() {
    python3 - "$CONFIG" "$@" <<'EOF' 2>/dev/null
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

echo -e "${VERT}══════════ NOVA — préparation du démarrage ══════════${NC}"
info "projet : $NOVA_DIR"
info "machine : $( [ $EST_PI -eq 1 ] && tr -d '\0' < /proc/device-tree/model || uname -srm )"
info "internet : $( [ $EN_LIGNE -eq 1 ] && echo disponible || echo 'absent — NOVA fonctionnera hors ligne' )"

# ─── 1. Environnement Python ─────────────────────────────────────────────
titre "Environnement Python"
if [ ! -x "$PY" ]; then
    if [ "$CHECK_ONLY" -eq 1 ]; then
        err "venv absent ($VENV)"
    else
        info "création du venv..."
        python3 -m venv "$VENV" && ok "venv créé" || err "création du venv impossible"
    fi
fi

if [ -x "$PY" ]; then
    ok "venv : $("$PY" --version 2>&1)"
    manquants=()
    erreurs_modules=0
    # module importé -> paquet pip ; « essentiel » = NOVA ne démarre pas sans
    verifier_module() {
        local module="$1" paquet="$2" niveau="$3"
        "$PY" -c "import $module" 2>/dev/null && return
        if [ "$niveau" = "essentiel" ]; then
            err "module $module manquant (paquet $paquet)"
            erreurs_modules=$((erreurs_modules + 1))
        else
            warn "module $module manquant (paquet $paquet) : fonction dégradée"
        fi
        manquants+=("$paquet")
    }
    verifier_module kivy "kivy==2.3.1" essentiel
    verifier_module llama_cpp llama-cpp-python optionnel
    verifier_module faster_whisper faster-whisper optionnel
    verifier_module piper piper-tts optionnel
    verifier_module sounddevice sounddevice optionnel
    # Batterie de l'UPS HAT (I2C) : sur le Pi seulement
    [ $EST_PI -eq 1 ] && verifier_module smbus2 smbus2 optionnel

    if [ ${#manquants[@]} -gt 0 ] && [ "$CHECK_ONLY" -eq 0 ]; then
        if [ $EN_LIGNE -eq 1 ]; then
            info "installation : ${manquants[*]}"
            if "$PY" -m pip install -q "${manquants[@]}"; then
                ok "modules installés"
                # seules les erreurs de modules sont réparées par l'installation
                ERREURS=$((ERREURS - erreurs_modules))
            else
                err "installation pip échouée (voir les messages ci-dessus)"
            fi
        else
            warn "pas d'internet : installation des modules manquants reportée"
        fi
    fi
fi

# ─── 2. Modèles d'IA (hors ligne) ────────────────────────────────────────
titre "Modèles d'IA"
LLM="$(lire_config ai llm_model qwen2.5-3b-instruct-q5_k_m.gguf)"
VOIX="$(lire_config ai tts_voice fr_FR-siwis-medium.onnx)"
WHISPER="$(lire_config ai whisper_model small)"
[ -f "$NOVA_DIR/models/llm/$LLM" ] && ok "LLM : $LLM" \
    || warn "LLM absent (models/llm/$LLM) : assistant en simulation (scripts/setup_ai.sh)"
[ -f "$NOVA_DIR/models/tts/$VOIX" ] && ok "voix : $VOIX" \
    || warn "voix absente (models/tts/$VOIX) : pas de réponse vocale"
# Whisper est chargé avec local_files_only=True (aucun accès réseau au
# démarrage) : il doit être dans le cache. On le télécharge une seule fois.
CACHE_WHISPER="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-$WHISPER"
if [ -d "$CACHE_WHISPER" ]; then
    ok "Whisper « $WHISPER » en cache local"
elif [ "$CHECK_ONLY" -eq 0 ] && [ $EN_LIGNE -eq 1 ] && [ -x "$PY" ]; then
    info "téléchargement unique de Whisper « $WHISPER »..."
    "$PY" -c "from faster_whisper import WhisperModel; WhisperModel('$WHISPER', device='cpu', compute_type='int8')" \
        >/dev/null 2>&1 && ok "Whisper téléchargé" || warn "téléchargement de Whisper impossible"
else
    warn "Whisper « $WHISPER » absent du cache : reconnaissance vocale en simulation"
fi

# ─── 3. Docker (serveurs de carte hors ligne) ────────────────────────────
titre "Cartes hors ligne (Docker)"
if ! command -v docker >/dev/null; then
    warn "Docker non installé : cartes, itinéraires et recherche indisponibles"
else
    if ! systemctl is-active --quiet docker 2>/dev/null; then
        if peut_sudo; then
            sudo systemctl enable --now docker && ok "service Docker démarré"
        else
            warn "service Docker arrêté (sudo systemctl enable --now docker)"
        fi
    fi
    # NOVA pilote Docker SANS sudo : l'utilisateur doit être dans le groupe
    if dans_groupe docker; then
        ok "utilisateur « $USER » dans le groupe docker"
        # Conteneurs créés sans redémarrage automatique : politique corrigée
        # sans les recréer (la base Nominatim est préservée)
        for c in nova-tileserver nova-valhalla nova-nominatim; do
            if docker inspect "$c" >/dev/null 2>&1; then
                [ "$CHECK_ONLY" -eq 0 ] && docker update --restart unless-stopped "$c" >/dev/null 2>&1
                ok "$c : $(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null) (NOVA le relance si besoin)"
            else
                info "$c absent : NOVA le créera au démarrage si les données sont présentes"
            fi
        done
    elif peut_sudo; then
        sudo usermod -aG docker "$USER" && \
            warn "ajouté au groupe docker : reconnecte-toi (ou redémarre) pour l'activer"
    else
        warn "« $USER » n'est pas dans le groupe docker (sudo usermod -aG docker $USER, puis reconnexion)"
    fi
fi

# ─── 4. Matériel du Raspberry Pi ─────────────────────────────────────────
if [ $EST_PI -eq 1 ]; then
    titre "Raspberry Pi"
    # I2C : batterie de l'UPS HAT (et futurs capteurs)
    if [ -e /dev/i2c-1 ]; then
        ok "bus I2C actif (/dev/i2c-1)"
    elif peut_sudo; then
        sudo raspi-config nonint do_i2c 0 && sudo modprobe i2c-dev && \
            ok "I2C activé" || warn "activation I2C impossible (sudo raspi-config)"
    else
        warn "I2C désactivé : batterie de l'UPS illisible (sudo raspi-config → Interface → I2C)"
    fi
    if dans_groupe i2c; then
        ok "utilisateur dans le groupe i2c"
    elif peut_sudo; then
        sudo usermod -aG i2c "$USER" && warn "ajouté au groupe i2c : reconnecte-toi pour l'activer"
    else
        warn "« $USER » n'est pas dans le groupe i2c (sudo usermod -aG i2c $USER)"
    fi
    # Bluetooth : service arrêté = état illisible dans les Paramètres
    if systemctl is-active --quiet bluetooth; then
        ok "service Bluetooth actif"
    elif peut_sudo; then
        sudo systemctl enable --now bluetooth && ok "service Bluetooth démarré"
    else
        warn "service Bluetooth arrêté (sudo systemctl enable --now bluetooth)"
    fi
    # Alimentation : avertissement 5V/5A du Pi 5 avec un UPS sans USB-PD
    if command -v vcgencmd >/dev/null; then
        t=$(vcgencmd get_throttled 2>/dev/null | sed 's/.*=//')
        if [ "$t" = "0x0" ]; then ok "alimentation correcte (aucune sous-tension)"
        else warn "alimentation : get_throttled=$t (sous-tension détectée, détail dans Paramètres)"; fi
    fi
    # Clavier du système en plus de celui de NOVA ?
    if [ "$(lire_config virtual_keyboard true)" = "true" ] && pgrep -x squeekboard >/dev/null; then
        warn "le clavier du système (squeekboard) tourne : il peut s'afficher en plus de celui de NOVA"
        info "  → Préférences → Configuration du Raspberry Pi → Affichage → Clavier virtuel : désactivé"
    fi
fi

# ─── 5. Démarrage automatique (option --autostart) ───────────────────────
if [ "$AUTOSTART" -eq 1 ]; then
    titre "Démarrage automatique"
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
    ok "NOVA se lancera à l'ouverture de session (~/.config/autostart/nova.desktop)"
fi

# ─── Bilan ───────────────────────────────────────────────────────────────
echo
if [ $ERREURS -gt 0 ]; then
    echo -e "${ROUGE}✗ $ERREURS erreur(s) bloquante(s)${NC} — corrige-les puis relance."
    exit 1
fi
if [ $AVERTISSEMENTS -gt 0 ]; then
    echo -e "${JAUNE}! $AVERTISSEMENTS avertissement(s)${NC} : NOVA démarre ; ces fonctions seront signalées comme indisponibles."
else
    echo -e "${VERT}✓ Tout est prêt.${NC}"
fi
[ "$CHECK_ONLY" -eq 1 ] && exit 0

# ─── 6. Lancement (avec relance sur « Redémarrer NOVA ») ─────────────────
mkdir -p "$LOG_DIR"
cd "$NOVA_DIR" || exit 1
while true; do
    echo -e "\n${VERT}▸ Lancement de NOVA${NC} (journal : data/logs/nova.log)"
    PYTHONUNBUFFERED=1 "$PY" software/nova/main.py 2>&1 | tee -a "$LOG_DIR/nova.log"
    code=${PIPESTATUS[0]}
    if [ "$code" -eq "$CODE_REDEMARRAGE" ]; then
        info "redémarrage demandé depuis NOVA"
        continue
    fi
    [ "$code" -ne 0 ] && echo -e "${ROUGE}NOVA s'est arrêté avec le code $code${NC} (voir data/logs/nova.log)"
    exit "$code"
done
