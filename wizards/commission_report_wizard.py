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
from odoo.exceptions import ValidationError, UserError
import base64
import calendar
from datetime import datetime, date  # ← NUEVO
from dateutil.relativedelta import relativedelta

PAYMENT_METHODS = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
]

# Plazo (en meses desde la fecha de factura) que tiene el cliente para pagar la
# factura COMPLETA. Si no la liquida dentro del plazo, la comisión no es pagadera
# al vendedor: la factura sigue saliendo en el reporte, pero no suma a pagar.
COMMISSION_PAYMENT_TERM_MONTHS = 3

# Límites de consulta para no saturar el servidor. Los administradores de
# sistemas (base.group_system) no tienen estos límites.
REPORT_MAX_RANGE_MONTHS = 3     # tamaño máximo del bloque consultado
REPORT_MAX_HISTORY_MONTHS = 6   # qué tan atrás se puede consultar

# Trimestres que el usuario elige en el reporte: (clave, nombre, primer mes)
QUARTERS = [
    ('q1', 'Enero - Marzo', 1),
    ('q2', 'Abril - Junio', 4),
    ('q3', 'Julio - Septiembre', 7),
    ('q4', 'Octubre - Diciembre', 10),
]

# Etiquetas tal y como se ven en los encabezados de la tabla, para el aviso de
# orden en pantalla. Las claves son los name= de las columnas del tree.
SORT_COLUMN_LABELS = {
    'commission_paid': 'Comisión pagada',
    'commission_payable': 'Pagadera',
    'not_payable_reason': 'Motivo',
    'commission_payable_amount': 'Comisión a pagar',
    'move_id': 'Factura',
    'invoice_date': 'Fecha Factura',
    'invoice_payment_date': 'Fecha de pago',
    'partner_id': 'Cliente',
    'payment_method': 'Forma de pago comisión',
    'payment_datetime': 'Fecha pago comisión',
    'payment_user_id': 'Registró',
    'amount_untaxed': 'Factura sin IVA',
    'commission_percent': '% Comisión',
    'commission_amount': 'Comisión',
}


def current_quarter_key(today):
    return f"q{(today.month - 1) // 3 + 1}"


def quarter_start(day):
    """Primer día del trimestre al que pertenece la fecha."""
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def get_quarter_range(key, today):
    """(inicio, fin) del trimestre `key` en su ocurrencia más reciente ya iniciada.

    En octubre de 2026 los cuatro trimestres son de 2026; en enero de 2027,
    "Enero - Marzo" es de 2027 y los otros tres de 2026. El último día sale de
    calendar.monthrange, que ya considera los años bisiestos.
    """
    first_month = {k: month for k, _label, month in QUARTERS}[key]
    year = today.year if date(today.year, first_month, 1) <= today else today.year - 1
    last_month = first_month + 2
    return (date(year, first_month, 1),
            date(year, last_month, calendar.monthrange(year, last_month)[1]))


def _default_quarter(self):
    return current_quarter_key(fields.Date.context_today(self))

def _default_date_start(self):
    today = fields.Date.context_today(self)
    return get_quarter_range(current_quarter_key(today), today)[0]

def _default_date_end(self):
    today = fields.Date.context_today(self)
    return get_quarter_range(current_quarter_key(today), today)[1]


# ===================== Helper: fecha de pago del cliente =====================
def get_invoice_payment_dates(moves):
    """
    Devuelve {move_id: date} con la fecha en la que cada factura quedó pagada
    por el cliente (la más reciente si hubo pagos parciales), o False si no
    tiene pagos.

    Recorre las conciliaciones de las líneas por cobrar/pagar y toma la fecha
    del asiento 'del otro lado' (pago, nota de crédito...). Trabaja sobre todo
    el recordset a la vez para que el ORM lea en bloque y no factura por
    factura. No usa invoice_payments_widget: en Odoo 16 ya no es JSON y
    calcularlo por factura es mucho más caro.
    """
    result = {m.id: False for m in moves}
    receivable_lines = moves.line_ids.filtered(
        lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
    )
    partials = receivable_lines.matched_debit_ids | receivable_lines.matched_credit_ids
    for pr in partials:
        for line, other_ml in ((pr.debit_move_id, pr.credit_move_id),
                               (pr.credit_move_id, pr.debit_move_id)):
            if line.move_id.id not in result or not other_ml.move_id.date:
                continue
            current = result[line.move_id.id]
            if not current or other_ml.move_id.date > current:
                result[line.move_id.id] = other_ml.move_id.date
    return result


