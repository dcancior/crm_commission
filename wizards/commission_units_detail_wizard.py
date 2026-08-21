# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║
# ║  Web: https://www.dcrsoluciones.com                              ║
# ║  Contacto: info@dcrsoluciones.com                                ║
# ║                                                                  ║
# ║  Este módulo está bajo licencia (LGPLv3).                        ║
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║
# ╚══════════════════════════════════════════════════════════════════╝
"""Detalle de unidades vendidas (productos / servicios) de un vendedor.

Se abre desde el "Reporte de Comisión de Ventas", pestaña "Meta de Venta",
al pulsar los indicadores "Productos vendidos" / "Servicios vendidos".
Muestra el desglose por producto, una gráfica de barras y permite descargar
el detalle en PDF.
"""

from markupsafe import Markup, escape

from odoo import models, fields, api

# Colores de las barras según el tipo de unidad
BAR_COLORS = {
    'product': '#4a7ba7',
    'service': '#3f9a8f',
}
MAX_CHART_BARS = 12


class CommissionUnitsDetailWizard(models.TransientModel):
    _name = 'commission.units.detail.wizard'
    _description = 'Detalle de unidades vendidas en el periodo'

    unit_type = fields.Selection(
        [('product', 'Productos'), ('service', 'Servicios')],
        string='Tipo', required=True, default='product', readonly=True,
    )
    user_id = fields.Many2one('res.users', string='Vendedor', readonly=True)
    date_start = fields.Date(string='Desde', readonly=True)
    date_end = fields.Date(string='Hasta', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda',
                                  default=lambda self: self.env.company.currency_id)

    line_ids = fields.One2many('commission.units.detail.line', 'wizard_id', string='Detalle')

    # ===== KPIs =====
    total_qty = fields.Float(string='Unidades totales', compute='_compute_totals', digits=(16, 2))
    total_amount = fields.Monetary(string='Importe sin IVA', compute='_compute_totals',
                                   currency_field='currency_id')
    product_count = fields.Integer(string='Productos distintos', compute='_compute_totals')

    chart_html = fields.Html(string='Gráfica', compute='_compute_chart_html', sanitize=False)

    @api.depends('line_ids.quantity', 'line_ids.amount_untaxed')
    def _compute_totals(self):
        for wiz in self:
            wiz.total_qty = sum(wiz.line_ids.mapped('quantity'))
            wiz.total_amount = sum(wiz.line_ids.mapped('amount_untaxed'))
            wiz.product_count = len(wiz.line_ids)

    @api.depends('line_ids.quantity', 'line_ids.product_name', 'unit_type')
    def _compute_chart_html(self):
        """Gráfica de barras horizontales con los productos más vendidos.

        Se construye con estilos en línea a propósito: así se ve igual en el
        diálogo del backend y dentro del PDF (wkhtmltopdf no carga los assets
        del backend).
        """
        for wiz in self:
            wiz.chart_html = wiz._build_chart_html()

    def _build_chart_html(self, max_bars=MAX_CHART_BARS):
        self.ensure_one()
        lines = self.line_ids[:max_bars]
        if not lines:
            return Markup(
                '<div style="color:#6b7280;font-style:italic;padding:8px 0;">'
                'No hay unidades vendidas en el periodo.</div>'
            )

        color = BAR_COLORS.get(self.unit_type, BAR_COLORS['product'])
        top_qty = max(lines.mapped('quantity') or [0.0]) or 1.0

        bars = []
        for line in lines:
            width = max((line.quantity or 0.0) / top_qty * 100.0, 1.0)
            bars.append(Markup(
                '<div style="margin-bottom:8px;">'
                '<div style="font-size:12px;color:#374151;line-height:1.3;">'
                '<span>{name}</span>'
                '<span style="float:right;font-weight:600;">{qty}</span>'
                '</div>'
                '<div style="background:#e9ecef;border-radius:3px;height:13px;width:100%;">'
                '<div style="background:{color};height:13px;border-radius:3px;width:{width:.1f}%;"></div>'
                '</div>'
                '</div>'
            ).format(
                name=escape(line.product_name or ''),
                qty=escape(f"{line.quantity or 0.0:.2f}"),
                color=color,
                width=width,
            ))

        hidden = len(self.line_ids) - len(lines)
        footer = Markup('')
        if hidden > 0:
            footer = Markup(
                '<div style="font-size:11px;color:#6b7280;margin-top:4px;">'
                'Se muestran los {shown} más vendidos de {total}.</div>'
            ).format(shown=len(lines), total=len(self.line_ids))

        return Markup('<div>{bars}{footer}</div>').format(
            bars=Markup('').join(bars), footer=footer
        )

    # ===== Construcción del detalle =====

    def _build_lines_from(self, report_wizard):
        """Agrupa por producto las líneas de factura del vendedor en el periodo.

        Parte de report_wizard._sold_invoice_lines(), que usa exactamente el
        mismo dominio que los KPIs del reporte, para que los totales cuadren.
        """
        self.ensure_one()
        product_lines, service_lines = report_wizard._sold_invoice_lines()
        source = product_lines if self.unit_type == 'product' else service_lines

        grouped = {}
        for line in source:
            data = grouped.setdefault(line.product_id.id, {
                'product': line.product_id,
                'quantity': 0.0,
                'amount': 0.0,
                'move_ids': set(),
            })
            data['quantity'] += line.quantity or 0.0
            data['amount'] += line.price_subtotal or 0.0
            data['move_ids'].add(line.move_id.id)

        rows = sorted(grouped.values(),
                      key=lambda d: (-d['quantity'], d['product'].display_name or ''))
        total_qty = sum(r['quantity'] for r in rows)

        self.line_ids = [(5, 0, 0)] + [(0, 0, {
            'product_id': r['product'].id,
            'product_name': r['product'].display_name,
            'default_code': r['product'].default_code or '',
            'uom_name': r['product'].uom_id.name or '',
            'quantity': r['quantity'],
            'amount_untaxed': r['amount'],
            'invoice_count': len(r['move_ids']),
            'share': (r['quantity'] / total_qty * 100.0) if total_qty else 0.0,
        }) for r in rows]
        return self

    # ===== Etiquetas / acciones =====

    def _period_label(self):
        self.ensure_one()
        date_start = fields.Date.to_string(self.date_start) if self.date_start else ''
        date_end = fields.Date.to_string(self.date_end) if self.date_end else ''
        return f"{date_start} → {date_end}".strip()

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('crm_commission.action_commission_units_detail_pdf').report_action(self)


class CommissionUnitsDetailLine(models.TransientModel):
    _name = 'commission.units.detail.line'
    _description = 'Línea del detalle de unidades vendidas'
    _order = 'quantity desc, product_name'

    wizard_id = fields.Many2one('commission.units.detail.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    # Copia del nombre para que el PDF no dependa de cambios posteriores
    product_name = fields.Char(string='Producto', readonly=True)
    default_code = fields.Char(string='Referencia', readonly=True)
    uom_name = fields.Char(string='UdM', readonly=True)

    quantity = fields.Float(string='Unidades', readonly=True, digits=(16, 2))
    amount_untaxed = fields.Monetary(string='Importe sin IVA', readonly=True,
                                     currency_field='currency_id')
    invoice_count = fields.Integer(string='Facturas', readonly=True)
    share = fields.Float(string='% del total', readonly=True, digits=(5, 2))

    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)
