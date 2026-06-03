#!/usr/bin/env python3
"""
Production-grade startup script for AI Trading System
Validates all systems before starting the server
"""
import sys
import os
from pathlib import Path

def check_python_version():
    """Ensure Python 3.8+"""
    if sys.version_info < (3, 8):
        print(f"ERROR: Python 3.8+ required (found {sys.version})")
        return False
    print(f"[OK] Python {sys.version.split()[0]}")
    return True

def check_dependencies():
    """Verify all required packages are installed"""
    required = [
        'flask', 'flask_socketio', 'pandas',
        'social_trading_intelligence', 'database_store',
        'security_utils', 'admin_auth', 'order_executor'
    ]

    all_ok = True
    for module in required:
        try:
            __import__(module)
            print(f"[OK] {module}")
        except ImportError:
            print(f"[FAIL] {module}")
            all_ok = False

    return all_ok

def check_files():
    """Verify required files exist"""
    required_files = [
        'server.py',
        'dashboard.html',
        'social_trading_intelligence.py',
        'order_executor.py',
        'database_store.py',
        'security_utils.py',
        'admin_auth.py'
    ]

    all_ok = True
    for fname in required_files:
        if Path(fname).exists():
            print(f"[OK] {fname}")
        else:
            print(f"[MISSING] {fname}")
            all_ok = False

    return all_ok

def check_server_import():
    """Test if server module imports correctly"""
    try:
        import server
        print("[OK] server.py imports successfully")
        return True
    except Exception as e:
        print(f"[FAIL] server.py import: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("AI TRADING SYSTEM - PRE-FLIGHT CHECK")
    print("="*60 + "\n")

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Required Files", check_files),
        ("Server Module", check_server_import),
    ]

    results = {}
    for name, check_fn in checks:
        print(f"\n{name}:")
        print("-" * 40)
        results[name] = check_fn()

    print("\n" + "="*60)
    if all(results.values()):
        print("STATUS: ALL SYSTEMS GO")
        print("="*60)
        print("\nStarting server...")
        print("Dashboard: http://localhost:5000/dashboard")
        print("API: http://localhost:5000/api")
        print("\nPress Ctrl+C to stop\n")

        os.system("python server.py")
    else:
        print("STATUS: FAILED - Fix issues above before running")
        print("="*60)
        sys.exit(1)

if __name__ == '__main__':
    main()
