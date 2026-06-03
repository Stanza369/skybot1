"""
ai_training.py - LSTM & Transformer Training Pipeline
Trains deep learning models on historical price data
"""
import argparse
import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from pathlib import Path
import logging
from typing import Tuple, Dict, Optional
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Device configuration
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
logger.info(f"Using device: {DEVICE}")

# ============================================================================
# DATA PROCESSING
# ============================================================================

class PriceDataset(Dataset):
    """PyTorch dataset for sequential price data"""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.FloatTensor(X)
        self.y = torch.LongTensor(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

class DataProcessor:
    """Handle price data loading and preprocessing"""

    def __init__(self, sequence_length: int = 60):
        self.sequence_length = sequence_length
        self.scaler = StandardScaler()
        self.feature_names = []

    def load_csv(self, filepath: str) -> pd.DataFrame:
        """Load XAUUSD price data from CSV"""
        logger.info(f"Loading data from {filepath}")
        df = pd.read_csv(filepath)

        # Validate columns
        required_cols = ['close', 'high', 'low', 'open']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"CSV must contain columns: {required_cols}")

        # Sort by timestamp if present
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"Loaded {len(df)} candles")
        return df

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate technical features for training"""
        logger.info("Engineering features...")

        features = df[['open', 'high', 'low', 'close']].copy()

        # Price-based features
        features['returns'] = df['close'].pct_change()
        features['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        features['high_low'] = (df['high'] - df['low']) / df['close']
        features['close_open'] = (df['close'] - df['open']) / df['open']

        # Momentum
        features['momentum_5'] = df['close'] - df['close'].shift(5)
        features['momentum_10'] = df['close'] - df['close'].shift(10)
        features['roc_5'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5)

        # Volatility
        features['volatility_5'] = df['close'].rolling(5).std()
        features['volatility_10'] = df['close'].rolling(10).std()

        # EMAs
        features['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        features['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        features['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        features['rsi_14'] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        features['macd'] = ema_12 - ema_26
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()

        # Bollinger Bands
        bb_mid = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        features['bb_upper'] = bb_mid + (bb_std * 2)
        features['bb_lower'] = bb_mid - (bb_std * 2)
        features['bb_position'] = (df['close'] - features['bb_lower']) / (features['bb_upper'] - features['bb_lower'])

        # Drop NaN rows created by rolling calculations
        features = features.dropna().reset_index(drop=True)

        self.feature_names = features.columns.tolist()
        logger.info(f"Generated {len(features.columns)} features")

        return features

    def create_sequences(self, features: pd.DataFrame,
                        target_col: str = 'close',
                        lookahead: int = 1) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for supervised learning"""
        logger.info(f"Creating sequences (length={self.sequence_length}, lookahead={lookahead})")

        X = []
        y = []

        for i in range(len(features) - self.sequence_length - lookahead):
            seq = features.iloc[i:i+self.sequence_length].values
            X.append(seq)

            # Target: next price direction
            current_price = features.iloc[i + self.sequence_length][target_col]
            future_price = features.iloc[i + self.sequence_length + lookahead][target_col]

            # 1 = BUY (price up), 0 = SELL (price down)
            label = 1 if future_price > current_price else 0
            y.append(label)

        X = np.array(X)
        y = np.array(y)

        logger.info(f"Created {len(X)} sequences")
        return X, y

    def normalize(self, X: np.ndarray, fit: bool = True) -> np.ndarray:
        """Normalize features"""
        if fit:
            X_reshaped = X.reshape(-1, X.shape[-1])
            self.scaler.fit(X_reshaped)

        X_reshaped = X.reshape(-1, X.shape[-1])
        X_normalized = self.scaler.transform(X_reshaped)
        X_normalized = X_normalized.reshape(X.shape)

        return X_normalized

# ============================================================================
# MODEL ARCHITECTURES
# ============================================================================

