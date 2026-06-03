# XAU/USD AI Trading System - MVP Setup

## Quick Start (5 minutes)

```bash
# 1. Run the pre-flight check
python run.py

# 2. Access dashboard
# Open: http://localhost:5000/dashboard
# Default creds: admin / admin123
```

## System Status

| Component | Status | Details |
|-----------|--------|---------|
| **Server** | ✓ Working | Flask + SocketIO operational |
| **Dashboard** | ✓ Fixed | HTML dashboard endpoint working |
| **MT5 Integration** | ⚠ Ready | Broker connection configurable |
| **AI Engine** | ✓ Ready | Mock signals functional |
| **Database** | ✓ Working | JSON-based persistence |

## Architecture

```
Dashboard (HTML)
    ↓
Flask Server (Port 5000)
    ├── /dashboard (HTML serving)
    ├── /api/trade/buy (Trade execution)
    ├── /api/trade/sell (Trade execution)
    ├── /api/account (Account state)
    ├── /api/auth/* (Login/auth)
    └── /api/admin/* (Admin functions)
    ↓
MT5 Broker (via order_executor.py)
    ├── Real: MetaTrader5 library
    └── Mock: Simulated price/fills
    ↓
Social Intelligence Database
    └── Trade history & sentiment
```

## Required Accounts

### MT5 Demo Account (XM Global)
1. Create account: https://www.xm.com
2. Get demo credentials:
   - Login (Account #)
   - Password
   - Server (e.g., XMGlobal-MT5 Demo)

### Store Securely
Add to environment variables or `.env`:
```
MT5_LOGIN=12345678
MT5_PASSWORD=yourpassword
MT5_SERVER=XMGlobal-MT5 Demo
```

## First Run Checklist

- [ ] Run `python run.py` - all checks pass
- [ ] Open http://localhost:5000/dashboard
- [ ] Login: admin / admin123
- [ ] See "Account" card with balance
- [ ] See "Execute Trade" section
- [ ] Try a small 0.01 lot BUY
- [ ] Check trade result in activity log

## Current Limitations (MVP)

| Feature | Status | Notes |
|---------|--------|-------|
| Live MT5 Trading | In Dev | Add account credentials first |
| AI Signals | Mock | Returns random signals |
| Risk Management | Basic | Simple position sizing |
| Monitoring | Basic | Real-time P&L only |
| Mobile Dashboard | Not Yet | Web-only for now |

## Key Files

```
run.py                          # Pre-flight check & startup
server.py                       # Flask API server (core)
dashboard.html                  # Web UI
order_executor.py               # MT5 broker integration
database_store.py               # JSON persistence
security_utils.py               # Encryption/passwords
admin_auth.py                   # Authentication
social_trading_intelligence.py  # Mock sentiment engine
```

## Known Issues & Fixes

### Issue: "ModuleNotFoundError"
**Fix:** Run `pip install -r requirements.txt`

### Issue: "Dashboard won't load"
**Fix:** Ensure you're logged in (login endpoint works), then access `/dashboard`

### Issue: "MT5 connection fails"
**Fix:** Add MT5 account credentials via admin panel

## Next Steps (This Month)

**Week 1**: ✓ Server stable + dashboard working  
**Week 2**: Risk controls + position sizing  
**Week 3**: MT5 connection hardening  
**Week 4**: Monitoring dashboard + alerts  

## Support

- Check `TODO.md` for detailed roadmap
- All API endpoints return JSON with `{success, message, data}`
- Logs saved to `trading_system.log`
- Database in `data/` directory

---

**WARNING**: This is an MVP. Start with paper/demo trading only. Never use real money until fully tested.
