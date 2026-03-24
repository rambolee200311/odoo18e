from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WorldDepotPortNode(models.Model):
    _name = "world.depot.port.node"
    _description = "Port And Terminal"
    _parent_name = "parent_id"
    _parent_store = True
    _order = "id desc"

    name = fields.Char(string="Name", required=True, index=True, copy=False)
    node_type = fields.Selection([("port", "Port"), ("terminal", "Terminal")], string="Node Type", required=True, default="port", index=True)
    country_id = fields.Many2one("res.country", string="Country", required=True, index=True)
    parent_id = fields.Many2one("world.depot.port.node", string="Parent Node", index=True)
    parent_path = fields.Char(index=True, copy=False)
    child_lines = fields.One2many("world.depot.port.node", "parent_id", string="Child Nodes")
    active = fields.Boolean(string="Active", default=True, index=True)

    terminal_code = fields.Char(string='Code', required=True)
    terminal_address = fields.Char(string='Address')
    address = fields.Many2one('res.partner', string='Address')
    street = fields.Char(string='Street', related='address.street', readonly=True)
    zip = fields.Char(string='Zip', related='address.zip', readonly=True)
    city = fields.Char(string='City', related='address.city', readonly=True)
    state = fields.Char(string='State', related='address.state_id.name', readonly=True)

    phone = fields.Char(string='Phone', related='address.phone', readonly=True)
    mobile = fields.Char(string='Mobile', related='address.mobile', readonly=True)

    remark = fields.Text(string="Remark")

    @api.constrains("parent_id")
    def checkParentLoop(self):
        for rec in self:
            if rec.parent_id and rec.parent_id.id == rec.id:
                raise ValidationError(_("Parent node cannot be itself."))
            if not rec._check_recursion():
                raise ValidationError(_("Hierarchy recursion is not allowed."))

    @api.constrains("node_type", "parent_id", "child_lines")
    def checkNodeTypeRules(self):
        for rec in self:
            # if rec.node_type == "terminal" and not rec.parent_id:
            #     raise ValidationError(_("Terminal must be under a port node."))
            # if rec.node_type == "terminal" and rec.parent_id and rec.parent_id.node_type != "port":
            #     raise ValidationError(_("Terminal parent must be a port node."))
            if rec.node_type == "terminal" and rec.child_lines:
                raise ValidationError(_("Terminal node cannot have child nodes."))
            if rec.node_type == "port" and rec.parent_id:
                raise ValidationError(_("Port node cannot only be under another port node."))

