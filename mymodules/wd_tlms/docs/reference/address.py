from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class Address(models.Model):
    _name = 'ptlmp.transport.address'
    _description = 'tlmp.transport.address'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "address_code"

    address_code = fields.Char(string='Code', readonly=True)
    street = fields.Char(string='Street', tracking=True)
    latlng = fields.Char(string='LatLng', help='Latitude and Longitude, separated by a comma, like 52.5200,13.4050', tracking=True)
    postcode = fields.Char(string='Zip')
    city = fields.Char(string='City')
    state = fields.Many2one("res.country.state", string='State', )
    country = fields.Many2one("res.country", string='Country')
    latitude = fields.Float(string='Latitude')
    longitude = fields.Float(string='Longitude')
    phone = fields.Char(string='Phone')
    mobile = fields.Char(string='Mobile')
    is_warehouse = fields.Boolean(string='Is Warehouse', default=False, tracking=True)
    warehouse = fields.Many2one("stock.warehouse", string='Warehouse', tracking=True)
    is_terminal = fields.Boolean(string='Is Terminal', default=False, tracking=True)
    terminal = fields.Many2one("ptlmp.transport.terminal", string='Terminal', tracking=True)
    company_name = fields.Char(string='Company Name')
    timeslot = fields.Char('Timeslot')
    remark = fields.Text(string='Remark', tracking=True)

    @api.constrains('address_code')
    def _check_address(self):
        for record in self:
            domain = [
                ('address_code', '=', record.address_code),
                ('id', '!=', record.id)
            ]
            existing_address = self.search(domain)
            if existing_address:
                raise ValidationError("The address already exists in the system.")

    @api.model
    def create(self, vals):
        address = []
        address_code = ''
        # 拼接地址部分
        if vals.get('street'):
            address.append(vals['street'])
        if vals.get('postcode'):
            address.append(vals['postcode'])
        if vals.get('country'):
            country = self.env['res.country'].browse(vals['country'])
            address.append(country.name)
        # 生成 address_code
        address_code = ', '.join(address) if address else ''
        if vals['is_warehouse'] and vals['warehouse']:
            warehouse = self.env['stock.warehouse'].browse(vals['warehouse'])
            address_code = f"Warehouse: {warehouse.name} - {address_code}"
        elif vals['is_terminal'] and vals['terminal']:
            terminal = self.env['tlmp.transport.terminal'].browse(vals['terminal'])
            address_code = f"Terminal: {terminal.terminal_name} - {address_code}"
        else:
            if vals.get('company_name'):
                company_name = vals['company_name']
                address_code = f"Company: {company_name} - {address_code}"
            else:
                address_code = f"Address: {address_code}"

        vals['address_code'] = address_code
        return super(Address, self).create(vals)

    def write(self, vals):
        for record in self:
            if record.is_warehouse or record.is_terminal:
                raise ValidationError("You can not edit addresses that are marked as a warehouse or terminal.")

            address = []
            # Fetch existing or updated values
            street = vals.get('street', record.street)
            postcode = vals.get('postcode', record.postcode)
            country_id = vals.get('country', record.country.id)
            company_name = vals.get('company_name', record.company_name)

            # Build the address parts
            if street:
                address.append(street)
            if postcode:
                address.append(postcode)
            if country_id:
                country = self.env['res.country'].browse(country_id)
                address.append(country.name)

            # Generate address_code
            address_code = ', '.join(address) if address else ''
            if company_name:
                address_code = f"Company: {company_name} - {address_code}"
            else:
                address_code = f"Address: {address_code}"

            vals['address_code'] = address_code

        return super(Address, self).write(vals)

    @api.onchange('warehouse')
    def _onchange_warehouse(self):
        for record in self:
            if record.warehouse:
                record.is_warehouse = True
                record.is_terminal = False
                record.street = record.warehouse.partner_id.street
                record.postcode = record.warehouse.partner_id.zip
                record.city = record.warehouse.partner_id.city
                record.state = record.warehouse.partner_id.state_id.id if record.warehouse.partner_id.state_id else False
                record.country = record.warehouse.partner_id.country_id.id
                record.phone = record.warehouse.partner_id.phone
                record.mobile = record.warehouse.partner_id.mobile
            else:
                record.is_warehouse = False

    @api.onchange('terminal')
    def _onchange_terminal(self):
        for record in self:
            if record.terminal:
                record.is_terminal = True
                record.is_warehouse = False
                record.street = record.terminal.address.street
                record.postcode = record.terminal.address.zip
                record.city = record.terminal.address.city
                record.state = record.terminal.address.state_id.id if record.terminal.address.state_id else False
                record.country = record.terminal.address.country_id.id if record.terminal.address.country_id else False
                record.phone = record.terminal.address.phone
                record.mobile = record.terminal.address.mobile
            else:
                record.is_terminal = False

    def get_address_form_warehouse(self):
        """从仓库同步地址（修复版）"""
        # 1. 删除所有标记为仓库的地址
        self.search([('is_warehouse', '=', True)]).unlink()

        # 2. 遍历所有有 partner_id 的仓库
        warehouses = self.env['stock.warehouse'].search([('partner_id', '!=', False)])
        for wh in warehouses:
            # 3. 确保 partner_id 存在且必要字段有效
            # if not wh.partner_id.country_id or not wh.partner_id.street:
            #     _logger.warning("Skipping warehouse %s: Incomplete address.", wh.name)
            #     continue

            # 4. 创建地址记录
            if wh.partner_id.country_id and wh.partner_id.street:
                self.create({
                    'street': wh.partner_id.street,
                    'postcode': wh.partner_id.zip,
                    'city': wh.partner_id.city,
                    'state': wh.partner_id.state_id.id if wh.partner_id.state_id else False,
                    'country': wh.partner_id.country_id.id,
                    'phone': wh.partner_id.phone,
                    'mobile': wh.partner_id.mobile,
                    'is_warehouse': True,
                    'warehouse': wh.id,
                    'is_terminal': False,
                    'terminal': False,
                })

    def get_address_form_terminal(self):
        """从终端同步地址（修复版）"""
        # 1. 删除所有标记为终端的地址
        self.search([('is_terminal', '=', True)]).unlink()

        # 2. 遍历所有有 address 的终端
        terminals = self.env['tlmp.transport.terminal'].search([('address', '!=', False)])
        for terminal in terminals:
            # 3. 确保终端地址有效
            # if not terminal.address.country_id or not terminal.address.street:
            #     _logger.warning("Skipping terminal %s: Incomplete address.", terminal.name)
            #    continue

            # 4. 创建地址记录
            if terminal.address.country_id and terminal.address.street:
                self.create({
                    'street': terminal.address.street,
                    'postcode': terminal.address.zip,
                    'city': terminal.address.city,
                    'state': terminal.address.state_id.id if terminal.address.state_id else False,
                    'country': terminal.address.country_id.id,
                    'phone': terminal.address.phone,
                    'mobile': terminal.address.mobile,
                    'is_terminal': True,
                    'terminal': terminal.id,
                    'is_warehouse': False,
                    'warehouse': False,
                })

    def button_fetch_google_maps_details(self):
        self.ensure_one()
        if not self.street and not self.latlng:
            raise UserError("Please enter a street or latlng to fetch details.")

        # Build address query from existing fields

        """
        if self.city:
            address_parts.append(self.city)
        if self.postcode:
            address_parts.append(self.postcode)
        if self.country:
            address_parts.append(self.country.name)
        """


        # Get Google Maps API key
        api_key = self.env['ir.config_parameter'].sudo().get_param('base_geolocalize.google_map_api_key')
        if not api_key:
            raise UserError("Google Maps API key not configured. Contact your administrator.")

        # API request
        try:
            response = None
            if self.latlng:
                lat, lng = self.latlng.split(',')
                address_query = f"{lat},{lng}"
                response = requests.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={'latlng': address_query, 'key': api_key},
                    timeout=10
                )
            if self.street:
                address_query = self.street
                response = requests.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={'address': address_query, 'key': api_key},
                    timeout=10
                )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            _logger.error("API Error: %s", str(e))
            raise UserError("Failed to connect to Google Maps API")

        if data.get('status') != 'OK':
            raise UserError("Address not found or API error")

        # Parse first result
        result = data['results'][0]
        components = {c['types'][0]: c for c in result['address_components']}

        # Update address fields
        if not self.street:
            self.street = components.get('route', {}).get('long_name', self.street)
        self.postcode = components.get('postal_code', {}).get('long_name', self.postcode)
        self.city = components.get('locality', {}).get('long_name', self.city) or \
                    components.get('administrative_area_level_2', {}).get('long_name', self.city)
        self.latitude = result['geometry']['location'].get('lat', self.latitude)
        self.longitude = result['geometry']['location'].get('lng', self.longitude)
        if not self.latlng:
            self.latlng = f"{self.latitude},{self.longitude}"

        # Update country
        if 'country' in components:
            country = self.env['res.country'].search([
                ('code', '=', components['country']['short_name'])
            ], limit=1)
            if country:
                self.country = country.id

        # Update state
        if 'administrative_area_level_1' in components and self.country:
            state = self.env['res.country.state'].search([
                ('name', 'ilike', components['administrative_area_level_1']['long_name']),
                ('country_id', '=', self.country.id)
            ], limit=1)
            if state:
                self.state = state.id

        return True