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

from lxml import etree

from odoo import models, api

# El cliente serializa como el texto "null" los atributos que no existen en el
# XML del tablero; al releerlos, Odoo intenta evaluarlos como expresión Python
# y revienta con "Name 'null' is not defined".
_NULL_VALUES = ('null', 'undefined', 'none')


class Board(models.AbstractModel):
    _inherit = 'board.board'

    @api.model
    def _arch_preprocessing(self, arch):
        """Limpia los atributos "null" que el cliente graba al guardar el diseño.

        Al guardar, el tablero vuelve a serializar cada panel y escribe
        context="null" (y domain="null") cuando el XML original no traía esos
        atributos. Al volver a abrir el tablero, el cliente evalúa ese texto como
        expresión Python y falla con "Name 'null' is not defined".

        Se quitan en lugar de sustituirlos por {} / [] a propósito: así el panel
        sigue usando el contexto y el dominio de su propia acción.
        """
        arch = super()._arch_preprocessing(arch)
        try:
            root = etree.fromstring(arch)
        except Exception:
            return arch

        limpiado = False
        for node in root.iter('action'):
            for attr in ('context', 'domain'):
                value = (node.get(attr) or '').strip().lower()
                if value in _NULL_VALUES:
                    del node.attrib[attr]
                    limpiado = True

        if not limpiado:
            return arch
        return etree.tostring(root, pretty_print=True, encoding='unicode')

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
