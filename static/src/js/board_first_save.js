/** @odoo-module **/
/*
 * Arregla el primer "Cambiar diseño" de un tablero.
 *
 * El controlador de board manda el id de la vista personalizada del usuario a
 * /web/view/edit_custom, pero ese id solo existe si el usuario YA habia
 * personalizado el tablero. La primera vez llega vacio y el servidor responde
 * "edit_custom() missing 1 required positional argument: 'custom_id'".
 *
 * Aqui se crea esa copia antes de guardar.
 */

import { patch } from "@web/core/utils/patch";
import { BoardController } from "@board/board_controller";

patch(BoardController.prototype, "crm_commission.board_first_save", {
    async saveBoard() {
        try {
            if (this.board && !this.board.customViewId) {
                const viewId = this.env.config && this.env.config.viewId;
                if (viewId) {
                    this.board.customViewId = await this.rpc("/web/dataset/call_kw", {
                        model: "board.board",
                        method: "ensure_custom_view",
                        args: [viewId],
                        kwargs: {},
                    });
                }
            }
        } catch (error) {
            console.warn("crm_commission: no se pudo preparar el guardado del tablero", error);
        }
        return this._super(...arguments);
    },
});
