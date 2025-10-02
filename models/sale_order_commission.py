# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # -------------------------------------------------------------------------
    # Campos de comisión (ejemplo simple)
    # -------------------------------------------------------------------------
    seller_name = fields.Char(
        string='Vendedor',
        compute='_compute_seller_commission',
        store=True,
    )
    commission_percent = fields.Float(
        string='Porcentaje Comisión (%)',
        compute='_compute_seller_commission',
        store=True,
        help="Porcentaje de comisión aplicado al pedido (ej. tomado del equipo de ventas).",
    )
    commission_amount = fields.Monetary(
        string='Monto Comisión',
        compute='_compute_seller_commission',
        store=True,
        currency_field='currency_id',
    )

    @api.depends(
        'user_id',
        'amount_untaxed',
        'user_id.sale_team_id',
        'user_id.sale_team_id.commission_percent',
    )
    def _compute_seller_commission(self):
        """Ejemplo: toma nombre del vendedor y porcentaje del equipo de ventas."""
        for order in self:
            user = order.user_id
            order.seller_name = user.name if user else ''
            percent = 0.0
            try:
                percent = user.sale_team_id.commission_percent if user and user.sale_team_id else 0.0
            except Exception:
                _logger.debug("El equipo de ventas no tiene 'commission_percent'; usando 0.0")
                percent = 0.0
            order.commission_percent = percent or 0.0
            order.commission_amount = (order.amount_untaxed or 0.0) * ((percent or 0.0) / 100.0)

    # -------------------------------------------------------------------------
    # Asistente para asignar mecánico (acción modal)
    # -------------------------------------------------------------------------
    def action_open_set_mechanic_wizard(self):
        """Abre un wizard para asignar mecánico a las líneas del pedido."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Asignar mecánico a líneas'),
            'res_model': 'sale.order.set.mechanic.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }

    # -------------------------------------------------------------------------
    # Helper: detectar si una línea está exenta por regla "PAQ*"
    # -------------------------------------------------------------------------
    @staticmethod
    def _is_paq_line(line):
        """
        Devuelve True si el nombre del producto de la línea comienza con 'PAQ',
        ignorando espacios y mayúsculas/minúsculas.
        """
        name = (
            (line.product_id.display_name or line.product_id.name or '')
            .strip()
            .upper()
        )
        return name.startswith('PAQ')

    # -------------------------------------------------------------------------
    # Aviso no bloqueante: DESACTIVADO en borrador (lo dejamos neutro)
    # -------------------------------------------------------------------------
    mechanic_warning_ack = fields.Boolean(
        string='Aviso de mecánico mostrado',
        default=False,
        copy=False,
    )

    @api.onchange('order_line')
    def _onchange_

    mechanic_exempt = fields.Boolean(
        string='Exento de mecánico',
        compute='_compute_mechanic_exempt',
        store=True,
    )

    @api.depends('product_id', 'product_id.name', 'product_id.display_name', 'display_mechanic_fields')
    def _compute_mechanic_exempt(self):
        for line in self:
            # Solo tiene sentido exentar si la línea “aplica” para mecánico
            if not getattr(line, 'display_mechanic_fields', False):
                line.mechanic_exempt = False
                continue
            name = (line.product_id.display_name or line.product_id.name or '').strip().upper()
            line.mechanic_exempt = name.startswith('PAQ')


    mechanic_exempt = fields.Boolean(
        string='Exento de mecánico',
        compute='_compute_mechanic_exempt',
        store=True,
    )

    @api.depends('product_id', 'product_id.name', 'product_id.display_name', 'display_mechanic_fields')
    def _compute_mechanic_exempt(self):
        for line in self:
            # Solo tiene sentido exentar si la línea “aplica” para mecánico
            if not getattr(line, 'display_mechanic_fields', False):
                line.mechanic_exempt = False
                continue
            name = (line.product_id.display_name or line.product_id.name or '').strip().upper()
            line.mechanic_exempt = name.startswith('PAQ')