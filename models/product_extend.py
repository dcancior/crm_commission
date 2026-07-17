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
    porcentaje_comision_mecanico = fields.Float(
        string="Porcentaje mecánico (%)",
        help="Porcentaje del precio unitario que se le paga al mecánico como comisión. "
             "Solo se usa si en Configuración el cálculo de comisión es por porcentaje. "
             "Es el valor por defecto; se puede editar por línea en la cotización.",
        digits=(16, 2),
        default=0.0,
    )

    # Refleja el método configurado en la compañía activa; la ficha del producto
    # lo usa para mostrar horas/costo por hora o el porcentaje según corresponda.
    mechanic_commission_calc_method = fields.Selection(
        [
            ('hours_cost', 'Comisión costo por hora'),
            ('percent', 'Comisión por porcentaje'),
        ],
        compute='_compute_mechanic_commission_calc_method',
        string='Cálculo de comisión (mecánico)',
    )

    def _compute_mechanic_commission_calc_method(self):
        method = self.env.company.mechanic_commission_calc_method or 'hours_cost'
        for tmpl in self:
            tmpl.mechanic_commission_calc_method = method
