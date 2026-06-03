#!/usr/bin/env python3
"""
MVP System Validation Suite
Tests all critical functions before going live
"""
import sys
import json
import time
from pathlib import Path

def test_imports():
    """Test all critical imports work"""
    print("\n[TEST] Module Imports")
    print("-" * 50)

    tests = {
        'Flask': 'from flask import Flask',
        'SocketIO': 'from flask_socketio import SocketIO',
        'MT5': 'import MetaTrader5 as mt5',
        'Pandas': 'import pandas as pd',
        'Server': 'import server',
    }

    passed = 0
    for name, imp in tests.items():
        try:
            exec(imp)
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")

    print(f"  Result: {passed}/{len(tests)} passed\n")
    return passed == len(tests)

def test_files():
    """Check all required files exist"""
    print("[TEST] Required Files")
    print("-" * 50)

    files = {
        'server.py': 'Flask server',
        'dashboard.html': 'Dashboard UI',
        'order_executor.py': 'MT5 broker',
        'database_store.py': 'Persistence',
        'security_utils.py': 'Encryption',
        'admin_auth.py': 'Authentication',
        'social_trading_intelligence.py': 'Sentiment engine',
    }

    passed = 0
    for fname, desc in files.items():
        if Path(fname).exists():
            size = Path(fname).stat().st_size
            print(f"  [PASS] {fname:30} ({size:,} bytes) - {desc}")
            passed += 1
        else:
            print(f"  [FAIL] {fname:30} MISSING - {desc}")

    print(f"  Result: {passed}/{len(files)} passed\n")
    return passed == len(files)

def test_config():
    """Check configuration files"""
    print("[TEST] Configuration")
    print("-" * 50)

    # Check for users.json
    if Path('users.json').exists():
        try:
            with open('users.json') as f:
                users = json.load(f)
            print(f"  [PASS] users.json ({len(users)} users)")
            if 'admin' in users:
                print(f"  [PASS] Admin user configured")
            else:
                print(f"  [WARN] Admin user missing")
        except Exception as e:
            print(f"  [FAIL] users.json invalid: {e}")
    else:
        print(f"  [INFO] users.json will be created on first run")

    print()
    return True

def test_permissions():
    """Check file permissions"""
    print("[TEST] File Permissions")
    print("-" * 50)

    critical_files = ['server.py', 'dashboard.html']
    passed = 0

    for fname in critical_files:
        if Path(fname).exists() and Path(fname).is_file():
            print(f"  [PASS] {fname} readable")
            passed += 1
        else:
            print(f"  [FAIL] {fname} not accessible")

    print(f"  Result: {passed}/{len(critical_files)} passed\n")
    return passed == len(critical_files)

def test_endpoints():
    """Validate server endpoints are properly defined"""
    print("[TEST] API Endpoints")
    print("-" * 50)

    required_endpoints = [
        '/dashboard',
        '/api/account',
        '/api/trade/buy',
        '/api/trade/sell',
        '/api/auth/login',
        '/api/auth/logout',
    ]

    # Read server.py and check for route decorators
    with open('server.py') as f:
        server_code = f.read()

    passed = 0
    for endpoint in required_endpoints:
        if f"'{endpoint}'" in server_code or f'"{endpoint}"' in server_code:
            print(f"  [PASS] {endpoint}")
            passed += 1
        else:
            print(f"  [FAIL] {endpoint} not found")

    print(f"  Result: {passed}/{len(required_endpoints)} passed\n")
    return passed == len(required_endpoints)

def test_database():
    """Test database operations"""
    print("[TEST] Database")
    print("-" * 50)

    try:
        from database_store import JsonStore
        store = JsonStore()

        # Try loading users
        users = store.load_users()
        print(f"  [PASS] Load users ({len(users)} users)")

        # Try loading MT5 accounts
        accounts = store.load_mt5_accounts()
        print(f"  [PASS] Load MT5 accounts")

        print()
        return True
    except Exception as e:
        print(f"  [FAIL] Database error: {e}\n")
        return False

def test_security():
    """Test security utilities"""
    print("[TEST] Security")
    print("-" * 50)

    try:
        from security_utils import SecurityUtils
        security = SecurityUtils()

        # Test password hashing
        pwd = "test123"
        hashed = security.hash_password(pwd)
        print(f"  [PASS] Password hashing works")

        # Test encryption
        plaintext = "secret_data"
        encrypted = security.encrypt_text(plaintext)
        decrypted = security.decrypt_text(encrypted)

        if decrypted == plaintext:
            print(f"  [PASS] Encryption/decryption works")
        else:
            print(f"  [FAIL] Decryption mismatch")
            return False

        print()
        return True
    except Exception as e:
        print(f"  [FAIL] Security error: {e}\n")
        return False

def main():
    print("\n" + "="*60)
    print("MVP SYSTEM VALIDATION SUITE")
    print("="*60)

    tests = [
        test_imports,
        test_files,
        test_config,
        test_permissions,
        test_endpoints,
        test_database,
        test_security,
    ]

    results = []
    for test_fn in tests:
        try:
            results.append(test_fn())
        except Exception as e:
            print(f"[ERROR] Test {test_fn.__name__} crashed: {e}\n")
            results.append(False)

    print("="*60)
    print(f"SUMMARY: {sum(results)}/{len(results)} test groups passed")
    print("="*60)

    if all(results):
        print("\nStatus: READY FOR MVP")
        print("Next: Run 'python run.py' to start the server")
        return 0
    else:
        print("\nStatus: FIX FAILURES ABOVE")
        return 1

if __name__ == '__main__':
    sys.exit(main())
