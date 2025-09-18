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

    def action_open_set_mechanic_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar mecánico a líneas',
            'res_model': 'sale.order.set.mechanic.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }

    # Flag para no repetir el aviso en este pedido
    mechanic_warning_ack = fields.Boolean(default=False, copy=False)

    @api.onchange('order_line.mechanic_id', 'order_line.product_id', 'order_line.display_mechanic_fields')
    def _onchange_mechanic_global_warning(self):
        """Muestra UN solo warning por pedido:
        - Solo si hay líneas de servicio sin mecánico
        - Y no existe aún ninguna línea de servicio con mecánico
        - Y aún no se mostró el aviso (mechanic_warning_ack = False)
        En cuanto el usuario seleccione al menos un mecánico en cualquier línea de servicio,
        ya no se vuelve a mostrar.
        """
        for order in self:
            if order.mechanic_warning_ack:
                continue

            # Filtramos líneas de servicio (según tu lógica: producto servicio y/o display flag)
            service_lines = order.order_line.filtered(
                lambda l: l.product_id and l.product_id.type == 'service'
            )
            if not service_lines:
                continue

            # ¿Hay al menos una línea de servicio con mecánico?
            any_with_mechanic = any(l.mechanic_id for l in service_lines)

            # ¿Hay alguna línea de servicio sin mecánico?
            any_missing_mechanic = any(not l.mechanic_id for l in service_lines)

            if (not any_with_mechanic) and any_missing_mechanic:
                order.mechanic_warning_ack = True  # marcamos como avisado (no repetirá)
                return {
                    'warning': {
                        'title': _('Falta seleccionar el mecánico'),
                        'message': _(
                            'Tienes líneas de SERVICIO sin mecánico. '
                            'Selecciona un valor en "Columna de mecánicos". '
                            'Este aviso no volverá a mostrarse en este pedido.'
                        ),
                    }
                }
        return {}


class SaleOrderSetMechanicWizard(models.TransientModel):
    _name = 'sale.order.set.mechanic.wizard'
    _description = 'Asignar mecánico a líneas de servicio del pedido'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', readonly=True)

    mechanic_id = fields.Many2one(
        'hr.employee',
        string='Mecánico',
        required=True,
        domain="[('active','=',True), ('job_id.name', 'ilike', 'mecán'), '|', ('company_id','=',False), ('company_id','=', company_id)]",
        help="Empleado que se asignará como mecánico a las líneas de servicio."
    )

    only_empty = fields.Boolean(
        string='Solo líneas sin mecánico',
        default=True,
        help="Si está activo, solo actualizará las líneas de servicio que no tengan mecánico asignado."
    )

    affected_count = fields.Integer(
        string='Líneas afectadas',
        compute='_compute_preview',
        help="Cantidad de líneas de servicio que se actualizarán con el mecánico seleccionado."
    )

    def _get_target_lines(self):
        self.ensure_one()
        lines = self.order_id.order_line.filtered(lambda l: l.product_id and l.product_id.type == 'service')
        if self.only_empty:
            lines = lines.filtered(lambda l: not l.mechanic_id)
        return lines

    @api.depends('order_id', 'only_empty')
    def _compute_preview(self):
        for w in self:
            w.affected_count = len(w._get_target_lines()) if w.order_id else 0

    def action_apply(self):
        self.ensure_one()
        lines = self._get_target_lines()
        lines.write({'mechanic_id': self.mechanic_id.id})
        return {'type': 'ir.actions.act_window_close'}
