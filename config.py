import os


class Config:
    SYMBOL = "XAUUSD"

    LOTS = 0.01

    STOP_LOSS = 3300.0
    TAKE_PROFIT = 3400.0

    MAX_SPREAD_POINTS = 200

    HOLD_SECONDS = 120

    DEVIATION = 20
    MAGIC = 123456

    DATA_PATH = "data"
    MODEL_PATH = "models/"

    CONFIDENCE_THRESHOLD = 0.70
    PREDICTION_HORIZON = 5


config = Config()

os.makedirs(config.DATA_PATH, exist_ok=True)
os.makedirs(config.MODEL_PATH, exist_ok=True)
