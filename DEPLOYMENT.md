# DEPLOYMENT GUIDE - AI Trading System MVP

## Pre-Deployment Checklist

### 1. System Requirements
- [ ] Python 3.8 or higher
- [ ] 2GB RAM minimum
- [ ] Windows 10+ or Linux
- [ ] Internet connection (for MT5 connection)
- [ ] 50MB free disk space

### 2. Environment Setup
```bash
# Verify Python
python --version

# Install dependencies (if needed)
pip install flask flask-socketio pandas MetaTrader5

# Run validation
python validate.py
```

### 3. Account Credentials

#### Create MT5 Demo Account
```
1. Visit: https://www.xm.com
2. Create demo account
3. Get credentials:
   - Account Number (Login)
   - Password
   - Server Name (e.g., XMGlobal-MT5 Demo)
4. Download MetaTrader 5 (if not installed)
```

#### Set Environment Variables (Optional but Recommended)
```bash
# Windows (Command Prompt)
set MT5_LOGIN=12345678
set MT5_PASSWORD=yourpassword
set MT5_SERVER=XMGlobal-MT5

# Linux/Mac
export MT5_LOGIN=12345678
export MT5_PASSWORD=yourpassword
export MT5_SERVER=XMGlobal-MT5
```

### 4. Security Setup
```bash
# Generate encryption key (first run creates automatically)
# Users are stored with encrypted passwords
# Never share users.json file
```

---

## STARTUP PROCEDURE

### Step 1: Pre-Flight Check
```bash
python validate.py
```

**Expected Output:**
```
============================================================
SUMMARY: 7/7 test groups passed
Status: READY FOR MVP
```

### Step 2: Start Server
```bash
python run.py
```

**Expected Output:**
```
============================================================
AI TRADING SYSTEM - PRE-FLIGHT CHECK
============================================================

Dashboard: http://localhost:5000/dashboard
API: http://localhost:5000/api

Press Ctrl+C to stop
```

### Step 3: Access Dashboard
```
1. Open: http://localhost:5000/dashboard
2. Login: admin / admin123
3. Change password immediately in production
```

### Step 4: Configure MT5 Account (Optional - Demo Trading)
```
1. Dashboard → Admin Panel (if admin account)
2. Add MT5 Account
3. Enter: Login, Password, Server
4. Credentials are encrypted and stored locally
```

---

## FIRST TRADES (Demo/Paper)

### Test 1: Simulation Mode (No MT5)
```
1. Dashboard open
2. Volume: 0.01 lots
3. Click "BUY"
4. Check Activity Log - order should execute
5. Check Account balance - should show simulated P&L
```

### Test 2: With MT5 Account
```
1. Configure MT5 credentials in admin panel
2. Ensure MetaTrader 5 is running on this machine
3. Place small order: 0.01 lots
4. Check MT5 terminal - order should appear
5. Close order and verify P&L
```

### Test 3: Risk Controls
```
1. Set position size to 0.05 lots
2. Place 5 BUY orders
3. System should prevent more than max_positions_open
4. Check risk_management.py for alert_history
```

---

## MONITORING & TROUBLESHOOTING

### Check Server Status
```bash
# Server running?
curl http://localhost:5000/dashboard

# Account endpoint
curl http://localhost:5000/api/account

# Login test
curl -X POST http://localhost:5000/api/auth/login \
  -d "username=admin&password=admin123"
```

### View Logs
```bash
# Real-time logs (from server output)
python run.py

# Trade history
cat trade_log.json | python -m json.tool

# Recent trades
python -c "
import json
with open('trade_log.json') as f:
    data = json.load(f)
    for t in data['trades'][-5:]:
        print(t)
"
```

### Common Issues

#### Issue: "Cannot connect to MT5"
**Solution:**
1. Ensure MetaTrader 5 is running
2. Check credentials are correct
3. Verify server name matches MT5 terminal
4. Look for logs: `check python run.py output`

#### Issue: "Dashboard loads but no account info"
**Solution:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Check browser console for errors (F12)
3. Verify server is running: `curl http://localhost:5000/api/account`

