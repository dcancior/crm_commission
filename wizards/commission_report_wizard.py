from odoo import models, fields, api
from datetime import datetime
import calendar

MONTHS = [
    ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'), ('04', 'Abril'),
    ('05', 'Mayo'), ('06', 'Junio'), ('07', 'Julio'), ('08', 'Agosto'),
    ('09', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')
]

class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Wizard para reporte de comisión mensual'

    user_id = fields.Many2one('res.users', string='Vendedor', required=True)
    month = fields.Selection(
        MONTHS,
        string='Mes',
        required=True,
        default=lambda self: datetime.now().strftime('%m')
    )
    year = fields.Selection(
        [(str(y), str(y)) for y in range(datetime.now().year, datetime.now().year - 10, -1)],
        string='Año',
        required=True,
        default=lambda self: str(datetime.now().year)
    )
    commission_total = fields.Float(string='Total Comisión', compute='_compute_commission_total', store=False)
    amount_total = fields.Float(string='Total Ventas', compute='_compute_commission_total', store=False)
    commission_percent = fields.Float(string='Porcentaje Comisión', compute='_compute_commission_total', store=False)

    @api.depends('user_id', 'month', 'year')
    def _compute_commission_total(self):
        for rec in self:
            if not rec.user_id or not rec.month or not rec.year:
                rec.amount_total = 0.0
                rec.commission_percent = 0.0
                rec.commission_total = 0.0
                continue
            year = int(rec.year)
            month = int(rec.month)
            last_day = calendar.monthrange(year, month)[1]
            date_start = f"{year}-{str(month).zfill(2)}-01"
            date_end = f"{year}-{str(month).zfill(2)}-{last_day}"
            orders = self.env['sale.order'].search([
                ('user_id', '=', rec.user_id.id),
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', date_start),
                ('date_order', '<=', date_end),
            ])
            commission_percent = rec.user_id.sale_team_id.commission_percent or 0.0
            rec.amount_total = sum(order.amount_untaxed for order in orders)
            rec.commission_percent = commission_percent
            rec.commission_total = rec.amount_total * (commission_percent / 100.0)

    def action_print_pdf(self):
        return self.env.ref('crm_commission.action_commission_report_pdf').report_action(self)