class LSTMPredictor(nn.Module):
    """LSTM for short-term price direction prediction"""

    def __init__(self, input_size: int, hidden_size: int = 128,
                 num_layers: int = 3, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout
        )
        self.fc1 = nn.Linear(hidden_size, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 2)  # Binary: BUY or SELL
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        lstm_out, (h_n, c_n) = self.lstm(x)

        # Use last hidden state
        last_hidden = h_n[-1]

        x = self.relu(self.fc1(last_hidden))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)

        return x

class TransformerPredictor(nn.Module):
    """Transformer for pattern recognition and reversal points"""

    def __init__(self, input_size: int, d_model: int = 64,
                 nhead: int = 8, num_layers: int = 3, dropout: float = 0.2):
        super().__init__()

        self.input_projection = nn.Linear(input_size, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=256,
            dropout=dropout,
            batch_first=True,
            activation='relu'
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.fc1 = nn.Linear(d_model, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 2)  # Binary: BUY or SELL

        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        x = self.input_projection(x)
        x = self.transformer(x)

        # Use mean pooling
        x = x.mean(dim=1)

        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)

        return x

# ============================================================================
# TRAINING
# ============================================================================

class ModelTrainer:
    """Train LSTM and Transformer models"""

    def __init__(self, model_type: str = 'lstm', epochs: int = 50,
                 batch_size: int = 32, learning_rate: float = 0.001,
                 early_stopping_patience: int = 10):
        self.model_type = model_type
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.early_stopping_patience = early_stopping_patience
        self.model = None
        self.history = {'train_loss': [], 'val_loss': [], 'val_acc': []}

    def create_model(self, input_size: int) -> nn.Module:
        """Instantiate model architecture"""
        logger.info(f"Creating {self.model_type.upper()} model with input_size={input_size}")

        if self.model_type == 'lstm':
            self.model = LSTMPredictor(input_size=input_size)
        elif self.model_type == 'transformer':
            self.model = TransformerPredictor(input_size=input_size)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

        self.model.to(DEVICE)
        logger.info(f"Model parameters: {sum(p.numel() for p in self.model.parameters()):,}")

        return self.model

    def train(self, train_loader: DataLoader, val_loader: DataLoader):
        """Train model with early stopping"""
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5, verbose=True
        )

        best_val_loss = float('inf')
        patience_counter = 0

        for epoch in range(self.epochs):
            # Training
            self.model.train()
            train_loss = 0.0

            for X_batch, y_batch in train_loader:
                X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)

                optimizer.zero_grad()
                outputs = self.model(X_batch)
                loss = criterion(outputs, y_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation
            self.model.eval()
            val_loss = 0.0
            val_preds = []
            val_targets = []

            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch, y_batch = X_batch.to(DEVICE), y_batch.to(DEVICE)

                    outputs = self.model(X_batch)
                    loss = criterion(outputs, y_batch)
                    val_loss += loss.item()

                    preds = outputs.argmax(dim=1).cpu().numpy()
                    val_preds.extend(preds)
                    val_targets.extend(y_batch.cpu().numpy())

            val_loss /= len(val_loader)
            val_acc = accuracy_score(val_targets, val_preds)

            self.history['train_loss'].append(train_loss)
            self.history['val_loss'].append(val_loss)
            self.history['val_acc'].append(val_acc)

            logger.info(f"Epoch {epoch+1}/{self.epochs} - "
                       f"Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}, "
                       f"Val Acc: {val_acc:.4f}")

            # Learning rate scheduling
            scheduler.step(val_loss)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save best model
                self.save_model(f'models/best_{self.model_type}_model.pt')
            else:
                patience_counter += 1
                if patience_counter >= self.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

    def evaluate(self, test_loader: DataLoader) -> Dict:
        """Evaluate model on test set"""
        self.model.eval()
        test_preds = []
        test_targets = []

        with torch.no_grad():
            for X_batch, y_batch in test_loader:
                X_batch = X_batch.to(DEVICE)
                outputs = self.model(X_batch)
                preds = outputs.argmax(dim=1).cpu().numpy()
                test_preds.extend(preds)
                test_targets.extend(y_batch.numpy())

        metrics = {
            'accuracy': accuracy_score(test_targets, test_preds),
            'precision': precision_score(test_targets, test_preds, zero_division=0),
            'recall': recall_score(test_targets, test_preds, zero_division=0),
            'f1': f1_score(test_targets, test_preds, zero_division=0),
        }

        logger.info(f"\nTest Set Metrics ({self.model_type.upper()}):")
        for metric, value in metrics.items():
            logger.info(f"  {metric.capitalize()}: {value:.4f}")

        return metrics

    def save_model(self, filepath: str):
        """Save model to disk"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), filepath)
        logger.info(f"Saved model to {filepath}")

    def load_model(self, filepath: str):
        """Load model from disk"""
        self.model.load_state_dict(torch.load(filepath, map_location=DEVICE))
        logger.info(f"Loaded model from {filepath}")

# ============================================================================
# MAIN TRAINING SCRIPT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Train AI models for trading')
    parser.add_argument('--data', type=str, required=True, help='Path to CSV file with XAUUSD data')
    parser.add_argument('--model', type=str, choices=['lstm', 'transformer', 'both'],
                       default='both', help='Model to train')
    parser.add_argument('--epochs', type=int, default=50, help='Number of training epochs')
    parser.add_argument('--batch_size', type=int, default=32, help='Batch size')
    parser.add_argument('--sequence_length', type=int, default=60, help='Sequence length')
    parser.add_argument('--test_size', type=float, default=0.15, help='Test set proportion')
    parser.add_argument('--val_size', type=float, default=0.15, help='Validation set proportion')

    args = parser.parse_args()

    # Load and process data
    processor = DataProcessor(sequence_length=args.sequence_length)
    df = processor.load_csv(args.data)
    features = processor.engineer_features(df)
    X, y = processor.create_sequences(features)
    X = processor.normalize(X, fit=True)

    # Split data
    total_samples = len(X)
    train_size = int(total_samples * (1 - args.test_size - args.val_size))
    val_size = int(total_samples * args.val_size)

    X_train, X_val, X_test = X[:train_size], X[train_size:train_size+val_size], X[train_size+val_size:]
    y_train, y_val, y_test = y[:train_size], y[train_size:train_size+val_size], y[train_size+val_size:]

    logger.info(f"\nData split: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")
    logger.info(f"Class distribution - BUY: {(y_train==1).sum()}, SELL: {(y_train==0).sum()}")

    # Create data loaders
    train_dataset = PriceDataset(X_train, y_train)
    val_dataset = PriceDataset(X_val, y_val)
    test_dataset = PriceDataset(X_test, y_test)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # Train models
    input_size = X_train.shape[2]

    for model_name in ['lstm', 'transformer'] if args.model == 'both' else [args.model]:
        logger.info(f"\n{'='*60}")
        logger.info(f"Training {model_name.upper()}")
        logger.info(f"{'='*60}")

        trainer = ModelTrainer(model_type=model_name, epochs=args.epochs,
                             batch_size=args.batch_size)
        trainer.create_model(input_size)
        trainer.train(train_loader, val_loader)
        trainer.evaluate(test_loader)
        trainer.save_model(f'models/{model_name}_model.pt')

    # Save feature scaler
    Path('models').mkdir(exist_ok=True)
    import pickle
    with open('models/feature_scaler.pkl', 'wb') as f:
        pickle.dump(processor.scaler, f)

    # Save feature names
    with open('models/feature_names.json', 'w') as f:
        json.dump(processor.feature_names, f)

    logger.info("\nTraining complete! Models saved to 'models/' directory")

if __name__ == '__main__':
    main()
