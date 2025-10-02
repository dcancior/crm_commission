# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import api, models, _
from odoo.exceptions import ValidationError, UserError

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

    def action_open_set_mechanic_wizard(self):  # Acción para abrir el wizard  # noqa: E265
        self.ensure_one()  # Garantiza un solo registro  # noqa: E265
        return {  # Devuelve acción ventana modal  # noqa: E265
            'type': 'ir.actions.act_window',  # Tipo de acción  # noqa: E265
            'name': _('Asignar mecánico a líneas'),  # Título de la ventana  # noqa: E265
            'res_model': 'sale.order.set.mechanic.wizard',  # Modelo del wizard  # noqa: E265
            'view_mode': 'form',  # Modo formulario  # noqa: E265
            'target': 'new',  # Abrir en modal  # noqa: E265
            'context': {  # Contexto por defecto  # noqa: E265
                'default_order_id': self.id,  # Pedido actual  # noqa: E265
                'default_company_id': self.company_id.id,  # Compañía del pedido  # noqa: E265
            },
        }  # noqa: E265

    mechanic_warning_ack = fields.Boolean(  # Flag para no repetir el aviso en el pedido
        default=False,  # Valor por defecto
        copy=False,  # No copiar al duplicar
    )  # Fin mechanic_warning_ack

    @api.onchange(  # Onchange a nivel pedido para avisar una sola vez
        "order_line.mechanic_id",
        "order_line.product_id",
        "order_line.display_mechanic_fields",
        "order_line.mechanic_is_placeholder",
    )
    def _onchange_mechanic_global_warning(self):  # Método onchange global
        for order in self:  # Itera pedidos
            if order.mechanic_warning_ack:  # Si ya se mostró, no repetir
                continue  # Salta a siguiente
            # Líneas de servicio del pedido
            service_lines = order.order_line.filtered(lambda l: l.product_id and l.product_id.type == "service")  # Solo servicios
            if not service_lines:  # Si no hay servicios, no avisar
                continue  # Salta
            # ¿Alguna línea tiene mecánico REAL? (no placeholder)
            any_real_mechanic = any(l.mechanic_id and not l.mechanic_is_placeholder for l in service_lines)  # True si hay alguno real
            # ¿Quedan pendientes? (sin mecánico o con placeholder)
            any_pending = any((not l.mechanic_id) or l.mechanic_is_placeholder for l in service_lines)  # True si faltan reales
            # Avisar solo si NO hay ninguno real y sí hay pendientes
            if (not any_real_mechanic) and any_pending:  # Condición de aviso único
                order.mechanic_warning_ack = True  # Marca como avisado
                return {  # Retorna warning no bloqueante
                    "warning": {
                        "title": _("Falta seleccionar el mecánico"),  # Título
                        "message": _(
                            "Tienes líneas de SERVICIO sin mecánico real. "
                            "Asigna al menos UN mecánico. "
                            "Este aviso se mostrará solo una vez."
                        ),  # Mensaje
                    }
                }  # Fin return
        return {}  # No hay aviso

    def action_confirm(self):
        for order in self:
            lines = order._get_lines_missing_mechanic()
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