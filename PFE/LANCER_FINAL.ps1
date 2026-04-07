# ============================================================
#  LANCER_FINAL.ps1 — Lance le VoiceBot via whisper_env
#  Utilise les chemins absolus (pas besoin d'activer conda)
# ============================================================

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "VoiceBot Tunisie Telecom"

# ── Chemins absolus ──────────────────────────────────────────
$CONDA_ROOT  = "C:\Users\Yasmine\anaconda3"
$ENV_NAME    = "whisper_env"
$PYTHON      = "$CONDA_ROOT\envs\$ENV_NAME\python.exe"
$PIP         = "$CONDA_ROOT\envs\$ENV_NAME\Scripts\pip.exe"
$SCRIPT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  VoiceBot Tunisie Telecom — Lancement Final      ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Vérifier que l'env whisper_env existe ────────────────────
if (-not (Test-Path $PYTHON)) {
    Write-Host "[ERREUR] Python whisper_env introuvable : $PYTHON" -ForegroundColor Red
    Write-Host "Verifiez que l'environnement conda 'whisper_env' existe." -ForegroundColor Yellow
    Read-Host "Appuyez sur Entree pour quitter"
    exit 1
}

Write-Host "[OK] Python whisper_env : $PYTHON" -ForegroundColor Green

# ── Afficher les versions actuelles ─────────────────────────
Write-Host ""
Write-Host "[*] Versions detectees :" -ForegroundColor Yellow
& $PYTHON -c "import sklearn; print(f'     scikit-learn : {sklearn.__version__}')" 2>$null
& $PYTHON -c "import transformers; print(f'     transformers : {transformers.__version__}')" 2>$null
& $PYTHON -c "import torch; print(f'     torch        : {torch.__version__}')" 2>$null
& $PYTHON -c "import sentence_transformers; print(f'     sentence-tr  : {sentence_transformers.__version__}')" 2>$null
Write-Host ""

# ── CORRECTION 1 : scikit-learn ─────────────────────────────
Write-Host "[1/3] Mise a jour scikit-learn..." -ForegroundColor Yellow
$skVer = & $PYTHON -c "import sklearn; print(sklearn.__version__)" 2>$null
$skOk  = & $PYTHON -c "import sklearn; v=tuple(map(int,sklearn.__version__.split('.'))); exit(0 if v>=(1,7) else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      sklearn $skVer trop ancien -> mise a jour..." -ForegroundColor Yellow
    & $PIP install "scikit-learn>=1.7.0" --upgrade --quiet
    Write-Host "      [OK] scikit-learn mis a jour." -ForegroundColor Green
} else {
    Write-Host "      [OK] scikit-learn $skVer (compatible)." -ForegroundColor Green
}

# ── CORRECTION 2 : transformers ─────────────────────────────
Write-Host ""
Write-Host "[2/3] Verification transformers..." -ForegroundColor Yellow
$trOk = & $PYTHON -c "
import torch.optim.lr_scheduler as s
exit(0 if hasattr(s, 'LRScheduler') else 1)
" 2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Host "      LRScheduler manquant -> mise a jour transformers..." -ForegroundColor Yellow
    & $PIP install "transformers>=4.40.0" --upgrade --quiet
    & $PIP install "sentence-transformers>=3.0.0" --upgrade --quiet
    Write-Host "      [OK] transformers mis a jour." -ForegroundColor Green
} else {
    Write-Host "      [OK] torch.LRScheduler present." -ForegroundColor Green
}

# ── CORRECTION 3 : packages supplementaires ─────────────────
Write-Host ""
Write-Host "[3/3] Packages supplementaires..." -ForegroundColor Yellow
& $PYTHON -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) { & $PIP install "flask>=2.3.0" --quiet }
& $PYTHON -c "import gtts" 2>$null
if ($LASTEXITCODE -ne 0) { & $PIP install gTTS --quiet }
& $PYTHON -c "import colorlog" 2>$null
if ($LASTEXITCODE -ne 0) { & $PIP install colorlog --quiet }
Write-Host "      [OK]" -ForegroundColor Green

# ── Lancement ────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Lancement du VoiceBot..." -ForegroundColor Cyan
Write-Host "  Ouvrez : http://localhost:5000" -ForegroundColor White
Write-Host "══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Set-Location $SCRIPT_DIR

# Ouvrir le navigateur dans 5 secondes
Start-Job -ScriptBlock {
    Start-Sleep 5
    Start-Process "http://localhost:5000"
} | Out-Null

# Lancer via app_launcher.py (avec les patches intégrés)
& $PYTHON "$SCRIPT_DIR\app_launcher.py"

Write-Host ""
Write-Host "Serveur arrete." -ForegroundColor Yellow
Read-Host "Appuyez sur Entree pour quitter"
