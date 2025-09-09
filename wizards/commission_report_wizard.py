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
import base64

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

    # ========= Filtros =========
    user_id = fields.Many2one('res.users', string='Vendedor', required=True)
    date_start = fields.Date(string='Desde', required=True, default=_default_date_start)
    date_end   = fields.Date(string='Hasta', required=True, default=_default_date_end)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError("La fecha final no puede ser menor que la fecha inicial.")

    filter_payment = fields.Selection(
        [('all', 'Todas'), ('paid', 'Pagadas'), ('unpaid', 'No pagadas')],
        string='Filtro pago comisión', default='all'
    )

    # ========= KPIs / Totales =========
    commission_percent = fields.Float(string='Porcentaje Comisión (Equipo)', digits=(16, 2), compute='_compute_totals')
    lines_count = fields.Integer(string='Líneas', compute='_compute_totals')
    amount_total = fields.Float(string='Total Ventas (Base)', digits=(16, 2),
                                currency_field='currency_id', compute='_compute_totals')
    commission_total = fields.Float(string='Total Comisión', digits=(16, 2),
                                    currency_field='currency_id', compute='_compute_totals')

    currency_id = fields.Many2one('res.currency', string='Moneda',
                                  default=lambda self: self.env.company.currency_id)

    # ========= Detalle =========
    line_ids = fields.One2many('commission.report.wizard.line', 'wizard_id')

    # ----------------- UTILIDADES PRIVADAS -----------------

    def _moves_domain(self):
        self.ensure_one()
        return [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', '=', 'paid'),
            ('invoice_user_id', '=', self.user_id.id),
            ('invoice_date', '>=', self.date_start),
            ('invoice_date', '<=', self.date_end),
        ]

    def _iter_moves_with_entries(self, create_missing=True):
        """Devuelve pares (move, entry) de forma eficiente.
        - create_missing=True  -> crea entries faltantes (para UI)
        - create_missing=False -> NO crea (para PDF), evita escrituras en reporte
        """
        self.ensure_one()
        Move = self.env['account.move']
        Entry = self.env['commission.payment.entry']

        # 1) Trae todas las facturas del rango
        moves = Move.search(self._moves_domain(), order='invoice_date asc, name asc')
        if not moves:
            return []

        # 2) Trae todas las entries en un solo query y mapéalas por move_id
        entries = Entry.search([
            ('move_id', 'in', moves.ids),
            ('salesperson_id', '=', self.user_id.id),
        ])
        entry_by_move = {e.move_id.id: e for e in entries}

        # 3) Normaliza legacy en lote (si aplica)
        legacy_map = {'efect': 'efectivo', 'trans': 'transferencia'}
        legacy_to_fix = entries.filtered(lambda e: e.payment_method in legacy_map)
        if legacy_to_fix:
            for e in legacy_to_fix:
                e.payment_method = legacy_map[e.payment_method]

        # 4) Crea en bloque SOLO si se pide (UI); nunca en el PDF
        if create_missing:
            missing_ids = [mid for mid in moves.ids if mid not in entry_by_move]
            if missing_ids:
                new_entries = Entry.create([{
                    'move_id': mid,
                    'salesperson_id': self.user_id.id,
                } for mid in missing_ids])
                entry_by_move.update({e.move_id.id: e for e in new_entries})

        # 5) Ensambla pares en el mismo orden de 'moves'
        return [(m, entry_by_move.get(m.id)) for m in moves if entry_by_move.get(m.id)]

    def _filter_pair_by_selection(self, pair):
        """Aplica el filtro (all/paid/unpaid) sobre (move, entry)."""
        self.ensure_one()
        _m, entry = pair
        if self.filter_payment == 'paid':
            return bool(entry.commission_paid)
        if self.filter_payment == 'unpaid':
            return not bool(entry.commission_paid)
        return True  # all

    # ----------------- CARGA DE LÍNEAS (UI) -----------------

    def _load_lines(self):
        """Reconstruye la tabla en UI respetando el filtro y creando entries faltantes."""
        for rec in self:
            if not (rec.user_id and rec.date_start and rec.date_end):
                continue

            pairs = rec._iter_moves_with_entries(create_missing=True)
            # Aplica el filtro actual del wizard
            pairs = [p for p in pairs if rec._filter_pair_by_selection(p)]

            rec.line_ids = [(5, 0, 0)] + [
                (0, 0, {
                    'move_id': m.id,
                    'payment_entry_id': entry.id,
                })
                for (m, entry) in pairs
            ]

    @api.model_create_multi
    def create(self, vals_list):
        """Asegura que, al crearse el wizard en servidor (al pulsar cualquier botón), las líneas ya queden cargadas."""
        recs = super().create(vals_list)
        for rec in recs:
            try:
                rec._load_lines()
            except Exception:
                # no romper creación del wizard si algo falla cargando líneas
                pass
        return recs

    @api.onchange('user_id', 'date_start', 'date_end', 'filter_payment')
    def _onchange_any_filter(self):
        self._load_lines()

    # ----------------- TOTALES / KPIs -----------------

    @api.depends('user_id', 'line_ids', 'line_ids.amount_untaxed', 'line_ids.commission_amount')
    def _compute_totals(self):
        for rec in self:
            rec.commission_percent = rec.user_id.sale_team_id.commission_percent if rec.user_id and rec.user_id.sale_team_id else 0.0
            rec.lines_count = len(rec.line_ids)
            rec.amount_total = sum(rec.line_ids.mapped('amount_untaxed')) if rec.line_ids else 0.0
            rec.commission_total = sum(rec.line_ids.mapped('commission_amount')) if rec.line_ids else 0.0

    # ----------------- ACCIONES -----------------

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
        # Mantiene filtro y líneas
        self._load_lines()
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
        """Renderiza el PDF en servidor (sin /report/pdf) y dispara descarga directa."""
        self.ensure_one()

        # Solo entradas existentes (no crear al generar PDF)
        pairs = self._iter_moves_with_entries(create_missing=False)
        pairs = [p for p in pairs if self._filter_pair_by_selection(p)]
        if not pairs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Reporte vacío',
                    'message': 'No hay facturas en el rango/filtro seleccionado.',
                    'sticky': False,
                    'type': 'warning',
                }
            }

        currency = self.currency_id or self.env.company.currency_id
        decimals = int(getattr(currency, 'decimal_places', 2) or 2)

        def money_str(amount):
            val = currency.round(amount or 0.0)
            s = f"{val:.{decimals}f}"
            return f"{currency.symbol} {s}" if (currency.position or 'after') == 'before' else f"{s} {currency.symbol}"

        invoice_lines = []
        amount_total = 0.0
        commission_total = 0.0

        for m, entry in pairs:
            amount_total += (m.amount_untaxed or 0.0)
            commission_total += (m.commission_amount or 0.0)
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
            'commission_total': commission_total,
            'commission_total_str': money_str(commission_total),
            'amount_total': amount_total,
            'amount_total_str': money_str(amount_total),
            'commission_percent': self.commission_percent,
            'commission_percent_str': f"{(self.commission_percent or 0.0):.2f}",
            'invoice_lines': invoice_lines,
            'currency': currency,
        }

        # Render QWeb PDF en servidor (sin assets extra/HTTP adicional)
        Report = self.env['ir.actions.report'].sudo().with_context(
            lang=self.env.user.lang or 'es_MX',
            no_abbrev=True,                  # menos procesamiento de cantidades
            discard_logo_check=True,         # evita chequeos extra de logo
        )
        pdf_bytes, _ = Report._render_qweb_pdf('crm_commission.action_commission_report_pdf', [self.id], data=data)

        # Crear attachment y devolver descarga directa
        fname = f"reporte_comisiones_{(self.user_id.name or '').replace(' ', '_')}_{fields.Datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        attachment = self.env['ir.attachment'].create({
            'name': fname,
            'type': 'binary',
            'datas': base64.b64encode(pdf_bytes),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f"/web/content/{attachment.id}?download=true",
            'target': 'self',
        }

    # --------- Botón “Marcar todas como pagadas” ----------
    def action_mark_all_paid(self):
        """
        Abre el wizard masivo con SOLO las entradas pendientes del rango/usuario actual.
        No depende de lo que haya alcanzado a renderizarse en la tabla.
        """
        self.ensure_one()

        pairs = self._iter_moves_with_entries()
        # Sin importar el filtro visual, nos quedamos con las NO pagadas (las que interesa marcar)
        unpaid_entries = self.env['commission.payment.entry'].browse([
            e.id for (_m, e) in pairs if not e.commission_paid
        ])

        if not unpaid_entries:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Marcar como pagadas',
                    'message': 'No hay comisiones pendientes en el rango y vendedor seleccionados.',
                    'sticky': False,
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': 'Marcar todas como pagadas',
            'res_model': 'commission.mass.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_entry_ids': [(6, 0, unpaid_entries.ids)],
                'parent_wizard_id': self.id,
            }
        }


