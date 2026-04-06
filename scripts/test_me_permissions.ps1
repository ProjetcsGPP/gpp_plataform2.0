# ============================================================
# GPP Plataform 2.0 — Testes manuais: GET /api/accounts/me/permissions/
# ============================================================
# PREENCHA AS VARIÁVEIS ABAIXO ANTES DE EXECUTAR
# ============================================================

$BASE_URL  = "http://localhost:8000"   # ajuste se necessário

# CASO 1 — PORTAL
$USERNAME1 = "alexandre.mohamad"
$SecurePassword1 = ConvertTo-SecureString "Awm2@11712" -AsPlainText -Force

# CASO 2 — ACOES_PNGI
$USERNAME2 = "alexandre.mohamad"
$SecurePassword2 = ConvertTo-SecureString "Awm2@11712" -AsPlainText -Force

# CASO 3 — CARGA_ORG_LOT
$USERNAME3 = "alexandre.mohamad"
$SecurePassword3 = ConvertTo-SecureString "Awm2@11712" -AsPlainText -Force

# ============================================================
# NÃO ALTERE ABAIXO DESTA LINHA
# ============================================================

function Show-Response {
    param($Label, $StatusCode, $Body)
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host " $Label" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Status : $StatusCode" -ForegroundColor Yellow
    try {
        $json = $Body | ConvertFrom-Json
        Write-Host "Body   :" -ForegroundColor Yellow
        $json | ConvertTo-Json -Depth 10 | Write-Host -ForegroundColor White
    } catch {
        Write-Host "Body   : $Body" -ForegroundColor White
    }
}

function Show-ErrorResponse {
    param($Label, $Exception)
    Write-Host "`n========================================" -ForegroundColor Magenta
    Write-Host " $Label" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta
    $errResp = $Exception.Response
    if ($errResp) {
        $statusCode = [int]$errResp.StatusCode
        $bodyText = $Exception.Message
        Write-Host "Status : $statusCode" -ForegroundColor Yellow
        Write-Host "Body   : $bodyText" -ForegroundColor White
    } else {
        Write-Host "Erro   : $($Exception.Message)" -ForegroundColor Red
    }
}

function Invoke-TestCase {
    param(
        [string]$CaseLabel,
        [string]$AppContext,
        [string]$Username,
        [SecureString]$SecurePassword
    )

    # Converte SecureString para plain text apenas para montar o JSON
    $bstr     = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    $plainPwd = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

    Write-Host "`n>>> INICIANDO $CaseLabel — $AppContext" -ForegroundColor Green

    # ── LOGIN ──────────────────────────────────────────────
    $loginBody = @{
        username    = $Username
        password    = $plainPwd
        app_context = $AppContext
    } | ConvertTo-Json

    try {
        $loginResp = Invoke-WebRequest `
            -Uri         "$BASE_URL/api/accounts/login/" `
            -Method      POST `
            -ContentType "application/json" `
            -Body        $loginBody `
            -ErrorAction Stop

        Show-Response "$CaseLabel — Login ($AppContext)" $loginResp.StatusCode $loginResp.Content

    } catch {
        Show-ErrorResponse "$CaseLabel — Falha no Login ($AppContext)" $_.Exception
        return
    }

    # ── EXTRAI O COOKIE ────────────────────────────────────
    $cookieName = "gpp_session_$AppContext"
    $cookieValue = $null

    $setCookieHeaders = $loginResp.Headers["Set-Cookie"]
    if ($setCookieHeaders) {
        foreach ($entry in $setCookieHeaders) {
            $parts = $entry -split ";"
            $nameValue = $parts[0].Trim()
            if ($nameValue -match "^$cookieName=") {
                $cookieValue = $nameValue
                break
            }
        }
    }

    if (-not $cookieValue) {
        Write-Host "`n[AVISO] Cookie '$cookieName' nao encontrado. Headers recebidos:" -ForegroundColor Red
        $loginResp.Headers.GetEnumerator() | Where-Object { $_.Key -match "Cookie|Set-Cookie" } |
            ForEach-Object { Write-Host "  $($_.Key): $($_.Value)" -ForegroundColor DarkYellow }
        return
    }

    Write-Host "`n[INFO] Cookie capturado: $cookieValue" -ForegroundColor DarkGray

    # ── GET /me/permissions/ ───────────────────────────────
    try {
        $permResp = Invoke-WebRequest `
            -Uri     "$BASE_URL/api/accounts/me/permissions/" `
            -Method  GET `
            -Headers @{ Cookie = $cookieValue } `
            -ErrorAction Stop

        Show-Response "$CaseLabel — GET /me/permissions/ ($AppContext)" $permResp.StatusCode $permResp.Content

    } catch {
        $errDetails = $_.ErrorDetails.Message
        $statusCode  = $_.Exception.Response.StatusCode.value__
        Write-Host "`n========================================" -ForegroundColor Magenta
        Write-Host " $CaseLabel — ERRO em /me/permissions/ ($AppContext)" -ForegroundColor Magenta
        Write-Host "========================================" -ForegroundColor Magenta
        Write-Host "Status : $statusCode" -ForegroundColor Yellow
        if ($errDetails) {
            try {
                $errJson = $errDetails | ConvertFrom-Json
                $errJson | ConvertTo-Json -Depth 5 | Write-Host -ForegroundColor White
            } catch {
                Write-Host "Body   : $errDetails" -ForegroundColor White
            }
        } else {
            Write-Host "Body   : $($_.Exception.Message)" -ForegroundColor White
        }
    }
}