def get_commission_status(move, payment_date):
    """
    Regla de pago de comisión: la factura debe estar pagada COMPLETA por el
    cliente dentro de COMMISSION_PAYMENT_TERM_MONTHS meses desde su fecha.
    Retorna (pagadera: bool, motivo: str). El motivo va vacío si es pagadera.
    """
    if not move.invoice_date:
        return True, ''
    deadline = move.invoice_date + relativedelta(months=COMMISSION_PAYMENT_TERM_MONTHS)
    deadline_str = deadline.strftime('%d/%m/%Y')
    term = f"{COMMISSION_PAYMENT_TERM_MONTHS} meses"
    if move.payment_state == 'paid':
        if payment_date and payment_date > deadline:
            return False, (f"Pagada completa el {payment_date.strftime('%d/%m/%Y')}, "
                           f"fuera del plazo de {term} (vencía el {deadline_str})")
        return True, ''
    if move.payment_state == 'partial':
        return False, f"Pagada solo parcialmente; el plazo de {term} venció el {deadline_str}"
    return False, f"Sin pagar; el plazo de {term} venció el {deadline_str}"


def get_display_reason(reason, entry):
    """Motivo a mostrar en la línea: si la comisión no es pagadera pero ya se le
    pagó al vendedor, se agrega la nota (sigue sin contar para pagar). Si se
    habilitó manualmente, el motivo ya trae esa nota."""
    if reason and entry.commission_paid and not entry.manual_payable:
        return (f"{reason}. Nota: se pagó la comisión y el plazo de los "
                f"{COMMISSION_PAYMENT_TERM_MONTHS} meses ya había vencido")
    return reason
# ============================================================================


