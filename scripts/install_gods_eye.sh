#!/bin/bash
# Installation de God's Eye View (globe 3D temps réel) pour l'app Terminal.
#
# Idempotent : on peut le relancer autant de fois qu'on veut. Il ne fait que
# ce qui manque (Node absent -> installé, dépôt absent -> cloné, sinon mis à
# jour) et finit par un résumé « installé / déjà présent / échec ».
#
# Node.js : l'outil exige Node >= 24.14 (<25) ou 26.x. Debian trixie ne
# fournit que Node 20. Plutôt que NodeSource (qui demande sudo avec mot de
# passe et ajoute un dépôt apt au système), on installe le binaire officiel
# de nodejs.org DANS le projet (external/node) : aucun droit root, rien hors
# du dossier NOVA, et une désinstallation se résume à supprimer le dossier.
# Si un Node système compatible existe déjà, il est utilisé tel quel.
#
# Usage : scripts/install_gods_eye.sh

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTERNAL_DIR="$ROOT_DIR/external"
INSTALL_DIR="$EXTERNAL_DIR/gods-eye-view"
NODE_DIR="$EXTERNAL_DIR/node"
REPO_URL="https://github.com/bilawalsidhu/gods-eye-view.git"
NODE_DIST="https://nodejs.org/dist/latest-v24.x"
# Dépôt (clone superficiel) + node_modules + Node : ~600 Mo observés ;
# on exige une marge confortable pour ne pas remplir la microSD.
ESPACE_MIN_MO=1500

declare -a RESUME=()
ECHEC=0

resume() { RESUME+=("$1"); }
echec() {
    resume "ÉCHEC   $1"
    ECHEC=1
    afficher_resume
    exit 1
}
afficher_resume() {
    echo
    echo "════════ Résumé God's Eye View ════════"
    for ligne in "${RESUME[@]}"; do echo "  $ligne"; done
    if [ "$ECHEC" -eq 0 ]; then
        echo "  → Prêt : bouton GOD'S EYE dans l'app Terminal de NOVA."
    fi
    echo "═══════════════════════════════════════"
}

# Node compatible ? (>=24.14 <25, ou 26.x — contrainte « engines » de l'outil)
node_compatible() {
    local bin="$1" version majeur mineur
    [ -x "$bin" ] || return 1
    version="$("$bin" --version 2>/dev/null)" || return 1
    version="${version#v}"
    majeur="${version%%.*}"
    mineur="$(echo "$version" | cut -d. -f2)"
    if [ "$majeur" = "24" ] && [ "$mineur" -ge 14 ]; then return 0; fi
    [ "$majeur" = "26" ]
}

# ─── 0. Prérequis ────────────────────────────────────────────────────────
for outil in git curl tar; do
    command -v "$outil" >/dev/null 2>&1 || echec "« $outil » est absent (sudo apt install $outil)"
done

# ─── 1. Espace disque ───────────────────────────────────────────────────
mkdir -p "$EXTERNAL_DIR"
LIBRE_MO=$(df -Pm "$EXTERNAL_DIR" | awk 'NR==2 {print $4}')
if [ ! -d "$INSTALL_DIR/node_modules" ] && [ "$LIBRE_MO" -lt "$ESPACE_MIN_MO" ]; then
    echec "espace disque insuffisant : ${LIBRE_MO} Mo libres, ${ESPACE_MIN_MO} Mo requis"
fi
echo "Espace disque : ${LIBRE_MO} Mo libres."

# ─── 2. Internet (tout le reste en dépend) ──────────────────────────────
if ! curl -fsS --max-time 8 -o /dev/null https://github.com; then
    echec "pas d'accès internet (github.com injoignable) : installation impossible"
fi

# ─── 3. Node.js ─────────────────────────────────────────────────────────
NODE_BIN=""
if node_compatible "$NODE_DIR/bin/node"; then
    NODE_BIN="$NODE_DIR/bin/node"
    resume "présent Node $("$NODE_BIN" --version) (local, external/node)"
elif command -v node >/dev/null 2>&1 && node_compatible "$(command -v node)"; then
    NODE_BIN="$(command -v node)"
    resume "présent Node $(node --version) (système)"
else
    case "$(uname -m)" in
        aarch64|arm64) ARCH="arm64" ;;
        x86_64)        ARCH="x64" ;;
        *) echec "architecture $(uname -m) non prise en charge par ce script" ;;
    esac
    echo "Node 24 absent : téléchargement du binaire officiel ($ARCH)…"
    SOMMES="$(curl -fsSL --max-time 30 "$NODE_DIST/SHASUMS256.txt")" \
        || echec "liste des versions de Node inaccessible ($NODE_DIST)"
    LIGNE="$(echo "$SOMMES" | grep "linux-$ARCH.tar.xz\$" | head -1)"
    [ -n "$LIGNE" ] || echec "aucune archive Node 24 pour linux-$ARCH"
    SHA_ATTENDU="${LIGNE%% *}"
    ARCHIVE="${LIGNE##* }"
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    curl -fL --progress-bar -o "$TMP/$ARCHIVE" "$NODE_DIST/$ARCHIVE" \
        || echec "téléchargement de $ARCHIVE interrompu"
    # Vérification d'intégrité : une archive tronquée donnerait un Node cassé
    echo "$SHA_ATTENDU  $TMP/$ARCHIVE" | sha256sum -c --quiet - \
        || echec "somme SHA-256 de $ARCHIVE incorrecte (téléchargement corrompu)"
    rm -rf "$NODE_DIR.nouveau"
    mkdir -p "$NODE_DIR.nouveau"
    tar -xJf "$TMP/$ARCHIVE" -C "$NODE_DIR.nouveau" --strip-components=1 \
        || echec "extraction de $ARCHIVE impossible"
    # Remplacement atomique : jamais de dossier node à moitié extrait
    rm -rf "$NODE_DIR"
    mv "$NODE_DIR.nouveau" "$NODE_DIR"
    NODE_BIN="$NODE_DIR/bin/node"
    node_compatible "$NODE_BIN" || echec "Node installé mais inutilisable"
    resume "installé Node $("$NODE_BIN" --version) dans external/node"
