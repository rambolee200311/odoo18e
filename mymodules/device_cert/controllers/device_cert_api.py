from odoo import http
from odoo.http import request
import logging
import base64
import json
from odoo import models, fields
from cryptography.fernet import Fernet, InvalidToken

_logger = logging.getLogger(__name__)

class DeviceCertAPI(http.Controller):
    
    # ========== Configuration Helper Methods ==========
    
    def _get_config_param(self, key, default=None):
        """Safely retrieve value from Odoo configuration parameters"""
        return request.env['ir.config_parameter'].sudo().get_param(key, default)
    
    def _get_api_auth_key(self):
        """Get API authentication key"""
        return self._get_config_param('custom_device_cert.api_auth_key', 
                                      'DEFAULT_KEY_PLEASE_CHANGE_IMMEDIATELY')
    
    def _get_encryption_key(self):
        """Get encryption key (ensuring it matches the one used by the model)"""
        key_b64 = self._get_config_param('custom_device_cert.encryption_key')
        if not key_b64:
            new_key = Fernet.generate_key()
            key_b64 = base64.urlsafe_b64encode(new_key).decode()
            request.env['ir.config_parameter'].sudo().set_param(
                'custom_device_cert.encryption_key', key_b64
            )
        return base64.urlsafe_b64decode(key_b64.encode())
    
    def _encrypt_password(self, plain_password):
        """Encrypt password"""
        if not plain_password:
            return None
        try:
            key = self._get_encryption_key()
            cipher = Fernet(key)
            return cipher.encrypt(plain_password.encode()).decode()
        except Exception as e:
            _logger.error(f"Password encryption failed: {e}")
            raise
    
    # ========== API Authentication Methods ==========
    
    def _authenticate_api_request(self):
        """Validate API request authentication"""
        expected_key = self._get_api_auth_key()
        provided_key = request.httprequest.headers.get('X-API-Key')
        
        if not provided_key or provided_key != expected_key:
            _logger.warning(f"API authentication failed. Expected key: {expected_key[:8]}..., Received: {provided_key}")
            return False, {'success': False, 'error': 'Invalid or missing API Key.'}
        return True, None
    
    def _log_api_request(self, device_id, cert_serial, ip_address, status, message):
        """Log API requests to database"""
        request.env['device.api.log'].sudo().create({
            'device_id': device_id or '',
            'cert_serial': cert_serial or '',
            'ip_address': ip_address or '',
            'status': status,
            'message': message or ''
        })
    
    # ========== API Endpoints ==========
    
    @http.route('/api/device_cert/bind', type='json', auth='none', methods=['POST'], csrf=False)
    def create_cert_binding(self, **kwargs):
        """
        Create or update device-certificate binding record
        Request body must contain: device_id, cert_serial, password, cert_file
        """
        # 1. API Authentication
        auth_valid, auth_error = self._authenticate_api_request()
        if not auth_valid:
            return auth_error
        
        # 2. Get request data
        try:
            raw_data = request.httprequest.data
            _logger.info(f"Raw request data length: {len(raw_data) if raw_data else 0}")
            
            if not raw_data:
                return {
                    'success': False,
                    'error': 'No data received in request body'
                }
            
            post_data = json.loads(raw_data)
            _logger.info(f"Parsed JSON data keys: {list(post_data.keys())}")
            
        except json.JSONDecodeError as e:
            _logger.error(f"JSON decode error: {e}")
            return {
                'success': False,
                'error': f'Invalid JSON format: {str(e)}'
            }
        except Exception as e:
            _logger.error(f"Error reading request data: {e}")
            return {
                'success': False,
                'error': f'Request data reading failed: {str(e)}'
            }
        
        # 3. Parameter Validation
        required_fields = ['device_id', 'cert_serial', 'password', 'cert_file']
        missing_fields = [f for f in required_fields if not post_data.get(f)]
        
        if missing_fields:
            return {
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }
        
        device_id = post_data.get('device_id')
        cert_serial = post_data.get('cert_serial')
        password = post_data.get('password')
        cert_file_b64 = post_data.get('cert_file')
        
        # 4. Encrypt Password
        try:
            encrypted_password = self._encrypt_password(password)
        except Exception as e:
            return {
                'success': False,
                'error': f'Password encryption failed: {str(e)}'
            }
        
        # 5. Prepare Data
        vals = {
            'device_id': device_id or 'PLACEHOLDER_FOR_FIRST_BIND',
            'cert_serial': cert_serial,
            'user_email': post_data.get('user_email'),
            'ip_address': post_data.get('ip_address'),
            'state': post_data.get('state', 'active'),
            'password_encrypted': encrypted_password,
            'cert_file': cert_file_b64,
            'cert_filename': post_data.get('cert_filename', f'{device_id or "certificate"}.p12'),
        }
        
        # 6. Find and Update/Create Record
        bind_env = request.env['device.cert.bind'].sudo()
        existing = bind_env.search([('cert_serial', '=', cert_serial)], limit=1)
        
        try:
            if existing:
                existing.write(vals)
                record = existing
                action = 'updated'
            else:
                record = bind_env.create(vals)
                action = 'created'
            
            _logger.info(f"Binding record {action}: ID={record.id}, Serial={cert_serial}")
            
            return {
                'success': True,
                'message': f'Binding {action} successfully',
                'record_id': record.id,
                'action': action
            }
            
        except Exception as e:
            _logger.exception(f"Failed to create/update binding record: {e}")
            return {
                'success': False,
                'error': f'Database operation failed: {str(e)}'
            }
    
    @http.route('/api/verify-device-cert', type='json', auth='public', csrf=False, cors='*')
    def verify_device_cert(self, **kwargs):
        """
        Device certificate verification API
        Workflow:
        1. Shell creates certificate: writes to device.cert.bind with cert_serial, is_placeholder=True
        2. First login: finds cert_serial with is_placeholder=True, updates device_id (is_placeholder becomes False)
        3. Subsequent login: finds cert_serial with device_id, is_placeholder=False, state='active'
        """
        try:
            # 1. Get request data
            httprequest = request.httprequest
            request_json = json.loads(httprequest.data.decode('utf-8')) if httprequest.data else {}
            device_id = request_json.get('device_id', '').strip()
            client_ip = httprequest.remote_addr
            
            # 2. Get certificate serial number
            cert_serial = (
                httprequest.headers.get('X-SSL-CLIENT-SERIAL', '').strip() or
                request_json.get('cert_serial', '').strip() or
                device_id
            )
            
            _logger.info(f"Verification request: device_id={device_id[:20] if device_id else ''}, "
                        f"cert_serial={cert_serial[:20] if cert_serial else ''}, ip={client_ip}")

            # 3. Validate parameters
            if not device_id or not cert_serial:
                error_msg = f"Missing required parameters: device_id={bool(device_id)}, cert_serial={bool(cert_serial)}"
                _logger.warning(error_msg)
                self._log_api_request(device_id, cert_serial, client_ip, 'failed', error_msg)
                return {
                    'allow': False,
                    'error': error_msg
                }
            
            # 4. Query certificate binding record
            DeviceCertBinding = request.env['device.cert.bind'].sudo()
            domain = [('cert_serial', '=', cert_serial)]
            binding_record = DeviceCertBinding.search(domain, limit=1)

            if not binding_record:
                # Certificate not found in database
                error_msg = f"Certificate not found: {cert_serial}"
                _logger.warning(f"❌ {error_msg}")
                self._log_api_request(device_id, cert_serial, client_ip, 'blocked', error_msg)
                return {
                    'allow': False,
                    'error': 'Certificate not registered in system. Please ensure certificate was created via shell script.',
                    'cert_serial': cert_serial
                }

            else:
                # 5. Check certificate status
                if binding_record.state != 'active':
                    error_msg = f"Certificate not active: {binding_record.state}"
                    _logger.warning(f"❌ {error_msg}")
                    self._log_api_request(device_id, cert_serial, client_ip, 'blocked', error_msg)
                    return {
                        'allow': False,
                        'error': error_msg
                    }
                
                # 6. Check if this is a placeholder record (first login scenario)
                if binding_record.is_placeholder:
                    # First login: Update placeholder with real device_id
                    binding_record.write({
                        'device_id': device_id,
                        'ip_address': client_ip,
                        'last_login': fields.Datetime.now()
                    })
                    
                    success_msg = f"First login successful: Updated placeholder with device_id={device_id[:20]}..."
                    _logger.info(f"✅ {success_msg}")
                    self._log_api_request(device_id, cert_serial, client_ip, 'allowed', success_msg)
                    
                    return {
                        'allow': True,
                        'first_time': True,
                        'message': 'First login successful. Device has been registered to certificate.',
                        'bound_to': device_id,
                        'cert_serial': cert_serial,
                        'was_placeholder': True
                    }
                
                # 7. Check if device_id matches (subsequent login)
                elif binding_record.device_id == device_id:
                    # Subsequent login: Update last login time
                    binding_record.write({
                        'last_login': fields.Datetime.now(),
                        'ip_address': client_ip
                    })
                    
                    success_msg = f"Login successful: Device verified"
                    _logger.info(f"✅ {success_msg}")
                    self._log_api_request(device_id, cert_serial, client_ip, 'allowed', success_msg)
                    
                    return {
                        'allow': True,
                        'first_time': False,
                        'message': 'Login successful. Device authorized for access.',
                        'bound_to': device_id,
                        'cert_serial': cert_serial,
                        'was_placeholder': False
                    }
                
                # 8. Device mismatch
                else:
                    error_msg = (f"Device mismatch: cert_serial={cert_serial}, "
                               f"bound_to={binding_record.device_id}, current={device_id}")
                    _logger.warning(f"❌ {error_msg}")
                    self._log_api_request(device_id, cert_serial, client_ip, 'blocked', error_msg)
                    
                    return {
                        'allow': False,
                        'error': 'Device fingerprint mismatch. This certificate is already bound to another device.',
                        'bound_to': binding_record.device_id,
                        'cert_serial': cert_serial
                    }

        except json.JSONDecodeError as e:
            error_msg = f"JSON parsing error: {str(e)}"
            _logger.error(f"❌ {error_msg}")
            self._log_api_request(None, None, httprequest.remote_addr, 'failed', error_msg)
            return {
                'allow': False,
                'error': error_msg
            }
            
        except Exception as e:
            error_msg = f"Verification exception: {str(e)}"
            _logger.exception(f"❌ {error_msg}")
            self._log_api_request(
                device_id if 'device_id' in locals() else None,
                cert_serial if 'cert_serial' in locals() else None,
                client_ip if 'client_ip' in locals() else None,
                'failed',
                error_msg
            )
            return {
                'allow': False,
                'error': error_msg
            }
    
    @http.route('/api/device_cert/status/<string:cert_serial>', type='json', auth='public', methods=['GET'], csrf=False, cors='*')
    def get_cert_status(self, cert_serial):
        """Query certificate binding status"""
        try:
            # Get client IP
            httprequest = request.httprequest
            client_ip = httprequest.remote_addr
            
            _logger.info(f"Status query: cert_serial={cert_serial[:20] if cert_serial else ''}, ip={client_ip}")

            # 1. Find record
            bind_env = request.env['device.cert.bind'].sudo()
            record = bind_env.search([('cert_serial', '=', cert_serial)], limit=1)
            
            if not record:
                self._log_api_request(None, cert_serial, client_ip, 'failed', f"Certificate not found: {cert_serial}")
                return {
                    'success': True,
                    'found': False,
                    'message': 'Certificate not found in database',
                    'cert_serial': cert_serial
                }
            
            # 2. Return status data
            data = {
                'cert_serial': record.cert_serial,
                'device_id': record.device_id or '',
                'is_placeholder': record.is_placeholder,
                'bound': not record.is_placeholder,  # True if device is bound
                'state': record.state,
                'user_email': record.user_email or '',
                'ip_address': record.ip_address or '',
                'create_date': record.create_date.isoformat() if record.create_date else None,
                'last_login': record.last_login.isoformat() if record.last_login else None,
                'record_id': record.id
            }
            
            log_msg = f"Status query: cert={cert_serial[:20]}, bound={not record.is_placeholder}"
            _logger.info(f"✅ {log_msg}")
            self._log_api_request(
                record.device_id, 
                cert_serial, 
                client_ip, 
                'allowed' if not record.is_placeholder else 'blocked', 
                log_msg
            )
            
            return {
                'success': True,
                'data': data,
                'message': 'Certificate bound to device' if not record.is_placeholder else 'Certificate is placeholder (waiting for first binding)',
                'timestamp': fields.Datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = f"Status query exception: {str(e)}"
            _logger.exception(f"❌ {error_msg}")
            self._log_api_request(None, cert_serial, request.httprequest.remote_addr, 'failed', error_msg)
            return {
                'success': False,
                'error': f'Error retrieving certificate status: {str(e)}',
                'cert_serial': cert_serial
            }