class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Wizard para reporte de comisión por rango de fechas'

    # ========= Filtros =========
    user_id = fields.Many2one('res.users', string='Vendedor', required=True)
    # Al elegir un trimestre se llenan Desde/Hasta (ver _onchange_quarter)
    quarter = fields.Selection(selection='_selection_quarters', string='Trimestre',
                               default=_default_quarter)
    date_start = fields.Date(string='Desde', required=True, default=_default_date_start)
    date_end   = fields.Date(string='Hasta', required=True, default=_default_date_end)

    @api.model
    def _selection_quarters(self):
        """Los cuatro trimestres con el año que les toca (ver get_quarter_range)."""
        today = fields.Date.context_today(self)
        return [(key, f"{label} {get_quarter_range(key, today)[0].year}")
                for key, label, _month in QUARTERS]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError("La fecha final no puede ser menor que la fecha inicial.")
            error = rec._range_error()
            if error:
                raise ValidationError(error)

    def _range_error(self):
        """Mensaje si el periodo excede los límites de consulta; False si es válido.

        Evita que un usuario pida un periodo enorme y sature el servidor:
        bloques de máximo REPORT_MAX_RANGE_MONTHS meses y solo dentro de los
        últimos REPORT_MAX_HISTORY_MONTHS meses. Los administradores de
        sistemas no tienen límite (son quienes generan los reportes generales).
        """
        self.ensure_one()
        if not (self.date_start and self.date_end) or self.date_end < self.date_start:
            return False
        if self.env.user.has_group('base.group_system'):
            return False
        ask_admin = "Si necesita un reporte general, solicítelo a su administrador de sistemas."
        if self.date_end > self.date_start + relativedelta(months=REPORT_MAX_RANGE_MONTHS):
            return (f"El periodo seleccionado es demasiado grande: el máximo son "
                    f"{REPORT_MAX_RANGE_MONTHS} meses (un trimestre) por consulta. {ask_admin}")
        # Se cuenta por trimestres completos: se permite todo el trimestre que
        # toca el límite de 6 meses, para que los trimestres no queden cortados.
        oldest = quarter_start(
            fields.Date.context_today(self) - relativedelta(months=REPORT_MAX_HISTORY_MONTHS))
        if self.date_start < oldest:
            return (f"Solo se pueden consultar los últimos {REPORT_MAX_HISTORY_MONTHS} meses "
                    f"(desde el {oldest.strftime('%d/%m/%Y')}). {ask_admin}")
        return False

    # Aviso en pantalla cuando el periodo excede los límites (ver _range_error)
    range_error_msg = fields.Char(string='Periodo no permitido', compute='_compute_range_error_msg')

    filter_payment = fields.Selection(
        [('all', 'Todas'), ('paid', 'Pagadas'), ('unpaid', 'No pagadas'),
         ('not_payable', 'No pagaderas')],
        string='Filtro pago comisión', default='all',
        help="Pagadas / No pagadas: estado del pago de la comisión al vendedor "
             "(No pagadas = pendientes de pagar, solo comisiones pagaderas).\n"
             "No pagaderas: facturas que el cliente no pagó completas dentro de "
             f"{COMMISSION_PAYMENT_TERM_MONTHS} meses."
    )

    # ========= Ordenación de la tabla (se sincroniza al pulsar un encabezado) =========
    # Guarda el criterio de orden elegido en la vista para que el PDF salga en el
    # mismo orden que la tabla. Se rellena desde JS (list_sort_sync.js) y también
    # sirve como orden por defecto del servidor.
    sort_field = fields.Char(string='Ordenar por', default='invoice_date')
    sort_direction = fields.Char(string='Sentido del orden', default='asc')
    # Solo informativo en pantalla (no aparece en el PDF)
    sort_label = fields.Char(string='Orden actual', compute='_compute_sort_label')

    # ========= KPIs / Totales =========
    commission_percent = fields.Float(string='Porcentaje Comisión (Equipo)', digits=(16, 2), compute='_compute_totals')
    lines_count = fields.Integer(string='Líneas', compute='_compute_totals')
    amount_total = fields.Float(string='Total Ventas (Base)', digits=(16, 2),
                                currency_field='currency_id', compute='_compute_totals')
    commission_total = fields.Float(string='Total Comisión', digits=(16, 2),
                                    currency_field='currency_id', compute='_compute_totals')
    # Facturas que salen en el reporte pero cuya comisión no se paga
    not_payable_count = fields.Integer(string='Facturas no pagaderas', compute='_compute_totals')
    commission_not_payable_total = fields.Float(string='Comisión no pagadera', digits=(16, 2),
                                                compute='_compute_totals')

    currency_id = fields.Many2one('res.currency', string='Moneda',
                                  default=lambda self: self.env.company.currency_id)

    # ========= Detalle =========
    line_ids = fields.One2many('commission.report.wizard.line', 'wizard_id')

    # ========= Meta de venta (segunda pestaña) =========
    has_goal = fields.Boolean(string='Tiene meta configurada', compute='_compute_goal_progress')
    goal_total = fields.Monetary(string='Meta del periodo', compute='_compute_goal_progress',
                                  currency_field='currency_id')
    achieved_total = fields.Monetary(string='Alcanzado', compute='_compute_goal_progress',
                                      currency_field='currency_id')
    remaining_total = fields.Monetary(string='Falta para la meta', compute='_compute_goal_progress',
                                       currency_field='currency_id')
    percent_goal = fields.Float(string='% de la meta', compute='_compute_goal_progress', digits=(16, 2))
    qty_products_sold = fields.Float(string='Productos vendidos', compute='_compute_goal_progress',
                                      digits=(16, 2))
    qty_services_sold = fields.Float(string='Servicios vendidos', compute='_compute_goal_progress',
                                      digits=(16, 2))

    # ----------------- UTILIDADES PRIVADAS -----------------

    def _moves_domain(self):
        """Facturas pagadas completas del vendedor en el rango (meta de venta y unidades vendidas)."""
        self.ensure_one()
        return [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', '=', 'paid'),
            ('invoice_user_id', '=', self.user_id.id),
            ('invoice_date', '>=', self.date_start),
            ('invoice_date', '<=', self.date_end),
        ]

    def _report_moves_domain(self):
        """Facturas de la tabla de comisiones: las pagadas completas más las que
        ya rebasaron el plazo de pago sin liquidarse (salen como no pagaderas).
        Las que aún están dentro del plazo sin pagar no se muestran todavía.
        """
        self.ensure_one()
        cutoff = fields.Date.context_today(self) - relativedelta(months=COMMISSION_PAYMENT_TERM_MONTHS)
        return [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_user_id', '=', self.user_id.id),
            ('invoice_date', '>=', self.date_start),
            ('invoice_date', '<=', self.date_end),
            '|',
            ('payment_state', '=', 'paid'),
            '&',
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date', '<', cutoff),
        ]

    def _commission_info(self, pairs):
        """{move_id: (fecha de pago del cliente, pagadera, motivo)} calculado una sola vez.

        Una comisión no pagadera por la regla del plazo se vuelve pagadera si un
        usuario la habilitó manualmente (entry.manual_payable); el motivo
        conserva la causa original y quién/cuándo la habilitó.
        """
        payment_dates = get_invoice_payment_dates(
            self.env['account.move'].concat(*[m for m, _e in pairs]))
        info = {}
        for m, entry in pairs:
            payable, reason = get_commission_status(m, payment_dates[m.id])
            if not payable and entry.manual_payable:
                payable = True
                when = ''
                if entry.manual_payable_datetime:
                    when = fields.Datetime.context_timestamp(
                        self, entry.manual_payable_datetime).strftime('%d/%m/%Y %H:%M')
                reason = (f"{reason}. Habilitada manualmente para pago por "
                          f"{entry.manual_payable_user_id.name or ''} el {when}")
            info[m.id] = (payment_dates[m.id], payable, reason)
        return info

    def _iter_moves_with_entries(self, create_missing=True):
        """Devuelve pares (move, entry) de forma eficiente.
        - create_missing=True  -> crea entries faltantes (para UI)
        - create_missing=False -> NO crea (para PDF), evita escrituras en reporte;
          las facturas sin entry salen con un entry vacío.
        """
        self.ensure_one()
        Move = self.env['account.move']
        Entry = self.env['commission.payment.entry']

        # 1) Trae todas las facturas del rango
        moves = Move.search(self._report_moves_domain(), order='invoice_date asc, name asc')
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
        for legacy, new in legacy_map.items():
            legacy_to_fix = entries.filtered(lambda e: e.payment_method == legacy)
            if legacy_to_fix:
                legacy_to_fix.write({'payment_method': new})

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
        return [(m, entry_by_move.get(m.id, Entry)) for m in moves]

    @api.depends('sort_field', 'sort_direction')
    def _compute_sort_label(self):
        """Texto que explica con qué columna y en qué sentido se está mostrando la tabla."""
        Line = self.env['commission.report.wizard.line']
        for rec in self:
            name = rec.sort_field or ''
            label = SORT_COLUMN_LABELS.get(name)
            if not label:
                field = Line._fields.get(name)
                label = field.string if field else ''
            if not label:
                rec.sort_label = ''
                continue
            sentido = 'descendente' if (rec.sort_direction or 'asc') == 'desc' else 'ascendente'
            rec.sort_label = (
                f"Se muestra ordenado de manera {sentido} por la columna «{label}»"
            )

    def _sort_key_funcs(self, info):
        """Mapa columna de la tabla -> función clave de ordenación sobre (move, entry).

        Las claves coinciden con los name= de las columnas del tree para poder
        reutilizar directamente lo que envía el clic en el encabezado.
        info es el resultado de _commission_info().
        """
        return {
            'commission_paid': lambda m, e: bool(e and e.commission_paid),
            'commission_payable': lambda m, e: info[m.id][1],
            'not_payable_reason': lambda m, e: info[m.id][2],
            'commission_payable_amount': lambda m, e: (m.commission_amount or 0.0) if info[m.id][1] else 0.0,
            'move_id': lambda m, e: (m.name or ''),
            'invoice_date': lambda m, e: m.invoice_date or date.min,
            'invoice_payment_date': lambda m, e: info[m.id][0] or date.min,
            'partner_id': lambda m, e: (m.partner_id.display_name or '').lower(),
            'payment_method': lambda m, e: (e.payment_method or '') if e else '',
            'payment_datetime': lambda m, e: (e.payment_datetime if e and e.payment_datetime else datetime.min),
            'payment_user_id': lambda m, e: ((e.payment_user_id.name or '') if e else '').lower(),
            'amount_untaxed': lambda m, e: m.amount_untaxed or 0.0,
            'commission_percent': lambda m, e: m.commission_percent or 0.0,
            'commission_amount': lambda m, e: m.commission_amount or 0.0,
        }

    def _sort_pairs(self, pairs, info):
        """Ordena los pares (move, entry) según sort_field / sort_direction.

        Si el campo no es ordenable (o no hay ninguno elegido) se respeta el
        orden por defecto de _iter_moves_with_entries: invoice_date asc, name asc.
        """
        self.ensure_one()
        key_func = self._sort_key_funcs(info).get(self.sort_field or '')
        if not key_func:
            return pairs
        reverse = (self.sort_direction or 'asc') == 'desc'
        # Desempate estable por número de factura
        return sorted(pairs, key=lambda p: (key_func(p[0], p[1]), p[0].name or ''), reverse=reverse)

    def _filter_pair_by_selection(self, pair, info):
        """Aplica el filtro (all/paid/unpaid/not_payable) sobre (move, entry)."""
        self.ensure_one()
        m, entry = pair
        payable = info[m.id][1]
        if self.filter_payment == 'paid':
            return bool(entry.commission_paid)
        if self.filter_payment == 'unpaid':
            # Pendientes de pagar al vendedor: solo las pagaderas
            return payable and not bool(entry.commission_paid)
        if self.filter_payment == 'not_payable':
            return not payable
        return True  # all

    def _report_pairs(self, create_missing=True):
        """Pares (move, entry) filtrados y ordenados como en pantalla, más su info de comisión."""
        self.ensure_one()
        pairs = self._iter_moves_with_entries(create_missing=create_missing)
        info = self._commission_info(pairs)
        # Aplica el filtro actual del wizard
        pairs = [p for p in pairs if self._filter_pair_by_selection(p, info)]
        # Aplica el orden elegido en la tabla (mismo que usará el PDF)
        return self._sort_pairs(pairs, info), info

    # ----------------- CARGA DE LÍNEAS (UI) -----------------

    def _load_lines(self):
        """Reconstruye la tabla en UI respetando el filtro y creando entries faltantes."""
        for rec in self:
            if not (rec.user_id and rec.date_start and rec.date_end) or rec._range_error():
                rec.line_ids = [(5, 0, 0)]
                continue

            pairs, info = rec._report_pairs(create_missing=True)

            lines = []
            for m, entry in pairs:
                payment_date, payable, reason = info[m.id]
                lines.append((0, 0, {
                    'move_id': m.id,
                    'payment_entry_id': entry.id,
                    'invoice_payment_date': payment_date,
                    'commission_payable': payable,
                    'not_payable_reason': get_display_reason(reason, entry),
                    'commission_payable_amount': m.commission_amount if payable else 0.0,
                }))
            rec.line_ids = [(5, 0, 0)] + lines

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

    # Nota: sort_field / sort_direction NO disparan recarga de líneas a propósito.
    # El reordenado en pantalla ya lo hace el cliente y recargar aquí borraría
    # ediciones sin guardar (p. ej. la forma de pago de comisión).
    @api.onchange('user_id', 'date_start', 'date_end', 'filter_payment')
    def _onchange_any_filter(self):
        # Con un periodo fuera de límites _load_lines no consulta nada (deja la
        # tabla vacía) y el formulario muestra range_error_msg. No se usa un
        # aviso emergente porque saltaría a mitad de la edición (p. ej. al mover
        # la fecha inicial antes que la final).
        # Si el usuario edita las fechas a mano, el trimestre deja de aplicar.
        if self.quarter and (self.date_start, self.date_end) != get_quarter_range(
                self.quarter, fields.Date.context_today(self)):
            self.quarter = False
        self._load_lines()

    # Odoo encadena el onchange: al cambiar Desde/Hasta aquí, se ejecuta
    # _onchange_any_filter y se recarga la tabla.
    @api.onchange('quarter')
    def _onchange_quarter(self):
        if self.quarter:
            self.date_start, self.date_end = get_quarter_range(
                self.quarter, fields.Date.context_today(self))

    @api.depends('date_start', 'date_end')
    def _compute_range_error_msg(self):
        for rec in self:
            rec.range_error_msg = rec._range_error() or False

    # ----------------- TOTALES / KPIs -----------------

    @api.depends('user_id', 'line_ids', 'line_ids.amount_untaxed', 'line_ids.commission_amount',
                 'line_ids.commission_payable')
    def _compute_totals(self):
        """Solo las comisiones pagaderas cuentan para pagar al vendedor."""
        for rec in self:
            rec.commission_percent = rec.user_id.sale_team_id.commission_percent if rec.user_id and rec.user_id.sale_team_id else 0.0
            payable_lines = rec.line_ids.filtered('commission_payable')
            not_payable_lines = rec.line_ids - payable_lines
            rec.lines_count = len(rec.line_ids)
            rec.amount_total = sum(payable_lines.mapped('amount_untaxed'))
            rec.commission_total = sum(payable_lines.mapped('commission_amount'))
            rec.not_payable_count = len(not_payable_lines)
            rec.commission_not_payable_total = sum(not_payable_lines.mapped('commission_amount'))

    @staticmethod
    def _months_in_range(date_start, date_end):
        """Lista de tuplas ('YYYY', 'MM') cubiertas por [date_start, date_end]."""
        months = []
        if not (date_start and date_end):
            return months
        y, m = date_start.year, date_start.month
        while (y, m) <= (date_end.year, date_end.month):
            months.append((str(y), str(m).zfill(2)))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return months

    def _sold_invoice_lines(self, moves=None):
        """Líneas de factura vendidas en el periodo, separadas en (productos, servicios).

        Usa el mismo dominio que los KPIs (_moves_domain), por lo que el detalle
        siempre cuadra con "Productos vendidos" / "Servicios vendidos".
        """
        self.ensure_one()
        AML = self.env['account.move.line']
        if not (self.user_id and self.date_start and self.date_end) or self._range_error():
            return AML, AML

        if moves is None:
            moves = self.env['account.move'].search(self._moves_domain())

        lines = moves.mapped('invoice_line_ids').filtered(
            lambda l: l.product_id and l.display_type not in ('line_section', 'line_note')
        )
        service_lines = lines.filtered(lambda l: l.product_id.type == 'service')
        return (lines - service_lines), service_lines

    @api.depends('user_id', 'date_start', 'date_end')
    def _compute_goal_progress(self):
        """Avance de la meta de venta del vendedor para el rango seleccionado.

        El "alcanzado" se calcula sobre TODAS las facturas pagadas del vendedor
        en el rango (mismo dominio que _moves_domain), sin importar el filtro
        de "pago de comisión" (filter_payment), que solo aplica a la tabla de
        facturas de abajo.
        """
        Goal = self.env['sale.commission.goal']
        for rec in self:
            rec.has_goal = False
            rec.goal_total = 0.0
            rec.achieved_total = 0.0
            rec.remaining_total = 0.0
            rec.percent_goal = 0.0
            rec.qty_products_sold = 0.0
            rec.qty_services_sold = 0.0

            if not (rec.user_id and rec.date_start and rec.date_end) or rec._range_error():
                continue

            periods = rec._months_in_range(rec.date_start, rec.date_end)
            if periods:
                goals = Goal.search([
                    ('user_id', '=', rec.user_id.id),
                    ('company_id', '=', rec.env.company.id),
                ])
                applicable = goals.filtered(lambda g: (g.year, g.month) in periods)
                rec.goal_total = sum(applicable.mapped('amount_goal'))
                rec.has_goal = bool(applicable)

            moves = self.env['account.move'].search(rec._moves_domain())
            rec.achieved_total = sum(moves.mapped('amount_untaxed'))
            rec.remaining_total = max(rec.goal_total - rec.achieved_total, 0.0)
            if rec.goal_total:
                rec.percent_goal = (rec.achieved_total / rec.goal_total) * 100.0

            product_lines, service_lines = rec._sold_invoice_lines(moves=moves)
            rec.qty_services_sold = sum(service_lines.mapped('quantity'))
            rec.qty_products_sold = sum(product_lines.mapped('quantity'))

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

    def action_back_to_report(self):
        """Botón "Regresar" de la pestaña Meta de Venta: reabre el reporte, que
        siempre abre en la primera pestaña (Facturas Comisionadas)."""
        action = self.action_refresh()
        action['name'] = 'Reporte de Comisión de Ventas'
        return action

    def action_save(self):
        self.ensure_one()
        self.env.flush_all()
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

    def action_view_products_sold(self):
        """Detalle de los productos vendidos en el periodo (clic en el KPI)."""
        return self._action_open_units_detail('product')

    def action_view_services_sold(self):
        """Detalle de los servicios vendidos en el periodo (clic en el KPI)."""
        return self._action_open_units_detail('service')

    def _action_open_units_detail(self, unit_type):
        self.ensure_one()
        detail = self.env['commission.units.detail.wizard'].create({
            'unit_type': unit_type,
            'user_id': self.user_id.id,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'currency_id': (self.currency_id or self.env.company.currency_id).id,
            'report_wizard_id': self.id,
        })
        detail._build_lines_from(self)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Productos vendidos' if unit_type == 'product' else 'Servicios vendidos',
            'res_model': 'commission.units.detail.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('crm_commission.view_commission_units_detail_form').id,
            'res_id': detail.id,
            'target': 'new',
        }

    def action_print_pdf(self):
        """Renderiza el PDF en servidor (sin /report/pdf) y dispara descarga directa."""
        self.ensure_one()

        # El wizard ya se guardó al pulsar el botón (y pasó _check_dates); esto es
        # solo por si se llama desde código con un periodo fuera de límites.
        error = self._range_error()
        if error:
            raise UserError(error)

        # Solo entradas existentes (no crear al generar PDF); respeta el filtro y
        # el orden con el que el usuario dejó la tabla en pantalla
        pairs, info = self._report_pairs(create_missing=False)
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
        not_payable_count = 0
        commission_not_payable_total = 0.0

        for m, entry in pairs:
            inv_paid_date, payable, reason = info[m.id]
            # Solo las comisiones pagaderas suman para pagar al vendedor
            if payable:
                amount_total += (m.amount_untaxed or 0.0)
                commission_total += (m.commission_amount or 0.0)
            else:
                not_payable_count += 1
                commission_not_payable_total += (m.commission_amount or 0.0)

            # Fecha de pago del cliente (NUEVO)
            inv_paid_date_str = inv_paid_date.strftime('%d/%m/%Y') if inv_paid_date else ''

            # Fecha/hora del registro de pago de comisión (ya existente)
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

                # Comisión (existente)
                'pay_method': dict(PAYMENT_METHODS).get(entry.payment_method, '') if entry else '',
                'pay_datetime': pay_dt,
                'pay_user': entry.payment_user_id.name if entry and entry.payment_user_id else '',
                'commission_paid': 'Sí' if entry and entry.payment_method else 'No',

                # NUEVO: fecha de pago por el cliente
                'invoice_payment_date': inv_paid_date_str,

                # Comisión no pagadera (factura no liquidada en plazo) y su motivo
                'payable': payable,
                'not_payable_reason': get_display_reason(reason, entry),
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
            'not_payable_count': not_payable_count,
            'commission_not_payable_total_str': money_str(commission_not_payable_total),
            'payment_term_months': COMMISSION_PAYMENT_TERM_MONTHS,
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
        info = self._commission_info(pairs)
        # Sin importar el filtro visual, nos quedamos con las NO pagadas (las que
        # interesa marcar) y solo si la comisión es pagadera
        unpaid_entries = self.env['commission.payment.entry'].browse([
            e.id for (m, e) in pairs if info[m.id][1] and not e.commission_paid
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

    # --------- Botón “Habilitar pago (plazo vencido)” ----------
    def action_open_enable_payment(self):
        """Abre el diálogo para habilitar manualmente comisiones no pagaderas.

        No es un botón por fila porque Odoo 16 no permite botones en filas de
        una tabla que aún no está guardada (las líneas se generan en onchange).
        Aquí el diálogo se crea ya guardado, así que sus casillas funcionan.
        """
        self.ensure_one()
        pairs = self._iter_moves_with_entries()
        info = self._commission_info(pairs)
        not_payable = [(m, e) for (m, e) in pairs if not info[m.id][1]]

        if not not_payable:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Habilitar pago',
                    'message': 'No hay comisiones no pagaderas en el periodo y vendedor seleccionados.',
                    'sticky': False,
                }
            }

        enable_wizard = self.env['commission.enable.payment.wizard'].create({
            'report_wizard_id': self.id,
            'line_ids': [(0, 0, {
                'entry_id': e.id,
                'reason': get_display_reason(info[m.id][2], e),
            }) for (m, e) in not_payable],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Habilitar pago de comisiones no pagaderas',
            'res_model': 'commission.enable.payment.wizard',
            'view_mode': 'form',
            'res_id': enable_wizard.id,
            'target': 'new',
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
    # store=True para que la columna se pueda ordenar (clic en el encabezado);
    # Odoo solo permite ordenar por columnas de campos almacenados.
    invoice_date = fields.Date(related='move_id.invoice_date', store=True)
    amount_untaxed = fields.Monetary(related='move_id.amount_untaxed', currency_field='currency_id', store=False)
    commission_percent = fields.Float(related='move_id.commission_percent', store=False)
    commission_amount = fields.Monetary(related='move_id.commission_amount', currency_field='currency_id', store=False)
    currency_id = fields.Many2one(related='move_id.currency_id', store=False)
    payment_state = fields.Selection(related='move_id.payment_state', string='Estado Pago', store=False)

    # NUEVO: fecha en que el cliente pagó la factura (la más reciente si hubo pagos parciales)
    # Campo almacenado para que la columna se pueda ordenar (clic en el encabezado);
    # lo rellena _load_lines en bloque cada vez que se reconstruyen las líneas.
    invoice_payment_date = fields.Date(string='Fecha de pago (cliente)', readonly=True)

    # Regla de pago: la factura debe pagarse completa dentro del plazo. Las que
    # no, salen en la tabla pero no suman para pagar al vendedor. Los rellena
    # _load_lines (ver get_commission_status).
    commission_payable = fields.Boolean(string='Pagadera', readonly=True, default=True)
    # Motivo de no pagadera, o la nota de quién/cuándo la habilitó manualmente
    not_payable_reason = fields.Char(string='Motivo', readonly=True)
    commission_payable_amount = fields.Monetary(string='Comisión a pagar', readonly=True,
                                                currency_field='currency_id')
    manual_payable = fields.Boolean(related='payment_entry_id.manual_payable', readonly=True)

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
        if vals.get('payment_method') and self.filtered(lambda l: not l.commission_payable):
            raise UserError("No se puede registrar el pago de una comisión no pagadera "
                            "(la factura no se pagó completa dentro del plazo).")
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

    # Habilitación manual de una comisión no pagadera (plazo de pago vencido).
    # La pone el botón "Habilitar pago" del reporte; queda quién y cuándo.
    manual_payable = fields.Boolean(string='Pago habilitado manualmente', readonly=True)
    manual_payable_user_id = fields.Many2one('res.users', string='Habilitó', readonly=True)
    manual_payable_datetime = fields.Datetime(string='Fecha habilitación', readonly=True)

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


# --------- Wizard: habilitar pago de comisiones no pagaderas ----------
class CommissionEnablePaymentWizard(models.TransientModel):
    _name = 'commission.enable.payment.wizard'
    _description = 'Habilitar pago de comisiones no pagaderas'

    report_wizard_id = fields.Many2one('commission.report.wizard', string='Reporte',
                                       readonly=True, ondelete='cascade')
    line_ids = fields.One2many('commission.enable.payment.wizard.line', 'wizard_id',
                               string='Comisiones no pagaderas')

    def action_select_all(self):
        self.ensure_one()
        self.line_ids.write({'selected': True})
        return self._reopen()

    def action_confirm(self):
        """Habilita las seleccionadas y registra quién y cuándo lo hizo."""
        self.ensure_one()
        entries = self.line_ids.filtered('selected').entry_id.filtered(lambda e: not e.manual_payable)
        if not self.line_ids.filtered('selected'):
            raise UserError("Seleccione al menos una comisión para habilitar.")
        if entries:
            entries.write({
                'manual_payable': True,
                'manual_payable_user_id': self.env.user.id,
                'manual_payable_datetime': fields.Datetime.now(),
            })
        return self.action_back_to_report()

    def action_back_to_report(self):
        self.ensure_one()
        if not self.report_wizard_id:
            return {'type': 'ir.actions.act_window_close'}
        return self.report_wizard_id.action_back_to_report()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Habilitar pago de comisiones no pagaderas',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class CommissionEnablePaymentWizardLine(models.TransientModel):
    _name = 'commission.enable.payment.wizard.line'
    _description = 'Comisión no pagadera a habilitar'

    wizard_id = fields.Many2one('commission.enable.payment.wizard', required=True, ondelete='cascade')
    selected = fields.Boolean(string='Habilitar')
    entry_id = fields.Many2one('commission.payment.entry', required=True, readonly=True, ondelete='cascade')
    move_id = fields.Many2one(related='entry_id.move_id', string='Factura')
    invoice_date = fields.Date(related='entry_id.move_id.invoice_date', string='Fecha Factura')
    partner_id = fields.Many2one(related='entry_id.move_id.partner_id', string='Cliente')
    currency_id = fields.Many2one(related='entry_id.move_id.currency_id')
    commission_amount = fields.Monetary(related='entry_id.move_id.commission_amount',
                                        currency_field='currency_id', string='Comisión')
    reason = fields.Char(string='Motivo', readonly=True)
