from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import base64

_logger = logging.getLogger(__name__)


class OutboundOrderDeepSeekVerification(models.Model):
    _inherit = 'world.depot.outbound.order'
    
    # Verification status fields
    check_status = fields.Selection([
        ('not_checked', 'Not Checked'),
        ('checking', 'Checking'),
        ('pass', '✅ Passed'),
        ('warning', '⚠️ Needs Attention'),
        ('error', '❌❌❌❌ Issues Found'),
        ('unknown', 'Unknown Status')
    ], string='Verification Status', default='not_checked', tracking=True)
    
    risk_level = fields.Selection([
        ('none', 'No Risk'),
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk'),
        ('unknown', 'Unknown Risk')
    ], string='Risk Level', default='unknown', tracking=True)
    
    check_result = fields.Text(string='Verification Results', readonly=True)
    check_time_begin = fields.Datetime(string='Check Start Time', readonly=True)
    check_duration = fields.Float(string='Check Duration (seconds)', readonly=True)
    last_check_date = fields.Datetime(string='Last Check Date', readonly=True)
    checked_by = fields.Many2one('res.users', string='Checked By', readonly=True)
    
    # File analysis metrics
    file_analysis_metrics = fields.Text(string='File Analysis Metrics')
    total_files_processed = fields.Integer(string='Total Files Processed', readonly=True)
    successfully_analyzed = fields.Integer(string='Successfully Analyzed', readonly=True)

    def action_verify_with_deepseek(self):
        """
        Main action to verify outbound order with DeepSeek
        """
        self.ensure_one()
        
        _logger.info("=== Starting DeepSeek verification for outbound order %s ===", self.billno)
        
        # Initialize utilities
        deepseek_checker = self.env['deepseek.checker']
        deepseek_utils = self.env['deepseek.utils']
        
        # Set start time and reset all fields
        self.check_time_begin = fields.Datetime.now()
        self._reset_verification_fields()
        
        try:
            
            # Update status to checking
            self._update_verification_status('checking')
            
            # Prepare data for verification
            _logger.info("Preparing order data for verification...")
            order_data = self._prepare_order_data()
            
            _logger.info("Preparing file attachments for verification...")
            attachments = self._prepare_any_file_attachments()
            
            _logger.info("Executing DeepSeek verification with %d attachments...", len(attachments))
            # Execute DeepSeek verification
            result = deepseek_checker.check_order_with_deepseek(order_data, attachments)
            
            # Calculate and store duration
            self.check_duration = (fields.Datetime.now() - self.check_time_begin).total_seconds()
            
            # Store results using utility method
            _logger.info("Storing verification results...")
            deepseek_utils.store_check_results(self, result)
            
            # Update file analysis metrics
            file_analysis = result.get('file_analysis', {})
            self.write({
                'total_files_processed': file_analysis.get('total_files_processed', 0),
                'successfully_analyzed': file_analysis.get('successfully_analyzed', 0)
            })
            
            _logger.info("=== DeepSeek verification completed successfully for outbound order %s ===", self.billno)
            _logger.info("Verification duration: %.2f seconds", self.check_duration)
            _logger.info("Files processed: %d/%d", 
                        file_analysis.get('successfully_analyzed', 0), 
                        file_analysis.get('total_files_processed', 0))
            
            # Return user-friendly notification
            return deepseek_utils.show_result_notification(result, self.id)
            
        except Exception as e:
            _logger.error("=== DeepSeek verification FAILED for outbound order %s ===", self.billno)
            _logger.error("Error: %s", str(e), exc_info=True)
            self._handle_verification_error(str(e))
            return deepseek_utils.show_error_notification(str(e))

    def _reset_verification_fields(self):
        """Reset all verification fields to initial state"""
        self.write({
            'check_result': '',
            'check_status': 'unknown',
            'risk_level': 'unknown',
            'check_duration': 0.0,
            'file_analysis_metrics': '',
            'total_files_processed': 0,
            'successfully_analyzed': 0
        })

    def _prepare_any_file_attachments(self):
        """
        Prepare any file type attachments for DeepSeek upload
        
        Returns:
            list: List of file data for DeepSeek API
        """
        self.ensure_one()
        
        attachments = []
        '''
        # Get all attachments related to this outbound order
        attachment_records = self.env['ir.attachment'].search([
            ('res_model', '=', 'world.depot.outbound.order'),
            ('res_id', '=', self.id)
        ])
        
        _logger.info("Found %d attachments for outbound order %s", len(attachment_records), self.id)
        
        for attachment in attachment_records:
            try:
                # Read file content
                file_content = attachment.datas
                if file_content:
                    # Decode base64 content
                    file_data = base64.b64decode(file_content)
                    
                    # Prepare file info for DeepSeek
                    file_info = {
                        'filename': attachment.name,
                        'data': file_data,
                        'type': attachment.mimetype or 'application/octet-stream',
                        'description': attachment.description or '',
                        'source': 'ir.attachment'
                    }
                    attachments.append(file_info)
                    
                    _logger.debug("Prepared attachment: %s (type: %s, size: %d bytes)", 
                                attachment.name, attachment.mimetype, len(file_data))
                    
            except Exception as e:
                _logger.warning("Failed to process attachment %s: %s", attachment.name, str(e))
                continue
           '''
        
        # Also check documents from outbound_order_docs_ids
        if hasattr(self, 'outbound_order_docs_ids') and self.outbound_order_docs_ids:
            for doc in self.outbound_order_docs_ids:
                try:
                    if doc.doc_type=='origin':
                        if hasattr(doc, 'file') and doc.file:
                            file_data = base64.b64decode(doc.file)
                            file_info = {
                                'filename': getattr(doc, 'filename', f'document_{doc.id}'),
                                'data': file_data,
                                'type': getattr(doc, 'mimetype', 'application/octet-stream'),
                                'description': getattr(doc, 'description', ''),
                                'source': 'outbound_order_doc'
                            }
                            attachments.append(file_info)
                            _logger.debug("Prepared document: %s", file_info['filename'])
                except Exception as e:
                    _logger.warning("Failed to process document %s: %s", doc.id, str(e))
                    continue
        
        # Check for any binary fields in the main record
        binary_fields = [field_name for field_name, field in self._fields.items() if field.type == 'binary']
        for field_name in binary_fields:
            try:
                field_data = getattr(self, field_name)
                if field_data:
                    file_data = base64.b64decode(field_data)
                    file_info = {
                        'filename': f"{field_name}_{self.billno or self.id}",
                        'data': file_data,
                        'type': 'application/octet-stream',
                        'description': f"File from field {field_name}",
                        'source': 'binary_field'
                    }
                    attachments.append(file_info)
                    _logger.debug("Prepared binary field: %s", field_name)
            except Exception as e:
                _logger.warning("Failed to process binary field %s: %s", field_name, str(e))
                continue
        
        _logger.info("Prepared %d file attachments for DeepSeek verification", len(attachments))
        return attachments
    
    def _update_verification_status(self, status):
        """Update verification status and metadata"""
        self.write({
            'check_status': status,
            'last_check_date': fields.Datetime.now(),
            'checked_by': self.env.user.id
        })

    def _prepare_order_data(self):
        """Prepare outbound order data for verification"""
        _logger.debug("Preparing order data for outbound order %s", self.billno)
        
        order_data = {
            'order_type': 'outbound_order',
            'billno': self.billno or '',
            'order_date': str(self.date) if self.date else '',
            'project': self.project.name if self.project else '',
            'warehouse': self.warehouse.name if self.warehouse else '',
            'state': self.state or '',  
            'remark': self.remark or '',
            
            # information
            'unload_company': self.unload_company.name if self.unload_company else '',
            'delivery_phone': self.delivery_phone or '',
            'delivery_mobile': self.delivery_mobile or '',
            'delivery_email': self.delivery_email or '',
            'delivery_street': self.delivery_street or '',
            'delivery_city': self.delivery_city or '',
            'delivery_zip': self.delivery_zip or '',
            'delivery_country': self.delivery_country_id.name if self.delivery_country_id else '',
            
            # Products information
            'products': self._prepare_product_data(),
            'total_products': len(self.outbound_order_product_ids) if self.outbound_order_product_ids else 0
        }
        
        _logger.debug("Order data prepared: %s", { v for k, v in order_data.items() if k != 'products'})
        return order_data

    def _prepare_product_data(self):
        """Prepare product information for verification"""
        products = []
        
        if not self.outbound_order_product_ids:
            _logger.debug("No products found for outbound order %s", self.billno)
            return products
            
        for product in self.outbound_order_product_ids:
            try:
                product_data = {
                    'product_id': product.product_id.id,
                    'product_name': product.product_id.name,
                    'quantity': getattr(product, 'quantity', 0),
                    'weight': getattr(product, 'weight', 0),
                    'remarks': getattr(product, 'remark', ''),
                }
                products.append(product_data)
            except Exception as e:
                _logger.warning("Failed to prepare product data for product %s: %s", product.id, str(e))
                continue
        
        _logger.debug("Prepared %d products for verification", len(products))
        return products

    def _handle_verification_error(self, error_message):
        """Handle verification errors"""
        self.write({
            'check_status': 'error',
            'check_result': f"Verification failed: {error_message}",
            'risk_level': 'high'
        })
        _logger.error("Ver handled for outbound order %s: %s", self.billno, error_message)

    def action_view_detailed_results(self):
        """
        Action to view detailed check results
        
        Returns:
            dict: Odoo client action for notification
            
        Raises:
            UserError: If no check results available
        """
        self.ensure_one()

        if not self.check_result:
            raise UserError(_("No verification results available. Please run the DeepSeek verification first."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('DeepSeek Verification Results - Outbound Order'),
                'message': self.check_result,
                'type': 'info',
                'sticky': True,
            }
        }

    def action_retry_verification(self):
        """
        Retry DeepSeek verification
        
        Returns:
            dict: Result of action_verify_with_deepseek
        """
        self.ensure_one()
        _logger.info("Retrying verification for outbound order %s", self.billno)
        self.action_verify_with_deepseek()

    def action_upload_files(self):
        """
        Action to manually upload files for DeepSeek verification
        
        Returns:
            dict: Odoo action for file upload
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Upload Files for DeepSeek Verification'),
            'res_model': 'ir.attachment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': 'panexlogi.outbound.order',
                'default_res_id': self.id,
                'default_name': f"DeepSeek_Verification_File_{self.billno or self.id}",
            }
        }

    def _get_verification_summary(self):
        """Get a quick summary of verification status"""
        if self.check_status == 'pass':
            return f"✅ Verified on {self.last_check_date} by {self.checked_by.name}"
        elif self.check_status == 'warning':
            return f"⚠️ Needs attention - checked on {self.last_check_date}"
        elif self.check_status == 'error':
            return f"❌❌❌❌ Issues found - please review"
        elif self.check_status == 'checking':
            return "⏳⏳⏳ Verification in progress..."
        else:
            return "Not yet verified"

    def action_debug_attachments(self):
        """
        Debug action to check what attachments are available
        
        Returns:
            dict: Odoo action showing attachment details
        """
        self.ensure_one()
        
        attachments = self._prepare_any_file_attachments()
        
        message_lines = []
        message_lines.append(f"=== Attachment Debug for Outbound Order {self.billno} ===")
        message_lines.append(f"Total attachments found: {len(attachments)}")
        message_lines.append("")
        
        for i, att in enumerate(attachments, 1):
            message_lines.append(f"Attachment {i}:")
            message_lines.append(f"  Name: {att.get('filename', 'N/A')}")
            message_lines.append(f"  Type: {att.get('type', 'N/A')}")
            message_lines.append(f"  Source: {att.get('source', 'N/A')}")
            data_size = len(att.get('data', b'')) if att.get('data') else 0
            message_lines.append(f"  Size: {data_size} bytes")
            message_lines.append("")
        
        # Add system information
        message_lines.append("=== System Information ===")
        message_lines.append(f"Order ID: {self.id}")
        message_lines.append(f"Order BillNo: {self.billno}")
        message_lines.append(f"Current Status: {self.check_status}")
        message_lines.append(f"Risk Level: {self.risk_level}")
        
        return {
            'type': 'actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Attachment Debug - Outbound Order'),
                'message': '\n'.join(message_lines),
                'type': 'info',
                'sticky': True,
            }
        }

    def action_check_system_attachments(self):
        """
        Check what attachments are available in the system for this order
        
        Returns:
            dict: Odoo action showing system attachment details
        """
        self.ensure_one()
        
        # Check ir.attachments
        ir_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'panexlogi.outbound.order'),
            ('res_id', '=', self.id)
        ])
        
        message_lines = []
        message_lines.append(f"=== System Attachment Check for Outbound Order {self.billno} ===")
        message_lines.append(f"ir.attachment records found: {len(ir_attachments)}")
        message_lines.append("")
        
        for i, att in enumerate(ir_attachments, 1):
            message_lines.append(f"Attachment {i}:")
            message_lines.append(f"  Name: {att.name}")
            message_lines.append(f"  Type: {att.mimetype}")
            message_lines.append(f"  Size: {att.file_size if hasattr(att, 'file_size') else 'N/A'} bytes")
            message_lines.append(f"  Description: {att.description or 'N/A'}")
            message_lines.append("")
        
        # Check binary fields
        binary_fields = [f for f in self._fields if self._fieldstype == 'binary']
        message_lines.append(f"Binary fields in model: {len(binary_fields)}")
        for field in binary_fields:
            has_data = bool(getattr(self, field))
            message_lines.append(f"  {field}: {'Has data' if has_data else 'Empty'}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('System Attachment Check'),
                'message': '\n'.join(message_lines),
                'type': 'info',
                'sticky': True,
            }
        }