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


class ResCompany(models.Model):
    _inherit = 'res.company'

    mechanic_commission_trigger = fields.Selection(
        [
            ('confirm', 'Al confirmar la cotización'),
            ('paid', 'Cuando se paga la factura'),
        ],
        string='Momento de pago de comisión (mecánico)',
        default='paid',
        required=True,
        help="Define cuándo se genera/hace efectiva la comisión del mecánico:\n"
             "- Al confirmar la cotización: se genera al confirmar el pedido de venta.\n"
             "- Cuando se paga la factura: se genera cuando la factura del cliente queda pagada (comportamiento actual).",
    )

    mechanic_commission_calc_method = fields.Selection(
        [
            ('hours_cost', 'Costo por hora y horas de reparación'),
            ('percent', 'Porcentaje de comisión'),
        ],
        string='Cálculo de comisión (mecánico)',
        default='hours_cost',
        required=True,
        help="Define cómo se calcula el monto de la comisión del mecánico:\n"
             "- Costo por hora y horas de reparación: usa el costo/hora y las horas requeridas "
             "definidas en la ficha del producto (comportamiento actual).\n"
             "- Porcentaje de comisión: usa un % sobre el subtotal de la línea, definido en la "
             "ficha del producto y editable en la línea de la cotización/factura.",
    )
