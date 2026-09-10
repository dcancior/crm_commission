# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Lista de servicios que exigen elegir el mecánico a mano.

Los servicios que estén en esta lista NO reciben el mecánico automáticamente
cuando se asigna uno en la cotización: hay que seleccionarlo en la columna
"Mecánico" de cada línea. Siguen exigiendo mecánico para poder confirmar.

La lista vive en product.template.mechanic_manual_only. Este asistente existe
para que el grupo "Ver Comisiones de Mecánicos" pueda mantenerla sin necesidad
de permisos de escritura sobre el catálogo de productos: el guardado escribe
solo ese campo, con sudo.
"""

from odoo import models, fields, api


class MechanicManualServiceWizard(models.TransientModel):
    _name = 'mechanic.manual.service.wizard'
    _description = 'Servicios con asignación manual de mecánico'

    product_tmpl_ids = fields.Many2many(
        'product.template',
        string='Servicios de asignación manual',
        domain=[('type', '=', 'service')],
        help="Productos de tipo servicio que NO reciben mecánico automáticamente.",
    )

    @api.model
    def default_get(self, fields_list):
        """Precarga la lista actual para poder agregar o quitar servicios."""
        res = super().default_get(fields_list)
        if 'product_tmpl_ids' in fields_list:
            current = self._current_manual_services()
            res['product_tmpl_ids'] = [(6, 0, current.ids)]
        return res

    @api.model
    def _current_manual_services(self):
        return self.env['product.template'].sudo().search([
            ('mechanic_manual_only', '=', True),
        ])

    def action_apply(self):
        """Guarda la lista: marca los agregados y desmarca los que se quitaron."""
        self.ensure_one()
        selected = self.product_tmpl_ids.sudo()
        current = self._current_manual_services()

        to_add = selected - current
        to_remove = current - selected

        if to_add:
            to_add.write({'mechanic_manual_only': True})
        if to_remove:
            to_remove.write({'mechanic_manual_only': False})

        if not (to_add or to_remove):
            message = "No hubo cambios en la lista."
        else:
            partes = []
            if to_add:
                partes.append(f"{len(to_add)} agregado(s)")
            if to_remove:
                partes.append(f"{len(to_remove)} quitado(s)")
            message = " y ".join(partes) + "."

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Servicios de asignación manual',
                'message': message,
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
