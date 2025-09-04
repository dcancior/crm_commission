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

    line_ids = fields.One2many(
        "mechanic.commission.wizard.line",
        "wizard_id",
        string="Pago de comisión por servicio",
        compute="_compute_totals",
        store=False,
        readonly=False,                # <-- permitir edición
        inverse="_inverse_line_ids",   # <-- NECESARIO para que Odoo “acepte” los cambios
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
                else:
                    # Mantén el estado si no se cambió; opcionalmente podrías "despagar" aquí
                    pass

                # Si tocó explícitamente el check de pagado (por si editaste inline en el tree)
                if line.is_paid and not entry.is_paid:
                    vals.setdefault('is_paid', True)
                    vals.setdefault('paid_date', fields.Datetime.now())
                    vals.setdefault('paid_by', self.env.user.id)
                elif (not line.is_paid) and entry.is_paid:
                    vals.update({'is_paid': False, 'paid_date': False, 'paid_by': False})

                if vals:
                    entry.write(vals)

    def action_save_lines(self):
        self.ensure_one()
        # Fuerza a aplicar lo editado en el O2M
        self._inverse_line_ids()

        # (Opcional) refrescar la vista y notificar
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mechanic.commission.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('crm_commission.view_mechanic_commission_wizard_form').id,
            'target': 'new',
            'context': dict(self.env.context, notif_msg='Cambios guardados.'),
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
                ("move_type", "=", "out_invoice"),
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
                # Horas requeridas del servicio y costo/hora desde el template
                hrs_req = (getattr(l.product_id.product_tmpl_id, 'service_hours_required', 0.0) or 0.0)
                cph     = (getattr(l.product_id.product_tmpl_id, 'service_cost_per_hour', 0.0) or 0.0)

                hrs = hrs_req * qty
                payout = cph * hrs  # cph * hrs_req * qty

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
                    'cost_per_hour': cph,
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
                    "paid_date": entry.paid_date,
                    "paid_by": entry.paid_by.id if entry.paid_by else False,
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

        # FACTURAS DEL CLIENTE pagadas
        moves = self.env['account.move'].search([
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
                    and l.mechanic_id.id == self.employee_id.id
        )

        Entry = self.env['mechanic.commission.entry']
        entries_to_keep = self.env['mechanic.commission.entry']

        for line in inv_lines:
            cph = (getattr(line.product_id.product_tmpl_id, 'service_cost_per_hour', 0.0) or 0.0)
            hrs_req = (getattr(line.product_id.product_tmpl_id, 'service_hours_required', 0.0) or 0.0)
            qty = line.quantity or 0.0
            hrs = hrs_req * qty
            payout = cph * hrs

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

        # Filtro de comisión (solo para el árbol del wizard)
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
        # Abre wizard de confirmación para elegir "Efectivo" o "Transferencia"
        return {
            'type': 'ir.actions.act_window',
            'name': 'Marcar todas como pagadas',
            'res_model': 'mechanic.commission.mass.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_entry_ids': [(6, 0, entries.ids)],   # pasa las entradas
                'parent_wizard_id': self.id,                  # para refrescar al cerrar
            }
        }

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

    # Estado de pago (editable: escribe en el persistente y setea metadata abajo)
    is_paid = fields.Boolean(string='Pagado', related='commission_entry_id.is_paid', readonly=False)

    # Fechas/usuario (related, solo lectura) - ¡DATETIME!
    paid_date = fields.Datetime(related='commission_entry_id.paid_date', readonly=True)
    paid_by = fields.Many2one('res.users', related='commission_entry_id.paid_by', readonly=True)

    # Forma de pago: RELATED EDITABLE -> guarda en la entrada persistente
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

            # A) Toggle de pagado desde la UI
            if 'is_paid' in vals:
                if vals['is_paid']:
                    entry.write({
                        'is_paid': True,
                        'paid_date': fields.Datetime.now(),
                        'paid_by': self.env.user.id,
                        # si no trae forma, default efectivo
                        **({} if entry.pago_comision else {'pago_comision': 'efect'}),
                    })
                else:
                    entry.write({
                        'is_paid': False,
                        'paid_date': False,
                        'paid_by': False,
                        # opcional: limpiar forma
                        # 'pago_comision': False,
                    })

            # B) Si el usuario selecciona una forma de pago, forzar pagado + metadata
            if 'pago_comision' in vals and vals['pago_comision']:
                entry.write({
                    'pago_comision': vals['pago_comision'],
                    'is_paid': True,
                    'paid_date': fields.Datetime.now(),
                    'paid_by': self.env.user.id,
                })
            # (Opcional) Si quieres que al limpiar la forma también se "despague":
            # elif 'pago_comision' in vals and not vals['pago_comision']:
            #     entry.write({'pago_comision': False, 'is_paid': False, 'paid_date': False, 'paid_by': False})

        return res


class MechanicCommissionMassPayWizard(models.TransientModel):
    _name = 'mechanic.commission.mass.pay.wizard'
    _description = 'Marcar comisiones pagadas (masivo)'

    entry_ids = fields.Many2many(
        'mechanic.commission.entry',
        'mc_masspay_entry_rel',   # <-- nombre corto para la tabla rel
        'wizard_id',              # <-- columna que apunta al wizard
        'entry_id',               # <-- columna que apunta a mechanic.commission.entry
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
            'paid_date': self.paid_date,          # Datetime (UTC)
            'paid_by': self.env.user.id,
        }
        if self.pay_note:
            vals['pay_note'] = self.pay_note
        self.entry_ids.write(vals)

        # Reabrir el wizard padre para ver los cambios actualizados
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

        # Fallback: cerrar si no hay padre (no debería pasar)
        return {'type': 'ir.actions.act_window_close'}