class CommissionReportWizardLine(models.TransientModel):
    _name = 'commission.report.wizard.line'
    _description = 'Línea del reporte de comisión'

    wizard_id = fields.Many2one('commission.report.wizard', required=True, ondelete='cascade')
    move_id = fields.Many2one('account.move', string='Factura', required=True,
                              domain=[('move_type', '=', 'out_invoice')])

    # Enlace PERSISTENTE
    payment_entry_id = fields.Many2one('commission.payment.entry', string='Registro de pago',
                                       ondelete='cascade')

    # Indicador (persistente en entry, reflejado aquí)
    commission_paid = fields.Boolean(
        string='Comisión pagada',
        related='payment_entry_id.commission_paid',
        store=True,
        index=True,
        readonly=True,
    )

    # Datos de factura (related)
    partner_id = fields.Many2one(related='move_id.partner_id', store=False)
    invoice_date = fields.Date(related='move_id.invoice_date', store=False)
    amount_untaxed = fields.Monetary(related='move_id.amount_untaxed', currency_field='currency_id', store=False)
    commission_percent = fields.Float(related='move_id.commission_percent', store=False)
    commission_amount = fields.Monetary(related='move_id.commission_amount', currency_field='currency_id', store=False)
    currency_id = fields.Many2one(related='move_id.currency_id', store=False)
    payment_state = fields.Selection(related='move_id.payment_state', string='Estado Pago', store=False)

    # Datos de pago (RELATED al entry)
    payment_method = fields.Selection(
        PAYMENT_METHODS, string='Forma de pago comisión',
        related='payment_entry_id.payment_method', readonly=False
    )
    payment_datetime = fields.Datetime(related='payment_entry_id.payment_datetime', readonly=True)
    payment_user_id = fields.Many2one('res.users', related='payment_entry_id.payment_user_id', readonly=True)

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        for line in self:
            if line.payment_entry_id and line.payment_method:
                line.payment_entry_id.payment_datetime = fields.Datetime.now()
                line.payment_entry_id.payment_user_id = self.env.user

    @api.model_create_multi
    def create(self, vals_list):
        """Asegura wizard_id/move_id; no crear líneas fantasma."""
        cleaned = []
        default_wiz = self.env.context.get('default_wizard_id')
        for vals in vals_list:
            if not vals.get('move_id'):
                continue
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


