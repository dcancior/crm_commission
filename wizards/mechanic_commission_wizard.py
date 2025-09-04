# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime
import calendar
import re  # para _get_report_base_filename

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

    # O2M NO compute: lo pobla exclusivamente _onchange_build_lines()
    line_ids = fields.One2many(
        "mechanic.commission.wizard.line",
        "wizard_id",
        string="Pago de comisión por servicio",
        readonly=False,
    )

    # Usuarios permitidos (miembros del equipo "Mecánicos")
    allowed_user_ids = fields.Many2many('res.users', compute='_compute_allowed_user_ids', store=False)
    allowed_employee_ids = fields.Many2many('hr.employee', compute='_compute_allowed_employee_ids', store=False)

    report_paid_filter = fields.Selection(
        [
            ('all', 'Todas'),
            ('paid', 'Pagadas'),
            ('unpaid', 'No pagadas'),
        ],
        string="Filtrar para PDF",
        default='all',
    )

    # --- PERSISTENCIA de lo editado en líneas (forma de pago, pagado, metadata) ---
    def _inverse_line_ids(self):
        for w in self:
            for line in w.line_ids:
                entry = line.commission_entry_id
                if not entry:
                    continue

                vals = {}
                # Si el usuario eligió forma de pago, forzar pagado + metadata
                if line.pago_comision:
                    vals.update({
                        'pago_comision': line.pago_comision,
                        'is_paid': True,
                        'paid_date': fields.Datetime.now(),
                        'paid_by': self.env.user.id,
                    })
                # Si tocó explícitamente el check de pagado (por edición inline)
                if line.is_paid and not entry.is_paid:
                    vals.setdefault('is_paid', True)
                    vals.setdefault('paid_date', fields.Datetime.now())
                    vals.setdefault('paid_by', self.env.user.id)
                elif (not line.is_paid) and entry.is_paid:
                    vals.update({'is_paid': False, 'paid_date': False, 'paid_by': False})

                if vals:
                    entry.write(vals)

    # Botón "Guardar cambios": NO 'reload' (cierra modal). Reabre el MISMO wizard.
    def action_save_lines(self):
        self.ensure_one()
        self._inverse_line_ids()      # persiste pagos/forma/metadata
        self._onchange_build_lines()  # reconstruye el O2M con los entries actuales
        self._compute_totals()        # recalcula KPIs ya mismo

        # Mantiene el modal abierto y evita cierres
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cambios guardados',
                'message': 'Líneas y totales actualizados.',
                'sticky': False,
            }
        }

    @api.depends()
    def _compute_allowed_employee_ids(self):
        Team = self.env['crm.team']
        Employee = self.env['hr.employee']
        team = Team.search([('name', '=', 'Mecánicos')], limit=1) \
            or Team.search([('name', 'ilike', 'mecan')], limit=1)
        emps = Employee.browse([])
        if team:
            member_users = team.member_ids.mapped('user_id')
            if team.user_id:
                member_users |= team.user_id
            if member_users:
                emps = Employee.search([('user_id', 'in', member_users.ids)])
        for w in self:
            w.allowed_employee_ids = emps

    @api.depends()
    def _compute_allowed_user_ids(self):
        Team = self.env['crm.team']
        team = Team.search([('name', '=', 'Mecánicos')], limit=1)
        for w in self:
            if team:
                users = team.member_ids.mapped('user_id')
                if team.user_id:
                    users |= team.user_id
                w.allowed_user_ids = users
            else:
                w.allowed_user_ids = self.env['res.users'].browse([])

    # >>>>>> Calcula KPIs leyendo mechanic.commission.entry (robusto) y respeta el filtro <<<<<<
    @api.depends(
        'employee_id', 'month', 'year', 'report_paid_filter',
        'line_ids', 'line_ids.is_paid', 'line_ids.pago_comision'
    )
    def _compute_totals(self):
        Entry = self.env['mechanic.commission.entry']
        for w in self:
            if not (w.employee_id and w.month and w.year):
                w.services_count = 0
                w.total_hours = 0.0
                w.payout_total = 0.0
                w.amount_invoiced = 0.0
                continue

            year = int(w.year)
            month = int(w.month)
            last_day = calendar.monthrange(year, month)[1]
            date_start = f"{year}-{str(month).zfill(2)}-01"
            date_end = f"{year}-{str(month).zfill(2)}-{last_day}"

            dom = [
                ('employee_id', '=', w.employee_id.id),
                ('invoice_date', '>=', date_start),
                ('invoice_date', '<=', date_end),
            ]
            entries = Entry.search(dom)
            if w.report_paid_filter == 'paid':
                entries = entries.filtered(lambda e: e.is_paid)
            elif w.report_paid_filter == 'unpaid':
                entries = entries.filtered(lambda e: not e.is_paid)

            w.services_count = len(entries)
            w.total_hours = sum(entries.mapped('hours') or [0.0])
            w.payout_total = sum(entries.mapped('payout') or [0.0])
            w.amount_invoiced = sum(entries.mapped('subtotal_customer') or [0.0])

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

        # Aplica filtro para el PDF sobre las líneas del wizard
        line_records = self.line_ids
        if self.report_paid_filter == 'paid':
            line_records = line_records.filtered(lambda r: bool(r.is_paid))
        elif self.report_paid_filter == 'unpaid':
            line_records = line_records.filtered(lambda r: not bool(r.is_paid))

        # KPIs recalculados para el PDF según el filtro
        services_count_pdf = len(line_records)
        total_hours_pdf = sum(line_records.mapped('hours') or [0.0])
        payout_total_pdf = sum(line_records.mapped('payout') or [0.0])
        amount_invoiced_pdf = sum(line_records.mapped('subtotal_customer') or [0.0])

        # Construir líneas para el template desde line_records filtradas
        lines = [{
            "is_paid": bool(l.is_paid),
            "invoice_name": l.invoice_name or "",
            "invoice_date": l.invoice_date or "",
            "product_name": l.product_name or "",
            "quantity": _num(l.quantity, 2),
            "cost_per_hour": _money(l.cost_per_hour),
            "hours": _num(l.hours, 2),
            "subtotal_customer": _money(l.subtotal_customer),
            "payout": _money(l.payout),
            "paid_date": fields.Datetime.to_string(l.paid_date) if l.paid_date else "",
        } for l in line_records]

        month_name = dict(self.fields_get(allfields=["month"])["month"]["selection"]).get(self.month, "") or ""

        data = {
            "employee_name": self.employee_id.name or "",
            "month": self.month or "",
            "month_name": month_name,
            "year": self.year or "",
            "services_count": int(services_count_pdf or 0),
            "total_hours": _num(total_hours_pdf, 2),
            "amount_invoiced": _money(amount_invoiced_pdf),
            "payout_total": _money(payout_total_pdf),
            "lines": lines,
        }
        return self.env.ref('crm_commission.action_mechanic_commission_report').report_action(self, data=data)

    @api.depends("month")
    def _compute_month_name(self):
        sel = dict(MONTHS)
        for w in self:
            w.month_name = sel.get(w.month or "", "")

    # ÚNICO lugar que construye line_ids (blindado y por registro)
    @api.onchange('employee_id', 'month', 'year')
    def _onchange_build_lines(self):
        for w in self:
            lines_cmds = []

            if not (w.employee_id and w.month and w.year):
                w.line_ids = [(5, 0, 0)]
                continue

            year = int(w.year)
            month = int(w.month)
            last_day = calendar.monthrange(year, month)[1]
            date_start = f"{year}-{str(month).zfill(2)}-01"
            date_end = f"{year}-{str(month).zfill(2)}-{last_day}"

            # FACTURAS DEL CLIENTE pagadas
            moves = w.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', '=', 'paid'),
                ('invoice_date', '>=', date_start),
                ('invoice_date', '<=', date_end),
            ])

            # LÍNEAS DE SERVICIO DEL mecánico seleccionado
            inv_lines = moves.mapped('invoice_line_ids').filtered(
                lambda l: l.product_id.type == 'service'
                          and getattr(l, 'mechanic_id', False)
                          and l.mechanic_id.id == w.employee_id.id
            )

            Entry = w.env['mechanic.commission.entry']
            entries_to_keep = Entry.browse()

            for line in inv_lines:
                cph = (getattr(line.product_id.product_tmpl_id, 'service_cost_per_hour', 0.0) or 0.0)
                hrs_req = (getattr(line.product_id.product_tmpl_id, 'service_hours_required', 0.0) or 0.0)
                qty = line.quantity or 0.0
                hrs = hrs_req * qty
                payout = cph * hrs

                vals_base = {
                    'company_id': w.env.company.id,
                    'employee_id': w.employee_id.id,
                    'invoice_id': line.move_id.id,
                    'invoice_line_id': line.id,
                    'invoice_name': f'{line.move_id.name or line.move_id.payment_reference or ""} - {line.move_id.partner_id.display_name}',
                    'invoice_date': line.move_id.invoice_date,
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'quantity': qty,
                    'hours': hrs,
                    'subtotal_customer': line.price_subtotal,
                    'payout': payout,
                    'cost_per_hour': cph,
                    'currency_id': line.currency_id.id or w.env.company.currency_id.id,
                    'month': str(month).zfill(2),
                    'year': str(year),
                }

                entry = Entry.search([
                    ('employee_id', '=', w.employee_id.id),
                    ('invoice_line_id', '=', line.id)
                ], limit=1)
                if entry:
                    entry.write(vals_base)
                else:
                    entry = Entry.create(vals_base)

                entries_to_keep |= entry

            # Construir comandos (aplicando filtro si corresponde)
            # Construir comandos (aplicando filtro si corresponde)
            lines_cmds = [
                (0, 0, {
                    'commission_entry_id': e.id,  # <-- solo esto
                })
                for e in entries_to_keep.sorted(lambda r: (r.invoice_date or fields.Date.today(), r.id))
            ]

            if w.report_paid_filter == 'paid':
                lines_cmds = [cmd for cmd in lines_cmds if cmd and cmd[2] and
                            w.env['mechanic.commission.entry'].browse(cmd[2]['commission_entry_id']).is_paid]
            elif w.report_paid_filter == 'unpaid':
                lines_cmds = [cmd for cmd in lines_cmds if cmd and cmd[2] and
                            not w.env['mechanic.commission.entry'].browse(cmd[2]['commission_entry_id']).is_paid]

            w.line_ids = [(5, 0, 0)] + lines_cmds

        # No llamamos _compute_totals aquí; el cliente lo pedirá al reabrir el form

    @api.onchange('report_paid_filter')
    def _onchange_report_paid_filter(self):
        self._onchange_build_lines()

    def action_mark_all_paid(self):
        self.ensure_one()
        entries = self.line_ids.mapped('commission_entry_id')
        if not entries:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Marcar como pagadas',
                    'message': 'No hay líneas para marcar.',
                    'sticky': False,
                }
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Marcar todas como pagadas',
            'res_model': 'mechanic.commission.mass.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_entry_ids': [(6, 0, entries.ids)],
                'parent_wizard_id': self.id,
            }
        }

    def _get_report_base_filename(self):
        """Nombre del archivo: Reporte de comisiones (Mecánico) AAAA-MM-DD HH-MM"""
        self.ensure_one()
        mech = (self.employee_id.name or "Sin mecanico").strip()
        mech_safe = re.sub(r'[\\/*?:"<>|]', '-', mech)
        dt_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        stamp = dt_local.strftime('%Y-%m-%d %H-%M')
        return f"Reporte de comisiones ({mech_safe}) {stamp}"


