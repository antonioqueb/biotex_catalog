/** @odoo-module **/
import { Component, useState, useRef, onWillStart, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Modal "Editar producto clasificado" de la etapa 3.
 *
 * La tabla sirve para revisar muchos productos rápido; este modal sirve para capturar uno a fondo.
 * Todo se guarda en la línea de la sesión: el producto de Odoo solo se escribe al confirmar la
 * clasificación. La referencia, el consecutivo y el orden no se tocan aquí.
 */
export class BiotexLineEditorDialog extends Component {
    static template = "biotex_catalog.LineEditorDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        lineId: Number,
        sessionId: Number,
        classCode: { type: String, optional: true },
        readonly: { type: Boolean, optional: true },
        onSaved: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.nameInput = useRef("editorName");
        this.state = useState({
            loading: true,
            line: {},
            catalogs: { uoms: [], package_types: [], countries: [], brands: [], specialties: [], contents: [] },
            classificationBrandId: false,
            classificationBrandName: "",
            draft: {},
            initial: {},
            errors: {},
            saving: false,
            confirmClose: false,
            detailsOpen: false,
            lookups: { manufacturer: [], distributor: [], equipment: [] },
        });
        onMounted(() => this.nameInput.el?.focus());
        onWillStart(async () => {
            const data = await this.orm.call("biotex.classification.session", "workspace_line_detail", [
                [this.props.sessionId], this.props.lineId,
            ]);
            this.state.line = data.line;
            this.state.catalogs = data.catalogs;
            this.state.classificationBrandId = data.classification_brand_id;
            this.state.classificationBrandName = data.classification_brand_name;
            const d = {
                new_name: data.line.new_name || "",
                uom_id: data.line.uom_id || false,
                measure: data.line.measure || "",
                content: data.line.content || "",
                package_type_id: data.line.package_type_id || false,
                package_qty: data.line.package_qty || 1,
                brand_id: data.line.brand_id || false,
                manufacturer_ref: data.line.manufacturer_ref || "",
                model: data.line.model || "",
                barcode: data.line.barcode || "",
                country_id: data.line.country_id || false,
                manufacturer_id: data.line.manufacturer_id || false,
                distributor_id: data.line.distributor_id || false,
                equipment_id: data.line.equipment_id || false,
                specialty_id: data.line.specialty_id || false,
                notes: data.line.notes || "",
            };
            this.state.draft = d;
            this.state.initial = { ...d };
            this.state.labels = {
                manufacturer: data.line.manufacturer_name || "",
                distributor: data.line.distributor_name || "",
                equipment: data.line.equipment_name || "",
            };
            this.state.loading = false;
        });
    }

    // ------------------------------------------------------------------ estado
    toggleDetails() { this.state.detailsOpen = !this.state.detailsOpen; }
    get dirty() {
        return Object.keys(this.state.initial).some((k) => this.state.draft[k] !== this.state.initial[k]);
    }
    get consecutiveLabel() {
        return this.state.line.consecutive_label || "";
    }
    get brandWarning() {
        const b = this.state.draft.brand_id;
        return b && this.state.classificationBrandId && b !== this.state.classificationBrandId;
    }
    get brandName() {
        const b = this.state.catalogs.brands.find((x) => x.id === this.state.draft.brand_id);
        return b ? `${b.code} · ${b.name}` : "";
    }

    // ------------------------------------------------------------------ entrada
    onInput(field, ev) {
        this.state.draft[field] = ev.target.value;
        delete this.state.errors[field];
    }
    onNumber(field, ev) {
        this.state.draft[field] = ev.target.value === "" ? "" : parseFloat(ev.target.value);
        delete this.state.errors[field];
    }
    onSelect(field, ev) {
        this.state.draft[field] = parseInt(ev.target.value, 10) || false;
        delete this.state.errors[field];
    }
    async onLookup(kind, ev) {
        const query = ev.target.value;
        if (query.length < 2) {
            this.state.lookups[kind] = [];
            return;
        }
        const model = kind === "equipment" ? "biotex.equipment" : "res.partner";
        const ctx = kind === "distributor" ? { biotex_supplier_only: true } : {};
        this.state.lookups[kind] = await this.orm.call(
            "biotex.classification.session", "workspace_search_relation", [model, query], { context: ctx });
    }
    pick(kind, record) {
        const field = { manufacturer: "manufacturer_id", distributor: "distributor_id", equipment: "equipment_id" }[kind];
        this.state.draft[field] = record.id;
        this.state.labels[kind] = record.name;
        this.state.lookups[kind] = [];
    }
    clearLookup(kind) {
        const field = { manufacturer: "manufacturer_id", distributor: "distributor_id", equipment: "equipment_id" }[kind];
        this.state.draft[field] = false;
        this.state.labels[kind] = "";
    }

    // ------------------------------------------------------------------ validación
    validate() {
        const errors = {};
        if (!(this.state.draft.new_name || "").trim()) errors.new_name = _t("Indica el nuevo nombre del producto.");
        if (!this.state.draft.uom_id) errors.uom_id = _t("Selecciona la unidad de medida.");
        const qty = this.state.draft.package_qty;
        if (qty !== "" && qty !== false && (isNaN(qty) || qty <= 0)) errors.package_qty = _t("Debe ser un número mayor que cero.");
        this.state.errors = errors;
        if (errors.package_qty) this.state.detailsOpen = true;
        return !Object.keys(errors).length;
    }

    // ------------------------------------------------------------------ guardar / cancelar
    async save() {
        if (this.props.readonly || this.state.saving || !this.validate()) return;
        this.state.saving = true;
        try {
            const vals = { ...this.state.draft };
            vals.package_qty = vals.package_qty === "" ? 1 : vals.package_qty;
            const session = await this.orm.call("biotex.classification.session", "workspace_update_line", [
                [this.props.sessionId], this.props.lineId, vals,
            ]);
            this.props.onSaved(session);
            this.notification.add(_t("Cambios guardados"), { type: "success" });
            this.props.close();
        } catch (e) {
            this.notification.add(e.data?.message || e.message, { type: "danger", sticky: true });
        } finally {
            this.state.saving = false;
        }
    }
    requestClose() {
        if (this.dirty && !this.props.readonly) {
            this.state.confirmClose = true;
            return;
        }
        this.props.close();
    }
    keepEditing() {
        this.state.confirmClose = false;
    }
    discardAndClose() {
        this.props.close();
    }
}
