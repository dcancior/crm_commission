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

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    mechanic_id = fields.Many2one(
        "hr.employee",
        string="Mecánico",
        help="Mecánico que realizó el servicio.",
        index=True,
        copy=False,
    )

    mechanic_hours_required = fields.Float(
        string="Horas requeridas (x unidad)",
        compute="_compute_mechanic_meta",
        store=False,
        digits=(16, 2),
    )
    mechanic_cost_per_hour = fields.Float(
        string="Costo por hora (x unidad)",
        compute="_compute_mechanic_meta",
        store=False,
        digits=(16, 2),
    )
    mechanic_cost_subtotal = fields.Monetary(
        string="Costo mecánico (subtotal)",
        compute="_compute_mechanic_cost",
        currency_field="currency_id",
        store=False,
    )

    @api.depends("product_id")
    def _compute_mechanic_meta(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            line.mechanic_hours_required = tmpl.service_hours_required if tmpl else 0.0
            line.mechanic_cost_per_hour = tmpl.service_cost_per_hour if tmpl else 0.0

    @api.depends(
        "quantity", "product_id", "mechanic_hours_required", "mechanic_cost_per_hour"
    )
    def _compute_mechanic_cost(self):
        for line in self:
            if line.product_id and line.product_id.type == "service":
                line.mechanic_cost_subtotal = (
                    (line.mechanic_hours_required or 0.0)
                    * (line.mechanic_cost_per_hour or 0.0)
                    * (line.quantity or 0.0)
                )
            else:
                line.mechanic_cost_subtotal = 0.0