class MechanicCommissionWizardLine(models.TransientModel):
    _name = 'mechanic.commission.wizard.line'
    _description = 'Línea wizard comisión mecánicos'

    wizard_id = fields.Many2one('mechanic.commission.wizard', required=True, ondelete='cascade')
    commission_entry_id = fields.Many2one('mechanic.commission.entry', required=True, ondelete='cascade')

    ## Copias para visualización -> AHORA RELATED
    invoice_name = fields.Char(related='commission_entry_id.invoice_name', readonly=True)
    invoice_date = fields.Date(related='commission_entry_id.invoice_date', readonly=True)
    product_name = fields.Char(related='commission_entry_id.product_name', readonly=True)
    quantity = fields.Float(related='commission_entry_id.quantity', readonly=True)
    hours = fields.Float(related='commission_entry_id.hours', readonly=True)
    subtotal_customer = fields.Monetary(related='commission_entry_id.subtotal_customer',
                                        currency_field='currency_id', readonly=True)
    payout = fields.Monetary(related='commission_entry_id.payout',
                            currency_field='currency_id', readonly=True)

    # Usa la moneda de la entrada (más correcto que la del wizard)
    currency_id = fields.Many2one(related='commission_entry_id.currency_id', readonly=True)

    # Ya la tienes related; la dejamos igual
    cost_per_hour = fields.Monetary(
        string='Costo por hora',
        readonly=True,
        currency_field='currency_id',
        related='commission_entry_id.cost_per_hour'
    )

    # Estado de pago (editable)
    is_paid = fields.Boolean(string='Pagado', related='commission_entry_id.is_paid', readonly=False)

    # Metadata pago (solo lectura aquí, se setea al escribir)
    paid_date = fields.Datetime(related='commission_entry_id.paid_date', readonly=True)
    paid_by = fields.Many2one('res.users', related='commission_entry_id.paid_by', readonly=True)

    # Forma de pago (editable, persiste en entry)
    pago_comision = fields.Selection(
        [('efect', 'Efectivo'), ('trans', 'Transferencia')],
        string='Forma de pago',
        related='commission_entry_id.pago_comision',
        readonly=False,
        store=False,
    )

    def write(self, vals):
        res = super().write(vals)
        for line in self:
            entry = line.commission_entry_id
            if not entry:
                continue

            # Toggle desde check
            if 'is_paid' in vals:
                if vals['is_paid']:
                    entry.write({
                        'is_paid': True,
                        'paid_date': fields.Datetime.now(),
                        'paid_by': self.env.user.id,
                        **({} if entry.pago_comision else {'pago_comision': 'efect'}),
                    })
                else:
                    entry.write({
                        'is_paid': False,
                        'paid_date': False,
                        'paid_by': False,
                    })

            # Elegir forma de pago => marcar pagado + metadata
            if 'pago_comision' in vals and vals['pago_comision']:
                entry.write({
                    'pago_comision': vals['pago_comision'],
                    'is_paid': True,
                    'paid_date': fields.Datetime.now(),
                    'paid_by': self.env.user.id,
                })
        return res


