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

class ProductTemplate(models.Model):
    _inherit = "product.template"

    service_hours_required = fields.Float(
        string="Horas requeridas",
        help="Horas estimadas para realizar el servicio por unidad.",
        digits=(16, 2),
        default=0.0,
    )
    service_cost_per_hour = fields.Float(
        string="Costo por hora (mecánico)",
        help="Costo que se paga al mecánico por hora para este servicio.",
        digits=(16, 2),
        default=0.0,
    )
    mechanic_commission_percent = fields.Float(
        string="Comisión mecánico (%)",
        help="Porcentaje de comisión que se le paga al mecánico sobre el subtotal de la línea. "
             "Solo se usa si en Configuración se eligió el cálculo de comisión por porcentaje. "
             "Es el valor por defecto; se puede editar por línea en la cotización.",
        digits=(16, 2),
        default=0.0,
    )

