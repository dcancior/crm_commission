# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountMoveLine(models.Model):
    """
    Cambiamos la lógica:
      - ANTES: comisión = horas_requeridas * costo_por_hora * cantidad  (solo para servicios)
      - AHORA: comisión = (list_price * porcentaje_comision/100) * cantidad  (solo para servicios)

    Importante:
      - Mantenemos el resultado en el MISMO campo: mechanic_cost_subtotal
        => No rompe vistas ni reportes que ya lo usan.
      - Los campos 'meta' se siguen mostrando (si existen en vistas), pero ahora calculan 0.
    """
    _inherit = "account.move.line"

    mechanic_id = fields.Many2one(
        "hr.employee",              # ← posicional primero
        string="Mecánico",
        help="Mecánico que realizó el servicio.",
        index=True,
        copy=False,
    )

    # ─────────────────────────────────────────────────────────────
    # META (deprecado lógicamente): ahora siempre 0 para evitar ruido
    # ─────────────────────────────────────────────────────────────
    mechanic_hours_required = fields.Float(
        string="Horas requeridas (x unidad)",
        compute="_compute_mechanic_meta",
        store=False,
        digits=(16, 2),
    )
    mechanic_cost_per_hour = fields.Float(
        string="Costo por hora (x unidad)",
        compute="_compute_mechanic_meta",
        store=False,
        digits=(16, 2),
    )

    # Resultado que consumen otros módulos/vistas (SE MANTIENE IGUAL)
    mechanic_cost_subtotal = fields.Monetary(
        string="Costo mecánico (subtotal)",
        compute="_compute_mechanic_cost",
        currency_field="currency_id",
        store=False,
    )

    @api.depends("product_id")
    def _compute_mechanic_meta(self):
        """
        Antes se traían horas y costo por hora del template del producto.
        Ahora, para no inducir a error, devolvemos 0.0 en ambos (y mantenemos
        los campos por compatibilidad con vistas ya existentes).
        """
        for line in self:
            line.mechanic_hours_required = 0.0
            line.mechanic_cost_per_hour = 0.0

    @api.depends("quantity", "product_id")
    def _compute_mechanic_cost(self):
        """
        Nueva regla:
          comisión por unidad = list_price * (porcentaje_comision / 100)
          subtotal comisión   = comisión por unidad * cantidad

        Notas:
        - Se aplica SOLO a productos tipo 'service'.
        - Usa SIEMPRE list_price del template (precio de venta base),
          tal como solicitaste (no toma descuentos ni price_unit).
        - Si no hay porcentaje definido, se toma 0.
        """
        for line in self:
            commission_subtotal = 0.0
            product = line.product_id
            if product and product.type == "service":
                tmpl = product.product_tmpl_id
                if tmpl:
                    list_price = tmpl.list_price or 0.0
                    pct = tmpl.porcentaje_comision or 0.0  # asumimos 0–100
                    commission_per_unit = list_price * (pct / 100.0)
                    commission_subtotal = commission_per_unit * (line.quantity or 0.0)
            line.mechanic_cost_subtotal = commission_subtotal
