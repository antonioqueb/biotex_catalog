/** @odoo-module **/
import { Component, useState, useRef, onWillStart, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { referenceTones } from "./reference";

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
            detailsOpen: true,
            readingImages: 0,
            photoPreviews: {},
            lookups: { manufacturer: [], distributor: [], equipment: [], country: [], specialty: [] },
            // etiquetas de las multi-selecciones (los ids viven en draft.<kind>_ids)
            multi: { country: [], equipment: [], specialty: [] },
            manufacturerSuggested: false,
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
                country_ids: (data.line.country_ids || []).map((c) => c.id),
                manufacturer_id: data.line.manufacturer_id || false,
                distributor_id: data.line.distributor_id || false,
                equipment_id: data.line.equipment_id || false,
                equipment_ids: (data.line.equipment_ids || []).map((e) => e.id),
                specialty_id: data.line.specialty_id || false,
                specialty_ids: (data.line.specialty_ids || []).map((sp) => sp.id),
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
            let manufacturerName = data.line.manufacturer_name || "";
            // Fabricante sugerido por la marca de la clasificación: solo si el campo está vacío y el usuario
            // nunca lo capturó ni lo vació a mano (`manufacturer_manual`). Entra también en `initial` para que
            // abrir y cerrar sin tocar nada no cuente como cambio.
            if (!d.manufacturer_id && !data.line.manufacturer_manual && data.brand_manufacturer_id) {
                d.manufacturer_id = data.brand_manufacturer_id;
                manufacturerName = data.brand_manufacturer_name;
            }
            this.state.manufacturerSuggested = !!d.manufacturer_id && !data.line.manufacturer_manual
                && d.manufacturer_id === data.brand_manufacturer_id;
            this.state.draft = d;
            this.state.initial = JSON.parse(JSON.stringify(d));
            this.state.labels = {
                manufacturer: manufacturerName,
                distributor: data.line.distributor_name || "",
                equipment: data.line.equipment_name || "",
            };
            this.state.multi = {
                country: [...(data.line.country_ids || [])],
                equipment: [...(data.line.equipment_ids || [])],
                specialty: [...(data.line.specialty_ids || [])],
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
    /** Nombre actual completo del producto, tal como se agregó a la sesión. */
    get productTitle() {
        return this.state.line.old_name || this.state.line.new_name || "";
    }
    /** Referencia final con los mismos tonos que la página 1 (grupo, familia, clasificador, marca, consecutivo). */
    get referenceSegments() {
        const code = this.state.line.reference || this.props.classCode || "";
        return code ? referenceTones(code) : [];
    }
    /** Nombre de la unidad indivisible elegida arriba; es la unidad en que se cuentan los empacados. */
    get baseUomName() {
        return this.state.catalogs.uoms.find((u) => u.id === this.state.draft.uom_id)?.name || "";
    }
    /** Producto ya clasificado con esta misma clave: el nombre y la referencia no se tocan. */
    get nameLocked() {
        return !!this.state.line.preserve_reference;
    }
    /** Descripción armada con medidas y complemento; se ofrece como sugerencia, no sustituye lo escrito. */
    get suggestedName() {
        const d = this.state.draft;
        const measures = d.measure_data.length
            ? d.measure_data.map((r) => [r.component, r.measure_type, r.value, r.unit].filter((x) => x !== "").join(" ")).join("; ")
            : d.measure;
        if (!measures && !d.description_extra) return "";
        return [d.base_name || d.new_name, measures, d.description_extra].filter(Boolean).join(" ").toUpperCase();
    }
    get showSuggestion() {
        if (this.nameLocked) return false;
        const suggested = this.suggestedName;
        return !!suggested && suggested !== (this.state.draft.new_name || "").toUpperCase();
    }
    useSuggestedName() {
        this.state.draft.new_name = this.suggestedName;
        delete this.state.errors.new_name;
    }
    // ------------------------------------------------------------------ entrada
    onInput(field, ev) {
        this.state.draft[field] = field === "barcode" || field === "manufacturer_ref" ? ev.target.value : ev.target.value.toUpperCase();
        ev.target.value = this.state.draft[field];
        // Sin medidas ni complemento, el nombre escrito es también la descripción base del producto.
        if (field === "new_name" && !this.state.draft.measure_data.length && !this.state.draft.description_extra) {
            this.state.draft.base_name = this.state.draft.new_name;
        }
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
        if (kind === "manufacturer") this.state.manufacturerSuggested = false;
        if (query.length < 2) {
            this.state.lookups[kind] = [];
            return;
        }
        if (kind === "country" || kind === "specialty") {
            // catálogos ya cargados: se filtran en el cliente
            const q = query.toLowerCase();
            const chosen = new Set(this.state.draft[kind + "_ids"]);
            const source = kind === "country" ? this.state.catalogs.countries : this.state.catalogs.specialties;
            this.state.lookups[kind] = source.filter((c) => !chosen.has(c.id) && c.name.toLowerCase().includes(q)).slice(0, 8);
            return;
        }
        const model = kind === "equipment" ? "biotex.equipment" : "res.partner";
        const ctx = kind === "distributor" ? { biotex_supplier_only: true } : {};
        this.state.lookups[kind] = await this.orm.call(
            "biotex.classification.session", "workspace_search_relation", [model, query], { context: ctx });
    }
    pick(kind, record, ev) {
        this.state.lookups[kind] = [];
        this.state.labels[kind + "Query"] = "";
        if (kind === "country" || kind === "equipment" || kind === "specialty") {
            // multi-selección: el primero elegido es el principal
            const field = kind + "_ids";
            if (!this.state.draft[field].includes(record.id)) {
                this.state.draft[field].push(record.id);
                this.state.multi[kind].push({ id: record.id, name: record.name });
            }
            const input = ev?.target.closest(".o_bcw_field")?.querySelector("input");
            if (input) { input.value = ""; input.focus(); }
            return;
        }
        const field = { manufacturer: "manufacturer_id", distributor: "distributor_id" }[kind];
        this.state.draft[field] = record.id;
        this.state.labels[kind] = record.name;
        if (kind === "manufacturer") this.state.manufacturerSuggested = false;
    }
    clearLookup(kind) {
        const field = { manufacturer: "manufacturer_id", distributor: "distributor_id" }[kind];
        this.state.draft[field] = false;
        this.state.labels[kind] = "";
        if (kind === "manufacturer") this.state.manufacturerSuggested = false;
    }
    removeMulti(kind, id) {
        const field = kind + "_ids";
        this.state.draft[field] = this.state.draft[field].filter((x) => x !== id);
        this.state.multi[kind] = this.state.multi[kind].filter((x) => x.id !== id);
    }
    addRow(kind) {
        // Un empacado nuevo cuenta en la unidad indivisible base; la cantidad se deduce de la descripción
        // ("CAJA CON 12" → 12) mientras el usuario no la escriba a mano (`_auto`).
        this.state.draft[kind].push(kind === "measure_data" ? { component: "", measure_type: "", value: "", unit: "" } : { name: "", quantity: 1, barcode: "", _auto: true });
    }
    /** Primer entero de la descripción del empacado, o 1 si no trae número. */
    static quantityFromName(name) {
        const match = /\d+/.exec(name || "");
        const value = match ? parseInt(match[0], 10) : 0;
        return value >= 1 ? value : 1;
    }
    removeRow(kind, index) {
        this.state.draft[kind].splice(index, 1);
    }
    onRow(kind, index, field, ev) {
        const raw = ev.target.value;
        const row = this.state.draft[kind][index];
        row[field] = ["value", "quantity"].includes(field) ? (raw === "" ? "" : Number(raw)) : (field === "barcode" ? raw : raw.toUpperCase());
        if (kind === "presentation_data") {
            if (field === "quantity") row._auto = false;
            if (field === "name" && row._auto) row.quantity = BiotexLineEditorDialog.quantityFromName(row.name);
        }
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
        if (!(this.state.draft.new_name || "").trim()) errors.new_name = _t("Indica el nuevo nombre del producto.");
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
            vals.presentation_data = vals.presentation_data.map(({ _auto, ...row }) => row);
            if (!(vals.base_name || "").trim()) vals.base_name = vals.new_name;
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
