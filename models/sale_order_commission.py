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

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    seller_name = fields.Char(string='Vendedor', compute='_compute_seller_commission', store=True)
    commission_percent = fields.Float(string='Porcentaje Comisión (%)', compute='_compute_seller_commission', store=True)
    commission_amount = fields.Monetary(string='Monto Comisión', compute='_compute_seller_commission', store=True, currency_field='currency_id')

    @api.depends('user_id', 'amount_untaxed')
    def _compute_seller_commission(self):
        for order in self:
            user = order.user_id
            order.seller_name = user.name if user else ''
            # Puedes tomar el porcentaje del usuario o del equipo
            percent = user.sale_team_id.commission_percent if user and user.sale_team_id else 0.0
            order.commission_percent = percent
            order.commission_amount = order.amount_untaxed * (percent / 100.0)