# ─── CASOS AUTENTICADOS ───────────────────────────────────────────────────────
Invoke-TestCase -CaseLabel "CASO 1" -AppContext "PORTAL"        -Username $USERNAME1 -SecurePassword $SecurePassword1
Invoke-TestCase -CaseLabel "CASO 2" -AppContext "ACOES_PNGI"    -Username $USERNAME2 -SecurePassword $SecurePassword2
Invoke-TestCase -CaseLabel "CASO 3" -AppContext "CARGA_ORG_LOT" -Username $USERNAME3 -SecurePassword $SecurePassword3

# ─── CASO 4 — Sem autenticacao (esperado 401) ─────────────────────────────────
Write-Host "`n>>> INICIANDO CASO 4 — Sem autenticacao" -ForegroundColor Green
try {
    $r = Invoke-WebRequest -Uri "$BASE_URL/api/accounts/me/permissions/" -Method GET -ErrorAction Stop
    Show-Response "CASO 4 — Sem autenticacao" $r.StatusCode $r.Content
} catch {
    $statusCode  = $_.Exception.Response.StatusCode.value__
    $errDetails  = $_.ErrorDetails.Message
    Write-Host "`n========================================" -ForegroundColor Magenta
    Write-Host " CASO 4 — Sem autenticacao (esperado 401)" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "Status : $statusCode" -ForegroundColor Yellow
    Write-Host "Body   : $errDetails" -ForegroundColor White
}

# ─── CASO 5 — Cookie forjado (esperado 401) ───────────────────────────────────
Write-Host "`n>>> INICIANDO CASO 5 — Cookie forjado" -ForegroundColor Green
try {
    $r = Invoke-WebRequest `
        -Uri     "$BASE_URL/api/accounts/me/permissions/" `
        -Method  GET `
        -Headers @{ Cookie = "gpp_session_PORTAL=sessao_invalida_forjada_12345" } `
        -ErrorAction Stop
    Show-Response "CASO 5 — Cookie forjado" $r.StatusCode $r.Content
} catch {
    $statusCode  = $_.Exception.Response.StatusCode.value__
    $errDetails  = $_.ErrorDetails.Message
    Write-Host "`n========================================" -ForegroundColor Magenta
    Write-Host " CASO 5 — Cookie forjado (esperado 401)" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "Status : $statusCode" -ForegroundColor Yellow
    Write-Host "Body   : $errDetails" -ForegroundColor White
}

Write-Host "`n>>> TESTES CONCLUIDOS" -ForegroundColor Green
