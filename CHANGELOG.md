# Changelog — CRM Commission (crm_commission)

Registro de cambios y guía de funcionamiento del módulo.
Pensado también como apoyo para presentaciones/diapositivas.

---

## [2026-07-06] Configuración de comisiones de mecánicos

### ✨ Nuevo: Panel de configuración
**Dónde:** Ajustes → Ventas → sección **"Comisiones"** (solo administradores).

Se agregó un panel de configuración con tres bloques:

#### 1. Visibilidad de menús
Dos interruptores independientes para activar/desactivar los menús a todos los usuarios internos:
- **Comisiones Mecánicos** → muestra el menú lateral "Comisiones Mecánicos".
- **Comisiones de Ventas** → muestra el menú lateral "Comisiones de Ventas".

> Para dar acceso a usuarios específicos (no a todos), dejar los switches apagados
> y activar el grupo en la ficha del usuario: pestaña *Derechos de acceso* →
> "Ver Comisiones de Mecánicos" / "Ver Comisiones de Ventas".

#### 2. Momento en que se genera la comisión del mecánico
- **Al confirmar la cotización** → la comisión se contabiliza al confirmar el pedido de venta.
- **Cuando se paga la factura** → la comisión se contabiliza hasta que la factura del cliente queda pagada.

#### 3. Método de cálculo de la comisión del mecánico
- **Comisión costo por hora** (comportamiento original):
  - En la ficha del producto (tipo *Servicio*) se capturan **Horas requeridas** y **Costo por hora (mecánico)**.
  - Fórmula: `costo_por_hora × horas_requeridas × cantidad`.
  - Ejemplo: 3 horas × $75.00 = **$225.00** de comisión.
- **Comisión por porcentaje** (nuevo):
  - En la ficha del producto se captura **Porcentaje mecánico (%)** (valor por defecto).
  - En la línea de la cotización aparece la columna editable **"Porcentaje mecánico"**, precargada desde el producto pero modificable por línea.
  - Fórmula: `precio_unitario × cantidad × porcentaje / 100`.
  - Ejemplo: servicio de $1,000.00 con 15% = **$150.00** de comisión.

### 🖥️ Cambios visuales según el método elegido
- **Ficha del producto** (solo productos tipo *Servicio*):
  - Modo costo por hora → muestra *Horas requeridas* y *Costo por hora*; oculta el porcentaje.
  - Modo porcentaje → muestra *Porcentaje mecánico (%)*; oculta horas y costo por hora.
- **Cotización (líneas de pedido):**
  - Modo costo por hora → columna *Costo mecánico (subtotal)* disponible; el porcentaje se oculta.
  - Modo porcentaje → columna *Porcentaje mecánico* editable (solo en líneas de servicio); el costo mecánico se oculta.
  - La columna **Mecánico** (`mechanic_id`) aparece siempre, igual que antes.
- El porcentaje capturado en la línea se copia automáticamente a la línea de la factura al facturar.

### 🗃️ Cambios técnicos (modelos)
- `res.company` / `res.config.settings`: campos `mechanic_commission_trigger` y `mechanic_commission_calc_method`.
- `product.template`: nuevo campo `porcentaje_comision_mecanico`.
- `sale.order.line`: nuevo campo `porcentaje_comision_mecanico` (editable, se precarga del producto).
- `account.move.line`: nuevo campo `porcentaje_comision_mecanico` (copiado desde la cotización).
- `mechanic.commission.entry`: nuevo campo `calc_method` (método usado al generar la entrada) y
  restricción de unicidad por mecánico + línea de cotización (evita duplicados).
- Wizard de comisiones: el cálculo del pago (`payout`) ahora respeta el método configurado.
- Grupo de seguridad renombrado: "Ver Reporte de Comisiones" → **"Ver Comisiones de Ventas"**.

### ⚠️ Notas de actualización
- Requiere actualizar el módulo: `-u crm_commission`.
- Nueva dependencia: `base_setup` (para el panel de Ajustes).
- El método por defecto es **Comisión costo por hora**, por lo que el comportamiento
  no cambia hasta que se seleccione porcentaje en Ajustes.

---

## Funcionamiento general del módulo (referencia)

### Comisiones de mecánicos — flujo completo
1. **Producto:** se configura el servicio (horas + costo/hora, o porcentaje según el método).
2. **Cotización:** en cada línea de servicio se asigna el **Mecánico** responsable.
   - Las líneas de servicio sin mecánico se resaltan en naranja.
   - No se puede confirmar el pedido si falta mecánico (excepto productos "PAQ*", exentos).
3. **Confirmación / pago de factura** (según configuración): el sistema genera la
   entrada de comisión (`mechanic.commission.entry`) para el mecánico.
4. **Reporte mensual** (menú *Comisiones Mecánicos → Reporte mensual*):
   - Filtros por mecánico (o "Todos"), rango de fechas y estado de pago.
   - KPIs: servicios, horas totales, importe facturado, total a pagar.
   - Registro de pago por línea (efectivo/transferencia) o masivo ("Marcar todas como pagadas").
   - Exportación a PDF con detalle del vehículo (marca, modelo, color).

### Comisiones de ventas — flujo completo
1. **Equipo de ventas:** se define el **% de comisión** en el equipo (CRM → Equipos).
2. Cada factura pagada del vendedor genera su comisión: `subtotal × % del equipo`.
3. **Reporte** (menú *Comisiones de Ventas*): filtros por vendedor, rango y estado;
   registro de pagos individual o masivo; exportación a PDF.

### Grupos de seguridad
| Grupo | Qué habilita |
|---|---|
| Ver Comisiones de Mecánicos | Menú y reporte de mecánicos |
| Ver Comisiones de Ventas | Menú y reporte de ventas |
| Ver Campos de Comisión en Pedidos | Bloque "Comisiones" en el pedido de venta |
| Ver comisiones en lista tree de facturación | Columnas de comisión en la lista de facturas |
