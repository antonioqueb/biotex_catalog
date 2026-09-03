/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Editor de una línea de la sesión.
 *
 * Iteración 1: nombre y unidad de medida, que es lo que la etapa 3 permite cambiar.
 * La pantalla definitiva (descripción estructurada, medidas, presentación, empaque, uso clínico)
 * se diseña después; el punto de entrada y el contrato ya quedan fijados aquí:
 * `onSave(vals)` recibe el diccionario de campos modificados y el asistente lo persiste.
 */
export class BiotexLineEditorDialog extends Component {
    static template = "biotex_catalog.LineEditorDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        line: Object,
        uoms: Array,
        classCode: { type: String, optional: true },
        readonly: { type: Boolean, optional: true },
        onSave: Function,
    };

    setup() {
        this.title = _t("Editar producto");
        this.draft = useState({
            new_name: this.props.line.new_name || "",
            uom_id: this.props.line.uom_id || false,
        });
    }

    onInput(field, ev) {
        this.draft[field] = field === "uom_id" ? parseInt(ev.target.value, 10) || false : ev.target.value;
    }

    async save() {
        await this.props.onSave({ new_name: this.draft.new_name, uom_id: this.draft.uom_id });
        this.props.close();
    }
}
