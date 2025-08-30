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
    
    # Usuarios permitidos (miembros del equipo "Mecánicos")
    allowed_user_ids = fields.Many2many('res.users', compute='_compute_allowed_user_ids', store=False)

    allowed_employee_ids = fields.Many2many(
        'hr.employee', compute='_compute_allowed_employee_ids', store=False
    )

    report_paid_filter = fields.Selection(
        [
            ('all', 'Todas'),
            ('paid', 'Pagadas'),
            ('unpaid', 'No pagadas'),
        ],
        string="Filtrar para PDF",
        default='all',
    )
    

    @api.depends()
    def _compute_allowed_employee_ids(self):
        Team = self.env['crm.team']
        Employee = self.env['hr.employee']

        # Busca el equipo por nombre (con y sin acento por si acaso)
        team = Team.search([('name', '=', 'Mecánicos')], limit=1) \
               or Team.search([('name', 'ilike', 'mecan')], limit=1)

        # Arranca vacío
        emps = Employee.browse([])

        if team:
            # OJO: En Odoo 16, team.member_ids son registros de crm.team.member.
            # De ahí sacamos los usuarios (res.users) con mapped('user_id')
            member_users = team.member_ids.mapped('user_id')
            # Incluye al líder si aplica
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
            w.allowed_user_ids = team.member_ids if team else self.env['res.users']  # si no hay equipo, quedará vacío


    #@api.depends('line_ids.subtotal_customer', 'line_ids.payout', 'line_ids.hours', 'employee_id', 'month', 'month', 'year' )
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

            moves = self.env["account.move"].search([
                ("move_type", "=", "out_invoice"),     # si quieres incluir devoluciones, usa ['out_invoice','out_refund']
                ("state", "=", "posted"),
                ("payment_state", "=", "paid"),
                ("invoice_date", ">=", date_start),
                ("invoice_date", "<=", date_end),
            ])

            lines = moves.mapped("invoice_line_ids").filtered(
                lambda l: getattr(l, "mechanic_id", False)
                    and l.mechanic_id.id == wiz.employee_id.id
                    and l.product_id.type == "service"
            )

            detail_vals = []
            Entry = self.env['mechanic.commission.entry']

            for l in lines:
                qty = l.quantity or 0.0
                # >>> Definir horas requeridas del servicio y costo/hora desde el template
                hrs_req = (getattr(l.product_id.product_tmpl_id, 'service_hours_required', 0.0) or 0.0)
                cph     = (getattr(l.product_id.product_tmpl_id, 'service_cost_per_hour', 0.0) or 0.0)

                hrs = hrs_req * qty
                payout = cph * hrs  # equivalente a cph * hrs_req * qty

                vals_entry = {
                    'company_id': self.env.company.id,
                    'employee_id': wiz.employee_id.id,
                    'invoice_id': l.move_id.id,
                    'invoice_line_id': l.id,
                    'invoice_name': l.move_id.name or l.move_id.ref or "",
                    'invoice_date': l.move_id.invoice_date,
                    'product_id': l.product_id.id,
                    'product_name': l.product_id.display_name,
                    'quantity': qty,
                    'hours': hrs,
                    'subtotal_customer': l.price_subtotal,
                    'payout': payout,
                    'cost_per_hour': cph,  # << persistimos CPH
                    'currency_id': (l.currency_id.id or self.env.company.currency_id.id),
                    'month': wiz.month,
                    'year': wiz.year,
                }
                entry = Entry.search([
                    ('employee_id', '=', wiz.employee_id.id),
                    ('invoice_line_id', '=', l.id),
                ], limit=1)
                if entry:
                    entry.write(vals_entry)
                else:
                    entry = Entry.create(vals_entry)

                detail_vals.append((0, 0, {
                    "commission_entry_id": entry.id,
                    "invoice_name": entry.invoice_name,
                    "invoice_date": entry.invoice_date,
                    "product_name": entry.product_name,
                    "quantity": entry.quantity,
                    "hours": entry.hours,
                    "cost_per_hour": entry.cost_per_hour,
                    "payout": entry.payout,
                    "subtotal_customer": entry.subtotal_customer,
                    "is_paid": entry.is_paid,
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

        # >>> NUEVO: aplica filtro para el PDF sobre las líneas del wizard
        line_records = self.line_ids
        if self.report_paid_filter == 'paid':
            line_records = line_records.filtered(lambda r: bool(r.is_paid))
        elif self.report_paid_filter == 'unpaid':
            line_records = line_records.filtered(lambda r: not bool(r.is_paid))

        # >>> NUEVO: KPIs recalculados para el PDF según el filtro
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
            "paid_date": fields.Date.to_string(l.paid_date) if l.paid_date else "",
        } for l in line_records]

        month_name = dict(self.fields_get(allfields=["month"])["month"]["selection"]).get(self.month, "") or ""

        data = {
            "employee_name": self.employee_id.name or "",
            "month": self.month or "",
            "month_name": month_name,
            "year": self.year or "",
            # >>> NUEVO: pasar los KPIs del PDF (ya filtrados)
            "services_count": int(services_count_pdf or 0),
            "total_hours": _num(total_hours_pdf, 2),
            "amount_invoiced": _money(amount_invoiced_pdf),
            "payout_total": _money(payout_total_pdf),
            "lines": lines,
            # "currency_id": self.currency_id,  # si tu template usa format_amount
        }

        return self.env.ref('crm_commission.action_mechanic_commission_report').report_action(self, data=data)

    
    @api.depends("month")
    def _compute_month_name(self):
        sel = dict(MONTHS)
        for w in self:
            w.month_name = sel.get(w.month or "", "")

    @api.onchange('employee_id', 'month', 'year')
    def _onchange_build_lines(self):
        if not (self.employee_id and self.month and self.year):
            self.line_ids = [(5, 0, 0)]
            return

        year = int(self.year)
        month = int(self.month)
        last_day = calendar.monthrange(year, month)[1]
        date_start = f"{year}-{str(month).zfill(2)}-01"
        date_end = f"{year}-{str(month).zfill(2)}-{last_day}"

        # 🔧 FACTURAS DEL CLIENTE **PAGADAS** (igual que en _compute_totals)
        moves = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),     # si luego quieres incluir devoluciones, agrega 'out_refund'
            ('state', '=', 'posted'),
            ('payment_state', '=', 'paid'),
            ('invoice_date', '>=', date_start),
            ('invoice_date', '<=', date_end),
        ])

        # 🔧 LÍNEAS DE SERVICIO DEL **MECÁNICO SELECCIONADO**
        inv_lines = moves.mapped('invoice_line_ids').filtered(
            lambda l: l.product_id.type == 'service'
                    and getattr(l, 'mechanic_id', False)
                    and l.mechanic_id.id == self.employee_id.id
        )

        Entry = self.env['mechanic.commission.entry']
        entries_to_keep = self.env['mechanic.commission.entry']

        for line in inv_lines:
            cph = (getattr(line.product_id.product_tmpl_id, 'service_cost_per_hour', 0.0) or 0.0)
            hrs_req = (getattr(line.product_id.product_tmpl_id, 'service_hours_required', 0.0) or 0.0)
            qty = line.quantity or 0.0
            hrs = hrs_req * qty
            payout = cph * hrs  # = cph * hrs_req * qty

            vals_base = {
                'company_id': self.env.company.id,
                'employee_id': self.employee_id.id,
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
                'currency_id': line.currency_id.id or self.env.company.currency_id.id,
                'month': str(month).zfill(2),
                'year': str(year),
            }

            entry = Entry.search([
                ('employee_id', '=', self.employee_id.id),
                ('invoice_line_id', '=', line.id)
            ], limit=1)
            if entry:
                entry.write(vals_base)
            else:
                entry = Entry.create(vals_base)

            entries_to_keep |= entry

        # Construir comandos (sin filtrar aún por comisión)
        lines_cmds = [
            (0, 0, {
                'commission_entry_id': e.id,
                'invoice_name': e.invoice_name,
                'invoice_date': e.invoice_date,
                'product_name': e.product_name,
                'quantity': e.quantity,
                'hours': e.hours,
                'subtotal_customer': e.subtotal_customer,
                'payout': e.payout,
                'cost_per_hour': e.cost_per_hour,
                'is_paid': e.is_paid,
                'paid_date': e.paid_date,
                'paid_by': e.paid_by.id if e.paid_by else False,
            })
            for e in entries_to_keep.sorted(lambda r: (r.invoice_date or fields.Date.today(), r.id))
        ]

        # 🧠 FILTRO DE COMISIÓN (solo para el árbol del wizard)
        if self.report_paid_filter == 'paid':
            lines_cmds = [cmd for cmd in lines_cmds if cmd[2].get('is_paid')]
        elif self.report_paid_filter == 'unpaid':
            lines_cmds = [cmd for cmd in lines_cmds if not cmd[2].get('is_paid')]

        self.line_ids = [(5, 0, 0)] + lines_cmds



    @api.onchange('report_paid_filter')
    def _onchange_report_paid_filter(self):
        # Reconstruye y aplica el filtro sin tocar mes/año/empleado
        self._onchange_build_lines()

    
    def action_mark_all_paid(self):
        self.ensure_one()
        entries = self.line_ids.mapped('commission_entry_id')
        today = fields.Date.context_today(self)
        entries.write({'is_paid': True, 'paid_date': today, 'paid_by': self.env.user.id})


    def _get_report_base_filename(self):
        """Nombre del archivo: Reporte de comisiones (Mecánico) AAAA-MM-DD HH-MM"""
        self.ensure_one()
        mech = (self.employee_id.name or "Sin mecanico").strip()
        mech_safe = re.sub(r'[\\/*?:"<>|]', '-', mech)  # limpia caracteres ilegales
        dt_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        stamp = dt_local.strftime('%Y-%m-%d %H-%M')  # sin dos puntos
        return f"Reporte de comisiones ({mech_safe}) {stamp}"

