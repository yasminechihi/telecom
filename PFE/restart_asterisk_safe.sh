#!/bin/bash
# ============================================================
#  restart_asterisk_safe.sh
#  Redémarrage propre d'Asterisk dans WSL2
#
#  POURQUOI CE SCRIPT ?
#  ---------------------
#  "service asterisk restart" dans WSL2 provoque parfois :
#    • AMI ne renvoie plus de banner → "Connection closed by foreign host"
#    • MicroSIP perd son enregistrement SIP
#
#  Ce script effectue un arrêt+démarrage propre et vérifie
#  que l'AMI répond correctement avant de terminer.
#
#  UTILISATION :
#    bash restart_asterisk_safe.sh
#  OU depuis Windows :
#    wsl -u root -- bash /mnt/c/.../PFE/restart_asterisk_safe.sh
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "  ${RED}✗${NC} $*"; }
info() { echo -e "  ${CYAN}→${NC}  $*"; }

echo ""
echo "======================================================"
echo "  Redémarrage Asterisk (méthode sécurisée WSL2)"
echo "======================================================"
echo ""

# ── 1. Arrêt propre ──────────────────────────────────────────
echo "[1/4] Arrêt Asterisk..."

if pgrep -x "asterisk" > /dev/null 2>&1; then
    # Essayer l'arrêt gracieux via CLI d'abord
    asterisk -rx "core stop now" 2>/dev/null && true
    GRACE_WAIT=0
    while pgrep -x "asterisk" > /dev/null 2>&1 && [ $GRACE_WAIT -lt 8 ]; do
        sleep 1
        GRACE_WAIT=$((GRACE_WAIT + 1))
    done

    # Si toujours en vie → forcer
    if pgrep -x "asterisk" > /dev/null 2>&1; then
        warn "Arrêt gracieux échoué — SIGTERM..."
        pkill -TERM asterisk 2>/dev/null || true
        sleep 3
    fi

    if pgrep -x "asterisk" > /dev/null 2>&1; then
        warn "Toujours en vie — SIGKILL..."
        pkill -KILL asterisk 2>/dev/null || true
        sleep 2
    fi
else
    info "Asterisk n'était pas en cours d'exécution."
fi

if pgrep -x "asterisk" > /dev/null 2>&1; then
    err "Impossible d'arrêter Asterisk !"
    exit 1
fi
ok "Asterisk arrêté."

# ── 2. Nettoyage fichiers de verrou ──────────────────────────
echo ""
echo "[2/4] Nettoyage des fichiers de verrou..."
rm -f /var/run/asterisk/asterisk.pid 2>/dev/null || true
rm -f /tmp/asterisk.pid 2>/dev/null || true
ok "Fichiers de verrou nettoyés."

# ── 3. Démarrage propre ───────────────────────────────────────
echo ""
echo "[3/4] Démarrage Asterisk..."

# Démarrer en mode daemon (pas -f qui garde le foreground)
if command -v asterisk > /dev/null 2>&1; then
    asterisk -g 2>/dev/null &
    ASTPID=$!
    disown $ASTPID 2>/dev/null || true
else
    err "Asterisk non trouvé ! Exécutez d'abord setup_asterisk_wsl.sh"
    exit 1
fi

# Attendre le démarrage (max 15 secondes)
BOOT_WAIT=0
while [ $BOOT_WAIT -lt 15 ]; do
    sleep 1
    BOOT_WAIT=$((BOOT_WAIT + 1))
    if pgrep -x "asterisk" > /dev/null 2>&1; then
        ok "Processus Asterisk démarré (${BOOT_WAIT}s)."
        break
    fi
done

if ! pgrep -x "asterisk" > /dev/null 2>&1; then
    err "Asterisk n'a pas démarré !"
    echo "    Logs : tail -30 /var/log/asterisk/full"
    exit 1
fi

# Laisser Asterisk initialiser tous ses modules
info "Initialisation des modules (AMI, SIP)..."
sleep 4

# Forcer le rechargement du module AMI — résout le bug "Connection closed by foreign host"
# qui survient quand res_manager.so ne s'est pas initialisé correctement au démarrage
info "Rechargement module AMI (manager reload)..."
asterisk -rx "manager reload" 2>/dev/null && ok "Module AMI rechargé." || warn "manager reload indisponible (Asterisk pas encore prêt — attente 3s...)"
sleep 3

# ── 4. Vérification AMI ───────────────────────────────────────
echo ""
echo "[4/4] Vérification AMI (port 5038)..."

AMI_OK=false
AMI_BANNER=""
for i in 1 2 3 4 5; do
    # Test TCP sur port 5038 avec lecture du banner (timeout 3s)
    BANNER=$(bash -c 'exec 3<>/dev/tcp/127.0.0.1/5038 2>/dev/null && cat <&3 & sleep 2; kill %1 2>/dev/null; wait' 2>/dev/null | head -1)
    if echo "$BANNER" | grep -qi "asterisk\|call manager"; then
        AMI_OK=true
        AMI_BANNER="$BANNER"
        break
    fi
    info "Tentative $i/5 — AMI pas encore prêt, attente 2s..."
    sleep 2
done

if $AMI_OK; then
    ok "AMI prêt ! Banner : $AMI_BANNER"
else
    warn "AMI ne répond pas encore. Vérifiez :"
    echo "     • sudo tail -20 /var/log/asterisk/full"
    echo "     • asterisk -rx \"manager show settings\""
fi

# ── Statut SIP peers ─────────────────────────────────────────
echo ""
echo "  Peers SIP enregistrés :"
asterisk -rx "sip show peers" 2>/dev/null | grep -v "^$" | head -10 || warn "SIP non disponible"

echo ""
echo "  Statut AMI :"
asterisk -rx "manager show settings" 2>/dev/null | grep -E "AMI|enabled|port|bind" | head -5 || warn "Manager info non disponible"

echo ""
echo "======================================================"
if $AMI_OK; then
    echo -e "  ${GREEN}✓ Asterisk prêt — AMI OK${NC}"
    echo "  MicroSIP devrait se ré-enregistrer automatiquement."
    echo "  Si MicroSIP ne ré-enregistre pas dans 30s :"
    echo "    → Dans MicroSIP : Bouton droit → Unregister → Register"
else
    echo -e "  ${YELLOW}⚠ Asterisk démarré mais AMI incertain${NC}"
    echo "  Vérifiez : tail -20 /var/log/asterisk/full"
fi
echo "======================================================"
echo ""
