
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MechanicCommissionEntry(models.Model):
    _name = 'mechanic.commission.entry'
    _description = 'Entrada de comisión por servicio mecánico'
    _order = 'invoice_date desc, id desc'
    _rec_name = 'invoice_name'

    
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True,
        help="Compañía a la que pertenece este cálculo de comisión."
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Mecánico',
        required=True,
        index=True,
        help="Empleado (mecánico) que realizó el servicio."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        related='employee_id.user_id',
        store=True,
        help="Usuario del sistema vinculado al empleado (útil para filtros/reportes)."
    )

    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        ondelete='set null',
        index=True,
        help="Factura de cliente donde se facturó el servicio."
    )
    invoice_line_id = fields.Many2one(
        'account.move.line',
        string='Línea de factura',
        ondelete='set null',
        index=True,
        help="Línea de factura asociada a este registro de comisión."
    )
    invoice_name = fields.Char(
        string='Factura (folio/cliente)',
        help="Nombre amigable de la factura, por ejemplo: FOLIO - Cliente."
    )
    invoice_date = fields.Date(
        string='Fecha factura',
        help="Fecha de emisión de la factura (se usa para ordenar/filtrar)."
    )

    product_id = fields.Many2one(
        'product.product',
        string='Servicio',
        index=True,
        help="Producto o servicio de la línea facturada."
    )
    product_name = fields.Char(
        string='Producto/Servicio',
        help="Nombre del producto/servicio al momento de calcular la comisión (snapshot)."
    )
    quantity = fields.Float(
        string='Cantidad',
        digits='Product Unit of Measure',
        help="Cantidad facturada del servicio/producto (unidades)."
    )


    hours = fields.Float(
        string='Horas',
        digits='Product Unit of Measure',
        help="Horas trabajadas reportadas para el servicio (si aplica)."
    )
    cost_per_hour = fields.Monetary(
        string='Costo por hora',
        currency_field='currency_id',
        help="Costo por hora utilizado para calcular la comisión (si aplica)."
    )

    subtotal_customer = fields.Monetary(
        string='Subtotal al cliente',
        currency_field='currency_id',
        help="Subtotal cobrado al cliente por la línea (sin impuestos)."
    )
    payout = fields.Monetary(
        string='Comisión del Mecánico',
        currency_field='currency_id',
        help="Importe de la comisión a pagar al mecánico (resultado calculado)."
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
        help="Moneda para los importes monetarios del registro."
    )

    is_paid = fields.Boolean(
        string='Pagado',
        default=False,
        help="Marcar cuando la comisión haya sido liquidada."
    )
    paid_date = fields.Datetime(
        string='Fecha y hora de pago',
        help="Momento en que se realizó el pago de la comisión."
    )
    paid_by = fields.Many2one(
        'res.users',
        string='Pagado por',
        help="Usuario responsable de registrar el pago (auditoría)."
    )
    pay_note = fields.Char(
        string='Nota pago',
        help="Observaciones o referencia del pago (folio, transferencia, etc.)."
    )

    month = fields.Char(
        string='Mes (MM)',
        size=2,
        index=True,
        help='Mes en formato "MM" (ej. "01" para enero).'
    )
    year = fields.Char(
        string='Año (YYYY)',
        size=4,
        index=True,
        help='Año en formato "YYYY" (ej. "2025").'
    )

    pago_comision = fields.Selection(
        [('efect', 'Efectivo'), ('trans', 'Transferencia')],
        string='Pago comisión',
        help="Método utilizado para pagar la comisión."
    )

    _sql_constraints = [
        (
            'uniq_employee_invoice_line',
            'unique(employee_id, invoice_line_id)',
            'Ya existe una entrada de comisión para esta línea y mecánico.'
        ),
    ]

    @api.constrains('month', 'year')
    def _check_period(self):
        """
        Valida el formato de periodo (si se capturó):
          - month debe ser 'MM' (2 dígitos)
          - year debe ser 'YYYY' (4 dígitos)
        No bloquea si están vacíos: se permiten registros sin periodo definido.
        """
        for r in self:
            if r.month and (len(r.month) != 2 or not r.month.isdigit()):
                raise ValidationError(_('Mes inválido: use formato "MM".'))
            if r.year and (len(r.year) != 4 or not r.year.isdigit()):
                raise ValidationError(_('Año inválido: use formato "YYYY".'))