#### Issue: "Orders not executing"
**Solution:**
1. Check MT5 mode: demo vs live
2. Verify spread is reasonable (<30 pips)
3. Check account has sufficient margin
4. Check risk limits in risk_management.py

#### Issue: "Server crashes on startup"
**Solution:**
1. Run `python validate.py` - see which test fails
2. Check Python version: `python --version`
3. Check all modules installed: `pip list`
4. Delete corrupted users.json and restart

---

## PRODUCTION DEPLOYMENT

### Phase 1: Demo Trading (Week 1-2)
```
- Run on demo/paper account only
- Use small lots (0.01)
- Test all features
- Monitor for 48+ hours with real market hours
- Verify all risk controls trigger correctly
```

### Phase 2: Live Testing (Week 3)
```
- Start with 0.01 lots on live account
- Use only $100-500 initial capital
- Trade during low-volatility sessions
- Monitor continuously (don't leave unattended)
- Have exit strategy ready
```

### Phase 3: Scale Up (Week 4+)
```
- Increase to 0.05 lots if Week 3 successful
- Review all trades and analytics
- Consider automated signals only after consistent P&L
- Keep daily loss limit enabled always
```

---

## CRITICAL SAFEGUARDS

### 1. Daily Loss Limit
```python
# In risk_management.py
max_daily_loss_percent = 2.0  # Max 2% loss per day
```
If hit, trading automatically stops for the day.

### 2. Maximum Drawdown
```python
max_drawdown_percent = 5.0  # Max 5% underwater
```
If exceeded, new trades are blocked.

### 3. Position Limits
```python
max_position_size = 1.0   # Max 1.0 lot per trade
max_positions_open = 5    # Max 5 concurrent positions
```

### 4. Manual Kill Switch
```bash
# Stop trading immediately
# Press Ctrl+C in terminal

# Force close all positions (if needed)
# Use MT5 terminal directly
```

---

## KEY FILES & PURPOSES

| File | Purpose |
|------|---------|
| `server.py` | Main Flask API server - core trading logic |
| `dashboard.html` | Web UI - browser-based trading interface |
| `run.py` | Pre-flight check & startup script |
| `validate.py` | System validation test suite |
| `risk_management.py` | Position sizing, drawdown controls, logging |
| `order_executor.py` | MT5 broker integration |
| `database_store.py` | User/account persistence (JSON) |
| `security_utils.py` | Password hashing & encryption |
| `trade_log.json` | Complete trade history |
| `users.json` | User credentials (encrypted passwords) |

---

## API ENDPOINTS (For Custom Integration)

```
POST /api/trade/buy?volume=0.05
POST /api/trade/sell?volume=0.05
GET  /api/account
GET  /api/auth/me
POST /api/auth/login
POST /api/auth/logout
GET  /api/admin/users
POST /api/admin/approve?user=username
```

---

## PERFORMANCE TARGETS (MVP)

| Metric | Target | Status |
|--------|--------|--------|
| Server startup | <5 seconds | ✓ |
| Dashboard load | <2 seconds | ✓ |
| Order execution | <1 second | ✓ |
| Account update | Real-time (socket) | ✓ |
| System uptime | >99% | Target |
| False signals | <20% | Monitor |

---

## SUPPORT & NEXT STEPS

### If something breaks:
1. Run `python validate.py` to diagnose
2. Check `trade_log.json` for recent activity
3. Review server output for errors
4. Check browser console (F12) for client-side errors

### To improve the system:
1. Monitor win rate (target: >55%)
2. Track P&L per day (target: >$50/day)
3. Review risk metrics weekly
4. Iterate on position sizing parameters

### Future enhancements:
- [ ] Advanced AI signal generation
- [ ] Multi-timeframe analysis
- [ ] Mobile dashboard
- [ ] Real-time Slack alerts
- [ ] Advanced backtesting framework

---

**IMPORTANT DISCLAIMER**
This system is provided for educational purposes. Always use demo/paper trading first. Never risk capital you cannot afford to lose. Past performance does not guarantee future results. Automated trading involves substantial risk of loss.

**Start with demo trading. Test thoroughly. Scale gradually. Monitor constantly.**
