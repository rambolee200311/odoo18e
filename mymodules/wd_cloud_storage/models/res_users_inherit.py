from odoo import models


class ResUsersInherit(models.Model):
    _inherit = 'res.users'

    def action_prepare_cloud_space(self):
        config_model = self.env['s3.config']
        config_model.get_current_config()
        node_model = self.env['s3.node']
        prepared_count = 0
        for rec in self:
            node_model.ensure_private_node(user_id=rec.id)
            prepared_count += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'Success',
                'message': f'Prepared cloud space for {prepared_count} user(s).',
                'sticky': False,
            },
        }