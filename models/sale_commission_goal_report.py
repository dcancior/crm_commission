# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝

from odoo import models, fields, tools
from .sale_commission_goal import MONTHS


class SaleCommissionGoalReport(models.Model):
    """Tablero histórico: meta de venta vs. logrado, por vendedor/mes/año.

    Vista SQL de solo lectura (no crea/edita registros): combina las metas
    capturadas en sale.commission.goal con las ventas realmente facturadas
    y pagadas (mismo criterio que commission.report.wizard) para poder
    graficar el histórico por año con las herramientas nativas de Odoo
    (graph/pivot), sin necesidad de recalcular nada en Python por petición.
    """
    _name = 'sale.commission.goal.report'
    _description = 'Histórico de metas de venta vs. logrado'
    _auto = False
    _order = 'year desc, month desc, user_id'

    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    year = fields.Char(string='Año', readonly=True)
    month = fields.Selection(MONTHS, string='Mes', readonly=True)

    amount_goal = fields.Monetary(string='Meta', currency_field='currency_id', readonly=True)
    amount_achieved = fields.Monetary(string='Alcanzado', currency_field='currency_id', readonly=True)
    amount_difference = fields.Monetary(
        string='Diferencia', currency_field='currency_id', readonly=True,
        help='Positivo: superó la meta. Negativo: le faltó para llegar.',
    )
    percent_achieved = fields.Float(
        string='% de la meta', readonly=True, digits=(16, 2), group_operator='avg',
    )
    reached_goal = fields.Boolean(string='Llegó a la meta', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    row_number() OVER (ORDER BY combo.year, combo.month, combo.user_id) AS id,
                    combo.user_id AS user_id,
                    combo.company_id AS company_id,
                    rc.currency_id AS currency_id,
                    combo.year AS year,
                    combo.month AS month,
                    combo.amount_goal AS amount_goal,
                    combo.amount_achieved AS amount_achieved,
                    (combo.amount_achieved - combo.amount_goal) AS amount_difference,
                    CASE WHEN combo.amount_goal > 0
                         THEN (combo.amount_achieved / combo.amount_goal) * 100.0
                         ELSE 0.0
                    END AS percent_achieved,
                    (combo.amount_goal > 0 AND combo.amount_achieved >= combo.amount_goal) AS reached_goal
                FROM (
                    SELECT
                        COALESCE(g.user_id, s.user_id) AS user_id,
                        COALESCE(g.company_id, s.company_id) AS company_id,
                        COALESCE(g.year, s.year) AS year,
                        COALESCE(g.month, s.month) AS month,
                        COALESCE(g.amount_goal, 0.0) AS amount_goal,
                        COALESCE(s.amount_achieved, 0.0) AS amount_achieved
                    FROM sale_commission_goal g
                    FULL OUTER JOIN (
                        SELECT
                            m.invoice_user_id AS user_id,
                            m.company_id AS company_id,
                            to_char(m.invoice_date, 'YYYY') AS year,
                            to_char(m.invoice_date, 'MM') AS month,
                            sum(m.amount_untaxed) AS amount_achieved
                        FROM account_move m
                        WHERE m.move_type = 'out_invoice'
                          AND m.state = 'posted'
                          AND m.payment_state = 'paid'
                          AND m.invoice_user_id IS NOT NULL
                        GROUP BY m.invoice_user_id, m.company_id,
                                 to_char(m.invoice_date, 'YYYY'), to_char(m.invoice_date, 'MM')
                    ) s ON s.user_id = g.user_id
                       AND s.company_id = g.company_id
                       AND s.year = g.year
                       AND s.month = g.month
                ) combo
                LEFT JOIN res_company rc ON rc.id = combo.company_id
                WHERE combo.user_id IN (
                    SELECT ru.id
                    FROM res_users ru
                    JOIN crm_team ct ON ct.id = ru.sale_team_id
                    WHERE ct.name::text ILIKE '%%Ventas%%'
                )
            )
        """ % {'table': self._table})
