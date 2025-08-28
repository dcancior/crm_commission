# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    mechanic_id = fields.Many2one(
        "hr.employee",
        string="Mecánico",
        help="Empleado responsable de realizar el servicio.",
    )

    mechanic_hours_required = fields.Float(
        string="Horas requeridas (x unidad)",
        related="product_id.product_tmpl_id.service_hours_required",
        readonly=True,
        store=False,
    )
    # << NUEVO: bandera para mostrar/ocultar en vista, evita product_id.type en attrs
    display_mechanic_fields = fields.Boolean(
        string="Mostrar campos de mecánico",
        compute="_compute_display_mechanic_fields",
        store=False,
    )

    mechanic_cost_per_hour = fields.Float(
        string="Costo por hora (x unidad)",
        related="product_id.product_tmpl_id.service_cost_per_hour",
        readonly=True,
        store=False,
    )

    mechanic_cost_subtotal = fields.Monetary(
        string="Costo mecánico (subtotal)",
        compute="_compute_mechanic_cost_subtotal",
        currency_field="currency_id",
        store=False,
        help="Horas requeridas × costo por hora × cantidad.",
    )

    @api.depends(
        "product_id",
        "product_uom_qty",
        "product_uom",
        "mechanic_hours_required",
        "mechanic_cost_per_hour",
    )
    def _compute_mechanic_cost_subtotal(self):
        for line in self:
            hrs = line.mechanic_hours_required or 0.0
            cph = line.mechanic_cost_per_hour or 0.0
            qty = line.product_uom_qty or 0.0
            if line.product_id and line.product_id.detailed_type == "service":
                line.mechanic_cost_subtotal = hrs * cph * qty
            else:
                line.mechanic_cost_subtotal = 0.0

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        if self.mechanic_id:
            vals["mechanic_id"] = self.mechanic_id.id
        return vals
    
    @api.depends("product_id.detailed_type")
    def _compute_display_mechanic_fields(self):
        for line in self:
            # detailed_type es seguro en v16: 'service', 'product', 'consu'
            line.display_mechanic_fields = bool(line.product_id) and line.product_id.detailed_type == "service"
