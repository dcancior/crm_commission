# -*- coding: utf-8 -*-
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
    # NUEVO: costo por hora (persistente)
    cost_per_hour = fields.Monetary(string='Costo por hora', currency_field='currency_id')

    subtotal_customer = fields.Monetary(string='Subtotal al cliente', currency_field='currency_id')
    payout = fields.Monetary(string='Comisión del Mecánico', currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id, required=True)

    # Control de pago de la comisión
    is_paid = fields.Boolean(string='Pagado', default=False)
    paid_date = fields.Date(string='Fecha de pago')
    paid_by = fields.Many2one('res.users', string='Pagado por')
    pay_note = fields.Char(string='Nota pago')

    # Auxiliar para filtros por periodo
    month = fields.Char(string='Mes (MM)', size=2, index=True)
    year = fields.Char(string='Año (YYYY)', size=4, index=True)

    _sql_constraints = [
        # Evita duplicados por misma línea de factura para el mismo mecánico
        ('uniq_employee_invoice_line',
         'unique(employee_id, invoice_line_id)',
         'Ya existe una entrada de comisión para esta línea y mecánico.'),
    ]

    @api.constrains('month', 'year')
    def _check_period(self):
        for r in self:
            if r.month and (len(r.month) != 2 or not r.month.isdigit()):
                raise ValidationError(_('Mes inválido: use formato "MM".'))
            if r.year and (len(r.year) != 4 or not r.year.isdigit()):
                raise ValidationError(_('Año inválido: use formato "YYYY".'))
