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
