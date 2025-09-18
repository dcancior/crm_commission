# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗  # Comentario decorativo
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║  # Comentario decorativo
# ║  Web: https://www.dcrsoluciones.com                              ║  # Comentario decorativo
# ║  Contacto: info@dcrsoluciones.com                                ║  # Comentario decorativo
# ║                                                                  ║  # Comentario decorativo
# ║  Este módulo está bajo licencia (LGPLv3).                        ║  # Comentario decorativo
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║  # Comentario decorativo
# ╚══════════════════════════════════════════════════════════════════╝  # Comentario decorativo

from odoo import api, fields, models, _  # Importa API de Odoo y _ para traducciones

# -----------------------------------------------------------------------------
# LÍNEAS DE VENTA
# -----------------------------------------------------------------------------
class SaleOrderLine(models.Model):  # Clase que hereda las líneas de pedido
    _inherit = "sale.order.line"  # Indicamos herencia de sale.order.line

    mechanic_id = fields.Many2one(  # Campo mecánico en la línea (NO requerido)
        "hr.employee",  # Modelo de empleado
        string="Mecánico",  # Etiqueta visible
        help="Empleado responsable de realizar el servicio.",  # Ayuda
        required=False,  # Asegura que no bloquea por ser requerido
    )  # Fin de mechanic_id

    mechanic_hours_required = fields.Float(  # Horas requeridas por unidad (related)
        string="Horas requeridas (x unidad)",  # Etiqueta
        related="product_id.product_tmpl_id.service_hours_required",  # Related al template
        readonly=True,  # Solo lectura
        store=False,  # No almacenar (se calcula al vuelo)
    )  # Fin de mechanic_hours_required

    display_mechanic_fields = fields.Boolean(  # Flag para controlar visibilidad en vistas
        string="Mostrar campos de mecánico",  # Etiqueta
        compute="_compute_display_mechanic_fields",  # Cómputo
        store=False,  # No almacenar
    )  # Fin de display_mechanic_fields

    mechanic_cost_per_hour = fields.Float(  # Costo por hora (related)
        string="Costo por hora (x unidad)",  # Etiqueta
        related="product_id.product_tmpl_id.service_cost_per_hour",  # Related al template
        readonly=True,  # Solo lectura
        store=False,  # No almacenar
    )  # Fin de mechanic_cost_per_hour

    mechanic_cost_subtotal = fields.Monetary(  # Subtotal del costo de mecánico
        string="Costo mecánico (subtotal)",  # Etiqueta
        compute="_compute_mechanic_cost_subtotal",  # Cómputo
        currency_field="currency_id",  # Moneda de la línea
        store=False,  # No almacenar
        help="Horas requeridas × costo por hora × cantidad.",  # Ayuda
    )  # Fin de mechanic_cost_subtotal

    product_type = fields.Selection(  # Tipo del producto para usar en la vista/decoration
        related="product_id.type",  # Related al tipo
        store=True,  # Guardar para usar en tree/condiciones
    )  # Fin de product_type

    # ⛔️ IMPORTANTE: Quitamos el onchange por línea y la constrains por línea
    # para NO bloquear el guardado cuando falte mecánico en algunas líneas.  # Comentario aclaratorio
    # (Si los tenías antes, ya no están aquí.)  # Comentario aclaratorio

    @api.depends(  # Dependencias para recalcular el costo de mecánico
        "product_id",
        "product_uom_qty",
        "product_uom",
        "mechanic_hours_required",
        "mechanic_cost_per_hour",
    )
    def _compute_mechanic_cost_subtotal(self):  # Método de cómputo del subtotal
        for line in self:  # Itera sobre líneas
            hrs = line.mechanic_hours_required or 0.0  # Horas por unidad
            cph = line.mechanic_cost_per_hour or 0.0  # Costo por hora
            qty = line.product_uom_qty or 0.0  # Cantidad
            if line.product_id and line.product_id.detailed_type == "service":  # Solo servicios
                line.mechanic_cost_subtotal = hrs * cph * qty  # Calcula subtotal
            else:
                line.mechanic_cost_subtotal = 0.0  # Cero si no es servicio

    def _prepare_invoice_line(self, **optional_values):  # Extiende valores de factura
        vals = super()._prepare_invoice_line(**optional_values)  # Llama super
        if self.mechanic_id:  # Si hay mecánico en la línea
            vals["mechanic_id"] = self.mechanic_id.id  # Transfiere a línea de factura
        return vals  # Retorna valores

    @api.depends("product_id.detailed_type")  # Depende del tipo detallado del producto
    def _compute_display_mechanic_fields(self):  # Cómputo de flag de visibilidad
        for line in self:  # Itera líneas
            # detailed_type en Odoo 16: 'service', 'product', 'consu'  # Comentario informativo
            line.display_mechanic_fields = bool(line.product_id) and line.product_id.detailed_type == "service"  # True solo si es servicio


# -----------------------------------------------------------------------------
# PEDIDO DE VENTA (AVISO UNA SOLA VEZ, NO BLOQUEANTE)
# -----------------------------------------------------------------------------
class SaleOrder(models.Model):  # Clase que hereda sale.order
    _inherit = "sale.order"  # Indicamos herencia de sale.order

    mechanic_warning_ack = fields.Boolean(  # Flag para no repetir el aviso en el pedido
        default=False,  # Valor por defecto
        copy=False,  # No copiar al duplicar
    )  # Fin de mechanic_warning_ack

    @api.onchange(  # Onchange a nivel pedido para avisar una sola vez
        "order_line.mechanic_id",
        "order_line.product_id",
        "order_line.display_mechanic_fields",
    )
    def _onchange_mechanic_global_warning(self):  # Método onchange global
        for order in self:  # Itera pedidos en el recordset
            if order.mechanic_warning_ack:  # Si ya se mostró, no repetir
                continue  # Salta a siguiente pedido
            service_lines = order.order_line.filtered(  # Filtra líneas de servicio
                lambda l: l.product_id and l.product_id.type == "service"
            )  # Fin del filtrado
            if not service_lines:  # Si no hay servicios, no avisar
                continue  # Salta
            any_with_mechanic = any(l.mechanic_id for l in service_lines)  # ¿Alguna línea de servicio con mecánico?
            any_missing_mechanic = any(not l.mechanic_id for l in service_lines)  # ¿Alguna de servicio sin mecánico?
            if (not any_with_mechanic) and any_missing_mechanic:  # Avisar solo si no hay ninguna con mecánico
                order.mechanic_warning_ack = True  # Marca como avisado (una sola vez)
                return {  # Retorna warning no bloqueante
                    "warning": {
                        "title": _("Falta seleccionar el mecánico"),  # Título
                        "message": _(
                            "Tienes líneas de SERVICIO sin mecánico. "
                            "Asigna mecánico al menos en UNA línea de servicio. "
                            "Este aviso se mostrará sólo una vez."
                        ),  # Mensaje
                    }
                }  # Fin return
        return {}  # No hay aviso
