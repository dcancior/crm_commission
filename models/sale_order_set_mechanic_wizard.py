# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import models, fields, api, _  # importa _ por si lo necesitas en mensajes  # noqa: E265

# -------------------------------------------------------------------
# Extensión mínima de sale.order SOLO para abrir el wizard
# (El aviso "una sola vez" y cualquier validación déjalos en sale_extend.py)
# -------------------------------------------------------------------
class SaleOrder(models.Model):  # noqa: E265
    _inherit = 'sale.order'  # noqa: E265

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

    def _action_confirm(self):
        """Asegura que warehouse_id sea un recordset antes de confirmar"""
        for order in self:
            if isinstance(order.warehouse_id, int):
                order.warehouse_id = self.env['stock.warehouse'].browse(order.warehouse_id)
        return super()._action_confirm()

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


# -------------------------------------------------------------------
# WIZARD: Asignar mecánico masivo a líneas de servicio del pedido
# -------------------------------------------------------------------
class SaleOrderSetMechanicWizard(models.TransientModel):  # noqa: E265
    _name = 'sale.order.set.mechanic.wizard'  # Nombre técnico  # noqa: E265
    _description = 'Asignar mecánico a líneas de servicio del pedido'  # Descripción  # noqa: E265

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')  # Pedido objetivo  # noqa: E265
    company_id = fields.Many2one('res.company', readonly=True)  # Compañía (para dominio de empleado)  # noqa: E265

    mechanic_id = fields.Many2one(  # Mecánico que se aplicará a las líneas  # noqa: E265
        'hr.employee',
        string='Mecánico',
        required=True,
        domain="[('active','=',True), ('job_id.name', 'ilike', 'mecán'), '|', ('company_id','=',False), ('company_id','=', company_id)]",  # noqa: E265
        help="Empleado que se asignará como mecánico a las líneas de servicio.",  # noqa: E265
    )  # noqa: E265

    only_empty = fields.Boolean(  # Solo líneas sin mecánico  # noqa: E265
        string='Solo líneas sin mecánico',
        default=True,
        help="Si está activo, solo actualizará las líneas de servicio que no tengan mecánico asignado.",  # noqa: E265
    )  # noqa: E265

    affected_count = fields.Integer(  # Conteo previo de líneas afectadas  # noqa: E265
        string='Líneas afectadas',
        compute='_compute_preview',
        help="Cantidad de líneas de servicio que se actualizarán con el mecánico seleccionado.",  # noqa: E265
    )  # noqa: E265

    # -------------------------------
    # Helpers del wizard
    # -------------------------------
    def _get_target_lines(self):  # Obtiene las líneas objetivo según filtros  # noqa: E265
        self.ensure_one()  # Un solo wizard  # noqa: E265
        lines = self.order_id.order_line.filtered(lambda l: l.product_id and l.product_id.type == 'service')  # Solo servicios  # noqa: E265
        if self.only_empty:  # Si solo vacías  # noqa: E265
            lines = lines.filtered(lambda l: not l.mechanic_id)  # Sin mecánico  # noqa: E265
        return lines  # Retorna recordset  # noqa: E265

    @api.depends('order_id', 'only_empty')  # Recalcula al cambiar pedido o flag  # noqa: E265
    def _compute_preview(self):  # Calcula affected_count  # noqa: E265
        for w in self:  # Itera wizards  # noqa: E265
            w.affected_count = len(w._get_target_lines()) if w.order_id else 0  # Conteo  # noqa: E265

    def action_apply(self):  # Aplica el mecánico a las líneas objetivo  # noqa: E265
        self.ensure_one()  # Un solo wizard  # noqa: E265
        lines = self._get_target_lines()  # Obtiene líneas  # noqa: E265
        lines.write({'mechanic_id': self.mechanic_id.id})  # Escribe mecánico  # noqa: E265
        return {'type': 'ir.actions.act_window_close'}  # Cierra modal  # noqa: E265
