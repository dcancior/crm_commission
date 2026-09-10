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
 *
 * OJO con this._super: el sistema de parches de Odoo 16 lo define solo mientras
 * dura la ejecucion SINCRONA de la funcion parcheada y lo restaura al volver.
 * Si se llama despues de un await ya no existe ("this._super is not a function"),
 * por eso se guarda en una variable antes de cualquier operacion asincrona y se
 * encadena con promesas en lugar de async/await.
 */

import { patch } from "@web/core/utils/patch";
import { BoardController } from "@board/board_controller";

patch(BoardController.prototype, "crm_commission.board_first_save", {
    saveBoard() {
        const _super = this._super.bind(this);
        const viewId = this.env.config && this.env.config.viewId;

        if (!this.board || this.board.customViewId || !viewId) {
            return _super();
        }

        return this.rpc("/web/dataset/call_kw", {
            model: "board.board",
            method: "ensure_custom_view",
            args: [viewId],
            kwargs: {},
        }).then(
            (customViewId) => {
                this.board.customViewId = customViewId;
                return _super();
            },
            (error) => {
                console.warn("crm_commission: no se pudo preparar el guardado del tablero", error);
                return _super();
            }
        );
    },
});
