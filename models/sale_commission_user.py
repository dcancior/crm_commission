from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    commission_percent = fields.Float(
        string='Porcentaje Comisión',
        help='Porcentaje de comisión para este vendedor'
    )