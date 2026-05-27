# TODO - Economic Calendar Intelligence Engine (ForexFactory → WS → Dashboard)

- [ ] Add backend: `trading-dashboard/backend/news_engine.py`
- [ ] Add backend: `trading-dashboard/backend/news_ai.py`
- [ ] Add backend: `trading-dashboard/backend/ws_news_streamer.py`
- [ ] Update `trading-dashboard/backend/main.py` to expose WebSocket `/api/ws/news`
- [ ] Update `trading-dashboard/frontend/dashboard.html` to add widgets for calendar + alerts
- [ ] Update `trading-dashboard/frontend/script_elite.js` to connect to `/api/ws/news` and render widgets
- [ ] Add minimal defensive parsing + event filtering (gold-relevant currencies)
- [ ] Install deps in dashboard backend (`beautifulsoup4`, `requests`)
- [ ] Smoke test: run backend, open dashboard, verify WS messages render

