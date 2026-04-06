# ============================================================
# GPP Plataform 2.0 — Testes manuais: GET /api/accounts/me/permissions/
# ============================================================
# PREENCHA AS VARIÁVEIS ABAIXO ANTES DE EXECUTAR
# ============================================================

$BASE_URL  = "http://localhost:8000"   # ajuste se necessário

# CASO 1 — PORTAL
$USERNAME1 = "alexandre.mohamad"
$PASSWORD1 = "Awm2@11712"

# CASO 2 — ACOES_PNGI
$USERNAME2 = "alexandre.mohamad"
$PASSWORD2 = "Awm2@11712"

# CASO 3 — CARGA_ORG_LOT
$USERNAME3 = "alexandre.mohamad"
$PASSWORD3 = "Awm2@11712"

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
    # PS7: a resposta de erro fica em $Exception.Response (HttpResponseMessage)
    $errResp = $Exception.Response
    if ($errResp) {
        $statusCode = [int]$errResp.StatusCode
        # Lê o body do erro — PS7 usa Content como string direto na exception
        $bodyText = $Exception.Message
        # Tenta extrair via ResponseBody se disponível (Invoke-WebRequest -ErrorVariable)
        Write-Host "Status : $statusCode" -ForegroundColor Yellow
        Write-Host "Body   : $bodyText" -ForegroundColor White
    } else {
        Write-Host "Erro   : $($Exception.Message)" -ForegroundColor Red
    }
}

function Run-TestCase {
    param($CaseLabel, $AppContext, $Username, $Password)

    Write-Host "`n>>> INICIANDO $CaseLabel — $AppContext" -ForegroundColor Green

    # ── LOGIN ──────────────────────────────────────────────
    $loginBody = @{
        username    = $Username
        password    = $Password
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

    # PS7: cookies ficam em $loginResp.Headers["Set-Cookie"] como array de strings
    $setCookieHeaders = $loginResp.Headers["Set-Cookie"]
    if ($setCookieHeaders) {
        foreach ($entry in $setCookieHeaders) {
            # Cada entry pode ser "gpp_session_PORTAL=abc123; Path=/; HttpOnly"
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
        # Captura body do erro 4xx via -ErrorVariable não funciona bem no PS7
        # Usa o truque de ler ErrorDetails se disponível
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
Run-TestCase -CaseLabel "CASO 1" -AppContext "PORTAL"       -Username $USERNAME1 -Password $PASSWORD1
Run-TestCase -CaseLabel "CASO 2" -AppContext "ACOES_PNGI"   -Username $USERNAME2 -Password $PASSWORD2
Run-TestCase -CaseLabel "CASO 3" -AppContext "CARGA_ORG_LOT" -Username $USERNAME3 -Password $PASSWORD3

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
