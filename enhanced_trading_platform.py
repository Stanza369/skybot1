"""Compatibility entrypoint.

Your earlier errors referenced `enhanced_trading_platform.py`, but this repo
does not contain it. This file forwards execution to the existing backend.

Usage:
  python enhanced_trading_platform.py

This will start the Flask server from server.py (port 5000) which serves
`dashboard.html` at:
  http://127.0.0.1:5000/dashboard
"""

import runpy

if __name__ == "__main__":
    runpy.run_module("server", run_name="__main__")

