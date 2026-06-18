from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import base64

_logger = logging.getLogger(__name__)

class InboundOrderDeepSeekVerification(models.Model):
    _inherit = 'world.depot.inbound.order'
    
    # Verification status fields
    check_status = fields.Selection([
        ('not_checked', 'Not Checked'),
        ('checking', 'Checking'),
        ('pass', '✅ Passed'),
        ('warning', '⚠️ Needs Attention'),
        ('error', '❌❌ Issues Found'),
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
        Main action to verify inbound order with DeepSeek
        """
        self.ensure_one()
        
        # Initialize utilities
        deepseek_checker = self.env['deepseek.checker']
        deepseek_utils = self.env['deepseek.utils']
        
        # Set start time
        self.check_time_begin = fields.Datetime.now()
        self.check_result = False
        self.check_status = 'unknown'
        self.risk_level = 'unknown'
        self.check_duration = 0.0
        self.file_analysis_metrics = ''
        self.total_files_processed = 0
        self.successfully_analyzed = 0
        
        try:
            # Update status to checking
            self._update_verification_status('checking')
            
            # Prepare data for verification
            order_data = self._prepare_order_data()
            attachments = self._prepare_any_file_attachments()
            
            # Execute DeepSeek verification
            result = deepseek_checker.check_order_with_deepseek(order_data, attachments)
            
            # Calculate and store duration
            self.check_duration = (fields.Datetime.now() - self.check_time_begin).total_seconds()
            
            # Store results using utility method
            deepseek_utils.store_check_results(self, result)
            
            # Update file analysis metrics
            file_analysis = result.get('file_analysis', {})
            self.write({
                'total_files_processed': file_analysis.get('total_files_processed', 0),
                'successfully_analyzed': file_analysis.get('successfully_analyzed', 0)
            })
            
            # Return user-friendly notification
            return deepseek_utils.show_result_notification(result, self.id)
            
        except Exception as e:
            _logger.error("DeepSeek verification failed for inbound order %s: %s", self.id, str(e))
            self._handle_verification_error(str(e))
            return deepseek_utils.show_error_notification(str(e))

    def _prepare_any_file_attachments(self):
        """
        Prepare any file type attachments for DeepSeek upload
        
        Returns:
            list: List of file data for DeepSeek API
        """
        self.ensure_one()
        
        attachments = []
        '''
        # Get all attachments related to this inbound order
        attachment_records = self.env['ir.attachment'].search([
            ('res_model', '=', 'world.depot.inbound.order'),
            ('res_id', '=', self.id)
        ])
        
        _logger.info("Found %d attachments for inbound order %s", len(attachment_records), self.id)
        
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
        # Also check documents from inbound_order_doc_ids
        if hasattr(self, 'inbound_order_doc_ids') and self.inbound_order_doc_ids:
            for doc in self.inbound_order_doc_ids:
                try:
                    if doc.doc_type == 'origin':
                        if hasattr(doc, 'file') and doc.file:
                            file_data = base64.b64decode(doc.file)
                            file_info = {
                                'filename': getattr(doc, 'filename', f'document_{doc.id}'),
                                'data': file_data,
                                'type': getattr(doc, 'mimetype', 'application/octet-stream'),
                                'description': getattr(doc, 'description', ''),
                                'source': 'inbound_order_doc'
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
        """Prepare inbound order data for verification"""
        return {
            'order_type': 'inbound_order',
            'billno': self.billno or '',
            'reference': self.reference or '',
            'order_date': str(self.date) if self.date else '',
            'arrival_date': str(self.a_date) if self.a_date else '',
            'container_no': self.cntr_no or '',
            'bill_of_lading': self.bl_no or '',
            'invoice_no': self.invoice_no or '',
            'owner': self.owner.name if self.owner else '',
            'project': self.project.name if self.project else '',
            'warehouse': self.warehouse.name if self.warehouse else '',
            'pallets': self.pallets,
            'total_weight': self.weight_total,
            'is_adr': self.is_adr,
            'is_bonded': self.is_bonded,
            'state': self.state,
            'status': self.status,
            'products': self._prepare_product_data()
        }

    def _prepare_product_data(self):
        """Prepare product information for verification"""
        products = []
        for product in self.inbound_order_product_ids:
            product_data = {
                'pallet_type': product.pallet_type or '',
                'pallets': product.pallets,
                'product_description': product.product_description or '',
                'adr': product.adr,
                'un_number': product.un_number or '',
                'quantity': product.quantity,
                'weight_total': product.weight_total,
                'products_on_pallet': self._prepare_pallet_products(product)
            }
            products.append(product_data)
        return products

    def _prepare_pallet_products(self, product):
        """Prepare products on each pallet"""
        pallet_products = []
        for pallet_product in product.inbound_order_product_pallet_ids:
            pallet_products.append({
                'product_name': pallet_product.product_id.name if pallet_product.product_id else '',
                'quantity': pallet_product.quantity,
                'weight': pallet_product.weight,
                'adr': pallet_product.adr,
                'un_number': pallet_product.un_number or ''
            })
        return pallet_products

    def _handle_verification_error(self, error_message):
        """Handle verification errors"""
        self.write({
            'check_status': 'error',
            'check_result': f"Verification failed: {error_message}"
        })

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
            raise UserError(_("No check results available. Please run the DeepSeek verification first."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'DeepSeek Verification Results',
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
        return self.action_verify_with_deepseek()

    def action_upload_files(self):
        """
        Action to manually upload files for DeepSeek verification
        
        Returns:
            dict: Odoo action for file upload
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Upload Files for DeepSeek Verification',
            'res_model': 'ir.attachment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': 'world.depot.inbound.order',
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
            return f"❌❌ Issues found - please review"
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
        message_lines.append(f"=== Attachment Debug for Order {self.billno} ===")
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
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Attachment Debug',
                'message': '\n'.join(message_lines),
                'type': 'info',
                'sticky': True,
            }
        }