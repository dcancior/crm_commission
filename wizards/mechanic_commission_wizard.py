# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime
import calendar

MONTHS = [
    ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'), ('04', 'Abril'),
    ('05', 'Mayo'), ('06', 'Junio'), ('07', 'Julio'), ('08', 'Agosto'),
    ('09', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')
]

class MechanicCommissionWizard(models.TransientModel):
    _name = "mechanic.commission.wizard"
    _description = "Wizard: Comisiones de mecánicos por mes (facturas pagadas)"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Mecánico",
        required=True,
    )
    month = fields.Selection(
        MONTHS,
        string="Mes",
        required=True,
        default=lambda self: datetime.now().strftime("%m"),
    )

    month_name = fields.Char(string="Mes (nombre)", compute="_compute_month_name", store=False)

    year = fields.Selection(
        [(str(y), str(y)) for y in range(datetime.now().year, datetime.now().year - 10, -1)],
        string="Año",
        required=True,
        default=lambda self: str(datetime.now().year),
    )

    services_count = fields.Integer(
        string="Servicios (líneas)",
        compute="_compute_totals",
        store=False,
    )
    total_hours = fields.Float(
        string="Horas totales",
        compute="_compute_totals",
        store=False,
        digits=(16, 2),
    )
    payout_total = fields.Monetary(
        string="Total a pagar",
        compute="_compute_totals",
        store=False,
        currency_field="currency_id",
    )
    amount_invoiced = fields.Monetary(
        string="Importe facturado (cliente)",
        compute="_compute_totals",
        store=False,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id.id,
    )

    line_ids = fields.One2many(
        "mechanic.commission.wizard.line",
        "wizard_id",
        string="Detalle",
        compute="_compute_totals",
        store=False,
    )

    @api.depends("employee_id", "month", "year")
    def _compute_totals(self):
        for wiz in self:
            wiz.line_ids = [(5, 0, 0)]
            wiz.services_count = 0
            wiz.total_hours = 0.0
            wiz.payout_total = 0.0
            wiz.amount_invoiced = 0.0

            if not wiz.employee_id or not wiz.month or not wiz.year:
                continue

            year = int(wiz.year)
            month = int(wiz.month)
            last_day = calendar.monthrange(year, month)[1]
            date_start = f"{year}-{str(month).zfill(2)}-01"
            date_end = f"{year}-{str(month).zfill(2)}-{last_day}"

            # Facturas cliente 'posted' y pagadas completamente en el rango
            moves = self.env["account.move"].search([
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "=", "paid"),
                ("invoice_date", ">=", date_start),
                ("invoice_date", "<=", date_end),
            ])

            lines = moves.mapped("invoice_line_ids").filtered(
                lambda l: l.mechanic_id.id == wiz.employee_id.id and l.product_id.type == "service"
            )

            detail_vals = []
            for l in lines:
                qty = l.quantity or 0.0
                hrs = (l.product_id.product_tmpl_id.service_hours_required or 0.0) * qty
                payout = (
                    (l.product_id.product_tmpl_id.service_cost_per_hour or 0.0)
                    * (l.product_id.product_tmpl_id.service_hours_required or 0.0)
                    * qty
                )
                detail_vals.append((0, 0, {
                    "invoice_name": l.move_id.name or l.move_id.ref or "",
                    "invoice_date": l.move_id.invoice_date,
                    "product_name": l.product_id.display_name,
                    "quantity": qty,
                    "hours": hrs,
                    "payout": payout,
                    "subtotal_customer": l.price_subtotal,
                }))

            wiz.line_ids = detail_vals
            wiz.services_count = len(lines)
            wiz.total_hours = sum(d[2]["hours"] for d in detail_vals) if detail_vals else 0.0
            wiz.payout_total = sum(d[2]["payout"] for d in detail_vals) if detail_vals else 0.0
            wiz.amount_invoiced = sum(d[2]["subtotal_customer"] for d in detail_vals) if detail_vals else 0.0

    def action_print_pdf(self):
        self.ensure_one()
        self._compute_totals()

        cur = self.currency_id or self.env.company.currency_id
        decimals = int(getattr(cur, "decimal_places", 2) or 2)

        def _num(x, nd=2):
            return f"{(x or 0.0):.{nd}f}"

        def _money(x):
            val = f"{(x or 0.0):.{decimals}f}"
            return f"{cur.symbol} {val}" if (getattr(cur, "position", "after") == "before") else f"{val} {cur.symbol}"

        lines = [{
            "invoice_name": l.invoice_name or "",
            "invoice_date": l.invoice_date or "",
            "product_name": l.product_name or "",
            "quantity": _num(l.quantity, 2),
            "hours": _num(l.hours, 2),
            "subtotal_customer": _money(l.subtotal_customer),
            "payout": _money(l.payout),
        } for l in self.line_ids]

        # Si no tienes o.month_name como campo, puedes calcularlo así:
        month_name = dict(self.fields_get(allfields=["month"])["month"]["selection"]).get(self.month, "") or ""

        data = {
            "employee_name": self.employee_id.name or "",
            "month": self.month or "",
            "month_name": month_name,
            "year": self.year or "",
            "services_count": int(self.services_count or 0),
            "total_hours": _num(self.total_hours, 2),
            "amount_invoiced": _money(self.amount_invoiced),
            "payout_total": _money(self.payout_total),
            "lines": lines,
        }

        return {
        "type": "ir.actions.report",
        "report_type": "qweb-pdf",
        # Usa el XMLID de la ACCIÓN, no del template
        "report_name": "crm_commission.action_mechanic_commission_report",
        "data": data,
        "context": {"active_model": "mechanic.commission.wizard", "active_ids": self.ids},
    }

    
    @api.depends("month")
    def _compute_month_name(self):
        sel = dict(MONTHS)
        for w in self:
            w.month_name = sel.get(w.month or "", "")

class MechanicCommissionWizardLine(models.TransientModel):
    _name = "mechanic.commission.wizard.line"
    _description = "Detalle para comisiones de mecánico"

    wizard_id = fields.Many2one("mechanic.commission.wizard", ondelete="cascade")
    invoice_name = fields.Char("Factura")
    invoice_date = fields.Date("Fecha factura")
    product_name = fields.Char("Servicio")
    quantity = fields.Float("Cantidad", digits=(16, 2))
    hours = fields.Float("Horas", digits=(16, 2))
    payout = fields.Monetary("Pago mecánico", currency_field="currency_id")
    subtotal_customer = fields.Monetary("Subtotal cliente", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id.id,
    )