class MechanicCommissionWizardLine(models.TransientModel):
    _name = 'mechanic.commission.wizard.line'
    _description = 'Línea wizard comisión mecánicos'

    wizard_id = fields.Many2one('mechanic.commission.wizard', required=True, ondelete='cascade')
    commission_entry_id = fields.Many2one('mechanic.commission.entry', required=True, ondelete='cascade')

    # Campos “vistos” en el tree (copiados para visualización)
    invoice_name = fields.Char(string='Factura', readonly=True)
    invoice_date = fields.Date(string='Fecha Factura', readonly=True)
    product_name = fields.Char(readonly=True)
    quantity = fields.Float(string='Cantidad', readonly=True)
    hours = fields.Float(string='Horas', readonly=True)
    subtotal_customer = fields.Monetary(readonly=True, currency_field='currency_id')
    payout = fields.Monetary(readonly=True, string='Comisión', currency_field='currency_id')
    currency_id = fields.Many2one(related='wizard_id.currency_id', store=False, readonly=True)
    cost_per_hour = fields.Monetary(
        string='Costo por hora',
        readonly=True,
        currency_field='currency_id',
        related='commission_entry_id.cost_per_hour'
    )

    # Checkbox editable que escribe en la entrada persistente:
    is_paid = fields.Boolean(string='Pagado', related='commission_entry_id.is_paid', readonly=False)

    # Opcional: acceso a fecha/usuario de pago como related (solo lectura)
    paid_date = fields.Date(related='commission_entry_id.paid_date', readonly=True)
    paid_by = fields.Many2one('res.users', related='commission_entry_id.paid_by', readonly=True)

    def write(self, vals):
        """Si el usuario tilda/destilda 'is_paid', setea metadata de pago."""
        res = super().write(vals)
        if 'is_paid' in vals:
            for line in self:
                entry = line.commission_entry_id
                if entry:
                    if vals['is_paid']:
                        entry.write({
                            'is_paid': True,
                            'paid_date': fields.Date.context_today(self),
                            'paid_by': self.env.user.id,
                        })
                    else:
                        entry.write({
                            'is_paid': False,
                            'paid_date': False,
                            'paid_by': False,
                        })
        return res