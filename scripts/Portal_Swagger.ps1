# ─── Configurações ────────────────────────────────────────────────────────────
$BASE_URL    = "http://localhost:8000"
$USERNAME    = "alexandre.mohamad"
$PASSWORD    = "Awm2@11712"
$APP_CONTEXT = "PORTAL"   # ajuste conforme o app_context que você usa

# ─── 1. Busca o CSRF token via endpoint público ───────────────────────────────
Write-Host ">> Obtendo CSRF token..." -ForegroundColor Cyan

# Usa /api/accounts/auth/aplicacoes/ — endpoint AllowAny que responde GET
$null = Invoke-WebRequest `
    -Uri "$BASE_URL/api/accounts/auth/aplicacoes/" `
    -Method GET `
    -SessionVariable session `
    -ErrorAction SilentlyContinue

$allCookies = $session.Cookies.GetCookies($BASE_URL)
$csrfCookie = $allCookies | Where-Object { $_.Name -eq "csrftoken" }
$csrfToken  = $csrfCookie.Value

if (-not $csrfToken) {
    Write-Host "   AVISO: csrftoken nao obtido. Tentando login sem ele..." -ForegroundColor Yellow
} else {
    Write-Host "   CSRF Token: $csrfToken" -ForegroundColor Gray
}

# ─── 2. Faz o login ───────────────────────────────────────────────────────────
Write-Host ">> Fazendo login como '$USERNAME' no app '$APP_CONTEXT'..." -ForegroundColor Cyan

$loginBody = @{
    username    = $USERNAME
    password    = $PASSWORD
    app_context = $APP_CONTEXT
} | ConvertTo-Json

$headers = @{ "Content-Type" = "application/json" }
if ($csrfToken) {
    $headers["X-CSRFToken"] = $csrfToken
}

$loginResponse = Invoke-WebRequest `
    -Uri "$BASE_URL/api/accounts/login/" `
    -Method POST `
    -Body $loginBody `
    -Headers $headers `
    -WebSession $session

if ($loginResponse.StatusCode -eq 200) {
    Write-Host "   Login OK!" -ForegroundColor Green

    $allSessionCookies = $session.Cookies.GetCookies($BASE_URL)
    $sessionCookie     = $allSessionCookies | Where-Object { $_.Name -like "gpp_session_*" }
    Write-Host "   Cookie de sessão: $($sessionCookie.Value)" -ForegroundColor Gray
} else {
    Write-Host "   Falha no login! Status: $($loginResponse.StatusCode)" -ForegroundColor Red
    Write-Host $loginResponse.Content
    exit 1
}

# ─── 3. Abre o Swagger UI no browser ─────────────────────────────────────────
Write-Host ">> Abrindo Swagger UI..." -ForegroundColor Cyan
Start-Process "$BASE_URL/api/docs/"

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " Swagger UI aberto no browser!"          -ForegroundColor Yellow
Write-Host " Schema JSON : $BASE_URL/api/schema/"    -ForegroundColor Gray
Write-Host " ReDoc       : $BASE_URL/api/redoc/"     -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Yellow