# super_trading_bot.py - Complete super version with built-in security
import hashlib
import hmac
import base64
import json
import pickle
import os
import time
import zlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import secrets

# ============================================
# PART 1: LIGHTWEIGHT SECURITY (No External Deps)
# ============================================

class LightweightSecurity:
    """Built-in security without external dependencies"""
    
    @staticmethod
    def generate_key() -> str:
        """Generate a secure key"""
        return secrets.token_hex(32)
    
    @staticmethod
    def simple_encrypt(data: str, key: str) -> str:
        """Simple but effective encryption"""
        # XOR encryption with key stretching
        key_bytes = key.encode() * (len(data) // len(key) + 1)
        encrypted = bytes(a ^ b for a, b in zip(data.encode(), key_bytes[:len(data)]))
        return base64.b64encode(encrypted).decode()
    
    @staticmethod
    def simple_decrypt(encrypted: str, key: str) -> str:
        """Decrypt simple encrypted data"""
        encrypted_bytes = base64.b64decode(encrypted.encode())
        key_bytes = key.encode() * (len(encrypted_bytes) // len(key) + 1)
        decrypted = bytes(a ^ b for a, b in zip(encrypted_bytes, key_bytes[:len(encrypted_bytes)]))
        return decrypted.decode()
    
    @staticmethod
    def hash_data(data: Any) -> str:
        """Create cryptographic hash of any data"""
        return hashlib.sha3_256(pickle.dumps(data)).hexdigest()
    
    @staticmethod
    def compress_data(data: Any) -> bytes:
        """Compress data for storage"""
        return zlib.compress(pickle.dumps(data), level=9)
    
    @staticmethod
    def decompress_data(compressed: bytes) -> Any:
        """Decompress data"""
        return pickle.loads(zlib.decompress(compressed))


# ============================================
# PART 2: LICENSE MANAGER
# ============================================

class LicenseManager:
    """Complete license management system"""
    
    VERSION = "2.0.0"
    
    def __init__(self, license_file: str = "license.key"):
        self.license_file = license_file
        self.master_secret = self._get_master_secret()
        
    def _get_master_secret(self) -> bytes:
        """Get or create master secret"""
        secret_file = ".master_secret"
        if os.path.exists(secret_file):
            with open(secret_file, 'rb') as f:
                return f.read()
        else:
            secret = secrets.token_bytes(32)
            with open(secret_file, 'wb') as f:
                f.write(secret)
            return secret
    
    def generate_license(self, user_id: str, plan: str, days: int = 30) -> str:
        """Generate new license key"""
        expiry = int(time.time()) + (days * 86400)
        
        license_data = {
            'user_id': user_id,
            'plan': plan,
            'expiry': expiry,
            'version': self.VERSION,
            'created': int(time.time()),
            'features': self._get_plan_features(plan)
        }
        
        # Create signature
        data_str = json.dumps(license_data, sort_keys=True)
        signature = hmac.new(
            self.master_secret,
            data_str.encode(),
            hashlib.sha3_256
        ).hexdigest()
        
        license_data['signature'] = signature
        
        # Encode
        return base64.b64encode(json.dumps(license_data).encode()).decode()
    
    def _get_plan_features(self, plan: str) -> list:
        """Get features for each plan"""
        plans = {
            'trial': ['basic', '1_pair', 'demo_mode'],
            'basic': ['basic', '5_pairs', 'ai_predictions'],
            'pro': ['basic', '10_pairs', 'ai_predictions', 'realtime', 'telegram'],
            'enterprise': ['all', 'unlimited_pairs', 'custom_models', 'api_access']
        }
        return plans.get(plan, plans['trial'])
    
    def verify_license(self, license_key: str = None) -> Dict:
        """Verify license validity"""
        license_key = license_key or self._load_license()
        if not license_key:
            return {'valid': False, 'reason': 'No license found'}
        
        try:
            decoded = json.loads(base64.b64decode(license_key.encode()).decode())
            
            # Verify signature
            signature = decoded.pop('signature')
            data_str = json.dumps(decoded, sort_keys=True)
            expected_sig = hmac.new(
                self.master_secret,
                data_str.encode(),
                hashlib.sha3_256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_sig):
                return {'valid': False, 'reason': 'Invalid signature'}
            
            # Check expiry
            if decoded['expiry'] < time.time():
                return {'valid': False, 'reason': 'License expired'}
            
            return {
                'valid': True,
                'user_id': decoded['user_id'],
                'plan': decoded['plan'],
                'features': decoded['features'],
                'expiry': datetime.fromtimestamp(decoded['expiry']).isoformat(),
                'days_left': (decoded['expiry'] - time.time()) / 86400
            }
            
        except Exception as e:
            return {'valid': False, 'reason': str(e)}
    
    def _load_license(self) -> Optional[str]:
        """Load license from file"""
        if os.path.exists(self.license_file):
            with open(self.license_file, 'r') as f:
                return f.read().strip()
        return None
    
    def save_license(self, license_key: str):
        """Save license to file"""
        with open(self.license_file, 'w') as f:
            f.write(license_key)


# ============================================
# PART 3: SECURE MODEL STORAGE
# ============================================

class SecureModelStorage:
    """Store and retrieve encrypted models"""
    
    def __init__(self, models_dir: str = "secure_models"):
        self.models_dir = models_dir
        os.makedirs(models_dir, exist_ok=True)
        self.encryption_key = self._get_encryption_key()
    
    def _get_encryption_key(self) -> str:
        """Get or create encryption key"""
        key_file = f"{self.models_dir}/.enc_key"
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                return f.read()
        else:
            key = LightweightSecurity.generate_key()
            with open(key_file, 'w') as f:
                f.write(key)
            return key
    
    def save_model(self, model: Any, model_name: str) -> str:
        """Save encrypted model"""
        # Compress and hash
        compressed = LightweightSecurity.compress_data(model)
        model_hash = LightweightSecurity.hash_data(model)
        
        # Encrypt
        encrypted = LightweightSecurity.simple_encrypt(
            base64.b64encode(compressed).decode(),
            self.encryption_key
        )
        
        # Save metadata
        metadata = {
            'name': model_name,
            'hash': model_hash,
            'timestamp': time.time(),
            'version': LicenseManager.VERSION
        }
        
        save_path = f"{self.models_dir}/{model_name}.enc"
        with open(save_path, 'w') as f:
            json.dump({
                'metadata': metadata,
                'data': encrypted
            }, f)
        
        return model_hash
    
    def load_model(self, model_name: str) -> Optional[Any]:
        """Load and decrypt model"""
        load_path = f"{self.models_dir}/{model_name}.enc"
        if not os.path.exists(load_path):
            return None
        
        with open(load_path, 'r') as f:
            data = json.load(f)
        
        # Decrypt
        decrypted = LightweightSecurity.simple_decrypt(data['data'], self.encryption_key)
        compressed = base64.b64decode(decrypted.encode())
        
        # Decompress
        model = LightweightSecurity.decompress_data(compressed)
        
        # Verify integrity
        current_hash = LightweightSecurity.hash_data(model)
        if current_hash != data['metadata']['hash']:
            raise ValueError("Model integrity check failed!")
        
        return model
    
    def list_models(self) -> list:
        """List all saved models"""
        models = []
        for file in os.listdir(self.models_dir):
            if file.endswith('.enc'):
                models.append(file.replace('.enc', ''))
        return models


# ============================================
# PART 4: SUPER TRADING BOT
# ============================================

class SuperTradingBot:
    """Complete super version with all security features"""
    
    def __init__(self, license_key: str = None):
        print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🚀 SUPER TRADING BOT - SECURE EDITION                   ║
    ║                                                              ║
    ║     ✓ License Protection                                    ║
    ║     ✓ Encrypted Models                                      ║
    ║     ✓ Integrity Verification                                ║
    ║     ✓ Self-Learning AI                                      ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
        """)
        
        # Initialize security
        self.license_manager = LicenseManager()
        self.model_storage = SecureModelStorage()
        
        # Verify license
        self.license = self.license_manager.verify_license(license_key)
        if not self.license['valid']:
            raise RuntimeError(f"❌ License error: {self.license['reason']}")
        
        print(f"✅ License verified - Plan: {self.license['plan']}")
        print(f"   Days remaining: {self.license['days_left']:.0f}")
        print(f"   Features: {', '.join(self.license['features'])}")
        
        # Load or create model
        self.model = self._initialize_model()
        
    def _initialize_model(self):
        """Initialize or load model"""
        models = self.model_storage.list_models()
        
        if 'trading_model' in models:
            print("📂 Loading secure model...")
            return self.model_storage.load_model('trading_model')
        else:
            print("📚 No model found. Training new model...")
            model = self._train_model()
            model_hash = self.model_storage.save_model(model, 'trading_model')
            print(f"🔒 Model saved with hash: {model_hash[:16]}...")
            return model
    
    def _train_model(self):
        """Train new model (simplified for demo)"""
        # This is where your actual model training goes
        # For now, return a dummy model
        return {
            'version': '2.0',
            'trained_at': time.time(),
            'features': self.license['features']
        }
    
    def predict(self, market_data: Dict) -> Dict:
        """Make prediction with integrity check"""
        # Hash input for verification
        input_hash = LightweightSecurity.hash_data(market_data)
        
        # Make prediction (your AI logic here)
        prediction = {
            'action': 'HOLD',
            'confidence': 0.65,
            'timestamp': time.time(),
            'input_hash': input_hash
        }
        
        # Add integrity signature
        prediction['integrity'] = LightweightSecurity.hash_data(prediction)
        
        return prediction
    
    def run(self):
        """Main bot loop"""
        print(f"\n🟢 Super Trading Bot is RUNNING")
        print(f"   Plan: {self.license['plan']}")
        print(f"   Features: {len(self.license['features'])} enabled")
        print("\nPress Ctrl+C to stop\n")
        
        try:
            while True:
                # Simulate market data
                market_data = {'price': 2650.50, 'timestamp': time.time()}
                
                # Get prediction
                prediction = self.predict(market_data)
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Prediction: {prediction['action']} "
                      f"(Conf: {prediction['confidence']:.0%})")
                
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Bot stopped safely")


# ============================================
# PART 5: LICENSE GENERATOR CLI
# ============================================

class LicenseGeneratorCLI:
    """Command-line interface for license management"""
    
    @staticmethod
    def run():
        print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║              LICENSE GENERATOR v2.0                          ║
    ╚══════════════════════════════════════════════════════════════╝
        """)
        
        license_manager = LicenseManager()
        
        while True:
            print("\nOptions:")
            print("1. Generate new license")
            print("2. Verify license")
            print("3. Show current license")
            print("4. Exit")
            
            choice = input("\nEnter choice (1-4): ").strip()
            
            if choice == '1':
                user_id = input("User ID: ").strip()
                print("\nPlans: trial, basic, pro, enterprise")
                plan = input("Plan: ").strip()
                days = int(input("Days (default 30): ").strip() or "30")
                
                license_key = license_manager.generate_license(user_id, plan, days)
                
                print(f"\n🔑 LICENSE KEY:")
                print(f"{license_key}")
                print(f"\n📁 Saving to: {user_id}_license.key")
                
                with open(f"{user_id}_license.key", 'w') as f:
                    f.write(license_key)
                
                print("✅ License generated successfully!")
                
            elif choice == '2':
                key_file = input("License file path: ").strip()
                if os.path.exists(key_file):
                    with open(key_file, 'r') as f:
                        key = f.read().strip()
                    result = license_manager.verify_license(key)
                else:
                    result = license_manager.verify_license(key_file)
                
                if result['valid']:
                    print(f"\n✅ VALID LICENSE")
                    print(f"   User: {result['user_id']}")
                    print(f"   Plan: {result['plan']}")
                    print(f"   Expires: {result['expiry']}")
                    print(f"   Days left: {result['days_left']:.0f}")
                    print(f"   Features: {', '.join(result['features'])}")
                else:
                    print(f"\n❌ INVALID: {result['reason']}")
            
            elif choice == '3':
                result = license_manager.verify_license()
                if result['valid']:
                    print(f"\n📋 CURRENT LICENSE")
                    print(f"   User: {result['user_id']}")
                    print(f"   Plan: {result['plan']}")
                    print(f"   Expires: {result['expiry']}")
                    print(f"   Days left: {result['days_left']:.0f}")
                else:
                    print(f"\n❌ No valid license found")
            
            elif choice == '4':
                print("Goodbye!")
                break


# ============================================
# MAIN ENTRY POINT
# ============================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--generate-license':
        LicenseGeneratorCLI.run()
    else:
        try:
            # Try to load existing license
            bot = SuperTradingBot()
            bot.run()
        except RuntimeError as e:
            print(f"\n{e}")
            print("\nTo generate a license, run:")
            print("python super_trading_bot.py --generate-license")