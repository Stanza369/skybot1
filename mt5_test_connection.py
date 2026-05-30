import MetaTrader5 as mt5
import time

print("Testing MT5 Connection...")
print("="*50)

# First, check if MT5 is installed
try:
    import MetaTrader5
    print("✅ MT5 module found")
except:
    print("❌ MT5 module not installed")
    print("Run: pip install MetaTrader5")
    exit()

# Try to initialize
print("\nAttempting to initialize MT5...")
if not mt5.initialize():
    print(f"❌ MT5 init failed: {mt5.last_error()}")
    print("\nTroubleshooting tips:")
    print("1. Make sure MetaTrader 5 is OPEN and LOGGED IN")
    print("2. Run MT5 as Administrator")
    print("3. Check if MT5 is frozen in Task Manager")
    exit()

print("✅ MT5 initialized successfully!")

# Try to login with your credentials
login = 1301500300
password = "Hlalele@123"
server = "XMGlobal-MT5 6"

print(f"\nAttempting to login...")
print(f"Login: {login}")
print(f"Server: {server}")

if mt5.login(login, password=password, server=server):
    print("✅ Login successful!")
    account = mt5.account_info()
    if account:
        print(f"   Account: {account.login}")
        print(f"   Balance: ${account.balance:.2f}")
        print(f"   Equity: ${account.equity:.2f}")
        print(f"   Server: {account.server}")
else:
    print(f"❌ Login failed: {mt5.last_error()}")
    print("\nPossible issues:")
    print("1. Wrong server name - check bottom right of MT5 window")
    print("2. Wrong password")
    print("3. Account not active")

mt5.shutdown()
print("\n" + "="*50)
print("Test complete")