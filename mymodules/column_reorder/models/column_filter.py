# -*- coding: utf-8 -*-
from odoo import models, api

class ColumnFilterFieldInfo(models.Model):
    _name = 'column.filter.field.info'
    _description = 'Column Filter Field Information Provider'
    _auto = False  # Not a real table, just a service model

    @api.model
    def get_field_info_batch(self, model_name, field_names):
        """Get field metadata for multiple fields at once.
        
        Returns a dict of field_name -> {type, string, selection, relation, searchable}
        """
        result = {}
        try:
            model = self.env[model_name]
            for fname in field_names:
                if fname in model._fields:
                    field = model._fields[fname]
                    info = {
                        'type': field.type,
                        'string': field.string,
                        'searchable': True,
                    }
                    # Include selection options
                    if field.type == 'selection' and hasattr(field, 'selection'):
                        if callable(field.selection):
                            try:
                                info['selection'] = field.selection(self.env)
                            except:
                                info['selection'] = []
                        elif field.selection:
                            info['selection'] = list(field.selection)
                        else:
                            info['selection'] = []
                    # Include relation model for relational fields
                    if field.type in ('many2one', 'many2many', 'one2many'):
                        info['relation'] = field.comodel_name
                    result[fname] = info
                else:
                    result[fname] = {'searchable': False}
        except Exception:
            pass
        return result

    @api.model
    def get_field_info(self, model_name, field_name):
        """Get field metadata for a single field."""
        result = self.get_field_info_batch(model_name, [field_name])
        return result.get(field_name, {'searchable': False})