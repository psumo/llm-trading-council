"""
Multi-Account Manager

Manages multiple trading accounts with encrypted credential storage.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .base import ExchangeAccount, ExchangeType, BaseTrader
from .factory import create_trader, create_and_initialize_trader
from src.utils.logger import log

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    log.warning("cryptography package not installed. Credential encryption disabled.")


class AccountManager:
    """
    Manages multiple exchange accounts with encrypted credential storage.
    
    Accounts are defined in config/accounts.json and API keys are loaded
    from environment variables for security.
    """
    
    def __init__(
        self, 
        config_path: str = None,
        encryption_key: bytes = None
    ):
        """
        Initialize the account manager.
        
        Args:
            config_path: Path to accounts.json config file
            encryption_key: Optional encryption key for credentials
        """
        self._accounts: Dict[str, ExchangeAccount] = {}
        self._traders: Dict[str, BaseTrader] = {}
        
        # Setup encryption if key provided and crypto available
        self._fernet = None
        if encryption_key and CRYPTO_AVAILABLE:
            self._fernet = Fernet(encryption_key)
        
        # Default config path
        if config_path is None:
            # Look in project root/config/accounts.json
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "accounts.json"
        
        self._config_path = Path(config_path)
    
    def add_account(self, account: ExchangeAccount) -> str:
        """
        Add a new account.
        
        Args:
            account: ExchangeAccount configuration
            
        Returns:
            Account ID
        """
        # Encrypt sensitive fields if encryption is enabled
        if self._fernet:
            if account.api_key:
                account.api_key = self._encrypt(account.api_key)
            if account.secret_key:
                account.secret_key = self._encrypt(account.secret_key)
            if account.private_key:
                account.private_key = self._encrypt(account.private_key)
            if account.passphrase:
                account.passphrase = self._encrypt(account.passphrase)
        
        self._accounts[account.id] = account
        log.info(f"Added account: {account.account_name} ({account.exchange_type.value})")
        
        return account.id
    
    def remove_account(self, account_id: str) -> bool:
        """
        Remove an account.
        
        Args:
            account_id: ID of account to remove
            
        Returns:
            True if removed successfully
        """
        if account_id in self._traders:
            del self._traders[account_id]
        
        if account_id in self._accounts:
            account = self._accounts[account_id]
            del self._accounts[account_id]
            log.info(f"Removed account: {account.account_name}")
            return True
        
        return False
    
    def get_account(self, account_id: str) -> Optional[ExchangeAccount]:
        """Get account by ID."""
        return self._accounts.get(account_id)
    
    def list_accounts(
        self, 
        user_id: str = None,
        exchange_type: ExchangeType = None,
        enabled_only: bool = False
    ) -> List[ExchangeAccount]:
        """
        List accounts with optional filters.
        
        Args:
            user_id: Filter by user ID
            exchange_type: Filter by exchange type
            enabled_only: Only return enabled accounts
            
        Returns:
            List of matching accounts
        """
        accounts = list(self._accounts.values())
        
        if user_id:
            accounts = [a for a in accounts if a.user_id == user_id]
        
        if exchange_type:
            accounts = [a for a in accounts if a.exchange_type == exchange_type]
        
        if enabled_only:
            accounts = [a for a in accounts if a.enabled]
        
        return accounts
    
    async def get_trader(self, account_id: str) -> Optional[BaseTrader]:
        """
        Get or create trader for an account.
        
        Args:
            account_id: Account ID
            
        Returns:
            BaseTrader instance or None if not found/failed
        """
        # Return cached trader if exists
        if account_id in self._traders:
            return self._traders[account_id]
        
        # Get account and create trader
        account = self._accounts.get(account_id)
        if not account:
            log.error(f"Account not found: {account_id}")
            return None
        
        if not account.enabled:
            log.warning(f"Account is disabled: {account.account_name}")
            return None
        
        # Decrypt credentials for trader creation
        decrypted_account = self._get_decrypted_account(account)
        
        # Create and initialize trader
        trader = await create_and_initialize_trader(decrypted_account)
        
        if trader:
            self._traders[account_id] = trader
        
        return trader
    
    async def get_all_traders(self) -> Dict[str, BaseTrader]:
        """
        Get traders for all enabled accounts.
        
        Returns:
            Dict mapping account_id to BaseTrader
        """
        traders = {}
        
        for account in self.list_accounts(enabled_only=True):
            trader = await self.get_trader(account.id)
            if trader:
                traders[account.id] = trader
        
        return traders
    
    def _get_decrypted_account(self, account: ExchangeAccount) -> ExchangeAccount:
        """Create a copy of account with decrypted credentials."""
        return ExchangeAccount(
            id=account.id,
            user_id=account.user_id,
            exchange_type=account.exchange_type,
            account_name=account.account_name,
            enabled=account.enabled,
            api_key=self._decrypt(account.api_key),
            secret_key=self._decrypt(account.secret_key),
            passphrase=self._decrypt(account.passphrase) if account.passphrase else "",
            private_key=self._decrypt(account.private_key) if account.private_key else "",
            wallet_addr=account.wallet_addr,
            testnet=account.testnet,
            created_at=account.created_at,
            updated_at=account.updated_at
        )
    
    def load_from_file(self, filepath: str = None) -> int:
        """
        Load accounts from JSON config file.
        
        Config format:
        {
            "accounts": [
                {
                    "id": "main-binance",
                    "name": "Main Account",
                    "exchange": "binance",
                    "enabled": true,
                    "testnet": false
                }
            ]
        }
        
        API keys are loaded from environment variables:
        ACCOUNT_{ID}_API_KEY, ACCOUNT_{ID}_SECRET_KEY
        
        Args:
            filepath: Path to config file (uses default if None)
            
        Returns:
            Number of accounts loaded
        """
        path = Path(filepath) if filepath else self._config_path
        
        if not path.exists():
            log.info(f"Accounts config not found: {path}, creating default config...")
            # Auto-create default config for Railway deployment
            self.create_default_config()
            # If creation succeeded, the file should now exist
            if not path.exists():
                log.warning(f"Failed to create default accounts config")
                return 0
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            accounts_data = data.get('accounts', [])
            loaded = 0
            
            for acc_data in accounts_data:
                try:
                    account = self._parse_account_config(acc_data)
                    self.add_account(account)
                    loaded += 1
                except Exception as e:
                    log.error(f"Failed to load account {acc_data.get('id', 'unknown')}: {e}")
            
            log.info(f"Loaded {loaded} accounts from {path}")
            return loaded
            
        except Exception as e:
            log.error(f"Failed to load accounts config: {e}")
            return 0
    
    def _parse_account_config(self, data: Dict[str, Any]) -> ExchangeAccount:
        """Parse account config and load API keys from environment."""
        account_id = data.get('id', '')
        
        # Convert exchange string to enum
        exchange_str = data.get('exchange', 'binance').lower()
        try:
            exchange_type = ExchangeType(exchange_str)
        except ValueError:
            raise ValueError(f"Unknown exchange type: {exchange_str}")
        
        # Load API keys from environment
        env_prefix = f"ACCOUNT_{account_id.upper().replace('-', '_')}"
        api_key = os.environ.get(f"{env_prefix}_API_KEY", "")
        secret_key = os.environ.get(f"{env_prefix}_SECRET_KEY", "")
        passphrase = os.environ.get(f"{env_prefix}_PASSPHRASE", "")
        private_key = os.environ.get(f"{env_prefix}_PRIVATE_KEY", "")
        
        # Fallback to legacy env vars if this is the first/default account
        if not api_key and account_id in ['main', 'default', 'main-binance']:
            api_key = os.environ.get('BINANCE_API_KEY', '')
            secret_key = os.environ.get('BINANCE_SECRET_KEY', '')
        
        return ExchangeAccount(
            id=account_id,
            user_id=data.get('user_id', 'default'),
            exchange_type=exchange_type,
            account_name=data.get('name', account_id),
            enabled=data.get('enabled', True),
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            private_key=private_key,
            wallet_addr=data.get('wallet_addr', ''),
            testnet=data.get('testnet', False)
        )
    
    def save_to_file(self, filepath: str = None) -> bool:
        """
        Save accounts config to JSON file.
        Note: API keys are NOT saved to file (security).
        
        Args:
            filepath: Path to save to (uses default if None)
            
        Returns:
            True if saved successfully
        """
        path = Path(filepath) if filepath else self._config_path
        
        try:
            # Ensure directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Build config (without sensitive data)
            accounts_config = []
            for account in self._accounts.values():
                accounts_config.append({
                    'id': account.id,
                    'name': account.account_name,
                    'user_id': account.user_id,
                    'exchange': account.exchange_type.value,
                    'enabled': account.enabled,
                    'testnet': account.testnet,
                    'wallet_addr': account.wallet_addr
                })
            
            data = {'accounts': accounts_config}
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            log.info(f"Saved accounts config to {path}")
            return True
            
        except Exception as e:
            log.error(f"Failed to save accounts config: {e}")
            return False
    
    def create_default_config(self) -> bool:
        """
        Create default accounts.json with legacy .env compatibility.
        
        If BINANCE_API_KEY exists in .env, creates a default account for it.
        
        Returns:
            True if config created
        """
        # Check if legacy env vars exist
        api_key = os.environ.get('BINANCE_API_KEY', '')
        testnet = os.environ.get('BINANCE_TESTNET', 'true').lower() == 'true'
        
        default_account = ExchangeAccount(
            id='main-binance',
            user_id='default',
            exchange_type=ExchangeType.BINANCE,
            account_name='Main Binance Account',
            enabled=True,
            api_key=api_key,
            secret_key=os.environ.get('BINANCE_SECRET_KEY', ''),
            testnet=testnet
        )
        
        self.add_account(default_account)
        return self.save_to_file()
    
    def _encrypt(self, text: str) -> str:
        """Encrypt text if encryption is enabled."""
        if not text or not self._fernet:
            return text
        return self._fernet.encrypt(text.encode()).decode()
    
    def _decrypt(self, text: str) -> str:
        """Decrypt text if encryption is enabled."""
        if not text or not self._fernet:
            return text
        try:
            return self._fernet.decrypt(text.encode()).decode()
        except Exception:
            # If decryption fails, return original (might not be encrypted)
            return text
