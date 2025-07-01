from odoo import models, fields, api
from datetime import datetime

class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Wizard para reporte de comisión mensual'

    user_id = fields.Many2one('res.users', string='Vendedor', required=True)
    month = fields.Selection(
        [(str(i), str(i)) for i in range(1, 13)],
        string='Mes',
        required=True,
        default=str(datetime.now().month)
    )
    year = fields.Integer(
        string='Año',
        required=True,
        default=datetime.now().year
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
            month_str = str(rec.month)
            date_start = f"{rec.year}-{month_str.zfill(2)}-01"
            if month_str == '12':
                date_end = f"{rec.year + 1}-01-01"
            else:
                date_end = f"{rec.year}-{str(int(month_str) + 1).zfill(2)}-01"
            orders = self.env['sale.order'].search([
                ('user_id', '=', rec.user_id.id),
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', date_start),
                ('date_order', '<', date_end),
            ])
            # Toma la comisión del equipo del usuario
            commission_percent = rec.user_id.sale_team_id.commission_percent or 0.0
            rec.amount_total = sum(order.amount_total for order in orders)
            rec.commission_percent = commission_percent
            rec.commission_total = rec.amount_total * (commission_percent / 100.0)