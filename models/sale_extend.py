# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗  # Comentario decorativo
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║  # Comentario decorativo
# ║  Web: https://www.dcrsoluciones.com                              ║  # Comentario decorativo
# ║  Contacto: info@dcrsoluciones.com                                ║  # Comentario decorativo
# ║                                                                  ║  # Comentario decorativo
# ║  Este módulo está bajo licencia (LGPLv3).                        ║  # Comentario decorativo
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║  # Comentario decorativo
# ╚══════════════════════════════════════════════════════════════════╝  # Comentario decorativo

from odoo import api, fields, models, _  # Importa API, campos, modelos y traducciones

# -----------------------------------------------------------------------------
# LÍNEAS DE VENTA
# -----------------------------------------------------------------------------
class SaleOrderLine(models.Model):  # Clase que hereda las líneas de pedido
    _inherit = "sale.order.line"  # Indicamos herencia de sale.order.line

    mechanic_id = fields.Many2one(  # Campo mecánico en la línea (NO requerido)
        "hr.employee",  # Modelo de empleado
        string="Mecánico",  # Etiqueta visible
        help="Empleado responsable de realizar el servicio.",  # Ayuda
        required=False,  # No bloquear por requerido
    )  # Fin mechanic_id

    mechanic_hours_required = fields.Float(  # Horas requeridas por unidad (related)
        string="Horas requeridas (x unidad)",  # Etiqueta
        related="product_id.product_tmpl_id.service_hours_required",  # Related al template
        readonly=True,  # Solo lectura
        store=False,  # No almacenar
    )  # Fin mechanic_hours_required

    display_mechanic_fields = fields.Boolean(  # Flag para controlar visibilidad en vistas
        string="Mostrar campos de mecánico",  # Etiqueta
        compute="_compute_display_mechanic_fields",  # Cómputo
        store=False,  # No almacenar
    )  # Fin display_mechanic_fields

    mechanic_cost_per_hour = fields.Float(  # Costo por hora (related)
        string="Costo por hora (x unidad)",  # Etiqueta
        related="product_id.product_tmpl_id.service_cost_per_hour",  # Related al template
        readonly=True,  # Solo lectura
        store=False,  # No almacenar
    )  # Fin mechanic_cost_per_hour

    mechanic_cost_subtotal = fields.Monetary(  # Subtotal del costo de mecánico
        string="Costo mecánico (subtotal)",  # Etiqueta
        compute="_compute_mechanic_cost_subtotal",  # Cómputo
        currency_field="currency_id",  # Moneda
        store=False,  # No almacenar
        help="Horas requeridas × costo por hora × cantidad.",  # Ayuda
    )  # Fin mechanic_cost_subtotal

    product_type = fields.Selection(  # Tipo del producto (para decoración/condiciones)
        related="product_id.type",  # Related al tipo
        store=True,  # Almacenar para usar en tree
    )  # Fin product_type

    mechanic_is_placeholder = fields.Boolean(  # True si el mecánico es el placeholder
        string="Mecánico placeholder",  # Etiqueta
        compute="_compute_mechanic_is_placeholder",  # Cómputo
        store=False,  # No almacenar
    )  # Fin mechanic_is_placeholder

    @api.depends("mechanic_id")  # Recalcular cuando cambia el mecánico
    def _compute_mechanic_is_placeholder(self):  # Marca si el mecánico es el placeholder
        for line in self:  # Itera líneas
            name = (line.mechanic_id.name or "").strip().upper()  # Nombre normalizado
            line.mechanic_is_placeholder = (name == "SELECCIONE UN MECÁNICO")  # True si coincide exactamente

    @api.onchange("product_id")  # Al cambiar el producto
    def _onchange_autoset_placeholder_mechanic(self):  # Autoselecciona placeholder si es servicio
        for line in self:  # Itera líneas
            if line.product_id and line.product_id.type == "service" and not line.mechanic_id:  # Servicio y sin mecánico
                placeholder = line._get_placeholder_mechanic()  # Busca empleado “SELECCIONE UN MECÁNICO”
                if placeholder:  # Si existe
                    line.mechanic_id = placeholder  # Asigna el placeholder

    def _get_placeholder_mechanic(self):  # Helper para encontrar el empleado placeholder
        self.ensure_one()  # Una sola línea
        company_id = (self.order_id.company_id.id if self.order_id else self.env.company.id)  # Compañía del pedido/actual
        Employee = self.env["hr.employee"]  # Modelo empleado
        # Búsqueda exacta por nombre, permitiendo empleado global (company_id False) o de la compañía actual
        emp = Employee.search([  # Busca exacto primero
            ("name", "=", "SELECCIONE UN MECÁNICO"),
            "|", ("company_id", "=", False), ("company_id", "=", company_id),
        ], limit=1)  # Límite 1
        if not emp:  # Si no encontró exacto
            emp = Employee.search([("name", "ilike", "SELECCIONE UN MECÁNICO")], limit=1)  # Búsqueda laxa
        return emp  # Devuelve record o vacío

    @api.depends(  # Dependencias para el subtotal
        "product_id",
        "product_uom_qty",
        "product_uom",
        "mechanic_hours_required",
        "mechanic_cost_per_hour",
    )
    def _compute_mechanic_cost_subtotal(self):  # Cálculo del subtotal
        for line in self:  # Itera líneas
            hrs = line.mechanic_hours_required or 0.0  # Horas
            cph = line.mechanic_cost_per_hour or 0.0  # Costo/hora
            qty = line.product_uom_qty or 0.0  # Cantidad
            line.mechanic_cost_subtotal = (hrs * cph * qty) if (line.product_id and line.product_id.detailed_type == "service") else 0.0  # Solo servicios

    def _prepare_invoice_line(self, **optional_values):  # Extiende valores de línea de factura
        vals = super()._prepare_invoice_line(**optional_values)  # Llama super
        # No trasladar el placeholder a la factura; solo pasa mecánicos reales
        if self.mechanic_id and not self.mechanic_is_placeholder:  # Si hay mecánico real
            vals["mechanic_id"] = self.mechanic_id.id  # Pásalo a la factura
        return vals  # Devuelve valores

    @api.depends("product_id.detailed_type")  # Depende del tipo detallado del producto
    def _compute_display_mechanic_fields(self):  # Cómputo del flag de visibilidad
        for line in self:  # Itera líneas
            # detailed_type en Odoo 16: 'service', 'product', 'consu'
            line.display_mechanic_fields = bool(line.product_id) and (line.product_id.detailed_type == "service")  # True solo si es servicio


# -----------------------------------------------------------------------------
# PEDIDO DE VENTA (AVISO UNA SOLA VEZ, NO BLOQUEANTE)
# -----------------------------------------------------------------------------
class SaleOrder(models.Model):  # Clase que hereda sale.order
    _inherit = "sale.order"  # Herencia de sale.order

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
