/** @odoo-module **/
import { Component, useState, useRef, onWillStart, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class BiotexEditorDialog extends Dialog {
    static props = { ...Dialog.props, requestClose: Function };
    dismiss() { return this.props.requestClose(); }
}

class BiotexPhotoPreviewDialog extends Component {
    static template = "biotex_catalog.ClassificationPhotoPreview";
    static components = { Dialog };
    static props = { close: Function, src: String, label: String };
}

/**
 * Modal "Editar producto clasificado" de la etapa 3.
 *
 * La tabla sirve para revisar muchos productos rápido; este modal sirve para capturar uno a fondo.
 * Todo se guarda en la línea de la sesión: el producto de Odoo solo se escribe al confirmar la
 * clasificación. La referencia, el consecutivo y el orden no se tocan aquí.
 */
export class BiotexLineEditorDialog extends Component {
    static template = "biotex_catalog.LineEditorDialog";
    static components = { Dialog: BiotexEditorDialog };
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
        this.dialog = useService("dialog");
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
            readingImages: 0,
            photoPreviews: {},
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
                manufacturer_ref: data.line.manufacturer_ref || "",
                model: data.line.model || "",
                barcode: data.line.barcode || "",
                country_id: data.line.country_id || false,
                manufacturer_id: data.line.manufacturer_id || false,
                distributor_id: data.line.distributor_id || false,
                equipment_id: data.line.equipment_id || false,
                specialty_id: data.line.specialty_id || false,
                notes: data.line.notes || "",
                base_name: data.line.base_name || data.line.new_name || "",
                description_extra: data.line.description_extra || "",
                usage_notes: data.line.usage_notes || "",
                internal_notes: data.line.internal_notes || "",
                compatibility_notes: data.line.compatibility_notes || "",
                measure_data: JSON.parse(JSON.stringify(data.line.measure_data || [])),
                presentation_data: JSON.parse(JSON.stringify(data.line.presentation_data || [])),
                image_changes: {},
            };
            this.state.draft = d;
            this.state.initial = JSON.parse(JSON.stringify(d));
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
    photoUrl(photo) {
        const changes = this.state.draft.image_changes;
        if (Object.hasOwn(changes, photo.field)) {
            return changes[photo.field] === false ? photo.original_url : this.state.photoPreviews[photo.field];
        }
        return photo.url;
    }
    photoPending(photo) {
        const changes = this.state.draft.image_changes;
        return Object.hasOwn(changes, photo.field) ? changes[photo.field] !== false : photo.pending;
    }
    previewPhoto(photo) {
        const src = this.photoUrl(photo);
        if (src) this.dialog.add(BiotexPhotoPreviewDialog, { src, label: photo.label });
    }
    async selectPhoto(photo, ev) {
        const input = ev.target;
        const file = input.files?.[0];
        if (!file || this.props.readonly || this.state.saving || this.state.readingImages) return;
        input.value = "";
        if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type) || file.size > 10 * 1024 * 1024) {
            this.notification.add(_t("Selecciona una imagen JPG, PNG, WebP o GIF de hasta 10 MB."), { type: "warning" });
            return;
        }
        this.state.readingImages++;
        try {
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = () => reject(new Error(_t("No se pudo leer la imagen.")));
                reader.readAsDataURL(file);
            });
            this.state.photoPreviews[photo.field] = data;
            this.state.draft.image_changes[photo.field] = data.split(",", 2)[1];
        } catch (error) {
            this.notification.add(error.message, { type: "danger" });
        } finally {
            this.state.readingImages--;
        }
    }
    useCurrentPhoto(photo) {
        if (this.props.readonly || this.state.saving || this.state.readingImages) return;
        this.state.draft.image_changes[photo.field] = false;
    }
    get dirty() {
        return JSON.stringify(this.state.draft) !== JSON.stringify(this.state.initial);
    }
    get consecutiveLabel() {
        return this.state.line.consecutive_label || "";
    }
    // ------------------------------------------------------------------ entrada
    onInput(field, ev) {
        this.state.draft[field] = field === "barcode" || field === "manufacturer_ref" ? ev.target.value : ev.target.value.toUpperCase();
        ev.target.value = this.state.draft[field];
        if (["base_name", "description_extra", "measure"].includes(field)) this.refreshDescription();
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
        this.state.labels[kind + "Query"] = query;
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

    refreshDescription() {
        const d = this.state.draft;
        const measures = d.measure_data.length ? d.measure_data.map((r) => [r.component, r.measure_type, r.value, r.unit].filter((x) => x !== "").join(" ")).join("; ") : d.measure;
        d.new_name = [d.base_name, measures, d.description_extra].filter(Boolean).join(" ").toUpperCase();
    }
    addRow(kind) {
        this.state.draft[kind].push(kind === "measure_data" ? { component: "", measure_type: "", value: "", unit: "" } : { name: "", quantity: 1, barcode: "" });
    }
    removeRow(kind, index) {
        this.state.draft[kind].splice(index, 1);
        if (kind === "measure_data") this.refreshDescription();
    }
    onRow(kind, index, field, ev) {
        const raw = ev.target.value;
        this.state.draft[kind][index][field] = ["value", "quantity"].includes(field) ? (raw === "" ? "" : Number(raw)) : (field === "barcode" ? raw : raw.toUpperCase());
        if (kind === "measure_data") this.refreshDescription();
    }
    async createRelation(kind) {
        const name = (this.state.labels[kind + "Query"] || "").trim();
        if (!name) return;
        try {
            const record = await this.orm.call("biotex.classification.session", "workspace_create_relation", [kind, name]);
            this.pick(kind, record);
        } catch (e) {
            this.notification.add(e.data?.message || e.message, { type: "danger" });
        }
    }

    // ------------------------------------------------------------------ validación
    validate() {
        const errors = {};
        if (!(this.state.draft.base_name || "").trim()) errors.new_name = _t("Indica la descripción base del producto.");
        if (!this.state.draft.uom_id) errors.uom_id = _t("Selecciona la unidad de medida.");
        const qty = this.state.draft.package_qty;
        if (qty !== "" && qty !== false && (isNaN(qty) || qty <= 0)) errors.package_qty = _t("Debe ser un número mayor que cero.");
        if (this.state.draft.measure_data.some((r) => !r.component.trim() || !r.measure_type.trim() || !r.unit.trim() || !Number.isFinite(Number(r.value)) || Number(r.value) <= 0)) errors.measure_data = _t("Completa componente, tipo, valor positivo y unidad en cada medida.");
        const presentations = this.state.draft.presentation_data;
        if (presentations.some((r) => !r.name.trim() || !r.barcode.trim() || !Number.isInteger(Number(r.quantity)) || Number(r.quantity) < 1) || new Set(presentations.map((r) => r.barcode)).size !== presentations.length) errors.presentation_data = _t("Cada presentación requiere nombre, cantidad entera positiva y un código distinto.");
        this.state.errors = errors;
        if (errors.package_qty) this.state.detailsOpen = true;
        return !Object.keys(errors).length;
    }

    // ------------------------------------------------------------------ guardar / cancelar
    async save() {
        if (this.props.readonly || this.state.saving || this.state.readingImages || !this.validate()) return;
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
        if (this.state.saving || this.state.readingImages) return;
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
