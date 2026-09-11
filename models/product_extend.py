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
        help="Porcentaje del precio unitario que se le paga al mecánico como comisión "
             "por este servicio. Si se deja en 0 se aplica el porcentaje general de "
             "Ajustes, así que solo hay que llenarlo cuando este servicio sea una "
             "excepción. Solo se usa si el cálculo de comisión es por porcentaje. "
             "Es el valor por defecto; se puede editar por línea en la cotización.",
        digits=(16, 2),
        # Los servicios nuevos nacen con el general ya escrito: se ve el número
        # que va a aplicar en vez de un 0 que hay que saber interpretar.
        default=lambda self: self.env.company.mechanic_commission_default_percent,
    )

    # Refleja el porcentaje general de la compañía para poder decir en la ficha
    # qué se va a aplicar cuando el servicio no trae uno propio.
    mechanic_commission_default_percent = fields.Float(
        string="Porcentaje mecánico general (%)",
        compute='_compute_mechanic_commission_defaults',
        digits=(16, 2),
    )

    # True cuando este servicio no tiene porcentaje propio y por tanto hereda el
    # general. Se usa solo para mostrar el aviso correcto en la ficha.
    mechanic_usa_porcentaje_general = fields.Boolean(
        compute='_compute_mechanic_commission_defaults',
    )

    @api.depends('porcentaje_comision_mecanico')
    def _compute_mechanic_commission_defaults(self):
        general = self.env.company.mechanic_commission_default_percent or 0.0
        for tmpl in self:
            tmpl.mechanic_commission_default_percent = general
            tmpl.mechanic_usa_porcentaje_general = not tmpl.porcentaje_comision_mecanico

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
