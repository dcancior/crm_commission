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

    def action_apply(self):
        self.ensure_one()

        order = self.order_id
        lines = self._get_target_lines()

        # 🔧 Asignar mecánico a las líneas seleccionadas
        if lines:
            lines.write({'mechanic_id': self.mechanic_id.id})
            
            # 📝 Mensaje en chatter
            order.message_post(
                body=f"🔧 Mecánico asignado: {self.mechanic_id.name} "
                     f"a {len(lines)} línea(s) por {self.env.user.name}"
            )

        # 🔍 Revisar si después de esta asignación aún faltan mecánicos en otras líneas
        missing = order.order_line.filtered(
            lambda l: l.product_id.type == 'service' and not l.mechanic_id
        )

        # --- LÓGICA DE INVENTARIO PENDIENTE ---
        # Si ya no faltan mecánicos, procesamos los pickings que se quedaron pausados
        if not missing:
            pickings_to_validate = order.picking_ids.filtered(
                lambda p: p.state not in ('done', 'cancel')
            )
            
            for picking in pickings_to_validate:
                # Intentamos reservar stock si no estaba reservado
                if picking.state in ('confirmed', 'waiting'):
                    picking.action_assign()

                # Si está listo (assigned), validamos automáticamente
                if picking.state == 'assigned':
                    for move in picking.move_ids_without_package:
                        if move.product_id.type == 'product':
                            move.quantity_done = move.product_uom_qty
                    
                    picking.button_validate()
                    _logger.info("Inventario validado tras asignación de mecánico: %s", picking.name)

        # 🔥 Gestión de Actividades (Limpieza)
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if activity_type:
            activities = self.env['mail.activity'].search([
                ('res_model', '=', 'sale.order'),
                ('res_id', '=', order.id),
                ('activity_type_id', '=', activity_type.id),
                ('state', '=', 'planned')
            ])

            # ✅ SOLO cerrar actividades si ya no hay pendientes de mecánico
            if activities and not missing:
                activities.action_done()

        return {'type': 'ir.actions.act_window_close'}