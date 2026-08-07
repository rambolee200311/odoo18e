import csv, io, json
from odoo import api, fields, models, _

class InvoiceParser(models.AbstractModel):
    _name = 'tlmp.invoice.parser'
    _description = 'Invoice Parser — CSV/XLSX/Encoding'

    @api.model
    def detect_encoding(self, raw_bytes):
        encodings = ['utf-8', 'gbk', 'iso-8859-1']
        for enc in encodings:
            try:
                raw_bytes.decode(enc)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
        return 'utf-8'

    @api.model
    def parse_csv(self, raw_bytes, encoding='auto', delimiter=','):
        if encoding == 'auto':
            encoding = self.detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding)
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = []
        for row in reader:
            rows.append(row)
        return rows, encoding

    @api.model
    def parse_xlsx(self, raw_bytes):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True)
            ws = wb.active
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([str(c) if c is not None else '' for c in row])
            return rows
        except ImportError:
            raise models.ValidationError(_(
                'openpyxl not available for .xlsx parsing'))
