# setup_microsip.ps1
# Active WSL2 mirrored networking (SIP UDP + RTP audio), demarre Asterisk, configure AMI.
# Execution : PowerShell Admin -> .\setup_microsip.ps1

$ErrorActionPreference = "Continue"

# Verifier si on a les droits Admin (necessaire pour netsh)
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")
if (-not $isAdmin) {
    Write-Host ""
    Write-Host "  [!!] Ce script n'est pas lance en Administrateur." -ForegroundColor Yellow
    Write-Host "       netsh portproxy ne fonctionnera pas, mais avec networkingMode=mirrored" -ForegroundColor Yellow
    Write-Host "       c'est optionnel. Le script continue..." -ForegroundColor Yellow
    Write-Host ""
}

function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "  [XX] $msg" -ForegroundColor Red }
function Write-Step { param($n,$msg) Write-Host ""; Write-Host "[$n] $msg" -ForegroundColor Cyan }

Write-Host ""
Write-Host "======================================================" -ForegroundColor Magenta
Write-Host "  MicroSIP + Asterisk WSL - Tunisie Telecom VoiceBot" -ForegroundColor Magenta
Write-Host "======================================================" -ForegroundColor Magenta

# -- 1. Activer networkingMode=mirrored dans .wslconfig ----------------
Write-Step "1/5" "Activation du reseau mirrored WSL2..."
Write-Host "  (necesaire pour SIP UDP 5060 et RTP audio depuis Windows)"

$wslConfigPath = "$env:USERPROFILE\.wslconfig"

if (Test-Path $wslConfigPath) {
    $content = [System.IO.File]::ReadAllText($wslConfigPath)
} else {
    $content = ""
}

$changed = $false

if ($content -match "(?im)^\[wsl2\]") {
    if ($content -match "(?im)^networkingMode\s*=") {
        $newContent = [regex]::Replace($content, "(?im)^networkingMode\s*=.*", "networkingMode=mirrored")
        if ($newContent -ne $content) {
            $content = $newContent
            $changed = $true
            Write-Ok "networkingMode mis a jour vers mirrored"
        } else {
            Write-Ok "networkingMode=mirrored deja configure"
        }
    } else {
        $content = [regex]::Replace($content, "(?im)(\[wsl2\])", "[wsl2]`nnetworkingMode=mirrored")
        $changed = $true
        Write-Ok "networkingMode=mirrored ajoute sous [wsl2]"
    }
} else {
    if ($content.Length -gt 0) {
        $content = $content.TrimEnd() + "`n"
    }
    $content += "[wsl2]`nnetworkingMode=mirrored`n"
    $changed = $true
    Write-Ok "Section [wsl2] creee avec networkingMode=mirrored"
}

if ($changed) {
    [System.IO.File]::WriteAllText($wslConfigPath, $content, [System.Text.Encoding]::UTF8)
    Write-Ok "Fichier .wslconfig sauvegarde : $wslConfigPath"
} else {
    Write-Ok "Fichier .wslconfig inchange"
}

# -- 2. Redemarrer WSL ------------------------------------------------
Write-Step "2/5" "Redemarrage de WSL2 (applique networkingMode=mirrored)..."
Write-Warn "Toutes les sessions WSL vont etre fermees..."

wsl --shutdown
if ($LASTEXITCODE -eq 0) {
    Write-Ok "WSL arrete avec succes"
} else {
    Write-Warn "wsl --shutdown a retourne le code $LASTEXITCODE (peut etre normal)"
}
Start-Sleep -Seconds 4

# -- 3. Installer + demarrer Asterisk dans WSL -----------------------
Write-Step "3/5" "Configuration et demarrage Asterisk dans WSL..."

# Calculer le chemin WSL du dossier courant (plusieurs methodes de fallback)
# $PSScriptRoot est la methode la plus fiable
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }

Write-Host "  Dossier script : $scriptDir" -ForegroundColor Gray

