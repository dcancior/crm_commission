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


class SaleCommissionReport(models.Model):
    """Libro de ventas y comisiones por vendedor: la base del tablero de Vendedores.

    Es el equivalente para vendedores de mechanic.commission.entry, pero como
    vista SQL de solo lectura: toda la información ya vive en account.move
    (commission_percent y commission_amount se guardan ahí), así que no hace
    falta materializar nada ni mantenerlo sincronizado.

    Se incluyen TODAS las facturas de cliente publicadas, no solo las cobradas,
    para poder comparar en el tablero lo facturado contra lo realmente cobrado:
    la comisión solo se gana cuando la factura se paga (mismo criterio que
    commission.report.wizard), así que ver lo que está facturado y sin cobrar
    es justo lo que permite decidir a quién hay que ir a cobrarle.
    """
    _name = 'sale.commission.report'
    _description = 'Ventas y comisiones por vendedor'
    _auto = False
    _order = 'invoice_date desc, id desc'

    move_id = fields.Many2one('account.move', string='Factura', readonly=True)
    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)
    team_id = fields.Many2one('crm.team', string='Equipo de ventas', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)
    invoice_date = fields.Date(string='Fecha de factura', readonly=True)

    amount_untaxed = fields.Monetary(
        string='Venta (base)', currency_field='currency_id', readonly=True,
        help='Importe sin impuestos: es la base sobre la que se calcula la comisión.',
    )
    amount_residual = fields.Monetary(
        string='Pendiente de cobro', currency_field='currency_id', readonly=True,
    )
    commission_percent = fields.Float(string='% Comisión', readonly=True, group_operator='avg')
    commission_amount = fields.Monetary(
        string='Comisión', currency_field='currency_id', readonly=True,
    )

    payment_state = fields.Selection(
        [
            ('not_paid', 'Sin pagar'),
            ('in_payment', 'En proceso de pago'),
            ('paid', 'Pagada'),
            ('partial', 'Parcialmente pagada'),
            ('reversed', 'Revertida'),
            ('invoicing_legacy', 'Facturación heredada'),
        ],
        string='Estado de cobro', readonly=True,
    )
    invoice_paid = fields.Boolean(
        string='Factura cobrada', readonly=True,
        help='Solo las facturas cobradas generan comisión para el vendedor.',
    )
    commission_paid = fields.Boolean(
        string='Comisión pagada al vendedor', readonly=True,
        help='Se marca desde el Reporte de Comisión de Ventas.',
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    m.id                        AS id,
                    m.id                        AS move_id,
                    m.invoice_user_id           AS user_id,
                    m.team_id                   AS team_id,
                    m.partner_id                AS partner_id,
                    m.company_id                AS company_id,
                    m.currency_id               AS currency_id,
                    m.invoice_date              AS invoice_date,
                    m.amount_untaxed            AS amount_untaxed,
                    m.amount_residual           AS amount_residual,
                    m.commission_percent        AS commission_percent,
                    m.commission_amount         AS commission_amount,
                    m.payment_state             AS payment_state,
                    (m.payment_state = 'paid')  AS invoice_paid,
                    COALESCE(e.commission_paid, FALSE) AS commission_paid
                FROM account_move m
                -- La entry de pago de comisión la crea el wizard bajo demanda,
                -- así que puede no existir: LEFT JOIN y COALESCE a FALSE para
                -- que la factura aparezca igual, como comisión aún no pagada.
                LEFT JOIN commission_payment_entry e
                       ON e.move_id = m.id
                      AND e.salesperson_id = m.invoice_user_id
                WHERE m.move_type = 'out_invoice'
                  AND m.state = 'posted'
                  AND m.invoice_user_id IS NOT NULL
            )
        """ % {'table': self._table})
