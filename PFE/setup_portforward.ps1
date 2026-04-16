# setup_portforward.ps1 — À lancer dans PowerShell Admin sur Windows
# Redirige le port AMI d'Asterisk (WSL2 → Windows)

$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "IP WSL2 : $wslIp"

netsh interface portproxy delete v4tov4 listenport=5038 listenaddress=0.0.0.0 2>>$null
netsh interface portproxy add v4tov4 listenport=5038 listenaddress=0.0.0.0 connectport=5038 connectaddress=$wslIp

Write-Host "Port forwarding AMI configuré : localhost:5038 -> $wslIp:5038" -ForegroundColor Green
