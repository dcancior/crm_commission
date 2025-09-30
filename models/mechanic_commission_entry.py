# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class MechanicCommissionEntry(models.Model):
    _name = 'mechanic.commission.entry'
    _description = 'Entrada de comisión por servicio mecánico'
    _order = 'invoice_date desc, id desc'
    _rec_name = 'invoice_name'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)

    employee_id = fields.Many2one('hr.employee', string='Mecánico', required=True, index=True)
    user_id = fields.Many2one('res.users', string='Usuario', related='employee_id.user_id', store=True)

    invoice_id = fields.Many2one('account.move', string='Factura', ondelete='set null', index=True)
    invoice_line_id = fields.Many2one('account.move.line', string='Línea de factura', ondelete='set null', index=True)
    invoice_name = fields.Char(string='Factura (folio/cliente)')
    invoice_date = fields.Date(string='Fecha factura')

    product_id = fields.Many2one('product.product', string='Servicio', index=True)
    product_name = fields.Char(string='Producto/Servicio')
    quantity = fields.Float(string='Cantidad', digits='Product Unit of Measure')
    hours = fields.Float(string='Horas', digits='Product Unit of Measure')

    # Persistencia de costos (si los usas)
    cost_per_hour = fields.Monetary(string='Costo por hora', currency_field='currency_id')
    price_unit = fields.Float(string='Precio Unitario', digits='Product Price', help='Precio unitario del servicio')

    # --- Porcentaje de comisión del MECÁNICO (en %) ---
    porcentaje_comision_mecanico = fields.Float(
        string='% Comisión mecánico',
        digits=(16, 2),
        help='Porcentaje de comisión para mecánicos (ejemplo: 50 = 50%).',
    )

    # Monto calculado de la comisión (compute sobre subtotal * %)
    commission_amount = fields.Monetary(
        string='Monto Comisión',
        currency_field='currency_id',
        compute='_compute_commission_amount',
        store=True
    )

    @api.onchange('porcentaje_comision_mecanico')
    def _onchange_normalize_pct(self):
        """Si capturan decimal (0.15), normaliza a % (15)."""
        for r in self:
            if r.porcentaje_comision_mecanico and 0 < r.porcentaje_comision_mecanico <= 1:
                r.porcentaje_comision_mecanico *= 100.0
            elif r.porcentaje_comision_mecanico and r.porcentaje_comision_mecanico > 100:
                r.porcentaje_comision_mecanico = 100.0

    @api.depends('subtotal_customer', 'porcentaje_comision_mecanico')
    def _compute_commission_amount(self):
        for record in self:
            subtotal = record.subtotal_customer or 0.0
            pct = record.porcentaje_comision_mecanico or 0.0  # en %
            record.commission_amount = subtotal * (pct / 100.0)

    subtotal_customer = fields.Monetary(string='Subtotal al cliente', currency_field='currency_id')
    payout = fields.Monetary(string='Comisión del Mecánico', currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id, required=True)

    # Control de pago
    is_paid = fields.Boolean(string='Pagado', default=False)
    paid_date = fields.Datetime(string='Fecha y hora de pago')
    paid_by = fields.Many2one('res.users', string='Pagado por')
    pay_note = fields.Char(string='Nota pago')

    # Filtros por periodo
    month = fields.Char(string='Mes (MM)', size=2, index=True)
    year = fields.Char(string='Año (YYYY)', size=4, index=True)

    pago_comision = fields.Selection(
        [('efect', 'Efectivo'), ('trans', 'Transferencia')],
        string='Pago comisión'
    )

    _sql_constraints = [
        ('uniq_employee_invoice_line',
         'unique(employee_id, invoice_line_id)',
         'Ya existe una entrada de comisión para esta línea y mecánico.'),
    ]

    payment_state = fields.Selection(related='invoice_id.payment_state', store=True)

    @api.constrains('month', 'year')
    def _check_period(self):
        for r in self:
            if r.month and (len(r.month) != 2 or not r.month.isdigit()):
                raise ValidationError(_('Mes inválido: use formato "MM".'))
            if r.year and (len(r.year) != 4 or not r.year.isdigit()):
                raise ValidationError(_('Año inválido: use formato "YYYY".'))
