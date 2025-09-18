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
