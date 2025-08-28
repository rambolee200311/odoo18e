import logging
import uuid
from passlib.context import CryptContext
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class DepotAPIUser(models.Model):
    _name = 'world.depot.api.user'
    _description = 'API User Credentials'

    # Security context for password hashing
    _crypt_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=14  # Appropriate security level
    )

    user_id = fields.Many2one('res.users', string='Odoo User', required=True)
    api_key = fields.Char(
        string='API Key',
        readonly=True,
        required=True,
        index=True,
        help="Public identifier for API access"
    )
    hashed_secret = fields.Char(
        string='Hashed Secret',
        required=True,
        help="Securely stored API secret (bcrypt hash)"
    )
    active = fields.Boolean(string='Active', default=True)

    # Virtual field for form handling (never stored)
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
    def generate_api_key(self):
        """Generate a new API key (GUID)"""
        for rec in self:
            if  not rec.api_key:
                rec.api_key = str(uuid.uuid4())

    @api.depends()
    def _compute_dummy(self):
        """Dummy compute method for virtual field"""
        for rec in self:
            rec.secret = ""  # Never show actual value

    def _set_secret(self):
        """Hash and store secret when set via virtual field"""
        for rec in self:
            if rec.secret:
                if len(rec.secret) < 12:
                    raise UserError(_("API secret must be at least 12 characters"))
                rec.hashed_secret = self._crypt_context.hash(rec.secret)

    @api.model
    def create(self, vals):
        """Handle secret hashing during creation"""
        # Extract the secret from vals if present (using pop to remove it from vals)
        secret = vals.pop('secret', None)
        # Create the record without the secret in vals
        record = super().create(vals)
        # If there was a secret provided, set it using the set_secret method
        if secret:
            record.set_secret(secret)
        return record

    def write(self, vals):
        """Handle secret updates"""
        if 'secret' in vals and vals['secret']:
            # Hash new secret
            if len(vals['secret']) < 12:
                raise ValidationError(_("API secret must be at least 12 characters"))
            vals['hashed_secret'] = self._crypt_context.hash(vals.pop('secret'))
        return super().write(vals)

    def set_secret(self, secret):
        """Set the secret for a single record (used in create and elsewhere)"""
        self.ensure_one()
        if len(secret) < 12:
            raise UserError(_("API secret must be at least 12 characters"))
        self.hashed_secret = self._crypt_context.hash(secret)

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
