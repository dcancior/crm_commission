# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import models, fields
from datetime import datetime

MONTHS = [
    ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'), ('04', 'Abril'),
    ('05', 'Mayo'), ('06', 'Junio'), ('07', 'Julio'), ('08', 'Agosto'),
    ('09', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
]


class SaleCommissionGoal(models.Model):
    _name = 'sale.commission.goal'
    _description = 'Meta de venta mensual por vendedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, user_id'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True,
                                 tracking=True)

    # Cualquier usuario interno: es el mismo criterio que usa el Reporte de
    # Comisión de Ventas, que tampoco filtra por equipo. Exigir equipo de ventas
    # dejaba fuera a vendedores reales que no lo tienen asignado.
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        domain="[('share', '=', False)]",
        tracking=True,
    )
    # Rango amplio (varios años atrás) para poder capturar/corregir metas de
    # periodos pasados, no solo del año en curso.
    year = fields.Selection(
        [(str(y), str(y)) for y in range(datetime.now().year - 5, datetime.now().year + 3)],
        string='Año',
        required=True,
        default=lambda self: str(datetime.now().year),
        tracking=True,
    )
    month = fields.Selection(
        MONTHS,
        string='Mes',
        required=True,
        default=lambda self: datetime.now().strftime('%m'),
        tracking=True,
    )
    amount_goal = fields.Monetary(
        string='Meta de venta',
        currency_field='currency_id',
        required=True,
        help='Meta de ventas (base, sin IVA) que debe alcanzar el vendedor en el mes.',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id, required=True
    )

    _sql_constraints = [
        ('uniq_goal_user_month_year_company',
         'unique(user_id, year, month, company_id)',
         'Ya existe una meta para este vendedor en ese mes y año.'),
    ]

    def name_get(self):
        month_labels = dict(MONTHS)
        result = []
        for rec in self:
            label = f"{rec.user_id.name or ''} - {month_labels.get(rec.month, rec.month)} {rec.year}"
            result.append((rec.id, label))
        return result
