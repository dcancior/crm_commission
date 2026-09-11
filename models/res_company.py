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


class ResCompany(models.Model):
    _inherit = 'res.company'

    mechanic_commission_trigger = fields.Selection(
        [
            ('confirm', 'Al confirmar la cotización'),
            ('paid', 'Cuando se paga la factura'),
        ],
        string='Momento de pago de comisión (mecánico)',
        default='paid',
        required=True,
        help="Define cuándo se genera/hace efectiva la comisión del mecánico:\n"
             "- Al confirmar la cotización: se genera al confirmar el pedido de venta.\n"
             "- Cuando se paga la factura: se genera cuando la factura del cliente queda pagada (comportamiento actual).",
    )

    mechanic_commission_calc_method = fields.Selection(
        [
            ('hours_cost', 'Comisión costo por hora'),
            ('percent', 'Comisión por porcentaje'),
        ],
        string='Cálculo de comisión (mecánico)',
        default='hours_cost',
        required=True,
        help="Define cómo se calcula el monto de la comisión del mecánico:\n"
             "- Comisión costo por hora: usa el costo/hora y las horas requeridas definidas "
             "en la ficha del producto (comportamiento actual).\n"
             "- Comisión por porcentaje: usa el % 'Porcentaje mecánico' sobre el precio "
             "unitario del servicio, editable en cada línea de la cotización.",
    )

    mechanic_commission_default_percent = fields.Float(
        string='Porcentaje mecánico general (%)',
        digits=(16, 2),
        default=0.0,
        help="Porcentaje que se aplica a cualquier servicio que no traiga uno propio "
             "en su ficha. Así no hay que capturarlo servicio por servicio: se pone "
             "una vez aquí y cada ficha solo lo sobrescribe si es un caso especial. "
             "Solo se usa cuando el cálculo de comisión es por porcentaje.",
    )

    mechanic_commission_calc_method_since = fields.Date(
        string='Método vigente desde',
        readonly=True,
        help="Fecha en que se eligió el método de cálculo actual. Se actualiza sola "
             "al cambiar el método y sirve para explicar en pantalla desde cuándo "
             "aplica: las comisiones anteriores conservan el método con el que "
             "nacieron.",
    )

    def write(self, vals):
        """Deja constancia de cuándo se cambió el método de cálculo.

        No cambia ningún comportamiento del cálculo: la fecha es solo
        informativa, para poder decirle al dueño del taller desde cuándo rige
        el método que ve en Ajustes. El cálculo en sí no mira esta fecha, sino
        el método que cada comisión guardó al generarse.
        """
        nuevo = vals.get('mechanic_commission_calc_method')
        if nuevo:
            hoy = fields.Date.context_today(self)
            for company in self:
                if company.mechanic_commission_calc_method != nuevo:
                    # super() por compañía: cada una pudo cambiar en fechas distintas.
                    super(ResCompany, company).write(
                        dict(vals, mechanic_commission_calc_method_since=hoy))
                else:
                    super(ResCompany, company).write(vals)
            return True
        return super().write(vals)
