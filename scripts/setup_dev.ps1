<#
.SYNOPSIS
    GPP Plataform 2.0 — Script de setup do ambiente de desenvolvimento (Windows / PowerShell)

.DESCRIPTION
    1. Cria virtualenv em .venv\
    2. Instala dependências de requirements.txt
    3. Gera par de chaves RSA em keys\ (private_key.pem / public_key.pem)
    4. Copia .env.example → .env (não sobrescreve se já existir)
    5. Executa migrate
    6. Executa setup_gpp
    7. Exibe instruções finais

.EXAMPLE
    .\scripts\setup_dev.ps1

.NOTES
    Requer: Python >= 3.11 (testado com 3.14), OpenSSL ou python cryptography no PATH.
    Execute a partir da raiz do projeto.
#>

#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Helpers ────────────────────────────────────────────────────────────────
function Write-Step($num, $msg) {
    Write-Host ""`n[$num] $msg" -ForegroundColor Cyan"
}
function Write-Ok($msg)  { Write-Host "  ✔ $msg" -ForegroundColor Green }
function Write-Warn($msg){ Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  ✘ $msg" -ForegroundColor Red }

# ── Verificação de pré-requisitos ──────────────────────────────────────────
Write-Host ""
Write-Host "=" * 62 -ForegroundColor Magenta
Write-Host "  GPP Platform 2.0 — Setup Ambiente Dev" -ForegroundColor Magenta
Write-Host "=" * 62 -ForegroundColor Magenta

$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pythonCmd = $candidate
        break
    }
}
if (-not $pythonCmd) {
    Write-Err "Python não encontrado no PATH. Instale Python >= 3.11 e tente novamente."
    exit 1
}
$pyVersion = & $pythonCmd --version 2>&1
Write-Ok "Python encontrado: $pyVersion"

# ── 1. Virtualenv ──────────────────────────────────────────────────────────
Write-Step 1 "Criando virtualenv em .venv\"
if (-not (Test-Path ".venv")) {
    & $pythonCmd -m venv .venv
    Write-Ok "Virtualenv criado."
} else {
    Write-Warn "Virtualenv já existe — reutilizando."
}

$pip  = ".venv\Scripts\pip.exe"
$python = ".venv\Scripts\python.exe"
#$manage = ".venv\Scripts\python.exe manage.py"

# ── 2. Instalar dependências ───────────────────────────────────────────────
Write-Step 2 "Instalando dependências de requirements.txt..."
if (-not (Test-Path "requirements.txt")) {
    Write-Err "requirements.txt não encontrado na raiz do projeto."
    exit 1
}
& $pip install --upgrade pip --quiet
& $pip install -r requirements.txt
Write-Ok "Dependências instaladas."

# ── 3. Gerar chaves RSA ────────────────────────────────────────────────────
Write-Step 3 "Gerando par de chaves RSA em keys\"
if (-not (Test-Path "keys")) {
    New-Item -ItemType Directory -Path "keys" | Out-Null
}

$privateKey = "keys\private_key.pem"
$publicKey  = "keys\public_key.pem"

if (-not (Test-Path $privateKey)) {
    # Tenta via módulo Python cryptography (já instalado no requirements)
    $rsaScript = @"
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
with open('$($privateKey -replace "\\\\","/")', 'wb') as f:
    f.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()
    ))
with open('$($publicKey -replace "\\\\","/")', 'wb') as f:
    f.write(key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo
    ))
print('RSA keys generated.')
"@
    & $python -c $rsaScript
    Write-Ok "Chaves RSA geradas: $privateKey / $publicKey"
} else {
    Write-Warn "Chave privada já existe — mantendo."
}

# ── 4. Arquivo .env ────────────────────────────────────────────────────────
Write-Step 4 "Configurando .env..."
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Ok ".env criado a partir de .env.example — edite as variáveis antes de continuar."
    } else {
        Write-Warn ".env.example não encontrado. Crie .env manualmente."
    }
} else {
    Write-Warn ".env já existe — mantendo (não sobrescrevendo)."
}

# Garante que GPP_ADMIN_PASSWORD esteja definida para setup_gpp
if (-not $env:GPP_ADMIN_PASSWORD) {
    Write-Warn "Variável de ambiente GPP_ADMIN_PASSWORD não definida."
    $adminPassword = Read-Host -Prompt "  → Digite a senha para o superuser GPP (GPP_ADMIN_PASSWORD)"
    if (-not $adminPassword) {
        Write-Err "Senha não pode ser vazia."
        exit 1
    }
    $env:GPP_ADMIN_PASSWORD = $adminPassword
}

if (-not $env:GPP_ADMIN_USERNAME) { $env:GPP_ADMIN_USERNAME = "admin" }
if (-not $env:GPP_ADMIN_EMAIL)    { $env:GPP_ADMIN_EMAIL = "admin@gpp.local" }

# ── 5. Migrate ─────────────────────────────────────────────────────────────
Write-Step 5 "Executando migrate..."
& $python manage.py migrate
Write-Ok "Migrate concluído."

# ── 6. setup_gpp ───────────────────────────────────────────────────────────
Write-Step 6 "Executando setup_gpp..."
& $python manage.py setup_gpp
Write-Ok "Setup GPP concluído."

# ── 7. Instruções finais ───────────────────────────────────────────────────
Write-Host ""
Write-Host ("=" * 62) -ForegroundColor Magenta
Write-Host "  SETUP CONCLUÍDO" -ForegroundColor Green
Write-Host ("=" * 62) -ForegroundColor Magenta
Write-Host ""
Write-Host "  Para iniciar o servidor de desenvolvimento:" -ForegroundColor White
Write-Host "    .venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "    python manage.py runserver" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Superuser:" -ForegroundColor White
Write-Host "    Username : $($env:GPP_ADMIN_USERNAME)" -ForegroundColor Yellow
Write-Host "    Email    : $($env:GPP_ADMIN_EMAIL)" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Admin Django:  http://127.0.0.1:8000/admin/" -ForegroundColor Cyan
Write-Host "  API Root:      http://127.0.0.1:8000/api/" -ForegroundColor Cyan
Write-Host ("─" * 62) -ForegroundColor DarkGray
