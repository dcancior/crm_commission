/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, "dcr_mechanic_notify", {
    setup() {
        this._super(...arguments);
        this.notification = useService("notification");
    },
    async saveRecord(record, options) {
        // Antes de guardar una línea, avisamos si falta mecánico
        if (record && record.model && record.model.root) {
            const data = record.data || {};
            const needsMechanic = !!data.display_mechanic_fields;
            const hasMechanic = !!data.mechanic_id;
            if (needsMechanic && !hasMechanic) {
                this.notification.add(
                    this.env._t("Esta línea requiere seleccionar un Mecánico."),
                    { type: "warning" }
                );
            }
        }
        return await this._super(record, options);
    },
});
