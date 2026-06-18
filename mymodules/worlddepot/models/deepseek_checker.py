import logging
import requests
import json
import base64
import re
from odoo import api, models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class DeepSeekChecker(models.Model):
    _name = 'deepseek.checker'
    _description = 'DeepSeek Document Verification Service'

    @api.model
    def check_order_with_deepseek(self, order_json, attachments=None):
        """
        Main method to verify documents using DeepSeek API with file upload
        """
        try:
            _logger.info("Starting DeepSeek document verification with file upload")
            
            # Debug logging
            _logger.info("Order JSON type: %s", type(order_json))
            _logger.info("Attachments type: %s", type(attachments))
            if attachments:
                _logger.info("Attachments length: %s", len(attachments))
            
            # Safely process attachments
            safe_attachments = self._safe_process_attachments(attachments)
            _logger.info("Successfully processed %s attachments", len(safe_attachments))
            
            # Prepare check data with file upload support
            check_data = self._prepare_check_data(order_json, safe_attachments)
            
            # Call DeepSeek API with file upload
            api_response = self._call_deepseek_api_with_files(check_data)
            
            # Parse and return result
            return self._parse_api_response(api_response)
            
        except Exception as e:
            _logger.error("DeepSeek check failed: %s", str(e), exc_info=True)
            return self._create_error_response(str(e))

    def _safe_process_attachments(self, attachments):
        """
        Enhanced attachment processing with better file type detection
        """
        if not attachments:
            return []

        safe_attachments = []
        
        # If attachments is a single item (not a list), make it a list
        if not isinstance(attachments, list):
            attachments = [attachments]
        
        for i, item in enumerate(attachments):
            try:
                attachment_dict = self._convert_to_attachment_dict(item, i)
                if attachment_dict and attachment_dict.get('data'):
                    # Enhanced MIME type detection
                    attachment_dict = self._enhance_attachment_info(attachment_dict)
                    safe_attachments.append(attachment_dict)
                    _logger.debug("Successfully processed attachment %s: %s", i, attachment_dict.get('name'))
            except Exception as e:
                _logger.warning("Failed to process attachment %s: %s", i, str(e))
                # Create error entry for tracking
                safe_attachments.append({
                    'name': f'error_attachment_{i}',
                    'data': b'',
                    'type': 'application/octet-stream',
                    'error': str(e),
                    'category': 'error'
                })
        
        return safe_attachments

    def _enhance_attachment_info(self, attachment_dict):
        """Enhance attachment with better file type detection"""
        try:
            utils = self.env['deepseek.utils']
            file_data = attachment_dict.get('data', b'')
            filename = attachment_dict.get('name', '')
            
            # Use utility method for MIME type detection
            mime_type = utils.detect_mime_type(filename, file_data)
            attachment_dict['type'] = mime_type
            
            # Add file size info
            attachment_dict['size'] = len(file_data)
            
            # Categorize file type
            file_category = self._categorize_file_type(mime_type, filename)
            attachment_dict['category'] = file_category
            
            # Add support status
            attachment_dict['supported'] = self._is_file_supported(mime_type, len(file_data))
            
            return attachment_dict
        except Exception as e:
            _logger.error("Error enhancing attachment info: %s", str(e))
            attachment_dict['category'] = 'unknown'
            attachment_dict['supported'] = False
            return attachment_dict

    def _categorize_file_type(self, mime_type, filename):
        """Categorize files for better processing"""
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type in ['application/pdf']:
            return 'document'
        elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
            return 'word'
        elif mime_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
            return 'excel'
        elif mime_type in ['application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
            return 'powerpoint'
        elif mime_type.startswith('text/'):
            return 'text'
        elif mime_type in ['application/zip', 'application/x-rar-compressed']:
            return 'archive'
        else:
            return 'other'

    def _is_file_supported(self, mime_type, file_size):
        """Check if file type and size are supported by DeepSeek"""
        supported_types = [
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
        
        max_size = 10 * 1024 * 1024  # 10MB limit
        
        return mime_type in supported_types and file_size <= max_size and file_size > 0

    def _convert_to_attachment_dict(self, item, index):
        """
        Convert any attachment format to a standardized dictionary
        """
        if item is None:
            return None
            
        # If it's already a dictionary with the right structure
        if isinstance(item, dict):
            data = item.get('data') or item.get('datas', b'')
            return {
                'name': item.get('name', f'attachment_{index}'),
                'data': data,
                'type': item.get('type', item.get('mimetype', 'application/octet-stream'))
            }
        
        # If it's an Odoo record (like ir.attachment)
        elif hasattr(item, 'datas'):
            return {
                'name': getattr(item, 'name', f'attachment_{index}'),
                'data': getattr(item, 'datas', b''),
                'type': getattr(item, 'mimetype', 'application/octet-stream')
            }
        
        # Enhanced base64 detection
        elif isinstance(item, str):
            # Improved base64 detection
            if self._is_likely_base64(item):
                try:
                    decoded_data = base64.b64decode(item)
                    return {
                        'name': f'base64_attachment_{index}',
                        'data': decoded_data,
                        'type': 'application/octet-stream'
                    }
                except Exception:
                    pass
            return {
                'name': f'text_attachment_{index}',
                'data': item.encode('utf-8'),
                'type': 'text/plain'
            }
        
        elif isinstance(item, bytes):
            return {
                'name': f'bytes_attachment_{index}',
                'data': item,
                'type': 'application/octet-stream'
            }
        
        # Fallback: create minimal attachment
        return {
            'name': f'unknown_attachment_{index}',
            'data': b'',
            'type': 'application/octet-stream'
        }

    def _is_likely_base64(self, text):
        """Improved base64 detection"""
        if len(text) < 100:
            return False
            
        # Check for common base64 patterns
        base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        sample = text[:200]
        return all(c in base64_chars for c in sample)

    def _prepare_check_data(self, order_json, attachments):
        """Enhanced data preparation with file categorization"""
        # Process order data
        if isinstance(order_json, str):
            try:
                order_data = json.loads(order_json)
            except json.JSONDecodeError:
                order_data = {'raw_data': order_json}
        elif isinstance(order_json, dict):
            order_data = order_json
        else:
            order_data = {'raw_data': str(order_json)}

        # Enhanced attachment processing
        attachment_info = []
        supported_files = []
        
        for i, attachment in enumerate(attachments):
            content_info = self._get_attachment_content(attachment)
            file_info = {
                'index': i,
                'name': attachment.get('name', f'attachment_{i}'),
                'type': attachment.get('type', 'unknown'),
                'category': attachment.get('category', 'unknown'),
                'size': len(attachment.get('data', b'')),
                'content_excerpt': content_info.get('excerpt'),
                'content_base64': content_info.get('base64'),
                'content_type': content_info.get('content_type'),
                'extraction_status': content_info.get('status', 'unknown'),
                'supported': content_info.get('supported', False)
            }
            
            attachment_info.append(file_info)
            
            # Track supported files for upload
            if content_info.get('supported', False):
                supported_files.append(file_info)

        _logger.info("Prepared check data: %s total attachments, %s supported files", 
                    len(attachment_info), len(supported_files))

        return {
            'order_data': order_data,
            'attachments': attachment_info,
            'supported_files': supported_files,
            'total_attachments': len(attachment_info),
            'supported_count': len(supported_files)
        }

    def _get_attachment_content(self, attachment):
        """Enhanced content extraction with file upload support"""
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
                except Exception:
                    data_bytes = data.encode('utf-8')
            else:
                data_bytes = bytes(str(data), 'utf-8')

            # Check if file is supported for upload
            mime_type = attachment.get('type', '')
            file_size = len(data_bytes)
            
            is_supported = self._is_file_supported(mime_type, file_size)
            result['supported'] = is_supported

            if is_supported:
                # For supported files, include as base64
                result.update({
                    'base64': base64.b64encode(data_bytes).decode('ascii'),
                    'content_type': 'base64',
                    'status': 'ready_for_upload'
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
                    'status': 'unsupported_file'
                })

        except Exception as e:
            _logger.error("Attachment processing error: %s", str(e))
            result['status'] = f'error: {str(e)}'

        return result

    def _call_deepseek_api_with_files(self, check_data):
        """Call DeepSeek API with file upload support"""
        api_key = self.env['ir.config_parameter'].sudo().get_param('deepseek.api_key')
        if not api_key:
            raise UserError(_("DeepSeek API key not configured. Please set 'deepseek.api_key' in System Parameters."))

        api_base = self.env['ir.config_parameter'].sudo().get_param(
            'deepseek.api_base',
            'https://api.deepseek.com/v1'
        )

        # Prepare messages with file uploads
        messages = self._build_messages_with_files(check_data)

        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4000,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            _logger.info("Calling DeepSeek API with file upload...")
            _logger.info("Uploading %s supported files", len(check_data.get('supported_files', [])))
            
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code != 200:
                error_msg = f"API Error {response.status_code}: {response.text}"
                _logger.error(error_msg)
                raise UserError(_(error_msg))
                
            _logger.info("DeepSeek API call successful")
            return response.json()
            
        except requests.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            _logger.error(error_msg)
            raise UserError(_(error_msg))

    def _build_messages_with_files(self, check_data):
        """Build messages with file attachments"""
        order_data = check_data.get('order_data', {})
        supported_files = check_data.get('supported_files', [])
        
        # Format order data
        if isinstance(order_data, dict):
            order_display = json.dumps(order_data, indent=2, ensure_ascii=False)
        else:
            order_display = str(order_data)

        messages = [
            {
                "role": "system",
                "content": """You are a professional document verification specialist with file analysis capabilities.
                Analyze the provided order data and attached files carefully. 
                For images: Extract text using OCR and verify against order data.
                For documents: Check content consistency, dates, amounts, and signatures.
                For spreadsheets: Verify calculations and data consistency.
                For text files: Extract and validate key information.
                Focus on detecting discrepancies, fraud indicators, and data quality issues.
                Provide detailed analysis with confidence scores."""
            }
        ]

        # Add file attachments first
        for file_info in supported_files:
            if file_info.get('content_base64'):
                file_message = {
                    "role": "user",
                    "content": f"Please analyze this {file_info.get('category', 'file')}: {file_info['name']}",
                    "file": file_info['content_base64']
                }
                messages.append(file_message)
                _logger.debug("Added file to messages: %s", file_info['name'])

        # Add the main analysis request
        analysis_prompt = self._build_analysis_prompt(check_data)
        messages.append({
            "role": "user",
            "content": analysis_prompt
        })

        _logger.info("Built %s messages for API call", len(messages))
        return messages

    def _build_analysis_prompt(self, check_data):
        """Build the analysis prompt for file analysis"""
        order_data = check_data.get('order_data', {})
        attachments = check_data.get('attachments', [])
        supported_files = check_data.get('supported_files', [])
        
        attachment_lines = []
        for att in attachments:
            status_icon = "✅" if att.get('supported') else "❌"
            attachment_lines.append(f"{status_icon} {att.get('name', 'unknown')} ({att.get('type', 'unknown')}) - {att.get('extraction_status', 'unknown')}")

        return f"""
DOCUMENT VERIFICATION ANALYSIS WITH FILE UPLOAD

ORDER DATA TO VERIFY:
{json.dumps(order_data, indent=2, ensure_ascii=False) if isinstance(order_data, dict) else order_data}

FILES PROVIDED:
Total files: {len(attachments)} | Supported for analysis: {len(supported_files)}
{chr(10).join(attachment_lines) if attachment_lines else "No files provided"}

ANALYSIS REQUIREMENTS:
1. Analyze all uploaded files and extract relevant information
2. Cross-reference extracted data with order information
3. Verify consistency across all documents and images
4. Flag any discrepancies, potential fraud indicators, or data quality issues
5. Provide confidence scores for each verification step
6. Specify which file each piece of information came from

SPECIFIC FILE TYPE ANALYSIS:
- PDFs: Extract text, check formatting, verify signatures
- Images: OCR text extraction, quality assessment
- Spreadsheets: Data validation, formula checking
- Documents: Content consistency, formatting verification

EXPECTED OUTPUT FORMAT:
{{
    "verification_status": "pass|warning|fail",
    "confidence_score": 0.95,
    "file_analysis": {{
        "total_files_processed": {len(attachments)},
        "successfully_analyzed": {len(supported_files)},
        "analysis_summary": "Brief summary of file analysis"
    }},
    "verified_fields": {{
        "invoice_number": {{"status": "matched", "confidence": 0.95, "source": "document_ocr"}},
        "date": {{"status": "matched", "confidence": 0.90, "source": "multiple_sources"}},
        "amount": {{"status": "mismatched", "confidence": 0.85, "source": "spreadsheet_analysis"}},
        "supplier": {{"status": "matched", "confidence": 0.98, "source": "document_text"}}
    }},
    "issues_found": [
        {{
            "severity": "high|medium|low",
            "type": "data_discrepancy|fraud_indicator|quality_issue",
            "source_file": "filename.pdf",
            "message": "description_of_issue",
            "suggestion": "recommended_action"
        }}
    ],
    "summary": "Overall analysis summary here",
    "next_steps": ["action1", "action2"]
}}

IMPORTANT: Respond with valid JSON only. Base your analysis on the actual content of the uploaded files.
Specify the source file for each finding when possible.
"""

    def _parse_api_response(self, api_response):
        """Enhanced response parsing for file analysis results"""
        try:
            if not api_response or 'choices' not in api_response:
                return self._create_error_response("Invalid API response format")

            content = api_response['choices'][0]['message']['content']
            _logger.info("Raw API response received with file analysis")

            # Enhanced JSON extraction
            try:
                # Look for JSON pattern more robustly
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    result = json.loads(json_str)
                    _logger.debug("Successfully parsed JSON response")
                else:
                    # If no JSON found, create a basic result
                    _logger.warning("No JSON found in response, using fallback")
                    result = {
                        "verification_status": "unknown",
                        "summary": content[:1000],
                        "issues_found": [],
                        "file_analysis": {
                            "total_files_processed": 0,
                            "successfully_analyzed": 0,
                            "analysis_summary": "JSON parsing failed"
                        }
                    }
            except json.JSONDecodeError as e:
                _logger.warning("JSON parse error, using fallback: %s", str(e))
                result = {
                    "verification_status": "warning",
                    "summary": f"Analysis completed but format issues: {content[:1000]}",
                    "issues_found": [{
                        "severity": "medium",
                        "type": "response_format",
                        "message": "API response format was not valid JSON",
                        "suggestion": "Check API configuration"
                    }],
                    "file_analysis": {
                        "total_files_processed": 0,
                        "successfully_analyzed": 0,
                        "analysis_summary": "JSON parsing error"
                    }
                }

            # Enhanced response standardization
            standardized_result = {
                "status": result.get("verification_status", "unknown"),
                "confidence": float(result.get("confidence_score", 0)),
                "verified_fields": result.get("verified_fields", {}),
                "issues": result.get("issues_found", []),
                "summary": result.get("summary", "No summary provided"),
                "file_analysis": result.get("file_analysis", {
                    "total_files_processed": 0,
                    "successfully_analyzed": 0,
                    "analysis_summary": "No file analysis data"
                }),
                "next_steps": result.get("next_steps", []),
                "api_usage": api_response.get("usage", {}),
                "model": api_response.get("model", "unknown"),
                "success": True
            }

            # Log file analysis results
            file_analysis = standardized_result.get('file_analysis', {})
            _logger.info(
                "File analysis completed: %s/%s files successfully analyzed",
                file_analysis.get('successfully_analyzed', 0),
                file_analysis.get('total_files_processed', 0)
            )

            return standardized_result

        except Exception as e:
            _logger.error("Response parsing failed: %s", str(e))
            return self._create_error_response(f"Response parsing error: {str(e)}")

    def _create_error_response(self, error_message):
        """Create standardized error response"""
        return {
            "status": "error",
            "error": error_message,
            "success": False,
            "summary": f"Check failed: {error_message}",
            "issues": [{
                "severity": "high",
                "type": "system",
                "message": error_message,
                "suggestion": "Check system configuration and try again"
            }],
            "file_analysis": {
                "total_files_processed": 0,
                "successfully_analyzed": 0,
                "analysis_summary": "Error occurred"
            }
        }

    # Enhanced testing method with file upload
    @api.model
    def test_with_files(self, order_data, test_files=None):
        """
        Test method with file upload support
        """
        try:
            if test_files is None:
                test_files = []
                
            _logger.info("Testing DeepSeek with %s files", len(test_files))
            result = self.check_order_with_deepseek(order_data, test_files)
            return result
        except Exception as e:
            return self._create_error_response(f"Test with files failed: {str(e)}")

    # Method that accepts Odoo attachment records directly
    @api.model
    def check_with_attachments(self, order_data, attachment_records=None):
        """
        Special method for Odoo attachment records with file upload
        """
        try:
            processed_attachments = []
            
            if attachment_records:
                # Convert Odoo records to attachment dicts
                for attachment in attachment_records:
                    processed_attachments.append({
                        'name': attachment.name,
                        'data': attachment.datas,
                        'type': attachment.mimetype
                    })
            
            _logger.info("Processing %s attachment records", len(processed_attachments))
            return self.check_order_with_deepseek(order_data, processed_attachments)
            
        except Exception as e:
            return self._create_error_response(f"Attachment check failed: {str(e)}")