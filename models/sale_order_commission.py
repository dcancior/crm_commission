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
    def _onchange_mechanic_global_warning(self):
        """No mostrar advertencia cuando la cotización está en borrador."""
        for order in self:
            if order.state == 'draft':
                return {}
        return {}

    # -------------------------------------------------------------------------
    # Bloqueo SOLO al confirmar:
    # - Requiere mecánico para líneas de servicio "pintadas"
    # - EXCEPTO si el producto comienza con 'PAQ'
    # -------------------------------------------------------------------------
    def action_confirm(self):
        for order in self:
            lines = order.order_line.filtered(
                lambda l:
                    # Debe aplicar la lógica de mecánico (tu flag de servicio)
                    getattr(l, 'display_mechanic_fields', False)
                    # Pero NO si es un producto "PAQ*"
                    and not self._is_paq_line(l)
                    # Y además falta el mecánico real (o es placeholder)
                    and (
                        not getattr(l, 'mechanic_id', False)
                        or getattr(l, 'mechanic_is_placeholder', False)
                    )
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



    @api.onchange('order_line')
    def _onchange_order_line_propagate_mechanic(self):
        """
        Propaga el mecánico seleccionado en una línea de servicio
        a las demás líneas de servicio del pedido.
        """
        for order in self:
            # Buscar un mecánico "fuente"
            source_line = next(
                (
                    line for line in order.order_line
                    if line.mechanic_id
                    and line.display_mechanic_fields
                    and not line.mechanic_exempt
                    and not line.mechanic_is_placeholder
                ),
                None
            )

            if not source_line:
                return

            mechanic = source_line.mechanic_id

            for line in order.order_line:
                if not line.display_mechanic_fields:
                    continue
                if line.mechanic_exempt:
                    continue
                if line.mechanic_id and not line.mechanic_is_placeholder:
                    continue

                line.mechanic_id = mechanic