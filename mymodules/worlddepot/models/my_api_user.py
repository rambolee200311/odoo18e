import logging
import uuid
from passlib.context import CryptContext
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class DepotAPIUser(models.Model):
    _name = 'world.depot.api.user'
    _description = 'API User Credentials'

    _crypt_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=14
    )

    user_id = fields.Many2one('res.users', string='Odoo User', required=True)
    api_key = fields.Char(
        string='API Key',
        help="Public identifier for API access"
    )
    hashed_secret = fields.Char(
        string='Hashed Secret',
        help="Securely stored API secret (bcrypt hash)"
    )
    active = fields.Boolean(string='Active', default=True)

    # Virtual field for form handling (write-only)
    secret = fields.Char(
        string='API Secret (Set Only)',
        compute='_compute_dummy',
        inverse='_set_secret',
        store=False,
        help="Set new API secret (write-only field)"
    )

    _sql_constraints = [
        ('api_key_uniq', 'unique(api_key)', 'API Key must be unique!'),
    ]

    @api.model
    def generate_api_key(self):
        """Generate a new unique API key (UUID)"""
        self.ensure_one()
        while True:
            new_key = str(uuid.uuid4())
            if not self.search([('api_key', '=', new_key)]):
                self.api_key = new_key
                break

    @api.depends()
    def _compute_dummy(self):
        """Dummy compute method for virtual field"""
        for rec in self:
            rec.secret = ""  # Never expose the actual secret

    def _set_secret(self):
        """Hash and store secret when set via virtual field"""
        for rec in self:
            if rec.secret:
                rec._validate_and_store_secret(rec.secret)

    def _validate_and_store_secret(self, secret):
        """Validate and hash the secret"""
        if len(secret) < 12:
            raise UserError(_("API secret must be at least 12 characters"))
        self.hashed_secret = self._crypt_context.hash(secret)

    @api.model
    def create(self, vals):
        """Handle API key generation and secret hashing during creation."""
        if 'api_key' not in vals or not vals.get('api_key'):
            vals['api_key'] = str(uuid.uuid4())
        secret = vals.pop('secret', None)
        record = super().create(vals)
        if secret:
            record._validate_and_store_secret(secret)
        return record

    def write(self, vals):
        """Handle secret updates during write"""
        if 'secret' in vals and vals['secret']:
            self._validate_and_store_secret(vals.pop('secret'))
        return super().write(vals)

    def verify_secret(self, secret):
        """Validate provided secret against stored hash"""
        self.ensure_one()
        if not self.hashed_secret or not secret:
            return False
        return self._crypt_context.verify(secret, self.hashed_secret)

    @api.constrains('hashed_secret')
    def _check_secret_strength(self):
        """Verify secret is properly hashed"""
        for rec in self:
            if not rec.hashed_secret or not rec.hashed_secret.startswith("$2b$"):
                raise ValidationError(_("Invalid secret storage format"))


class DepotAPIToken(models.Model):
    _name = 'world.depot.api.token'
    _description = 'API Access Tokens'

    user_id = fields.Many2one('res.users', string='User', required=True)
    token = fields.Char(string='Access Token', required=True, index=True)
    expires = fields.Datetime(string='Expiration', required=True)

    @api.model
    def _cron_clean_expired_tokens(self):
        """Remove expired tokens hourly"""
        expired = self.search([('expires', '<', fields.Datetime.now())])
        expired.unlink()
