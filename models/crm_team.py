from odoo import models, fields

class CrmTeam(models.Model):
    _inherit = 'crm.team'

    commission_percent = fields.Float(
        string='Comisión (%)',
        help='Porcentaje de comisión para los vendedores de este equipo'
    )