fi
# npm doit être celui du même Node (sinon mélange de versions)
export PATH="$(dirname "$NODE_BIN"):$PATH"

# ─── 4. Dépôt God's Eye View ────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Dépôt présent : mise à jour…"
    if git -C "$INSTALL_DIR" pull --ff-only --quiet; then
        resume "à jour  dépôt ($(git -C "$INSTALL_DIR" log -1 --format=%h))"
    else
        # Pas bloquant : la version déjà installée reste utilisable
        resume "ATTENTION mise à jour du dépôt impossible, version existante conservée"
    fi
elif [ -e "$INSTALL_DIR" ]; then
    echec "$INSTALL_DIR existe mais n'est pas un dépôt git (à vérifier/supprimer à la main)"
else
    echo "Clonage de $REPO_URL…"
    # --depth 1 : l'historique complet (~110 Mo) ne sert à rien ici
    git clone --depth 1 --quiet "$REPO_URL" "$INSTALL_DIR" \
        || echec "clonage du dépôt impossible"
    resume "installé dépôt ($(git -C "$INSTALL_DIR" log -1 --format=%h))"
fi

# ─── 5. Dépendances npm ────────────────────────────────────────────────
cd "$INSTALL_DIR" || echec "dossier $INSTALL_DIR inaccessible"
# Puppeteer (outil de tests de l'auteur) télécharge Chrome à l'installation :
# inutile pour l'usage, ~300 Mo, et sans build Chrome officiel pour Linux ARM64.
export PUPPETEER_SKIP_DOWNLOAD=1
echo "Installation des dépendances (npm ci, plusieurs minutes sur le Pi)…"
if npm ci --no-audit --no-fund --loglevel=error; then
    resume "installé dépendances npm"
else
    echec "npm ci a échoué (voir les messages ci-dessus)"
fi

# ─── 6. Diagnostic de l'outil ──────────────────────────────────────────
echo "Diagnostic (npm run doctor)…"
if npm run --silent doctor; then
    resume "OK      npm run doctor"
else
    # L'outil fonctionne sans clé API : le doctor peut signaler des clés
    # manquantes sans que ce soit bloquant.
    resume "ATTENTION npm run doctor signale des points (voir ci-dessus)"
fi

# ─── 7. Multitouch de l'écran (zoom à deux doigts sur le globe) ────────
# Raspberry Pi OS configure l'écran tactile en « émulation souris »
# (/etc/xdg/labwc/rc.xml, mouseEmulation="yes") : le bureau ne transmet qu'UN
# doigt, donc aucun pincement possible dans aucune application. On surcharge
# ce réglage côté utilisateur (sans root ; labwc fusionne les deux fichiers).
# Vérifié : NOVA (Kivy) reçoit toujours un seul appui par toucher.
RC_UTILISATEUR="$HOME/.config/labwc/rc.xml"
RC_SYSTEME="/etc/xdg/labwc/rc.xml"
ECRAN_TACTILE="$(awk -F'"' '/^N: Name=/{nom=$2} /^H: Handlers=/{ if (nom ~ /ft5x06|Goodix|[Tt]ouch/) {print nom; exit} }' /proc/bus/input/devices)"
if [ -z "$ECRAN_TACTILE" ] || ! pgrep -x labwc >/dev/null; then
    resume "ignoré  multitouch (pas d'écran tactile ou bureau autre que labwc)"
elif [ -f "$RC_UTILISATEUR" ] && grep -q 'mouseEmulation="no"' "$RC_UTILISATEUR"; then
    resume "présent multitouch de l'écran ($ECRAN_TACTILE)"
elif [ -f "$RC_UTILISATEUR" ]; then
    # Un réglage personnel existe déjà : on ne l'écrase pas
    resume "ATTENTION $RC_UTILISATEUR existe : ajoute mouseEmulation=\"no\" à la main pour le zoom à deux doigts"
else
    SORTIE_ECRAN="$(grep -F "deviceName=\"$ECRAN_TACTILE\"" "$RC_SYSTEME" 2>/dev/null | grep -o 'mapToOutput="[^"]*"' | head -1)"
    mkdir -p "$(dirname "$RC_UTILISATEUR")"
    cat > "$RC_UTILISATEUR" <<XML
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <touch deviceName="$ECRAN_TACTILE" ${SORTIE_ECRAN:-mapToOutput=\"DSI-1\"} mouseEmulation="no" />
</openbox_config>
XML
    pkill -HUP -x labwc      # relit la configuration sans fermer la session
    resume "activé  multitouch de l'écran ($ECRAN_TACTILE)"
fi

ESPACE=$(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1)
resume "espace  God's Eye View occupe $ESPACE"
afficher_resume