class MechanicCommissionMassPayWizard(models.TransientModel):
    _name = 'mechanic.commission.mass.pay.wizard'
    _description = 'Marcar comisiones pagadas (masivo)'

    entry_ids = fields.Many2many(
        'mechanic.commission.entry',
        'mc_masspay_entry_rel',
        'wizard_id',
        'entry_id',
        string='Entradas',
        required=True,
    )
    pago_comision = fields.Selection(
        [('efect', 'Efectivo'), ('trans', 'Transferencia')],
        string='Forma de pago',
        required=True
    )
    paid_date = fields.Datetime(string='Fecha y hora de pago', default=lambda self: fields.Datetime.now())
    pay_note = fields.Char(string='Nota (opcional)')

    def action_confirm(self):
        self.ensure_one()
        vals = {
            'is_paid': True,
            'pago_comision': self.pago_comision,
            'paid_date': self.paid_date,
            'paid_by': self.env.user.id,
        }
        if self.pay_note:
            vals['pay_note'] = self.pay_note
        self.entry_ids.write(vals)

        parent_id = self.env.context.get('parent_wizard_id')
        if parent_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mechanic.commission.wizard',
                'res_id': parent_id,
                'view_mode': 'form',
                'view_id': self.env.ref('crm_commission.view_mechanic_commission_wizard_form').id,
                'target': 'new',
                'context': dict(self.env.context, notif_msg='Comisiones marcadas como pagadas.'),
            }
        return {'type': 'ir.actions.act_window_close'}