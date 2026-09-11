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
        help="Porcentaje del precio unitario que se le paga al mecánico por este "
             "servicio. Solo se usa cuando arriba está marcado 'Porcentaje propio'. "
             "Puede ser 0: ese servicio no paga comisión al mecánico interno. "
             "Solo aplica si el cálculo de comisión es por porcentaje; se puede "
             "editar por línea en la cotización.",
        digits=(16, 2),
        default=0.0,
    )

    # De dónde sale el % de este servicio. Es un campo aparte y no "0 = hereda"
    # a propósito: un 0 puede ser deliberado. Hay servicios que el taller paga a
    # mecánicos externos y no deben generar comisión a los internos, y eso tiene
    # que poder decirse sin que el sistema lo confunda con "no lo he configurado".
    mechanic_percent_source = fields.Selection(
        [
            ('general', 'Usar el porcentaje general'),
            ('propio', 'Porcentaje propio de este servicio'),
        ],
        string='Porcentaje del mecánico',
        default='general',
        required=True,
        help="Usar el porcentaje general: este servicio sigue el porcentaje definido "
             "en Ajustes, y cambia solo si ese cambia.\n"
             "Porcentaje propio: este servicio usa el porcentaje de abajo, aunque sea "
             "0 (por ejemplo, trabajos que se pagan a un mecánico externo y no generan "
             "comisión para los mecánicos del taller).",
    )

    # Refleja el porcentaje general de la compañía para poder decir en la ficha
    # qué se va a aplicar cuando el servicio sigue al general.
    mechanic_commission_default_percent = fields.Float(
        string="Porcentaje mecánico general (%)",
        compute='_compute_mechanic_commission_defaults',
        digits=(16, 2),
    )

    # El % que de verdad se le va a pagar al mecánico por este servicio.
    mechanic_percent_efectivo = fields.Float(
        string="Porcentaje que se aplica (%)",
        compute='_compute_mechanic_commission_defaults',
        digits=(16, 2),
    )

    @api.depends('porcentaje_comision_mecanico', 'mechanic_percent_source')
    def _compute_mechanic_commission_defaults(self):
        general = self.env.company.mechanic_commission_default_percent or 0.0
        for tmpl in self:
            tmpl.mechanic_commission_default_percent = general
            tmpl.mechanic_percent_efectivo = tmpl._mechanic_effective_percent()

    def _mechanic_effective_percent(self):
        """Porcentaje de comisión que aplica a este servicio.

        Único lugar donde se decide entre el porcentaje general y el propio, para
        que la ficha, la línea de la cotización y el cálculo de la comisión no
        puedan contradecirse.

        Un servicio con porcentaje propio devuelve su valor tal cual, incluido el
        0: significa "este servicio no paga comisión al mecánico interno", no
        "falta configurarlo".
        """
        self.ensure_one()
        if self.mechanic_percent_source == 'propio':
            return self.porcentaje_comision_mecanico or 0.0
        return self.env.company.mechanic_commission_default_percent or 0.0

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
