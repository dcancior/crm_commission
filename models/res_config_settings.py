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