# Convertir chemin Windows vers chemin WSL
$wslRaw = wsl wslpath -a "$scriptDir" 2>$null
if ($wslRaw -and $wslRaw.Trim() -ne "") {
    $wslPath = $wslRaw.Trim()
} else {
    # Fallback manuel : C:\Users\Yasmine\... -> /mnt/c/Users/Yasmine/...
    $driveLetter = $scriptDir.Substring(0,1).ToLower()
    $rest = $scriptDir.Substring(2) -replace '\\', '/'
    $wslPath = "/mnt/$driveLetter$rest"
    Write-Host "  wslpath fallback : $wslPath" -ForegroundColor Gray
}
$setupScript = "$wslPath/setup_asterisk_wsl.sh"
Write-Host "  Script WSL : $setupScript" -ForegroundColor Gray

# Verifier si Asterisk est installe
$asteriskInstalled = wsl -u root -- which asterisk 2>$null
if (-not $asteriskInstalled) {
    Write-Warn "Asterisk n'est pas installe - installation complete..."
    Write-Host "  (peut prendre 2-3 minutes)" -ForegroundColor Yellow
} else {
    Write-Ok "Asterisk detecte : $($asteriskInstalled.Trim())"
    Write-Host "  Re-application configuration (sip.conf, extensions.conf, modules.conf)..." -ForegroundColor Gray
}

# Toujours lancer le script de configuration
wsl -u root -- bash "$setupScript"
if ($LASTEXITCODE -eq 0) {
    Write-Ok "Configuration Asterisk appliquee avec succes"
} else {
    Write-Warn "Configuration partielle (code=$LASTEXITCODE)"
    Write-Host "  Si le probleme persiste, ouvrez WSL et tapez :" -ForegroundColor Gray
    Write-Host "  sudo bash $setupScript" -ForegroundColor Gray
}
Start-Sleep -Seconds 3

# Demarrer Asterisk
wsl -u root -- service asterisk start
Start-Sleep -Seconds 4

# Note: $pid est une variable reservee PowerShell, on utilise $astPid
$astPid = (wsl -u root -- pgrep -x asterisk 2>$null)
$astPidStr = if ($astPid) { "$astPid".Trim() } else { "" }
if ($astPidStr -match '\d+') {
    Write-Ok "Asterisk en cours d'execution (PID: $astPidStr)"
} else {
    Write-Warn "Service non detecte - tentative de demarrage direct..."
    wsl -u root -- bash -c 'nohup asterisk -f > /tmp/asterisk_start.log 2>&1 &'
    Start-Sleep -Seconds 5
    $astPid2 = (wsl -u root -- pgrep -x asterisk 2>$null)
    $astPid2Str = if ($astPid2) { "$astPid2".Trim() } else { "" }
    if ($astPid2Str -match '\d+') {
        Write-Ok "Asterisk demarre (PID: $astPid2Str)"
    } else {
        Write-Err "Asterisk ne demarre pas"
        Write-Host "    Dans WSL tapez : sudo service asterisk start" -ForegroundColor Gray
        Write-Host "    Logs         : sudo tail -20 /var/log/asterisk/full" -ForegroundColor Gray
    }
}

# -- 4. Firewall Windows + Port forwarding ---------------------------
Write-Step "4/5" "Ouverture Pare-feu Windows + Port forwarding AMI..."

# Ouvrir le pare-feu pour SIP (UDP 5060) et RTP audio (UDP 10000-10099)
# OBLIGATOIRE pour que MicroSIP puisse communiquer avec Asterisk dans WSL2
netsh advfirewall firewall delete rule name="Asterisk SIP UDP 5060" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Asterisk SIP UDP 5060" protocol=UDP dir=in localport=5060 action=allow | Out-Null
netsh advfirewall firewall delete rule name="Asterisk SIP UDP 5060 out" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Asterisk SIP UDP 5060 out" protocol=UDP dir=out localport=5060 action=allow | Out-Null
Write-Ok "Pare-feu : UDP 5060 (SIP) ouvert en entree et sortie"

