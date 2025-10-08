# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗  # Comentario decorativo
# ║  DCR INFORMATIC SERVICES SAS DE CV                               ║  # Comentario decorativo
# ║  Web: https://www.dcrsoluciones.com                              ║  # Comentario decorativo
# ║  Contacto: info@dcrsoluciones.com                                ║  # Comentario decorativo
# ║                                                                  ║  # Comentario decorativo
# ║  Este módulo está bajo licencia (LGPLv3).                        ║  # Comentario decorativo
# ║  Licencia completa: https://www.gnu.org/licenses/lgpl-3.0.html   ║  # Comentario decorativo
# ╚══════════════════════════════════════════════════════════════════╝  # Comentario decorativo

from odoo import api, fields, models, _  # Importa API, tipos de campos, base Model y utilitario de traducción _


# -----------------------------------------------------------------------------
# LÍNEAS DE VENTA
# -----------------------------------------------------------------------------
class SaleOrderLine(models.Model):
    """
    Extiende sale.order.line para:
      - Asociar (opcionalmente) un mecánico a líneas de servicio.
      - Mostrar/ocultar campos de mecánico de forma contextual (solo en servicios).
      - Calcular el subtotal de mano de obra (horas * costo/hora * cantidad).
      - Detectar si el mecánico seleccionado es un 'placeholder' (SELECCIONAR/variantes).
      - Exentar líneas de la regla de mecánico si el producto inicia con 'PAQ'.

    Principios:
      - No se marcan campos como 'required' para no bloquear captura en borrador.
      - La validación dura sucede al confirmar el pedido (en otra clase/modelo).
      - Se privilegian 'related' y 'compute' sin store para mantener la UI reactiva,
        salvo cuando se usan en decoraciones/filtrado (store=True).
    """
    _inherit = "sale.order.line"  # Heredamos el modelo base de líneas de venta

    # -------------------------------------------------------------------------
    # ASIGNACIÓN / IDENTIFICACIÓN DEL MECÁNICO
    # -------------------------------------------------------------------------
    mechanic_id = fields.Many2one(
        "hr.employee",
        string="Mecánico",
        help="Empleado responsable de realizar el servicio. No es obligatorio en borrador; "
             "la validación se ejecuta al confirmar el pedido.",
        required=False,  # No bloquea la captura; el bloqueo se hace al confirmar.
    )

    mechanic_hours_required = fields.Float(
        string="Horas requeridas (x unidad)",
        related="product_id.product_tmpl_id.service_hours_required",
        readonly=True,
        store=False,  # No persistimos: ya existe en product.template
        # Uso: referencia de horas por unidad para cálculo de costo de mano de obra.
    )

    display_mechanic_fields = fields.Boolean(
        string="Mostrar campos de mecánico",
        compute="_compute_display_mechanic_fields",
        store=False,  # Bandera puramente de UI/visibilidad
        # True => la línea es de servicio; la vista muestra campos de mecánico.
    )

    mechanic_cost_per_hour = fields.Float(
        string="Costo por hora (x unidad)",
        related="product_id.product_tmpl_id.service_cost_per_hour",
        readonly=True,
        store=False,  # No persistimos: ya existe en product.template
        # Uso: costo unitario de mano de obra para el cálculo del subtotal.
    )

    mechanic_cost_subtotal = fields.Monetary(
        string="Costo mecánico (subtotal)",
        compute="_compute_mechanic_cost_subtotal",
        currency_field="currency_id",
        store=False,  # Si se requiere en reportes/pivots, considerar store=True
        help="Fórmula: Horas requeridas × Costo por hora × Cantidad (solo en servicios).",
    )

    product_type = fields.Selection(
        related="product_id.type",
        store=True,  # Persistimos para usar en decoraciones/filtrado de vistas árbol
        # Nota: 'type' es el tipo general (product/consu/service); en Odoo 16 también está detailed_type.
    )

    mechanic_is_placeholder = fields.Boolean(
        string="Mecánico placeholder",
        compute="_compute_mechanic_is_placeholder",
        store=False,  # Indicador dinámico; no requiere persistencia
        # True cuando mechanic_id apunta a un registro placeholder (p.ej. 'SELECCIONAR').
    )

    @api.depends("mechanic_id")
    def _compute_mechanic_is_placeholder(self):
        """
        Marca la línea como 'placeholder' si el nombre del mecánico es 'SELECCIONAR'.

        Por qué:
          - La UI usa este flag para decorar en naranja (warning) y para validar al confirmar.
        Recomendación:
          - Si es posible, añade hr.employee.is_placeholder (Boolean) y úsalo en vez del nombre.
        """
        for line in self:
            name = (line.mechanic_id.name or "").strip().upper()
            line.mechanic_is_placeholder = (name == "SELECCIONAR")

    @api.onchange("product_id")
    def _onchange_autoset_placeholder_mechanic(self):
        """
        UX: Si la línea es de servicio (display_mechanic_fields) y no hay mecánico,
        autoasigna el placeholder, EXCEPTO cuando la línea está exenta (PAQ*).

        Beneficios:
          - Unifica el criterio con la decoración de la vista y con el bloqueo al confirmar.
          - Evita depender de 'type' vs 'detailed_type' entre versiones.
          - Respeta la exención para productos 'PAQ*' (paquetes).
        """
        for line in self:
            # 1) ¿La línea aplica la lógica de mecánico? (servicio)
            is_service_line = bool(getattr(line, 'display_mechanic_fields', False))

            # 2) ¿Está exenta? Preferimos el flag; si no existe, calculamos por nombre 'PAQ*'
            if hasattr(line, 'mechanic_exempt'):
                is_exempt = bool(line.mechanic_exempt)
            else:
                name = (getattr(line.product_id, 'display_name', '') or getattr(line.product_id, 'name', '') or '').strip().upper()
                is_exempt = name.startswith('PAQ')

            # 3) Solo autoasignar si: es servicio, NO exento, y aún no hay mecánico
            if is_service_line and (not is_exempt) and (not line.mechanic_id):
                placeholder = line._get_placeholder_mechanic()
                if placeholder:
                    line.mechanic_id = placeholder  # Asignación no bloqueante

    def _get_placeholder_mechanic(self):
        """
        Retorna un empleado-placeholder solo si:
        - La línea es de SERVICIO, y
        - El nombre del producto NO comienza con 'PAQ'.

        Estrategia de búsqueda (multi-compañía):
        1) Si existe hr.employee.is_placeholder => úsalo (True).
        2) Intento exacto con nombres comunes:
            - 'SELECCIONAR'
            - 'SELECCIONE UN MECÁNICO'
            - 'SELECCIONE UN MECANICO' (sin acento)
        3) Fallback: ILIKE por prefijo 'SELECCION%' (cubre 'SELECCIONAR/SELECCIONE', con o sin acento).

        Devuelve:
        - hr.employee(1) si encuentra placeholder
        - recordset vacío si no aplica o no encuentra
        """
        self.ensure_one()

        product = self.product_id
        # Determina si es servicio (compatibilidad: detailed_type o type)
        detailed_type = getattr(product, 'detailed_type', False) or getattr(product, 'type', False)
        is_service = bool(product) and (detailed_type == 'service')

        # Exención por 'PAQ*'
        prod_name = (getattr(product, 'display_name', '') or getattr(product, 'name', '') or '').strip().upper()
        if (not is_service) or prod_name.startswith('PAQ'):
            return self.env['hr.employee'].browse(False)  # no aplica

        Employee = self.env["hr.employee"]
        company_id = (self.order_id.company_id.id if self.order_id else self.env.company.id)

        def _with_company(dom):
            # Permite placeholder global (company_id False) o de la compañía actual
            return ['|', ('company_id', '=', False), ('company_id', '=', company_id)] + dom

        # 1) Si existe el campo booleano is_placeholder, úsalo (la mejor práctica)
        if 'is_placeholder' in Employee._fields:
            emp = Employee.search(_with_company([('is_placeholder', '=', True), ('active', '=', True)]), limit=1)
            if not emp:
                # Intento sin 'active' por si está archivado accidentalmente
                emp = Employee.search(_with_company([('is_placeholder', '=', True)]), limit=1)
            if emp:
                return emp

        # 2) Intento exacto con nombres comunes
        exact_names = [
            'SELECCIONAR',
            'SELECCIONE UN MECÁNICO',
            'SELECCIONE UN MECANICO',  # sin acento
        ]
        emp = Employee.search(_with_company([('name', 'in', exact_names), ('active', '=', True)]), limit=1)
        if not emp:
            emp = Employee.search(_with_company([('name', 'in', exact_names)]), limit=1)
        if emp:
            return emp

        # 3) Fallback flexible (prefijo 'SELECCION%', case-insensitive)
        emp = Employee.search(_with_company([('name', 'ilike', 'SELECCION%'), ('active', '=', True)]), limit=1)
        if not emp:
            emp = Employee.search(_with_company([('name', 'ilike', 'SELECCION%')]), limit=1)

        return emp  # puede ser vacío si no existe placeholder

    # -------------------------------------------------------------------------
    # CÁLCULO DE COSTOS
    # -------------------------------------------------------------------------
    @api.depends(
        "product_id",
        "product_uom_qty",
        "product_uom",
        "mechanic_hours_required",
        "mechanic_cost_per_hour",
    )
    def _compute_mechanic_cost_subtotal(self):
        """
        Calcula el subtotal de mano de obra únicamente para líneas de servicio.

        Fórmula:
          subtotal = horas_requeridas * costo_por_hora * cantidad

        Notas:
          - detailed_type (Odoo 16): 'service', 'product', 'consu'.
          - Si no es servicio, el subtotal se fuerza a 0.0.
        """
        for line in self:
            hrs = line.mechanic_hours_required or 0.0
            cph = line.mechanic_cost_per_hour or 0.0
            qty = line.product_uom_qty or 0.0
            line.mechanic_cost_subtotal = (
                hrs * cph * qty
                if (line.product_id and line.product_id.detailed_type == "service")
                else 0.0
            )

    # -------------------------------------------------------------------------
    # VISIBILIDAD EN VISTAS
    # -------------------------------------------------------------------------
    @api.depends("product_id.detailed_type")
    def _compute_display_mechanic_fields(self):
        """
        Activa la bandera de visibilidad de campos de mecánico cuando detailed_type == 'service'.

        Motivo:
          - Centraliza el criterio de "línea de servicio" que la UI leerá para mostrar/ocultar
            campos y para activar decoraciones (warning).
        """
        for line in self:
            # detailed_type en Odoo 16: 'service', 'product', 'consu'
            line.display_mechanic_fields = bool(line.product_id) and (line.product_id.detailed_type == "service")

    # -------------------------------------------------------------------------
    # EXENCIÓN POR 'PAQ*'
    # -------------------------------------------------------------------------
    mechanic_exempt = fields.Boolean(
        string='Exento de mecánico',
        compute='_compute_mechanic_exempt',
        store=True,  # Se usa en vistas (decoración) y validaciones; persistir mejora rendimiento en listas
        help="True cuando el nombre del producto comienza con 'PAQ' (paquetes).",
    )

    @api.depends('product_id', 'product_id.name', 'product_id.display_name', 'display_mechanic_fields')
    def _compute_mechanic_exempt(self):
        """
        Marca la línea como exenta si aplica mecánico y el producto inicia con 'PAQ'.

        Detalle:
          - Solo tiene sentido exentar cuando display_mechanic_fields == True (i.e. servicios).
          - Se normaliza el nombre (strip + upper) y se evalúa startswith('PAQ').
          - Esta bandera permite que:
              * La UI NO pinte en naranja (decoración condicionada).
              * La validación al confirmar NO bloquee para paquetes 'PAQ*'.
        """
        for line in self:
            if not getattr(line, 'display_mechanic_fields', False):
                line.mechanic_exempt = False
                continue
            name = (line.product_id.display_name or line.product_id.name or '').strip().upper()
            line.mechanic_exempt = name.startswith('PAQ')

    # -------------------------------------------------------------------------
    # TRASLADO A FACTURA
    # -------------------------------------------------------------------------
    def _prepare_invoice_line(self, **optional_values):
        """
        Extiende los valores de la línea de factura para trasladar el mecánico cuando sea real.

        Reglas:
          - Si mechanic_id existe y NO es placeholder, se copia a la línea de factura.
          - Si es placeholder, NO se traslada (evita ensuciar documentos legales con marcadores).
        """
        vals = super()._prepare_invoice_line(**optional_values)
        if self.mechanic_id and not self.mechanic_is_placeholder:
            vals["mechanic_id"] = self.mechanic_id.id
        return vals


    # Campo editable que el usuario maneja en la vista (sustituye a margin_percent visualmente)
    manual_margin_percent = fields.Float(
        string="Margen %",
        help="Margen de utilidad deseado. Se aplica sobre el costo (purchase_price) para calcular el precio de venta."
    )

    @api.onchange('manual_margin_percent', 'purchase_price')
    def _onchange_manual_margin_percent_apply_price(self):
        """ Cuando el usuario cambia el margen o el costo, recalculamos el precio unitario. """
        for line in self:
            # Toma costo: purchase_price (si no, standard_price como respaldo)
            cost = line.purchase_price
            if not cost and line.product_id:
                cost = line.product_id.standard_price
            if cost is None:
                continue

            margin = (line.manual_margin_percent or 0.0) / 100.0
            currency = (line.order_id and line.order_id.pricelist_id.currency_id) or line.currency_id
            if currency:
                line.price_unit = currency.round(cost * (1.0 + margin))
            else:
                line.price_unit = cost * (1.0 + margin)

    @api.onchange('price_unit')
    def _onchange_price_unit_recompute_margin(self):
        """ Si el usuario modifica el precio, recalculamos el % de margen para que la columna sea coherente. """
        for line in self:
            cost = line.purchase_price or (line.product_id and line.product_id.standard_price) or 0.0
            if cost:
                line.manual_margin_percent = (line.price_unit / cost - 1.0) * 100.0
            else:
                # Sin costo no podemos calcular margen; deja en 0 para evitar NaN.
                line.manual_margin_percent = 0.0

    def _apply_manual_margin(self):
        """ Utilidad interna para create/write: aplicar manual_margin_percent -> price_unit """
        for line in self:
            cost = line.purchase_price or (line.product_id and line.product_id.standard_price) or 0.0
            margin = (line.manual_margin_percent or 0.0) / 100.0
            currency = (line.order_id and line.order_id.pricelist_id.currency_id) or line.currency_id
            price = cost * (1.0 + margin)
            line.price_unit = currency.round(price) if currency else price

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Si viene el margen pero no viene el price_unit explícito, aplícalo.
        for rec, vals in zip(records, vals_list):
            if 'manual_margin_percent' in vals and 'price_unit' not in vals:
                rec._apply_manual_margin()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Si se cambió el margen (o el costo) y NO se fijó explícitamente price_unit, vuelve a aplicar el margen.
        if 'manual_margin_percent' in vals or 'purchase_price' in vals:
            lines = self
            # Evitar pisar un price_unit que el usuario haya puesto explícitamente en este write
            if 'price_unit' in vals:
                lines = self.env['sale.order.line']  # vacío
            for line in lines:
                line._apply_manual_margin()
        return res
