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
    # Aviso no bloqueante: DESACTIVADO en borrador
    # (si no quieres el aviso nunca, devuelve {} sin más)
    # -------------------------------------------------------------------------
    mechanic_warning_ack = fields.Boolean(
        string='Aviso de mecánico mostrado',
        default=False,
        copy=False,
    )

    @api.onchange('order_line')
    def _onchange_mechanic_global_warning(self):
        """No mostrar advertencia cuando la cotización está en borrador."""
        for order in self:
            if order.state == 'draft':
                return {}
        # Si quisieras mantener el aviso en otros estados (p.ej. 'sent'),
        # puedes pegar aquí la lógica anterior. Por ahora, no mostramos nada.
        return {}

    # -------------------------------------------------------------------------
    # Bloqueo SOLO al confirmar: NO permite confirmar si hay líneas “pintadas”
    # (mismo criterio que la decoración-warning en la vista)
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for order in self:
            # Condición en-línea para que UI y validación estén sincronizadas
            lines = order.order_line.filtered(
                lambda l: getattr(l, 'display_mechanic_fields', False)
                and (not getattr(l, 'mechanic_id', False) or getattr(l, 'mechanic_is_placeholder', False))
            )
            if lines:
                details = "\n".join(
                    f"• {l.product_id.display_name or l.name} (línea {l.sequence or '-'})"
                    for l in lines
                )
                raise UserError(_(
                    "Antes de confirmar, selecciona un Mecánico en todas las líneas de servicio "
                    "resaltadas en naranja.\n\nFaltan en:\n%s"
                ) % details)

        return super().action_confirm()
