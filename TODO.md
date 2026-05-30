- [ ] Inspect current elite-dashboard integration points (done: read dashboard.html/script_elite.js/style.css/main.py/mt5_service.py)
- [x] Plan approved for production-grade persistence + risk + Telegram wiring
- [ ] Remove remaining simulations in elite UI (frontend): replace `elite_bridge.js` simulated AI votes/proxies with real backend signals
- [x] Fix close-persistence: ensure `ProductionTradingBot.close_trade()` updates correct DB row (ticket vs order_id mismatch)

- [ ] Make account metrics real: patch `trading-dashboard/backend/mt5_service.py::account_info()` to fetch actual MT5 margin/free_margin/equity
- [ ] Add backend AI signal endpoint (real indicator/model execution) and wire frontend
- [ ] Verify WS/candles feed matches dashboard chart expectations
- [ ] Smoke test end-to-end: connect MT5 → place order → close order → verify DB row + UI updates
- [ ] Run existing tests (risk/strategy)

