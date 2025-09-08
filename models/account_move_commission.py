# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    commission_percent = fields.Float(
        string='Porcentaje Comisión (%)',
        compute='_compute_commission_data',
        store=True
    )
    commission_amount = fields.Monetary(
        string='Monto Comisión',
        compute='_compute_commission_data',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('invoice_user_id', 'amount_untaxed')
    def _compute_commission_data(self):
        for move in self:
            percent = move.invoice_user_id.sale_team_id.commission_percent if move.invoice_user_id and move.invoice_user_id.sale_team_id else 0.0
            move.commission_percent = percent
            move.commission_amount = move.amount_untaxed * (percent / 100.0)