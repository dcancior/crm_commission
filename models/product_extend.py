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
        string='% Comisión',
        help='Porcentaje de comisión (ejemplo: ingrese 25 para 25%)',
        digits=(5, 2),  # 5 dígitos en total, 2 decimales
        default=0.0,
    )

    @api.onchange('porcentaje_comision_mecanico')
    def _onchange_porcentaje_comision_mecanico(self):
        """Asegura que el porcentaje se guarde como número entero"""
        for record in self:
            # Si el valor es menor a 1, lo multiplicamos por 100
            if 0 < record.porcentaje_comision_mecanico < 1:
                record.porcentaje_comision_mecanico = record.porcentaje_comision_mecanico * 100
            # Limitar a un máximo de 100%
            elif record.porcentaje_comision_mecanico > 100:
                record.porcentaje_comision_mecanico = 100
