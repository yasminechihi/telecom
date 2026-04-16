#!/bin/bash
# ============================================================
#  setup_asterisk_wsl.sh — Asterisk pour MicroSIP + TT VoiceBot
#
#  Ce script configure Asterisk dans WSL pour :
#    • Enregistrement de MicroSIP (softphone Windows)
#    • Notification agent lors d'un transfert bot → humain
#    • Interface AMI pour Python (user_app.py)
#
#  UTILISATION :
#    1. Ouvrir WSL  (Win + R → wsl)
#    2. cd /mnt/c/Users/Yasmine/Documents/telecom/PFE
#    3. bash setup_asterisk_wsl.sh
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "  ${RED}✗${NC} $*"; }

echo ""
echo "======================================================"
echo "  Asterisk WSL — Tunisie Telecom VoiceBot + MicroSIP"
echo "======================================================"

# ── 1. Installer Asterisk ─────────────────────────────────
echo ""
echo "[1/6] Installation Asterisk..."
sudo apt-get update -qq
sudo apt-get install -y asterisk asterisk-core-sounds-en asterisk-core-sounds-fr 2>/dev/null || \
sudo apt-get install -y asterisk
ok "Asterisk installé"

# ── 2. AMI — manager.conf ─────────────────────────────────
echo ""
echo "[2/6] Configuration AMI (manager.conf)..."
sudo tee /etc/asterisk/manager.conf > /dev/null <<'EOF'
[general]
enabled  = yes
port     = 5038
bindaddr = 0.0.0.0
displayconnects = no

; ── Compte Python/Flask (user_app.py → asterisk_ami.py) ──
[ttadmin]
secret  = TT@2026
permit  = 0.0.0.0/0.0.0.0
read    = all
write   = all,originate
EOF
ok "manager.conf écrit"

# ── 2b. Modules — forcer le chargement de chan_sip ────────
# Dans Asterisk 18+, chan_sip peut être désactivé par défaut.
# On s'assure qu'il est chargé et que chan_pjsip ne crée pas de conflit.
echo ""
echo "[2b] Activation chan_sip (module SIP pour MicroSIP)..."

# Lire modules.conf et s'assurer que chan_sip.so est chargé
if sudo grep -q "noload.*chan_sip" /etc/asterisk/modules.conf 2>/dev/null; then
    sudo sed -i 's/noload.*chan_sip\.so.*/load => chan_sip.so/' /etc/asterisk/modules.conf
    ok "chan_sip.so : noload remplacé par load"
fi
# Ajouter explicitement si absent
if ! sudo grep -q "chan_sip" /etc/asterisk/modules.conf 2>/dev/null; then
    echo "" | sudo tee -a /etc/asterisk/modules.conf > /dev/null
    echo "load => chan_sip.so" | sudo tee -a /etc/asterisk/modules.conf > /dev/null
    ok "chan_sip.so : ajouté dans modules.conf"
else
    ok "chan_sip.so : déjà présent dans modules.conf"
fi

# ── 3. SIP — sip.conf (pour MicroSIP) ────────────────────
echo ""
echo "[3/6] Configuration SIP (sip.conf pour MicroSIP)..."
sudo tee /etc/asterisk/sip.conf > /dev/null <<'EOF'
[general]
; ── Paramètres globaux ───────────────────────────────────
context          = default
bindport         = 5060
bindaddr         = 0.0.0.0
srvlookup        = yes
; NAT / WSL2 — essentiel pour que MicroSIP fonctionne sur Windows
nat              = force_rport,comedia
directmedia      = no
canreinvite      = no
; Codec audio (ulaw = G.711 µ-law, qualité téléphonique)
disallow         = all
allow            = ulaw
allow            = alaw
allow            = g722
dtmfmode         = rfc2833
; Enregistrement SIP
registertimeout  = 20
registerattempts = 0
; Logs
debug            = no

; ── Compte Agent (MicroSIP sur Windows) ──────────────────
[1001]
type             = friend
host             = dynamic
secret           = agent1234
context          = tt-transfer
callerid         = Agent TT <1001>
; NAT / WSL2 — obligatoire pour passer au travers du réseau virtuel WSL2
nat              = force_rport,comedia
directmedia      = no
canreinvite      = no
; insecure : permet l'enregistrement même si le port source change (WSL2)
insecure         = port,invite
; Codecs
disallow         = all
allow            = ulaw
allow            = alaw
allow            = g722
dtmfmode         = rfc2833
qualify          = yes
qualifyfreq      = 30
EOF
ok "sip.conf écrit (compte 1001 pour MicroSIP)"

# ── 4. RTP — rtp.conf (ports limités) ────────────────────
echo ""
echo "[4/6] Configuration RTP (ports audio)..."
sudo tee /etc/asterisk/rtp.conf > /dev/null <<'EOF'
[general]
; Plage de ports RTP (audio) réduite pour WSL2
; Avec networkingMode=mirrored ces ports sont accessibles depuis Windows
rtpstart = 10000
rtpend   = 10099
; Strictement UDP
rtpchecksums = no
EOF
ok "rtp.conf écrit (ports 10000-10099)"

# ── 5. Dialplan — extensions.conf ─────────────────────────
echo ""
echo "[5/6] Configuration dialplan (extensions.conf)..."

