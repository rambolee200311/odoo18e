# mymodules/device_cert/tools/encryption_tools.py
import base64
import logging
from cryptography.fernet import Fernet
from odoo import models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class EncryptionTool(models.AbstractModel):
    """
    Unified encryption tools for device certificate password management
    Uses consistent API-style methods for both encryption and decryption
    """
    _name = 'device.cert.encryption.tool'
    _description = 'Device Certificate Encryption Tool'
    
    ENCRYPTION_KEY_PARAM = 'custom_device_cert.encryption_key'
    
    def _get_encryption_key(self):
        """
        Get the encryption key from system parameters or generate a new one.
        Consistent with both API and model requirements.
        """
        config_param = self.env['ir.config_parameter'].sudo()
        key_b64 = config_param.get_param(self.ENCRYPTION_KEY_PARAM)
        
        if not key_b64:
            # Automatically generate a new key
            new_key = Fernet.generate_key()
            key_b64 = base64.urlsafe_b64encode(new_key).decode()
            config_param.set_param(self.ENCRYPTION_KEY_PARAM, key_b64)
            _logger.info("New encryption key has been generated.")
        
        return base64.urlsafe_b64decode(key_b64.encode())
    
    def encrypt(self, plain_text):
        """
        Encrypt text using API-style method (Fernet.encrypt() with .decode()).
        This matches the API encryption method you provided.
        
        Args:
            plain_text (str): The text to encrypt
            
        Returns:
            str: Encrypted text (Fernet bytes decoded to string)
            
        Raises:
            UserError: If encryption fails
        """
        if not plain_text:
            return None
        
        try:
            key = self._get_encryption_key()
            cipher = Fernet(key)
            encrypted_bytes = cipher.encrypt(plain_text.encode())
            # API-style: direct decode of Fernet encrypted bytes
            return encrypted_bytes.decode()
        except Exception as e:
            _logger.error(f"API-style encryption failed: {e}")
            raise UserError(_("Encryption failed: %s") % str(e))
    
    def decrypt(self, encrypted_text):
        """
        Decrypt text using API-style method (Fernet.decrypt()).
        This correctly handles API-encrypted data.
        
        Args:
            encrypted_text (str): The encrypted text to decrypt
            
        Returns:
            str: Decrypted plain text
            
        Raises:
            UserError: If decryption fails
        """
        if not encrypted_text:
            return None
        
        try:
            key = self._get_encryption_key()
            cipher = Fernet(key)
            
            # Convert string back to bytes for Fernet decryption
            encrypted_bytes = encrypted_text.encode()
            
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            _logger.error(f"API-style decryption failed: {e}")
            raise UserError(_("Decryption failed: Invalid token/key mismatch"))
    
    def encrypt_base64(self, plain_text):
        """
        Alternative: Encrypt with base64 encoding (for backward compatibility).
        
        Args:
            plain_text (str): The text to encrypt
            
        Returns:
            str: Base64-encoded encrypted text
        """
        if not plain_text:
            return None
        
        try:
            key = self._get_encryption_key()
            cipher = Fernet(key)
            encrypted_bytes = cipher.encrypt(plain_text.encode())
            return base64.b64encode(encrypted_bytes).decode()
        except Exception as e:
            _logger.error(f"Base64 encryption failed: {e}")
            raise UserError(_("Encryption failed: %s") % str(e))
    
    def decrypt_base64(self, encrypted_text):
        """
        Alternative: Decrypt base64-encoded text (for backward compatibility).
        
        Args:
            encrypted_text (str): Base64-encoded encrypted text
            
        Returns:
            str: Decrypted plain text
        """
        if not encrypted_text:
            return None
        
        try:
            key = self._get_encryption_key()
            cipher = Fernet(key)
            
            # Decode base64 to bytes
            encrypted_bytes = base64.b64decode(encrypted_text)
            
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            _logger.error(f"Base64 decryption failed: {e}")
            raise UserError(_("Decryption failed: %s") % str(e))
    
    def decrypt_auto(self, encrypted_text):
        """
        Auto-detect format and decrypt (handles both API and base64 formats).
        
        Args:
            encrypted_text (str): The encrypted text
            
        Returns:
            str: Decrypted plain text
        """
        if not encrypted_text:
            return None
        
        # Try API-style decryption first
        try:
            return self.decrypt(encrypted_text)
        except:
            pass
        
        # If API-style fails, try base64 format
        try:
            return self.decrypt_base64(encrypted_text)
        except Exception as e:
            error_msg = f"[Decryption Error: Invalid token/key mismatch | {e}]"
            _logger.error(error_msg)
            return error_msg
    
    def validate_encryption(self, test_text="TestPassword123"):
        """
        Validate that encryption and decryption work correctly.
        
        Args:
            test_text (str): Text to use for validation
            
        Returns:
            dict: Validation results
        """
        try:
            # Test API-style encryption/decryption
            api_encrypted = self.encrypt(test_text)
            api_decrypted = self.decrypt(api_encrypted)
            
            # Test base64-style encryption/decryption
            base64_encrypted = self.encrypt_base64(test_text)
            base64_decrypted = self.decrypt_base64(base64_encrypted)
            
            return {
                'success': True,
                'api_style': {
                    'encrypted': api_encrypted,
                    'decrypted': api_decrypted,
                    'valid': api_decrypted == test_text
                },
                'base64_style': {
                    'encrypted': base64_encrypted,
                    'decrypted': base64_decrypted,
                    'valid': base64_decrypted == test_text
                },
                'formats_match': api_encrypted != base64_encrypted
            }
        except Exception as e:
            _logger.error(f"Encryption validation failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }