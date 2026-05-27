"""scripts/demo_trade.py

Non-live demo runner.

Runs the bot in MODE=demo.

Note: your current code treats MODE as either 'demo' (signals only)
or 'live' (place & manage orders). This script ensures MODE=demo.
"""

import os
import subprocess
import sys


def main() -> None:
    os.environ.setdefault("MODE", "demo")
    subprocess.check_call([sys.executable, "main.py"])


if __name__ == "__main__":
    main()

