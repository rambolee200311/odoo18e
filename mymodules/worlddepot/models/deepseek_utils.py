import logging
import json
import base64
from odoo import _, models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class DeepSeekUtils(models.AbstractModel):
    """Enhanced utility class with file upload support"""
    _name = 'deepseek.utils'
    _description = 'DeepSeek Utility Methods'

    # Enhanced MIME type mapping
    MIME_TYPE_MAPPING = {
        # Document formats
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        
        # Image formats
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.bmp': 'image/bmp', '.tiff': 'image/tiff', '.tif': 'image/tiff',
        
        # Text formats
        '.txt': 'text/plain', '.csv': 'text/csv',
        '.json': 'application/json', '.xml': 'application/xml',
        '.html': 'text/html', '.htm': 'text/html',
        
        # Archive formats
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed',
        '.tar': 'application/x-tar',
        
        # Magic numbers
        b'%PDF': 'application/pdf',
        b'\x89PNG\r\n\x1a\n': 'image/png',
        b'\xff\xd8\xff': 'image/jpeg',
        b'PK\x03\x04': 'application/zip',
        b'\xd0\xcf\x11\xe0': 'application/msword',
        b'\x50\x4B\x03\x04': 'application/zip',  # Alternative ZIP signature
    }

    # Status mapping constants
    STATUS_MAP = {
        '✅ Passed': 'pass',
        '⚠️ Needs Attention': 'warning',
        '❌❌ Issues Found': 'error',
        '❌❌ Check Failed': 'error',
        'pass': 'pass',
        'warning': 'warning',
        'fail': 'error',
        'error': 'error'
    }

    def store_check_results(self, record, result):
        """
        Enhanced result storage with file analysis information
        """
        try:
            # Validate input types
            if not record:
                _logger.error("No record provided for storing results")
                return False
                
            # Handle case where result might be a list instead of dict
            if isinstance(result, list):
                _logger.warning("Result is a list, expected dictionary. Using first item if available.")
                if result and isinstance(result[0], dict):
                    result = result[0]
                else:
                    self._set_error_results(record, "Invalid result format: expected dictionary but got empty list")
                    return False
            
            if not isinstance(result, dict):
                self._set_error_results(record, f"Invalid result format: expected dictionary but got {type(result).__name__}")
                return False
            
            # Store detailed results as readable text
            record.check_result = self.format_friendly_check_result(result)
            
            # Store simplified status fields
            self._store_simplified_status(record, result)
            
            # Store file analysis metrics if available
            self._store_file_analysis_metrics(record, result)
            
            _logger.info("Stored check results successfully - Status: %s, Risk: %s", 
                        record.check_status, record.risk_level)
            return True

        except Exception as e:
            _logger.error("Error storing check results: %s", str(e))
            self._set_error_results(record, str(e))
            return False

    def _store_simplified_status(self, record, result):
        """Extract and store simplified status information with type safety"""
        try:
            # Safely get display information
            display_info = result.get('display', {})
            if not isinstance(display_info, dict):
                display_info = {}
            
            # Set check status
            status_text = display_info.get('status', result.get('status', 'Unknown Status'))
            if not isinstance(status_text, str):
                status_text = str(status_text)
            record.check_status = self._map_status_text_to_value(status_text)
            
            # Set risk level
            risk_level_info = display_info.get('risk_level', {})
            record.risk_level = self._determine_risk_level(risk_level_info)

        except Exception as e:
            _logger.error("Error storing simplified status: %s", str(e))
            record.check_status = 'unknown'
            record.risk_level = 'unknown'

    def _store_file_analysis_metrics(self, record, result):
        """Store file analysis metrics if available"""
        try:
            file_analysis = result.get('file_analysis', {})
            if isinstance(file_analysis, dict):
                # Store file analysis metrics in a JSON field if available
                if hasattr(record, 'file_analysis_metrics'):
                    record.file_analysis_metrics = json.dumps(file_analysis)
                
                # Log file analysis results
                total_files = file_analysis.get('total_files_processed', 0)
                successful_files = file_analysis.get('successfully_analyzed', 0)
                
                if total_files > 0:
                    success_rate = (successful_files / total_files) * 100
                    _logger.info("File analysis: %s/%s files processed (%.1f%% success rate)", 
                                successful_files, total_files, success_rate)
                    
        except Exception as e:
            _logger.warning("Error storing file analysis metrics: %s", str(e))

    def _ensure_bytes(self, file_data):
        """Ensure the returned attachment data is bytes."""
        if not file_data:
            return b''
        
        # If it's already bytes or a memoryview/bytearray, return as-is
        if isinstance(file_data, (bytes, bytearray, memoryview)):
            return bytes(file_data)
        
        # If it's a text string, try base64 decode first, otherwise encode utf-8
        if isinstance(file_data, str):
            # Handle data URI: data:<mime>;base64,<data>
            if file_data.startswith('data:') and ',' in file_data:
                try:
                    _hdr, b64 = file_data.split(',', 1)
                    return base64.b64decode(b64)
                except Exception:
                    pass
            try:
                return base64.b64decode(file_data)
            except Exception:
                try:
                    return file_data.encode('utf-8')
                except Exception:
                    return b''
        
        # Fallback: convert to string then to bytes
        try:
            return str(file_data).encode('utf-8')
        except Exception:
            return b''

    def _map_status_text_to_value(self, status_text):
        """Map status text to selection value with type safety"""
        if not isinstance(status_text, str):
            status_text = str(status_text)
            
        # First try exact matches
        status_text_lower = status_text.lower()
        for pattern, status_value in self.STATUS_MAP.items():
            if pattern.lower() in status_text_lower:
                return status_value
        
        # Fallback to keyword matching
        if 'pass' in status_text_lower or 'success' in status_text_lower:
            return 'pass'
        elif 'warn' in status_text_lower or 'attention' in status_text_lower:
            return 'warning'
        elif 'error' in status_text_lower or 'fail' in status_text_lower or 'issue' in status_text_lower:
            return 'error'
        
        return 'unknown'

    def _determine_risk_level(self, risk_level_info):
        """Determine risk level from risk level info with type safety"""
        if isinstance(risk_level_info, dict):
            level = risk_level_info.get('level', risk_level_info.get('text', 'unknown'))
            if isinstance(level, str):
                return level.lower() if level.lower() in ['none', 'low', 'medium', 'high'] else 'unknown'
            return str(level)
        
        risk_text = str(risk_level_info).lower()
        if 'high' in risk_text:
            return 'high'
        elif 'medium' in risk_text:
            return 'medium'
        elif 'low' in risk_text:
            return 'low'
        elif 'none' in risk_text or 'no risk' in risk_text:
            return 'none'
        return 'unknown'

    def _set_error_results(self, record, error_message):
        """Set error results when exception occurs"""
        try:
            record.check_status = 'error'
            record.risk_level = 'unknown'
            record.check_result = f"Error storing results: {error_message}"
        except Exception as e:
            _logger.error("Failed to set error results: %s", str(e))

    def format_friendly_check_result(self, result):
        """
        Enhanced result formatting with file analysis information
        """
        try:
            if not isinstance(result, dict):
                return f"Invalid result format: expected dictionary but got {type(result).__name__}"
            
            lines = []
            lines.append("📊📊 DEEPSEEK DOCUMENT VERIFICATION RESULTS")
            lines.append("=" * 60)
            lines.append("")
            
            # File analysis summary
            file_analysis = result.get('file_analysis', {})
            total_files = file_analysis.get('total_files_processed', 0)
            successful_files = file_analysis.get('successfully_analyzed', 0)
            
            lines.append("📁📁 FILE ANALYSIS SUMMARY")
            lines.append(f"• Total files processed: {total_files}")
            lines.append(f"• Successfully analyzed: {successful_files}")
            if total_files > 0:
                success_rate = (successful_files / total_files) * 100
                lines.append(f"• Analysis success rate: {success_rate:.1f}%")
            lines.append(f"• Summary: {file_analysis.get('analysis_summary', 'N/A')}")
            lines.append("")
            
            # Quick summary box
            lines.append("📋📋 QUICK SUMMARY")
            status = result.get('status', 'Unknown')
            confidence = result.get('confidence', 0)
            lines.append(f"• Status: {status}")
            lines.append(f"• Confidence Score: {confidence:.2f}")
            lines.append(f"• Risk Level: {result.get('risk_level', 'Unknown')}")
            lines.append("")
            
            # Simple summary in plain language
            summary = result.get('summary', 'No summary available')
            if not isinstance(summary, str):
                summary = str(summary)
                
            # Break long summary into readable chunks
            if len(summary) > 120:
                words = summary.split(' ')
                current_line = []
                for word in words:
                    if len(' '.join(current_line + [word])) > 80:
                        lines.append(' '.join(current_line))
                        current_line = [word]
                    else:
                        current_line.append(word)
                if current_line:
                    lines.append(' '.join(current_line))
            else:
                lines.append(summary)
            lines.append("")
            
            # Verified fields section
            verified_fields = result.get('verified_fields', {})
            if verified_fields:
                lines.append("✅✅ VERIFIED FIELDS")
                for field_name, field_info in list(verified_fields.items())[:10]:  # Limit to 10 fields
                    if isinstance(field_info, dict):
                        status = field_info.get('status', 'unknown')
                        confidence = field_info.get('confidence', 0)
                        source = field_info.get('source', 'unknown')
                        status_icon = "✅" if status == 'matched' else "⚠️" if status == 'mismatched' else "❓"
                        lines.append(f"{status_icon} {field_name}: {status} (confidence: {confidence:.2f}, source: {source})")
                    else:
                        lines.append(f"• {field_name}: {field_info}")
                lines.append("")
            
            # Issues section - enhanced for file analysis
            issues = result.get('issues', [])
            critical_issues = [issue for issue in issues if isinstance(issue, dict) and issue.get('severity') == 'high']
            warning_issues = [issue for issue in issues if isinstance(issue, dict) and issue.get('severity') == 'medium']
            suggestion_issues = [issue for issue in issues if isinstance(issue, dict) and issue.get('severity') == 'low']
            
            lines.append("🚨🚨 ISSUES FOUND")
            if len(issues) == 0:
                lines.append("✅ No issues detected - Everything looks good!")
            else:
                if critical_issues:
                    lines.append(f"🔴🔴 CRITICAL ISSUES: {len(critical_issues)} found")
                    for i, issue in enumerate(critical_issues[:3], 1):
                        message = issue.get('message', 'No message')
                        source_file = issue.get('source_file', '')
                        suggestion = issue.get('suggestion', '')
                        lines.append(f"   {i}. {message}")
                        if source_file:
                            lines.append(f"      📁 Source: {source_file}")
                        if suggestion:
                            lines.append(f"      💡💡 Suggestion: {suggestion}")
                    if len(critical_issues) > 3:
                        lines.append(f"   ... and {len(critical_issues) - 3} more critical issues")
                    lines.append("")
                
                if warning_issues:
                    lines.append(f"🟡🟡🟡 WARNINGS: {len(warning_issues)} found")
                    for i, issue in enumerate(warning_issues[:3], 1):
                        message = issue.get('message', 'No message')
                        source_file = issue.get('source_file', '')
                        suggestion = issue.get('suggestion', '')
                        lines.append(f"   {i}. {message}")
                        if source_file:
                            lines.append(f"      📁 Source: {source_file}")
                        if suggestion:
                            lines.append(f"      💡💡 Suggestion: {suggestion}")
                    if len(warning_issues) > 3:
                        lines.append(f"   ... and {len(warning_issues) - 3} more warnings")
                    lines.append("")
                
                if suggestion_issues:
                    lines.append(f"💡💡 SUGGESTIONS: {len(suggestion_issues)} minor improvements")
                    for i, issue in enumerate(suggestion_issues[:2], 1):
                        message = issue.get('message', 'No message')
                        lines.append(f"   {i}. {message}")
                    lines.append("")
            
            # Next steps section
            next_steps = result.get('next_steps', [])
            if next_steps:
                lines.append("🎯🎯 RECOMMENDED ACTIONS")
                for i, step in enumerate(next_steps[:5], 1):
                    if isinstance(step, str):
                        lines.append(f"   {i}. {step}")
                lines.append("")
            
            # Final status indicator
            if critical_issues:
                lines.append("❌❌ ACTION REQUIRED: Please address critical issues before proceeding.")
            elif warning_issues:
                lines.append("⚠️ REVIEW RECOMMENDED: Please review warnings before final approval.")
            else:
                lines.append("✅ ALL CLEAR: No significant issues found. Ready for approval.")
            
            # API usage information
            api_usage = result.get('api_usage', {})
            if api_usage:
                lines.append("")
                lines.append("🔧🔧 API USAGE")
                lines.append(f"• Model: {result.get('model', 'Unknown')}")
                lines.append(f"• Tokens used: {api_usage.get('total_tokens', 'N/A')}")
            
            return "\n".join(lines)

        except Exception as e:
            _logger.error("Error formatting check result: %s", str(e))
            return f"Error formatting results: {str(e)}"

    def show_result_notification(self, result, record_id=None):
        """
        Enhanced notification with file analysis information
        """
        try:
            # Validate input
            if not isinstance(result, dict):
                return self.show_error_notification("Invalid result format")
            
            # Get file analysis information
            file_analysis = result.get('file_analysis', {})
            total_files = file_analysis.get('total_files_processed', 0)
            successful_files = file_analysis.get('successfully_analyzed', 0)
            
            # Get simplified issue counts
            issues = result.get('issues', [])
            critical_count = len([issue for issue in issues if isinstance(issue, dict) and issue.get('severity') == 'high'])
            warning_count = len([issue for issue in issues if isinstance(issue, dict) and issue.get('severity') == 'medium'])
            
            # Build enhanced message
            status = result.get('status', 'Unknown')
            confidence = result.get('confidence', 0)
            
            message_parts = [
                f"Status: {status}",
                f"Confidence: {confidence:.2f}",
                f"Files: {successful_files}/{total_files} analyzed"
            ]
            
            # Very simple issue summary
            if critical_count > 0:
                message_parts.append(f"🚨🚨 {critical_count} critical issue(s)")
            if warning_count > 0:
                message_parts.append(f"⚠️ {warning_count} warning(s)")
            
            if critical_count == 0 and warning_count == 0:
                message_parts.append("✅ No issues found")
            
            message = "\n".join(message_parts)
            
            # Determine notification type
            if critical_count > 0:
                notification_type = 'danger'
            elif warning_count > 0:
                notification_type = 'warning'
            else:
                notification_type = 'success'

            # Build notification parameters
            notification_params = {
                'title': 'Document Verification Complete',
                'message': message,
                'type': notification_type,
                'sticky': True,
            }
            
            # Only add next action if we have a record_id and it's not the abstract model itself
            if record_id and hasattr(self, '_name') and self._name != 'deepseek.utils':
                notification_params['next'] = {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': record_id,
                    'views': [(False, 'form')],
                    'target': 'current',
                }

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': notification_params
            }

        except Exception as e:
            _logger.error("Error showing result notification: %s", str(e))
            return self.show_error_notification(f"Notification error: {str(e)}")

    def show_error_notification(self, error_message):
        """
        Show brief error notification
        """
        try:
            if not isinstance(error_message, str):
                error_message = str(error_message)
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Verification Failed',
                    'message': f'Error: {error_message}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        except Exception as e:
            _logger.error("Error showing error notification: %s", str(e))
            # Fallback notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'An unexpected error occurred',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
    def prepare_attachments(self, record, lines=None):
        """
        Enhanced attachment preparation with better logging and error handling
        """
        try:
            attachments = []
            if not lines:
                lines = []
            
            _logger.info("=== Preparing attachments for record %s ===", record.id)
            
            # Method 1: Check ir.attachment table (most common storage)
            attachments.extend(self._get_attachments_from_ir_attachment(record))
            
            # Method 2: Check binary fields in the main record
            attachments.extend(self._get_binary_attachments_from_record(record, 'main'))
            
            # Method 3: Check line items attachments
            for line in lines:
                # Check ir.attachment for line items
                attachments.extend(self._get_attachments_from_ir_attachment(line, 'line'))
                
                # Check binary fields in line items
                attachments.extend(self._get_binary_attachments_from_record(line, 'line_item'))
            
            # Enhanced logging with file type analysis
            _logger.info("=== ATTACHMENT ANALYSIS ===")
            file_type_summary = {}
            for i, attachment in enumerate(attachments, 1):
                file_type = attachment.get('type', 'Unknown')
                file_type_summary[file_type] = file_type_summary.get(file_type, 0) + 1
                
                _logger.info("Attachment %s:", i)
                _logger.info("  Name: %s", attachment.get('name', 'Unknown'))
                _logger.info("  Type: %s", file_type)
                _logger.info("  Size: %s bytes", len(attachment.get('data', b'')))
                _logger.info("  Source: %s", attachment.get('source', 'Unknown'))
            
            # Log summary
            _logger.info("=== FILE TYPE SUMMARY ===")
            for file_type, count in file_type_summary.items():
                _logger.info("  %s: %s files", file_type, count)
            
            _logger.info("=== Total attachments prepared: %s ===", len(attachments))
            return attachments

        except Exception as e:
            _logger.error("Error preparing attachments: %s", str(e))
            return []

    def _get_attachments_from_ir_attachment(self, record, record_type='main'):
        """
        Enhanced attachment retrieval with better error handling
        """
        attachments = []
        
        try:
            if not record:
                return attachments
                
            # Search for attachments related to this record
            attachment_records = self.env['ir.attachment'].search([
                ('res_model', '=', record._name),
                ('res_id', '=', record.id)
            ])
            
            _logger.info("Found %s attachments in ir.attachment for %s %s", 
                        len(attachment_records), record_type, record.id)
            
            for attach in attachment_records:
                try:
                    file_data = None
                    filename = attach.name or attach.store_fname or f'attachment_{attach.id}'
                    mime_type = attach.mimetype or 'application/octet-stream'

                    # Primary: use datas if present
                    if getattr(attach, 'datas', None):
                        file_data = self._ensure_bytes(attach.datas)
                        source = 'ir.attachment'

                    # Secondary: attachment stored in filestore (no datas)
                    elif getattr(attach, 'store_fname', None):
                        try:
                            # Preferred: use ORM helper to read file content
                            file_data = attach._file_read(attach.store_fname)
                            file_data = self._ensure_bytes(file_data)
                            source = 'ir.attachment_filestore'
                        except Exception:
                            # Fallback: try direct filesystem access
                            try:
                                full_path = attach._full_path(attach.store_fname)
                                with open(full_path, 'rb') as fh:
                                    file_data = fh.read()
                                source = 'ir.attachment_filestore'
                            except Exception as fe:
                                _logger.warning("Unable to read filestore file for attachment %s: %s", attach.id, str(fe))

                    # If we have file data, attempt MIME detection if needed
                    if file_data:
                        if mime_type == 'application/octet-stream' and filename:
                            mime_type = self.detect_mime_type(filename, file_data)

                        # If the DB stored mimetype is generic/empty, update it with detected type
                        try:
                            stored_mime = getattr(attach, 'mimetype', None)
                            if not stored_mime or stored_mime == 'application/octet-stream':
                                try:
                                    attach.sudo().write({'mimetype': mime_type})
                                    _logger.debug("Updated attachment %s mimetype to %s", attach.id, mime_type)
                                except Exception as write_err:
                                    _logger.debug("Could not update mimetype for attachment %s: %s", attach.id, str(write_err))
                        except Exception:
                            pass

                        attachments.append({
                            'name': filename,
                            'data': file_data,
                            'type': mime_type,
                            'source': source,
                            'res_field': attach.res_field,
                            'store_fname': attach.store_fname
                        })

                        _logger.debug("Added attachment from ir.attachment: %s, field: %s, type: %s, source: %s", 
                                    filename, attach.res_field, mime_type, source)

                except Exception as e:
                    _logger.warning("Error processing attachment %s: %s", attach.id, str(e))
        
        except Exception as e:
            _logger.error("Error accessing ir.attachment for record %s: %s", record.id, str(e))
        
        return attachments

    def _get_binary_attachments_from_record(self, record, record_type):
        """
        Enhanced binary field extraction
        """
        attachments = []
        
        try:
            if not record:
                return attachments
                
            for field_name, field in record._fields.items():
                if field.type == 'binary':
                    try:
                        file_data = getattr(record, field_name, None)
                        if file_data:
                            # Get filename from corresponding filename field
                            filename_field = f"{field_name}filename"
                            filename = getattr(record, filename_field, 
                                            f'{record_type}_{record.id}_{field_name}')
                            
                            # Normalize to bytes and detect MIME type
                            file_data = self._ensure_bytes(file_data)
                            mime_type = self.detect_mime_type(filename, file_data)

                            # If the detected mime type is generic, try to find a linked ir.attachment
                            try:
                                if mime_type in (None, 'application/octet-stream'):
                                    attach = self.env['ir.attachment'].search([
                                        ('res_model', '=', record._name),
                                        ('res_id', '=', record.id),
                                        ('res_field', '=', field_name)
                                    ], limit=1)
                                    if attach and attach.mimetype and attach.mimetype != 'application/octet-stream':
                                        mime_type = attach.mimetype
                                        source = 'binary_field_linked_ir_attachment'
                                        _logger.debug("Using linked ir.attachment %s mimetype %s for field %s on %s", attach.id, mime_type, field_name, record._name)
                            except Exception as e:
                                _logger.debug("Error looking up linked ir.attachment for %s.%s: %s", record._name, field_name, e)
                            
                            attachments.append({
                                'name': filename,
                                'data': file_data,
                                'type': mime_type,
                                'source': 'binary_field',
                                'field_name': field_name
                            })
                            
                            _logger.debug("Added attachment from binary field: %s, field: %s, type: %s", 
                                        filename, field_name, mime_type)
                            
                    except Exception as e:
                        _logger.warning("Error processing binary field %s: %s", field_name, str(e))
        except Exception as e:
            _logger.error("Error accessing binary fields for record %s: %s", record.id, str(e))
        
        return attachments

    # Add the missing detect_mime_type method here
    def detect_mime_type(self, filename, file_data):
        """
        Enhanced MIME type detection for files
        """
        try:
            # Priority 1: Detect by filename extension
            if filename and isinstance(filename, str):
                filename_lower = filename.lower()
                for ext, mime_type in self.MIME_TYPE_MAPPING.items():
                    if isinstance(ext, str) and filename_lower.endswith(ext):
                        _logger.debug("Detected by extension: %s -> %s", filename, mime_type)
                        return mime_type
            
            # Priority 2: Detect by magic bytes (search in a larger head and ignore leading whitespace)
            if file_data:
                try:
                    data_bytes = file_data if isinstance(file_data, (bytes, bytearray)) else self._ensure_bytes(file_data)
                    if data_bytes and len(data_bytes) > 4:
                        head = data_bytes[:512]  # Check first 512 bytes for better detection
                        head_stripped = head.lstrip()

                        for magic, mime_type in self.MIME_TYPE_MAPPING.items():
                            if isinstance(magic, bytes) and (magic in head or magic in head_stripped):
                                _logger.debug("Detected by magic bytes: %s", mime_type)
                                return mime_type
                except Exception as e:
                    _logger.debug("Magic bytes detection failed: %s", str(e))
            
            # Priority 3: Special handling for common document scenarios
            if filename and isinstance(filename, str):
                filename_lower = filename.lower()
                # If filename suggests PDF or contains 'pdf', assume PDF
                if 'pdf' in filename_lower or any(keyword in filename_lower for keyword in ['invoice', 'bill', 'receipt', 'order', 'document']):
                    _logger.info("Assuming PDF for document-like filename: %s", filename)
                    return 'application/pdf'
            
            # Final fallback
            _logger.debug("Unknown file type: %s", filename)
            return 'application/octet-stream'
            
        except Exception as e:
            _logger.error("Error detecting MIME type for %s: %s", filename, str(e))
            return 'application/octet-stream'

    # Additional utility methods that might be needed
    def validate_attachment_size(self, file_data, max_size_mb=10):
        """Validate attachment size"""
        try:
            file_size = len(file_data) if file_data else 0
            max_size = max_size_mb * 1024 * 1024  # Convert MB to bytes
            return file_size <= max_size
        except Exception as e:
            _logger.error("Error validating attachment size: %s", str(e))
            return False

    def get_supported_file_types(self):
        """Get list of supported file types for DeepSeek API"""
        return [
            'application/pdf',
            'text/plain',
            'text/csv',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'image/jpeg',
            'image/png',
            'image/gif'
        ]
        
    def _safe_file_read(self, attachment, store_fname):
        """Safe file read with fallbacks"""
        try:
            # Try standard Odoo method first
            if hasattr(attachment, '_file_read'):
                return attachment._file_read(store_fname)
            else:
                # Fallback to custom implementation
                return self._file_read(store_fname)
        except Exception as e:
            _logger.error("Error reading file %s: %s", store_fname, str(e))
            return b''

    def _safe_full_path(self, attachment, store_fname):
        """Safe full path resolution"""
        try:
            if hasattr(attachment, '_full_path'):
                return attachment._full_path(store_fname)
            else:
                return self._full_path(store_fname)
        except Exception as e:
            _logger.error("Error getting full path for %s: %s", store_fname, str(e))
            return None    
        
    def _file_read(self, store_fname):
        """Custom file read method if not available in Odoo"""
        try:
            # This is a fallback implementation
            full_path = self._full_path(store_fname)
            with open(full_path, 'rb') as f:
                return f.read()
        except Exception as e:
            _logger.error("Error reading file %s: %s", store_fname, str(e))
            return b''

    def _full_path(self, store_fname):
        """Get full path for stored file"""
        # This should be implemented based on your Odoo filestore location
        import os
        filestore = self.env['ir.attachment']._filestore()
        return os.path.join(filestore, store_fname)     
    
    def _get_attachment_content(self, attachment):
        """Enhanced content extraction with proper file upload support"""
        result = {
            'excerpt': None,
            'base64': None,
            'content_type': None,
            'status': 'not_attempted',
            'supported': False
        }

        try:
            if not attachment:
                result['status'] = 'empty_attachment'
                return result

            data = attachment.get('data')
            if not data:
                result['status'] = 'no_data'
                return result

            # Handle different data types
            if isinstance(data, bytes):
                data_bytes = data
            elif isinstance(data, str):
                try:
                    data_bytes = base64.b64decode(data)
                except:
                    data_bytes = data.encode('utf-8')
            else:
                data_bytes = bytes(str(data), 'utf-8')

            # Check if file is supported for upload
            mime_type = attachment.get('type', '')
            # If MIME is missing or generic, try to detect from bytes
            if not mime_type or mime_type == 'application/octet-stream':
                try:
                    mime_type = self.detect_mime_type(attachment.get('name', ''), data_bytes)
                    _logger.debug("Detected mime_type from bytes: %s", mime_type)
                except Exception as e:
                    _logger.debug("Byte-based mime detection failed: %s", e)
            file_size = len(data_bytes)
            
            is_supported = self._is_file_supported(mime_type, file_size)
            result['supported'] = is_supported

            if is_supported:
                # For supported files, include as base64 (DeepSeek requires base64)
                try:
                    base64_data = base64.b64encode(data_bytes).decode('ascii')
                    result.update({
                        'base64': base64_data,
                        'content_type': 'base64',
                        'status': 'ready_for_upload',
                        'size': file_size
                    })
                    _logger.info("File prepared for upload: %s, size: %s bytes, type: %s", 
                            attachment.get('name', 'unknown'), file_size, mime_type)
                except Exception as e:
                    result.update({
                        'status': f'base64_error: {str(e)}',
                        'supported': False
                    })
            else:
                # For unsupported files, create a preview
                preview = f"File: {attachment.get('name', 'unknown')}, Type: {mime_type}, Size: {file_size} bytes"
                if file_size > (10 * 1024 * 1024):
                    preview += " [FILE TOO LARGE]"
                elif not self._is_file_supported(mime_type, file_size):
                    preview += " [UNSUPPORTED TYPE]"
                    
                result.update({
                    'excerpt': preview,
                    'content_type': 'text',
                    'status': 'unsupported_file',
                    'size': file_size
                })
                _logger.warning("File not supported for upload: %s, type: %s, size: %s", 
                            attachment.get('name', 'unknown'), mime_type, file_size)

        except Exception as e:
            _logger.error("Attachment processing error: %s", str(e))
            result['status'] = f'error: {str(e)}'

        return result

    def _is_file_supported(self, mime_type, file_size):
        """Check if file type and size are supported by DeepSeek API"""
        supported_types = [
            'application/pdf',
            'text/plain', 'text/csv',
            'application/msword', 
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'image/jpeg', 'image/png', 'image/gif'
        ]
        
        # DeepSeek API typically supports files up to 10MB
        max_size = 10 * 1024 * 1024  # 10MB
        
        # Check if type is supported AND size is within limits AND file has content
        is_supported = (
            mime_type in supported_types and 
            file_size <= max_size and 
            file_size > 0
        )
        
        _logger.debug("File support check: type=%s, size=%s, supported=%s", 
                    mime_type, file_size, is_supported)
        return is_supported

    def _build_messages_with_files(self, check_data):
        """Build messages with file attachments - FIXED VERSION"""
        order_data = check_data.get('order_data', {})
        supported_files = check_data.get('supported_files', [])
        
        messages = [
            {
                "role": "system",
                "content": """You are a professional document verification specialist with file analysis capabilities.
                Analyze the provided order data and attached files carefully. 
                For PDFs: Extract text and verify against order data.
                Focus on detecting discrepancies, fraud indicators, and data quality issues."""
            }
        ]

        # Add file attachments first (DeepSeek requires files before the main message)
        for file_info in supported_files:
            b64 = file_info.get('content_base64') or file_info.get('base64')
            if b64:
                # Provide file metadata together with base64 bytes. Many APIs expect
                # a named/mime annotated file payload rather than a raw base64 string.
                file_payload = {
                    'type': 'file',
                    'name': file_info.get('name'),
                    'mimetype': file_info.get('type') or file_info.get('mimetype') or 'application/octet-stream',
                    'data': b64,
                    'size': file_info.get('size', None)
                }

                file_message = {
                    'role': 'user',
                    # Short human prompt to indicate what this file is
                    'content': f"Please analyze the attached file: {file_info.get('name')}",
                    # Attach file payload in a structured array so downstream code
                    # or the API can locate file objects reliably.
                    'files': [file_payload]
                }
                messages.append(file_message)
                _logger.info("Added file to upload: %s (size=%s bytes, mime=%s)", file_info.get('name'), file_info.get('size'), file_payload['mimetype'])

        # Add the main analysis request
        analysis_prompt = self._build_analysis_prompt(check_data)
        messages.append({
            "role": "user",
            "content": analysis_prompt
        })

        _logger.info("Built %s messages for API call, uploading %s files", 
                    len(messages), len(supported_files))
        return messages