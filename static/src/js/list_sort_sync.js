/** @odoo-module **/
/*
 * Sincroniza el orden de las tablas de los wizards de comisiones con los campos
 * sort_field / sort_direction del wizard padre.
 *
 * Motivo: al pulsar un encabezado, Odoo reordena la lista solo en el cliente y
 * el servidor no se entera, por lo que el PDF (action_print_pdf) siempre salía
 * en el orden por defecto. Guardando el criterio en el wizard, el PDF puede
 * reproducir exactamente el orden que se ve en pantalla.
 */

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// Listas x2many cuyo orden se sincroniza con el wizard padre.
const LINE_MODELS = [
    "commission.report.wizard.line",     // Reporte de Comisión de Ventas
    "mechanic.commission.wizard.line",   // Reporte de Comisiones (Mecánicos)
];

patch(ListRenderer.prototype, "crm_commission.list_sort_sync", {
    async onClickSortColumn(column) {
        const list = this.props.list;
        const isCommissionList = list && LINE_MODELS.includes(list.resModel);

        // Estado previo (antes de que el super reordene en cliente), por si la
        // lista no expone orderBy en esta versión.
        const root = isCommissionList && list.model ? list.model.root : null;
        const previous = root && root.data ? root.data : {};
        const previousField = previous.sort_field;
        const previousDirection = previous.sort_direction || "asc";

        await this._super(...arguments);

        // El wizard padre debe exponer los campos de orden en la vista.
        if (!isCommissionList || !root || !root.data || !("sort_field" in root.data)) {
            return;
        }

        try {
            const name = column && column.name;
            if (!name) {
                return;
            }

            let direction;
            const orderBy = list.orderBy || [];
            const current = orderBy.find((o) => o.name === name);
            if (current) {
                // La lista ya calculó el sentido: lo reutilizamos.
                direction = current.asc === false ? "desc" : "asc";
            } else if (previousField === name) {
                // Mismo campo: se alterna asc <-> desc.
                direction = previousDirection === "asc" ? "desc" : "asc";
            } else {
                direction = "asc";
            }

            if (previousField === name && previousDirection === direction) {
                return;
            }

            await root.update({ sort_field: name, sort_direction: direction });
        } catch (error) {
            // Nunca romper el ordenado en pantalla si algo cambia de API.
            console.warn("crm_commission: no se pudo sincronizar el orden", error);
        }
    },
});
