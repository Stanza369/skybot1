import MetaTrader5 as mt5

# Initialize MT5
if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
else:
    print("MT5 initialized successfully!")
    
    # Try to login
    login = 317085721
    password = "Stanza@3691"
    server = "XMGlobal-MT5 7"
    
    if mt5.login(login, password=password, server=server):
        print("Login successful!")
        account = mt5.account_info()
        print(f"Balance: ${account.balance:.2f}")
        print(f"Equity: ${account.equity:.2f}")
    else:
        print(f"Login failed: {mt5.last_error()}")
    
    mt5.shutdown()