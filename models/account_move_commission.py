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


class AccountMove(models.Model):
    """
    Extensión del modelo `account.move` (facturas y documentos contables)
    para calcular y almacenar una **comisión comercial** a nivel de factura.

    QUÉ HACE:
      - Agrega dos campos:
        * commission_percent (Float, %): Porcentaje de comisión que aplica
          a ESTA factura, tomado del equipo de ventas del usuario asignado
          a la factura (invoice_user_id.sale_team_id.commission_percent).
        * commission_amount (Monetary): Importe de comisión = amount_untaxed
          * (commission_percent / 100).
      - Ambos campos son `store=True`, por lo que quedan persistidos en BD.

    DE DÓNDE VIENE EL %:
      - Del equipo de ventas (sale_team_id) del usuario asignado a la factura
        (invoice_user_id). Si no existe, se usa 0.0.

    CUÁNDO SE RECALCULA:
      - Decorador @api.depends('invoice_user_id', 'amount_untaxed'):
        Se recalcula cuando cambia el usuario de la factura o el subtotal sin impuestos.

    IMPORTANTE:
      - Este cálculo es **comercial** (por factura) y NO interviene en la
        comisión operativa del mecánico por línea. Pueden coexistir sin problema.
      - `commission_amount` se calcula con `amount_untaxed` total de la factura;
        no considera descuentos por línea, impuestos ni productos excluidos.
        Si se requiere granularidad por línea, habría que migrar la lógica
        a nivel de `account.move.line` y sumar.

    POSIBLES MEJORAS FUTURAS (TODO):
      - Hacer que el % se tome del cliente (partner) o de una política por producto.
      - Incluir devoluciones/abonos y recomputar bajo ciertas condiciones.
      - Depender de `invoice_line_ids` para excluir líneas no comisionables.
    """
    _inherit = 'account.move'

    # Porcentaje de comisión que aplica a esta factura.
    # Origen: equipo de ventas (sale_team) del 'invoice_user_id'.
    commission_percent = fields.Float(
        string='Porcentaje Comisión (%)',
        compute='_compute_commission_data',  # se calcula en el método de abajo
        store=True                           # se guarda en BD (útil para reportes)
    )

    # Importe monetario de la comisión comercial calculada.
    # Fórmula: amount_untaxed * (commission_percent / 100)
    commission_amount = fields.Monetary(
        string='Monto Comisión',
        compute='_compute_commission_data',
        store=True,                          # persistido para búsquedas/agrupaciones
        currency_field='currency_id'         # respeta la moneda de la factura
    )

    @api.depends('invoice_user_id', 'amount_untaxed')
    def _compute_commission_data(self):
        """
        Calcula el porcentaje y el monto de comisión de la factura.

        LÓGICA:
          - Si la factura tiene `invoice_user_id` y su `sale_team_id` define
            `commission_percent`, se toma ese valor; en caso contrario, 0.0.
          - Monto de comisión = amount_untaxed * (percent / 100).

        NOTAS:
          - `store=True` → el valor queda persistido; si cambia el % del equipo
            de ventas después, NO se actualiza automáticamente salvo que cambien
            las dependencias (`invoice_user_id` o `amount_untaxed`). Si se requiere
            recálculo retroactivo, se debe forzar recompute explícitamente.
          - amount_untaxed es el subtotal sin impuestos; no incluye impuestos ni retenciones.
        """
        for move in self:
            # Obtiene el % del equipo de ventas del usuario asignado a la factura.
            # Si falta usuario o equipo, usa 0.0 por seguridad.
            percent = (
                move.invoice_user_id.sale_team_id.commission_percent
                if move.invoice_user_id and move.invoice_user_id.sale_team_id
                else 0.0
            )
            move.commission_percent = percent

            # Calcula el importe de comisión en base al subtotal sin impuestos.
            move.commission_amount = move.amount_untaxed * (percent / 100.0)
