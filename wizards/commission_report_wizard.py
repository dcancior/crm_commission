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

    # Totales / KPIs
    amount_total = fields.Float(string='Total Ventas (Base)', digits=(16, 2), currency_field='currency_id', compute='_compute_totals', store=False)
    commission_total = fields.Float(string='Total Comisión', digits=(16, 2), currency_field='currency_id', compute='_compute_totals', store=False)
    commission_percent = fields.Float(string='Porcentaje Comisión (Equipo)', digits=(16, 2), compute='_compute_totals', store=False)
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)

    # Detalle de facturas (sólo pagadas)
    line_ids = fields.One2many('commission.report.wizard.line', 'wizard_id')

    # Helpers
    date_start = fields.Date(string='Desde', compute='_compute_dates', store=False)
    date_end = fields.Date(string='Hasta', compute='_compute_dates', store=False)

    @api.depends('month', 'year')
    def _compute_dates(self):
        for rec in self:
            if rec.month and rec.year:
                y, m = int(rec.year), int(rec.month)
                last_day = calendar.monthrange(y, m)[1]
                rec.date_start = datetime(y, m, 1).date()
                rec.date_end = datetime(y, m, last_day).date()
            else:
                rec.date_start = False
                rec.date_end = False

    def _load_lines(self):
        """Carga las líneas reutilizando los campos ya calculados en account.move.
        Filtra sólo facturas cliente 'posted' y 'paid' dentro del rango por fecha de factura.
        """
        for rec in self:
            rec.line_ids = [(5, 0, 0)]  # limpia
            if not (rec.user_id and rec.date_start and rec.date_end):
                continue

            domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', '=', 'paid'),
                ('invoice_user_id', '=', rec.user_id.id),
                ('invoice_date', '>=', rec.date_start),
                ('invoice_date', '<=', rec.date_end),
            ]
            moves = rec.env['account.move'].search(domain, order='invoice_date asc, name asc')

            values = [(0, 0, {'move_id': m.id}) for m in moves]
            if values:
                rec.line_ids = values


    @api.depends('user_id', 'month', 'year', 'line_ids.move_id')
    def _compute_totals(self):
        for rec in self:
            # por claridad, siempre recarga líneas si cambian filtros (en vista el usuario puede tocar mes/año)
            if rec.user_id and rec.date_start and rec.date_end:
                rec._load_lines()
                commission_percent = rec.user_id.sale_team_id.commission_percent or 0.0
                rec.commission_percent = commission_percent
                rec.amount_total = sum(rec.line_ids.mapped('amount_untaxed'))
                # Total comisión: usa commission_amount del move (ya calculado en tu modelo account.move)
                rec.commission_total = sum(rec.line_ids.mapped('commission_amount'))
            else:
                rec.amount_total = 0.0
                rec.commission_total = 0.0
                rec.commission_percent = 0.0

    def action_refresh(self):
        """Botón para refrescar líneas manualmente desde el wizard (opcional)."""
        self.ensure_one()
        self._load_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


    # Detalle de facturas (sólo pagadas)
    #@api.depends('user_id', 'month', 'year')
    #def _compute_commission_total(self):
    #    for rec in self:
    #        if not rec.user_id or not rec.month or not rec.year:
    #            rec.amount_total = 0.0
    #            rec.commission_percent = 0.0
    #            rec.commission_total = 0.0
    #            continue
    #        year = int(rec.year)
    #        month = int(rec.month)
    #        last_day = calendar.monthrange(year, month)[1]
    #        date_start = f"{year}-{str(month).zfill(2)}-01"
    #        date_end = f"{year}-{str(month).zfill(2)}-{last_day}"
    #        orders = self.env['sale.order'].search([
    #            ('user_id', '=', rec.user_id.id),
    #            ('state', 'in', ['sale', 'done']),
    #            ('date_order', '>=', date_start),
    #            ('date_order', '<=', date_end),
    #
    # 
    #        commission_percent = rec.user_id.sale_team_id.commission_percent or 0.0
    #        ])
    #        rec.amount_total = sum(order.amount_untaxed for order in orders)
    #        rec.commission_percent = commission_percent
    #        rec.commission_total = rec.amount_total * (commission_percent / 100.0)


    def action_print_pdf(self):
        self.ensure_one()
        self._load_lines()  # asegura dataset al día

        currency = self.currency_id or self.env.company.currency_id
        decimals = getattr(currency, 'decimal_places', 2) or 2

        # Usa currency.round(...) o importa float_round si prefieres
        def money_str(amount):
            val = currency.round(amount or 0.0)
            s = f"{val:.{decimals}f}"
            return f"{currency.symbol} {s}" if (currency.position or 'after') == 'before' else f"{s} {currency.symbol}"

        invoice_lines = []
        for line in self.line_ids:
            m = line.move_id
            invoice_lines.append({
                'number': m.name or m.ref or '',
                'date': m.invoice_date and m.invoice_date.strftime('%d/%m/%Y') or '',
                'partner': m.partner_id.display_name or '',
                'amount_untaxed': m.amount_untaxed,
                'amount_untaxed_str': money_str(m.amount_untaxed),
                'commission_percent': m.commission_percent,
                'commission_percent_str': f"{(m.commission_percent or 0.0):.2f}",
                'commission_amount': m.commission_amount,
                'commission_amount_str': money_str(m.commission_amount),
                'payment_state': m.payment_state or '',
            })

        data = {
            'user_name': self.user_id.name,
            'month': self.month,
            'month_name': dict(self.fields_get(allfields=['month'])['month']['selection'])[self.month],
            'year': self.year,
            'commission_total': self.commission_total,
            'commission_total_str': money_str(self.commission_total),
            'amount_total': self.amount_total,
            'amount_total_str': money_str(self.amount_total),
            'commission_percent': self.commission_percent,
            'commission_percent_str': f"{(self.commission_percent or 0.0):.2f}",
            'invoice_lines': invoice_lines,
            'currency': currency,
        }

        # Usa el ir.actions.report ya definido en XML
        action = self.env.ref('crm_commission.action_commission_report_pdf').report_action(self, data=data)
        # Mantener el wizard abierto tras la descarga:
        action['close_on_report_download'] = False
        return action

    def money_str(amount):
        # redondea según la precisión de la moneda (currency.rounding)
        val = currency.round(amount or 0.0)
        s = f"{val:.{decimals}f}"
        return f"{currency.symbol} {s}" if (currency.position or 'after') == 'before' else f"{s} {currency.symbol}"

        # Construimos líneas con campos ya formateados
        invoice_lines = []
        for line in self.line_ids:
            m = line.move_id
            invoice_lines.append({
                'number': m.name or m.ref or '',
                'date': m.invoice_date and m.invoice_date.strftime('%d/%m/%Y') or '',
                'partner': m.partner_id.display_name or '',
                'amount_untaxed': m.amount_untaxed,                          # numérico (por si lo ocupas)
                'amount_untaxed_str': money_str(m.amount_untaxed),           # string formateado
                'commission_percent': m.commission_percent,
                'commission_percent_str': f"{(m.commission_percent or 0.0):.2f}",
                'commission_amount': m.commission_amount,
                'commission_amount_str': money_str(m.commission_amount),
                'payment_state': m.payment_state or '',
            })

        data = {
            'user_name': self.user_id.name,
            'month': self.month,
            'month_name': dict(self.fields_get(allfields=['month'])['month']['selection'])[self.month],
            'year': self.year,
            'commission_total': self.commission_total,
            'commission_total_str': money_str(self.commission_total),   # 👈 ya listo
            'amount_total': self.amount_total,
            'amount_total_str': money_str(self.amount_total),           # 👈 ya listo
            'commission_percent': self.commission_percent,
            'commission_percent_str': f"{(self.commission_percent or 0.0):.2f}",  # 👈 ya listo
            'invoice_lines': invoice_lines,
            # Por si lo quieres usar en el template
            'currency': currency,
            'currency_symbol': currency.symbol,
            'currency_position': currency.position,
        }

        return {
            'type': 'ir.actions.report',
            'report_name': 'crm_commission.commission_report_pdf',
            'report_type': 'qweb-pdf',
            'data': data,
        }


class CommissionReportWizardLine(models.TransientModel):
    _name = 'commission.report.wizard.line'
   

    wizard_id = fields.Many2one('commission.report.wizard', string='Wizard', required=True, ondelete='cascade')
    move_id = fields.Many2one('account.move', string='Factura', required=True, domain=[('move_type', '=', 'out_invoice')])

    # Reutilizamos campos del move (ya calculados)
    partner_id = fields.Many2one(related='move_id.partner_id', string='Cliente', store=False)
    invoice_date = fields.Date(related='move_id.invoice_date', string='Fecha', store=False)
    amount_untaxed = fields.Monetary(related='move_id.amount_untaxed', string='Base', store=False, currency_field='currency_id')
    commission_percent = fields.Float(related='move_id.commission_percent', string='% Comisión', store=False)
    commission_amount = fields.Monetary(related='move_id.commission_amount', string='Comisión', store=False, currency_field='currency_id')
    payment_state = fields.Selection(related='move_id.payment_state', string='Estado Pago', store=False)
    currency_id = fields.Many2one(related='move_id.currency_id', string='Moneda', store=False)