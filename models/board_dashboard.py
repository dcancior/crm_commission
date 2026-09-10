# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Soporte para guardar cambios de diseño en los tableros (módulo board).

El tablero guarda la disposición de paneles en una copia por usuario
(ir.ui.view.custom). El cliente web solo envía el id de esa copia, pero el
servidor únicamente la devuelve si YA existe, así que el primer "Cambiar
diseño" de cada usuario fallaba con:

    TypeError: edit_custom() missing 1 required positional argument: 'custom_id'

Aquí se expone el método que crea esa copia la primera vez (lo llama
board_first_save.js) y uno para restablecer el tablero original.
"""

from odoo import models, api


class Board(models.AbstractModel):
    _inherit = 'board.board'

    @api.model
    def ensure_custom_view(self, view_id):
        """Devuelve la copia personalizada del usuario para ese tablero, creándola si falta.

        Su contenido se sobrescribe enseguida con el diseño que envía el cliente;
        lo único importante es que exista para poder guardarlo.
        """
        Custom = self.env['ir.ui.view.custom']
        custom = Custom.search([
            ('user_id', '=', self.env.uid),
            ('ref_id', '=', view_id),
        ], limit=1)
        if not custom:
            view = self.env['ir.ui.view'].sudo().browse(view_id)
            custom = Custom.create({
                'user_id': self.env.uid,
                'ref_id': view_id,
                'arch': view.arch or '',
            })
        return custom.id

    @api.model
    def reset_dashboard(self, xmlid='crm_commission.board_mechanic_dashboard_form'):
        """Borra la personalización del usuario para volver al tablero original.

        Útil cuando alguien deja el tablero a medias o cuando el módulo publica
        paneles nuevos: mientras exista copia personalizada, esos cambios no se ven.
        """
        view = self.env.ref(xmlid, raise_if_not_found=False)
        if view:
            self.env['ir.ui.view.custom'].search([
                ('user_id', '=', self.env.uid),
                ('ref_id', '=', view.id),
            ]).unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
