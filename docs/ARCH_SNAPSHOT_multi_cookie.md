## 🔄 Multi-Cookie Auth (Nova Fase)

**Status**: Implementado na branch `feature/multi-cookie-auth`

### Como funciona

- Cada app tem seu cookie: `gpp_session_ACOES_PNGI`, `gpp_session_CARGA_ORG_LOT`
- Login cria cookie específico: `POST /api/accounts/login/ {app_context}`
- Middleware valida cookie correto pela URL
- Logout específico: `POST /api/acoes-pngi/auth/logout/`
- **Tabs paralelas funcionam nativamente**

### Fluxo frontend

```
Landing → Login ACOES_PNGI → /app/acoes-pngi/
Nova tab → Login CARGA_ORG_LOT → /app/carga-org-lot/
```

**Sem switch, sem portal obrigatório.**