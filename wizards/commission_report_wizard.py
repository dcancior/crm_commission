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
from odoo.exceptions import ValidationError

PAYMENT_METHODS = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
]


def _default_date_start(self):
    today = fields.Date.context_today(self)
    return today.replace(day=1)


def _default_date_end(self):
    return fields.Date.context_today(self)


class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Wizard para reporte de comisión por rango de fechas'

    # Filtros
    user_id = fields.Many2one('res.users', string='Vendedor', required=True)
    date_start = fields.Date(string='Desde', required=True, default=_default_date_start)
    date_end = fields.Date(string='Hasta', required=True, default=_default_date_end)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError("La fecha final no puede ser menor que la fecha inicial.")

    filter_payment = fields.Selection(
        [('all', 'Todas'), ('paid', 'Pagadas'), ('unpaid', 'No pagadas')],
        string='Filtro pago comisión',
        default='all'
    )

    # Totales / KPIs
    lines_count = fields.Integer(string='Líneas', compute='_compute_totals', store=False)
    amount_total = fields.Float(
        string='Total Ventas (Base)', digits=(16, 2),
        currency_field='currency_id', compute='_compute_totals'
    )
    commission_total = fields.Float(
        string='Total Comisión', digits=(16, 2),
        currency_field='currency_id', compute='_compute_totals'
    )
    commission_percent = fields.Float(
        string='Porcentaje Comisión (Equipo)', digits=(16, 2),
        compute='_compute_totals'
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

    # ÚNICO O2M (se reconstruye según filtro)
    line_ids = fields.One2many('commission.report.wizard.line', 'wizard_id', string='Líneas')

    # ---------------------------
    # Construcción de líneas O2M
    # ---------------------------
    def _load_lines(self):
        """Reconstruye line_ids respetando vendedor/fechas y el filtro."""
        Entry = self.env['commission.payment.entry']
        for rec in self:
            if not (rec.user_id and rec.date_start and rec.date_end):
                rec.line_ids = [(5, 0, 0)]
                continue

            # Facturas del vendedor pagadas en el rango
            domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', '=', 'paid'),
                ('invoice_user_id', '=', rec.user_id.id),
                ('invoice_date', '>=', rec.date_start),
                ('invoice_date', '<=', rec.date_end),
            ]
            moves = rec.env['account.move'].search(domain, order='invoice_date asc, name asc')
            move_ids = moves.ids

            # Normaliza legacy ('efect'/'trans' → 'efectivo'/'transferencia') si existiera
            legacy_map = {'efect': 'efectivo', 'trans': 'transferencia'}
            entries = Entry.search([('move_id', 'in', move_ids),
                                    ('salesperson_id', '=', rec.user_id.id)])
            for e in entries:
                if e.payment_method in legacy_map:
                    e.write({'payment_method': legacy_map[e.payment_method]})

            # Construye comandos según filtro
            cmds = [(5, 0, 0)]
            for m in moves:
                entry = Entry.search([
                    ('move_id', '=', m.id),
                    ('salesperson_id', '=', rec.user_id.id)
                ], limit=1)
                if not entry:
                    entry = Entry.create({
                        'move_id': m.id,
                        'salesperson_id': rec.user_id.id,
                    })

                include = True
                if rec.filter_payment == 'paid':
                    include = bool(entry.commission_paid)
                elif rec.filter_payment == 'unpaid':
                    include = not bool(entry.commission_paid)

                if include:
                    cmds.append((0, 0, {
                        'move_id': m.id,
                        'payment_entry_id': entry.id,
                    }))

            rec.line_ids = cmds

    @api.depends('user_id', 'line_ids', 'line_ids.amount_untaxed', 'line_ids.commission_amount')
    def _compute_totals(self):
        for rec in self:
            rec.commission_percent = (
                rec.user_id.sale_team_id.commission_percent
                if rec.user_id and rec.user_id.sale_team_id else 0.0
            )
            rec.lines_count = len(rec.line_ids)
            rec.amount_total = sum(rec.line_ids.mapped('amount_untaxed')) if rec.line_ids else 0.0
            rec.commission_total = sum(rec.line_ids.mapped('commission_amount')) if rec.line_ids else 0.0

    @api.onchange('user_id', 'date_start', 'date_end')
    def _onchange_filters(self):
        self._load_lines()

    @api.onchange('filter_payment')
    def _onchange_filter_payment(self):
        self._load_lines()

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

    def action_save(self):
        self.ensure_one()
        self.flush()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cambios guardados',
                'message': 'Pagos de comisión actualizados.',
                'sticky': False,
            }
        }

    def action_print_pdf(self):
        self.ensure_one()
        self.flush()
        currency = self.currency_id or self.env.company.currency_id
        decimals = int(getattr(currency, 'decimal_places', 2) or 2)

        def money_str(amount):
            val = currency.round(amount or 0.0)
            s = f"{val:.{decimals}f}"
            return f"{currency.symbol} {s}" if (currency.position or 'after') == 'before' else f"{s} {currency.symbol}"

        lines = self.line_ids  # ya vienen filtradas
        invoice_lines = []
        for line in lines:
            m = line.move_id
            entry = line.payment_entry_id
            pay_dt = ''
            if entry and entry.payment_datetime:
                pay_dt = fields.Datetime.context_timestamp(self, entry.payment_datetime).strftime('%d/%m/%Y %H:%M:%S')
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
                'pay_method': dict(PAYMENT_METHODS).get(entry.payment_method, '') if entry else '',
                'pay_datetime': pay_dt,
                'pay_user': entry.payment_user_id.name if entry and entry.payment_user_id else '',
                'commission_paid': 'Sí' if entry and entry.payment_method else 'No',
            })

        ds = self.date_start.strftime('%d/%m/%Y') if self.date_start else ''
        de = self.date_end.strftime('%d/%m/%Y') if self.date_end else ''

        data = {
            'user_name': self.user_id.name,
            'date_start_str': ds,
            'date_end_str': de,
            'filter_payment': self.filter_payment,
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
        action['close_on_report_download'] = False
        return action


class CommissionReportWizardLine(models.TransientModel):
    _name = 'commission.report.wizard.line'
    _description = 'Línea del reporte de comisión'

    wizard_id = fields.Many2one('commission.report.wizard', required=True, ondelete='cascade')
    move_id = fields.Many2one(
        'account.move', string='Factura', required=True,
        domain=[('move_type', '=', 'out_invoice')]
    )

    # Enlace PERSISTENTE al registro de pago
    payment_entry_id = fields.Many2one(
        'commission.payment.entry', string='Registro de pago', ondelete='cascade'
    )

    # Datos de factura (related)
    partner_id = fields.Many2one(related='move_id.partner_id', store=False)
    invoice_date = fields.Date(related='move_id.invoice_date', store=False)
    amount_untaxed = fields.Monetary(related='move_id.amount_untaxed', currency_field='currency_id', store=False)
    commission_percent = fields.Float(related='move_id.commission_percent', store=False)
    commission_amount = fields.Monetary(related='move_id.commission_amount', currency_field='currency_id', store=False)
    currency_id = fields.Many2one(related='move_id.currency_id', store=False)
    payment_state = fields.Selection(related='move_id.payment_state', string='Estado Pago', store=False)

    # Datos de pago (related al entry, editable)
    payment_method = fields.Selection(
        PAYMENT_METHODS, string='Forma de pago comisión',
        related='payment_entry_id.payment_method', readonly=False
    )
    payment_datetime = fields.Datetime(related='payment_entry_id.payment_datetime', readonly=True)
    payment_user_id = fields.Many2one('res.users', related='payment_entry_id.payment_user_id', readonly=True)

    # Booleano de estado (almacenado en entry)
    commission_paid = fields.Boolean(
        related='payment_entry_id.commission_paid',
        store=True, index=True, readonly=True, string='Comisión pagada'
    )

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        for line in self:
            if line.payment_entry_id and line.payment_method:
                line.payment_entry_id.payment_datetime = fields.Datetime.now()
                line.payment_entry_id.payment_user_id = self.env.user

    @api.model_create_multi
    def create(self, vals_list):
        cleaned = []
        default_wiz = self.env.context.get('default_wizard_id')
        for vals in vals_list:
            if not vals.get('move_id'):
                continue  # evita líneas fantasma
            if not vals.get('wizard_id') and default_wiz:
                vals['wizard_id'] = default_wiz
            cleaned.append(vals)
        if not cleaned:
            return self.browse()
        return super().create(cleaned)

    def write(self, vals):
        res = super().write(vals)
        if 'payment_method' in vals:
            for line in self:
                entry = line.payment_entry_id
                if entry and entry.payment_method and not entry.payment_datetime:
                    entry.write({
                        'payment_datetime': fields.Datetime.now(),
                        'payment_user_id': self.env.user.id,
                    })
        return res


class CommissionPaymentEntry(models.Model):
    _name = 'commission.payment.entry'
    _description = 'Pago de comisión por factura y vendedor'
    _rec_name = 'move_id'

    move_id = fields.Many2one('account.move', string='Factura', required=True, ondelete='cascade')
    salesperson_id = fields.Many2one('res.users', string='Vendedor', required=True, ondelete='cascade')

    payment_method = fields.Selection(PAYMENT_METHODS, string='Forma de pago')
    payment_datetime = fields.Datetime(string='Fecha/Hora pago')
    payment_user_id = fields.Many2one('res.users', string='Registró')
    note = fields.Char(string='Nota')

    commission_paid = fields.Boolean(string='Comisión pagada', compute='_compute_paid', store=True)

    _sql_constraints = [
        ('move_salesperson_uniq',
         'unique(move_id, salesperson_id)',
         'Ya existe un registro de pago de comisión para esa factura y vendedor.'),
    ]

    @api.depends('payment_method')
    def _compute_paid(self):
        for r in self:
            r.commission_paid = bool(r.payment_method)
