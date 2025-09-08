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

PAYMENT_METHODS = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
]


class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Wizard para reporte de comisión mensual'

    user_id = fields.Many2one('res.users', string='Vendedor', required=True)
    month = fields.Selection(
        MONTHS, string='Mes', required=True,
        default=lambda self: datetime.now().strftime('%m')
    )
    year = fields.Selection(
        [(str(y), str(y)) for y in range(datetime.now().year, datetime.now().year - 10, -1)],
        string='Año', required=True, default=lambda self: str(datetime.now().year)
    )

    # Totales / KPIs
    amount_total = fields.Float(
        string='Total Ventas (Base)', digits=(16, 2),
        currency_field='currency_id', compute='_compute_totals', store=False
    )
    commission_total = fields.Float(
        string='Total Comisión', digits=(16, 2),
        currency_field='currency_id', compute='_compute_totals', store=False
    )
    commission_percent = fields.Float(
        string='Porcentaje Comisión (Equipo)', digits=(16, 2),
        compute='_compute_totals', store=False
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

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
        """Carga y sincroniza líneas con facturas pagadas.
        Preserva forma de pago/fecha/usuario capturados por el usuario.
        """
        for rec in self:
            if not (rec.user_id and rec.date_start and rec.date_end):
                rec.line_ids = [(5, 0, 0)]
                continue

            existing_map = {l.move_id.id: l for l in rec.line_ids}

            domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', '=', 'paid'),
                ('invoice_user_id', '=', rec.user_id.id),
                ('invoice_date', '>=', rec.date_start),
                ('invoice_date', '<=', rec.date_end),
            ]
            moves = rec.env['account.move'].search(domain, order='invoice_date asc, name asc')

            values = []
            for m in moves:
                prev = existing_map.get(m.id)
                vals = {'move_id': m.id}
                if prev:
                    vals.update({
                        'payment_method': prev.payment_method,
                        'payment_datetime': prev.payment_datetime,
                        'payment_user_id': prev.payment_user_id.id if prev.payment_user_id else False,
                    })
                values.append((0, 0, vals))

            rec.line_ids = [(5, 0, 0)] + values

    @api.depends('user_id', 'line_ids.amount_untaxed', 'line_ids.commission_amount')
    def _compute_totals(self):
        for rec in self:
            # % de comisión desde el equipo del vendedor (si existe)
            rec.commission_percent = (
                rec.user_id.sale_team_id.commission_percent
                if rec.user_id and rec.user_id.sale_team_id
                else 0.0
            )
            # Totales basados en las líneas ya cargadas en pantalla
            rec.amount_total = sum(rec.line_ids.mapped('amount_untaxed')) if rec.line_ids else 0.0
            rec.commission_total = sum(rec.line_ids.mapped('commission_amount')) if rec.line_ids else 0.0

    def action_refresh(self):
        self.ensure_one()
        self._load_lines()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_print_pdf(self):
        self.ensure_one()
        # ❌ No llames a self._load_lines() aquí; respeta lo que el usuario acaba de capturar
        self.flush()  # opcional: asegura que el inline edit quede escrito antes de leer

        currency = self.currency_id or self.env.company.currency_id
        decimals = getattr(currency, 'decimal_places', 2) or 2

        def money_str(amount):
            val = currency.round(amount or 0.0)
            s = f"{val:.{decimals}f}"
            return f"{currency.symbol} {s}" if (currency.position or 'after') == 'before' else f"{s} {currency.symbol}"

        method_labels = dict(PAYMENT_METHODS)
        invoice_lines = []
        for line in self.line_ids:
            m = line.move_id
            pay_method = method_labels.get(line.payment_method or '', '')
            pay_dt = ''
            if line.payment_datetime:
                pay_dt = fields.Datetime.context_timestamp(self, line.payment_datetime).strftime('%d/%m/%Y %H:%M:%S')
            pay_user = line.payment_user_id.name if line.payment_user_id else ''
            # 👇 Define aquí el texto "Sí/No" según haya método elegido
            commission_paid = 'Sí' if line.payment_method else 'No'
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
                'pay_method': pay_method,
                'pay_datetime': pay_dt,
                'pay_user': pay_user,
                'commission_paid': commission_paid,
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

        action = self.env.ref('crm_commission.action_commission_report_pdf').report_action(self, data=data)
        action['close_on_report_download'] = False  # mantener wizard abierto
        return action

    @api.onchange('user_id', 'month', 'year')
    def _onchange_filters(self):
        self._compute_dates()
        self._load_lines()


    def action_save(self):
        """Guardar cambios sin cerrar el wizard."""
        self.ensure_one()
        self.flush()  # asegura que one2many y cambios de celda se escriban
        # Muestra el mismo wizard otra vez (target=new mantiene el modal)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.report.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class CommissionReportWizardLine(models.TransientModel):
    _name = 'commission.report.wizard.line'
    _description = 'Línea del reporte de comisión'

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

    # Selección por línea + sellos
    payment_method = fields.Selection(
        PAYMENT_METHODS, string='Forma de pago comisión',
        help='Seleccione cómo se paga la comisión de esta factura',
    )
    payment_datetime = fields.Datetime(
        string='Fecha/Hora pago', readonly=True,
        help='Se llena automáticamente al elegir el método'
    )
    payment_user_id = fields.Many2one(
        'res.users', string='Registró', readonly=True,
        help='Usuario que registró el pago de la comisión'
    )

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.payment_method:
            self.payment_datetime = fields.Datetime.now()
            self.payment_user_id = self.env.user


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('payment_method'):
                vals.setdefault('payment_datetime', fields.Datetime.now())
                vals.setdefault('payment_user_id', self.env.user.id)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        # Si se acaba de establecer payment_method y no hay sellos, sellar ahora
        if 'payment_method' in vals:
            for rec in self:
                if rec.payment_method and not rec.payment_datetime:
                    rec.payment_datetime = fields.Datetime.now()
                    rec.payment_user_id = self.env.user
        return res

    commission_paid = fields.Boolean(
        string='Comisión pagada',
        compute='_compute_commission_paid',
        store=False
    )

    @api.depends('payment_method')
    def _compute_commission_paid(self):
        for rec in self:
            rec.commission_paid = bool(rec.payment_method)