netsh advfirewall firewall delete rule name="Asterisk RTP UDP" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Asterisk RTP UDP" protocol=UDP dir=in localport=10000-10099 action=allow | Out-Null
netsh advfirewall firewall delete rule name="Asterisk RTP UDP out" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Asterisk RTP UDP out" protocol=UDP dir=out localport=10000-10099 action=allow | Out-Null
Write-Ok "Pare-feu : UDP 10000-10099 (RTP audio) ouvert"

netsh advfirewall firewall delete rule name="Asterisk AMI 5038" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Asterisk AMI 5038" protocol=TCP dir=in localport=5038 action=allow | Out-Null
Write-Ok "Pare-feu : TCP 5038 (AMI) ouvert"

# Port forwarding TCP 5038 (AMI) pour les cas sans mirrored networking
$wslIpRaw = wsl hostname -I 2>$null
if ($wslIpRaw) {
    $wslIp = $wslIpRaw.Trim().Split(" ")[0]
    Write-Host "  IP WSL2 detectee : $wslIp"

    netsh interface portproxy delete v4tov4 listenport=5038 listenaddress=0.0.0.0 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenport=5038 listenaddress=0.0.0.0 connectport=5038 connectaddress=$wslIp | Out-Null
    Write-Ok "Port forwarding TCP 5038 : localhost -> ${wslIp}:5038"
} else {
    Write-Warn "IP WSL2 non disponible - mirrored networking actif, localhost direct"
}

# -- 5. Test connexion AMI --------------------------------------------
Write-Step "5/5" "Test connexion AMI Asterisk sur localhost:5038..."
Start-Sleep -Seconds 2

try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $ar = $tcpClient.BeginConnect("127.0.0.1", 5038, $null, $null)
    $ok = $ar.AsyncWaitHandle.WaitOne(3000, $false)
    if ($ok -and $tcpClient.Connected) {
        Write-Ok "AMI accessible sur localhost:5038 !"
        $tcpClient.Close()
    } else {
        Write-Warn "AMI port 5038 non accessible - Asterisk n'est peut-etre pas encore pret"
        Write-Host "    Attendez 5 secondes et relancez : python -c ""from asterisk_ami import check_asterisk_available; print(check_asterisk_available())""" -ForegroundColor Gray
    }
} catch {
    Write-Warn "Test AMI echoue : $_"
}

# -- Affichage configuration MicroSIP -------------------------------
Write-Host ""
Write-Host "======================================================" -ForegroundColor Magenta
Write-Host "  CONFIGURATION MICROSIP" -ForegroundColor White
Write-Host "======================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Telecharger MicroSIP (gratuit) :" -ForegroundColor Cyan
Write-Host "  https://www.microsip.org/downloads" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Dans MicroSIP : clic droit icone -> Add account"
Write-Host ""
Write-Host "  +-----------------------------------------+" -ForegroundColor Yellow
Write-Host "  |  SIP server / Domain : 127.0.0.1       |" -ForegroundColor Yellow
Write-Host "  |  SIP server port     : 5060             |" -ForegroundColor Yellow
Write-Host "  |  Username            : 1001             |" -ForegroundColor Yellow
Write-Host "  |  Password            : agent1234        |" -ForegroundColor Yellow
Write-Host "  +-----------------------------------------+" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Apres OK, MicroSIP doit afficher :" -ForegroundColor White
Write-Host "  [1001] Registered" -ForegroundColor Green
Write-Host ""
Write-Host "  Si Unregistered :"
Write-Host "   - Relancer ce script en Admin"
Write-Host "   - Verifier Asterisk dans WSL :"
Write-Host "     wsl -u root -- asterisk -rx ""sip show peers""" -ForegroundColor Gray
Write-Host ""
Write-Host "  Test de bout en bout :"
Write-Host "   1. MicroSIP affiche [Registered]"
Write-Host "   2. Lancer user_app.py"
Write-Host "   3. Declencher un transfert dans le chat"
Write-Host "   4. MicroSIP SONNE -> decrocher"
Write-Host "   5. Entendre : BIP + numero client en chiffres"
Write-Host ""
Write-Host "======================================================" -ForegroundColor Magenta
Write-Host "  Termine !" -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Magenta
Write-Host ""

Read-Host "Appuyez sur Entree pour fermer"