# Sauvegarder l'original si pas encore fait
if [ ! -f /etc/asterisk/extensions.conf.orig ]; then
    sudo cp /etc/asterisk/extensions.conf /etc/asterisk/extensions.conf.orig
    warn "Original sauvegardé → extensions.conf.orig"
fi

sudo tee /etc/asterisk/extensions.conf > /dev/null <<'EOF'
; ============================================================
;  extensions.conf — Dialplan Tunisie Telecom VoiceBot
; ============================================================

[general]
static   = yes
writeprotect = no
autofallthrough = yes

; ── Contexte par défaut (sécurité — bloque tout) ─────────
[default]
exten => _.,1,Hangup()

; ── Contexte Agent / MicroSIP ────────────────────────────
;  Ce contexte s'exécute CÔTÉ AGENT (MicroSIP) quand
;  le bot déclenche un transfert.
;
;  Flux :
;    1. Python appelle AMI Originate → Channel=SIP/1001
;    2. MicroSIP sonne chez l'agent
;    3. Agent décroche → Asterisk joue ce dialplan
;    4. L'agent entend : bip + numéro client en chiffres
;    5. L'agent rappelle le client manuellement
;
[tt-transfer]

; Extension de notification (appelée par AMI Originate)
exten => notify,1,NoOp(=== Transfert TT : client=${CLIENT_NAME} tel=${CLIENT_NUM} ticket=${TICKET_ID} ===)
exten => notify,n,Answer()
exten => notify,n,Wait(1)
; Premier bip d'alerte
exten => notify,n,Playback(beep)
exten => notify,n,Wait(0.5)
; Annoncer le numéro client chiffre par chiffre
exten => notify,n,SayDigits(${CLIENT_NUM})
exten => notify,n,Wait(0.5)
; Répéter une deuxième fois
exten => notify,n,Playback(beep)
exten => notify,n,Wait(0.5)
exten => notify,n,SayDigits(${CLIENT_NUM})
exten => notify,n,Wait(1)
; Garder la ligne ouverte 90 secondes (l'agent peut raccrocher quand il veut)
exten => notify,n,Wait(90)
exten => notify,n,Hangup()

; Extension de test (vérifier que le son fonctionne)
exten => 9999,1,Answer()
exten => 9999,n,Playback(beep)
exten => 9999,n,SayDigits(21612345678)
exten => 9999,n,Hangup()

; ── Contexte interne (numéros locaux 1XXX) ───────────────
[from-internal]
exten => _1XXX,1,NoOp(Appel interne vers ${EXTEN})
exten => _1XXX,n,Dial(SIP/${EXTEN},30)
exten => _1XXX,n,Hangup()

; Test son
exten => 9999,1,Answer()
exten => 9999,n,Playback(hello-world)
exten => 9999,n,Hangup()
EOF
ok "extensions.conf écrit (contexte tt-transfer)"

# ── 6. Démarrer Asterisk (méthode sécurisée WSL2) ─────────
echo ""
echo "[6/6] Démarrage Asterisk..."

# Arrêter proprement si déjà en cours
if pgrep -x "asterisk" > /dev/null 2>&1; then
    warn "Asterisk déjà en cours — arrêt propre..."
    asterisk -rx "core stop now" 2>/dev/null || true
    sleep 3
    # Forcer si toujours actif
    pkill -TERM asterisk 2>/dev/null || true
    sleep 2
fi

# Nettoyer les fichiers de verrou
rm -f /var/run/asterisk/asterisk.pid /tmp/asterisk.pid 2>/dev/null || true

# Démarrer en mode daemon (NE PAS utiliser "service asterisk start" en WSL2 :
# provoque "Connection closed by foreign host" sur l'AMI car les modules
# ne se réinitialisent pas correctement après un service restart)
asterisk -g 2>/dev/null || asterisk 2>/dev/null &
sleep 4

if pgrep -x "asterisk" > /dev/null; then
    ok "Asterisk est en cours d'exécution"
else
    err "Asterisk ne s'est pas démarré"
    echo "    Vérifiez les logs : sudo tail -50 /var/log/asterisk/full"
fi

# ── Résumé et prochaines étapes ───────────────────────────
echo ""
echo "======================================================"
echo "  PROCHAINES ÉTAPES"
echo "======================================================"
echo ""
echo "  1. Sur Windows (PowerShell Admin), lancez :"
echo "     .\\setup_microsip.ps1"
echo "     → Active le réseau miroir WSL2 (UDP SIP + RTP)"
echo "     → Redémarre WSL et Asterisk"
echo ""
echo "  2. Configurer MicroSIP :"
echo "     Serveur  : 127.0.0.1"
echo "     Port SIP : 5060"
echo "     Username : 1001"
echo "     Password : agent1234"
echo ""
echo "  3. Tester la connexion AMI depuis Python :"
echo "     python -c \"from asterisk_ami import check_asterisk_available; print(check_asterisk_available())\""
echo ""
echo "  4. Lancer l'interface utilisateur :"
echo "     LANCER_USER_APP.cmd  (ou : python user_app.py)"
echo ""
echo "  Console Asterisk (debug) :"
echo "    sudo asterisk -r"
echo "    CLI> sip show peers        ← voir si MicroSIP est enregistré"
echo "    CLI> sip show registry"
echo "    CLI> core show channels"
echo ""
echo "  Logs Asterisk :"
echo "    sudo tail -f /var/log/asterisk/full"
echo ""
echo "======================================================"
echo "  Configuration terminée !"
echo "======================================================"
echo ""
