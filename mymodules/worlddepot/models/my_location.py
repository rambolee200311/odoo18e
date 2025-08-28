from odoo import api, fields, models, _


class StockLocation(models.Model):
    _inherit = "stock.location"

    from odoo import api, fields, models, _

    class StockLocation(models.Model):
        _inherit = "stock.location"

        @api.model
        def cron_auto_generate_locations(self):
            """
            Cron job to automatically generate locations based on the configured rules.
            This method can be scheduled to run periodically.
            """
            # Fixed configuration values
            parent_location_name = 'LOODS10'
            parent_complete_name = 'SPN/Stock/LOODS10'

            # Find parent location
            parent_location = self.search([('complete_name', '=', parent_complete_name)], limit=1)
            if not parent_location:
                return  # Exit if parent location doesn't exist

            # Generate first level locations (01)
            for i in range(1, 41):  # Only creates location "01"
                loc_name = f"{i:02d}"  # Format as 2-digit string (01)
                # Build complete name without storing it permanently
                level1_complete_name = f"{parent_complete_name}/{loc_name}"

                # Find or create first-level location
                level1_location = self.search([
                    ('name', '=', loc_name),
                    ('location_id', '=', parent_location.id)
                ], limit=1)

                if not level1_location:
                    level1_location = self.create({
                        'name': loc_name,
                        'location_id': parent_location.id,
                        'barcode': f"SPN-{parent_location_name}-{loc_name}",
                        'usage': 'internal',
                        'active': True,
                    })

                # Generate second level locations (01/01 and 01/02)
                for j in range(1, 16):  # Creates locations "01" and "02"
                    child_name = f"{j:02d}"  # Format as 2-digit string
                    # Build complete name dynamically
                    child_complete_name = f"{level1_complete_name}/{child_name}"

                    # Check if child exists
                    if not self.search([
                        ('name', '=', child_name),
                        ('location_id', '=', level1_location.id)
                    ], limit=1):
                        self.create({
                            'name': child_name,
                            'location_id': level1_location.id,
                            'barcode': f"SPN-{parent_location_name}-{loc_name}-{child_name}",
                            'usage': 'internal',
                            'active': True,
                        })

        @api.model
        def cron_auto_generate_locations_bond(self):
            """
            Cron job to automatically generate locations based on the configured rules.
            This method can be scheduled to run periodically.
            """
            # Fixed configuration values
            parent_location_name = 'LOODS14'
            parent_complete_name = 'SPN/Stock/LOODS14'

            # Find parent location
            parent_location = self.search([('complete_name', '=', parent_complete_name)], limit=1)
            if not parent_location:
                return  # Exit if parent location doesn't exist

            # Generate first level locations (01)
            for i in range(37, 73):  # Only creates location "01"
                loc_name = f"{i:02d}"  # Format as 2-digit string (01)
                # Build complete name without storing it permanently
                level1_complete_name = f"{parent_complete_name}/{loc_name}"

                # Find or create first-level location
                level1_location = self.search([
                    ('name', '=', loc_name),
                    ('location_id', '=', parent_location.id)
                ], limit=1)

                if not level1_location:
                    level1_location = self.create({
                        'name': loc_name,
                        'location_id': parent_location.id,
                        'barcode': f"SPN-{parent_location_name}-{loc_name}",
                        'usage': 'internal',
                        'active': True,
                    })

