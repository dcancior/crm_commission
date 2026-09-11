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


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mechanic_commission_trigger = fields.Selection(
        related='company_id.mechanic_commission_trigger',
        string='Momento de pago de comisión (mecánico)',
        readonly=False,
    )

    mechanic_commission_calc_method = fields.Selection(
        related='company_id.mechanic_commission_calc_method',
        string='Cálculo de comisión (mecánico)',
        readonly=False,
    )

    # Solo lectura: la estampa res.company al detectar el cambio de método.
    mechanic_commission_calc_method_since = fields.Date(
        related='company_id.mechanic_commission_calc_method_since',
        string='Método vigente desde',
        readonly=True,
    )

    # Activan/desactivan de forma independiente el menú y acceso a cada reporte
    # de comisiones para los usuarios internos (grupos definidos en
    # security/mechanic_commission_groups.xml).
    group_mechanic_commission_view = fields.Boolean(
        string='Comisiones Mecánicos',
        implied_group='crm_commission.group_mechanic_commission_view',
        help='Muestra el menú y reporte de Comisiones de Mecánicos a los usuarios internos.',
    )
    group_commission_view = fields.Boolean(
        string='Comisiones de Ventas',
        implied_group='crm_commission.group_commission_view',
        help='Muestra el menú y reporte de Comisiones de Ventas a los usuarios internos.',
    )