# --------- Wizard de pago masivo ----------
class CommissionMassPayWizard(models.TransientModel):
    _name = 'commission.mass.pay.wizard'
    _description = 'Marcar comisiones pagadas (masivo)'

    entry_ids = fields.Many2many(
        'commission.payment.entry',
        'cm_masspay_entry_rel',
        'wizard_id', 'entry_id',
        string='Registros',
        required=True,
    )
    payment_method = fields.Selection(PAYMENT_METHODS, string='Forma de pago', required=True)
    payment_datetime = fields.Datetime(string='Fecha y hora de pago',
                                       default=lambda self: fields.Datetime.now())
    note = fields.Char(string='Nota (opcional)')

    def action_confirm(self):
        self.ensure_one()

        vals = {
            'payment_method': self.payment_method,
            'payment_datetime': self.payment_datetime,
            'payment_user_id': self.env.user.id,
        }
        if self.note:
            vals['note'] = self.note

        # Marca SOLO los no pagados (por seguridad)
        to_write = self.entry_ids.filtered(lambda e: not e.commission_paid)
        if to_write:
            to_write.write(vals)

        # Reabrir/refrescar el wizard padre con datos y KPIs cargados
        parent_id = self.env.context.get('parent_wizard_id')
        if parent_id:
            parent = self.env['commission.report.wizard'].browse(parent_id)
            # refresca líneas en servidor antes de reconstruir la vista
            try:
                parent._load_lines()
            except Exception:
                pass
            return parent.action_refresh()

        return {'type': 'ir.actions.act_window_close'}
