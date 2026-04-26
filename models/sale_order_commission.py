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

    # Campo para permitir confirmar sin mecánico (opcional, según tu lógica de negocio)
    allow_no_mechanic = fields.Boolean(
        string="Permitir sin mecánico",
        help="Permite confirmar la orden sin asignar mecánico aún. El mecánico se podrá asignar después."
    )

    # Campo para detectar si falta mecánico en líneas de servicio (para aviso o bloqueo)
    has_missing_mechanic = fields.Boolean(
        compute="_compute_has_missing_mechanic",
        store=True
    )

    allow_without_mechanic = fields.Boolean(
        string="Permitir sin mecánico",
        help="Permite confirmar la orden sin asignar mecánico. Se deberá asignar después."
    )
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

    def action_assign_mechanic_after_confirm(self):
        self.ensure_one()

        # Registrar en chatter
        self.message_post(
            body=f"Se abrió el asistente para asignar mecánico por {self.env.user.name}"
        )

        return self.action_open_set_mechanic_wizard()

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

            # Si NO permite sin mecánico → validar
            if not order.allow_without_mechanic:

                lines_without_mechanic = order.order_line.filtered(
                    lambda l: l.product_id.type == 'service' and not l.mechanic_id
                )

                if lines_without_mechanic:
                    raise ValidationError(
                        "No puedes confirmar sin asignar mecánico a las líneas de servicio.\n\n"
                        "Activa 'Permitir sin mecánico' si deseas continuar."
                    )

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

    def _recompute_mechanic_commissions(self):
        """
        Fuerza la regeneración de comisiones para este pedido.
        """
        self.ensure_one()

        wizard = self.env['mechanic.commission.wizard'].create({
            'employee_selection': 'all',
            'date_from': self.date_order.date(),
            'date_to': self.date_order.date(),
        })

        wizard._onchange_build_lines()

    @api.depends('order_line.mechanic_id', 'order_line.display_mechanic_fields', 'allow_no_mechanic')
    def _compute_missing_mechanic(self):
        for order in self:
            missing = any(
                getattr(l, 'display_mechanic_fields', False)
                and not getattr(l, 'mechanic_id', False)
                for l in order.order_line
            )
            order.has_missing_mechanic = bool(order.allow_no_mechanic and missing)


    @api.depends('order_line.mechanic_id')
    def _compute_has_missing_mechanic(self):
        for order in self:
            order.has_missing_mechanic = any(
                l.product_id.type == 'service' and not l.mechanic_id
                for l in order.order_line
            )