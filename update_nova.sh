#!/usr/bin/env bash
# Met NOVA à jour depuis GitHub en une commande (sur la Pi comme sur le PC) :
#   1. met de côté les modifications locales (git stash, rien n'est perdu) ;
#   2. récupère la dernière version de main (HTTPS : aucune clé SSH requise) ;
#   3. réinstalle les dépendances Python si elles ont changé.
#
# Usage : ./update_nova.sh            mettre à jour
#         ./update_nova.sh --start    mettre à jour puis lancer NOVA
#
# Les réglages propres à une machine vont dans config/system.local.json :
# ce fichier n'est pas suivi par Git, donc jamais écrasé par une mise à jour.

REPO_URL="https://github.com/Mitchou1/Nova-Project.git"
BRANCH="main"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[nova]${NC} $1"; }
warn()  { echo -e "${YELLOW}[nova]${NC} $1"; }
error() { echo -e "${RED}[nova]${NC} $1"; }

# Tout le script est dans main() : bash le lit donc en entier avant de
# l'exécuter, et le git pull peut remplacer ce fichier sans casser la suite.
main() {
    local nova_dir
    nova_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$nova_dir" || exit 1

    local start_after=0
    case "${1:-}" in
        --start) start_after=1 ;;
        "") ;;
        *) error "Option inconnue : $1"; exit 2 ;;
    esac

    info "Mise à jour de NOVA dans $nova_dir"

    if [ -n "$(git status --porcelain)" ]; then
        local label
        label="update_nova $(date '+%Y-%m-%d %H:%M')"
        git stash push -u -m "$label" > /dev/null || { error "git stash a échoué."; exit 1; }
        warn "Modifications locales mises de côté ($label)."
        warn "Pour les voir : git stash list   /   git stash show -p stash@{0}"
    fi

    if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
        info "Passage sur la branche $BRANCH..."
        git checkout "$BRANCH" || { error "Impossible de passer sur $BRANCH."; exit 1; }
    fi

    local before
    before="$(git rev-parse HEAD)"

    # origin peut être en SSH (git@github.com) sans clé sur la Pi : on
    # retombe alors sur l'adresse HTTPS publique.
    if ! git pull --ff-only origin "$BRANCH" 2> /dev/null; then
        warn "origin injoignable, nouvel essai en HTTPS..."
        git remote set-url origin "$REPO_URL"
        if ! git pull --ff-only origin "$BRANCH"; then
            error "Mise à jour impossible (pas d'Internet, ou historique local divergent)."
            error "Si des commits ont été faits sur cette machine : git log --oneline -5"
            exit 1
        fi
    fi

    if [ "$before" = "$(git rev-parse HEAD)" ]; then
        info "NOVA est déjà à jour ($(git log --oneline -1))."
    else
        info "Nouveautés installées :"
        git log --oneline "$before..HEAD" | sed 's/^/   /'
    fi

    ./start_nova.sh --setup-only || exit 1

    if [ "$start_after" -eq 1 ]; then
        exec ./start_nova.sh
    fi
    info "Terminé. Lance NOVA avec : ./start_nova.sh"
}

main "$@"
exit $?
