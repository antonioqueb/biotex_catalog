/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { BiotexLineEditorDialog } from "./line_editor";

const MODEL = "biotex.classification.session";
const PAGE_SIZE = 10;

/**
 * Los cuatro niveles de la clasificación, en el orden en que se eligen.
 * `tone` es la clase de color: verde, morado, naranja y azul se mantienen en las tarjetas,
 * en el resumen y en los segmentos de la clave.
 */
const LEVELS = [
    { key: "group", label: "Grupo", icon: "fa-th-large", tone: "group" },
    { key: "family", label: "Familia", icon: "fa-folder-open-o", tone: "family" },
    { key: "classifier", label: "Clasificador", icon: "fa-crosshairs", tone: "classifier" },
    { key: "brand", label: "Marca", icon: "fa-bookmark-o", tone: "brand" },
];

/** La clave v2 es GG-MMMM-FFF-CCC-NN: la marca va en el segundo segmento, no al final. */
const CODE_ORDER = ["group", "brand", "family", "classifier"];

export class BiotexClassificationWorkspace extends Component {
    static template = "biotex_catalog.ClassificationWorkspace";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.levels = LEVELS;

        this.state = useState({
            loading: true,
            tree: [],
            brands: [],
            uoms: [],
            drafts: [],
            session: null,
            pick: { group: false, family: false, classifier: false, brand: false },
            openPicker: null,
            pickerSearch: "",
            brandHints: [],
            stage: 1,
            collapsed: { 1: false, 2: false },
            search: { query: "", offset: 0, total: 0, records: [], loading: false },
            scan: false,
            busy: false,
            dragId: null,
            overId: null,
        });

        this.debouncedSearch = useDebounced(() => this.runSearch(0), 300);

        onWillStart(async () => {
            const sessionId = this.props.action?.context?.biotex_session_id || null;
            await this.bootstrap(sessionId);
        });
    }

    // ================================================================= carga
    async bootstrap(sessionId) {
        const data = await this.orm.call(MODEL, "workspace_bootstrap", [sessionId]);
        Object.assign(this.state, { tree: data.tree, brands: data.brands, uoms: data.uoms, drafts: data.drafts, loading: false });
        this.applySession(data.session);
        if (this.state.session) {
            this.state.stage = this.lines.length ? 3 : 2;
            this.state.collapsed[1] = true;
            this.state.collapsed[2] = this.state.stage === 3;
            await this.runSearch(0);
        }
    }

    applySession(session) {
        this.state.session = session;
        if (session) {
            this.state.pick = {
                group: session.group_id, family: session.family_id,
                classifier: session.classifier_id, brand: session.brand_id,
            };
        }
    }

    async openDraft(draftId) {
        this.state.loading = true;
        await this.bootstrap(draftId);
    }

    // ================================================================= selección jerárquica
    get groups() { return this.state.tree; }
    get selectedGroup() { return this.state.tree.find((g) => g.id === this.state.pick.group) || null; }
    get selectedFamily() { return this.selectedGroup?.families.find((f) => f.id === this.state.pick.family) || null; }
    get selectedClassifier() { return this.selectedFamily?.classifiers.find((c) => c.id === this.state.pick.classifier) || null; }
    get selectedBrand() { return this.state.brands.find((b) => b.id === this.state.pick.brand) || null; }

    /** Opción normalizada {id, code, name, note} de cualquier nivel, para pintar tarjetas y listas iguales. */
    selection(key) {
        switch (key) {
            case "group": {
                const g = this.selectedGroup;
                return g && { id: g.id, code: g.code, name: g.name, note: g.axis || g.division || "" };
            }
            case "family": {
                const f = this.selectedFamily;
                return f && { id: f.id, code: f.code, name: f.name, note: f.composite || "" };
            }
            case "classifier": {
                const c = this.selectedClassifier;
                return c && { id: c.id, code: c.code, name: c.name, note: this.selectedGroup?.axis || "" };
            }
            case "brand": {
                const b = this.selectedBrand;
                return b && { id: b.id, code: b.code, name: b.name, note: "" };
            }
        }
        return null;
    }

    /** Cada nivel solo se abre cuando el anterior está resuelto: la selección es dependiente. */
    levelEnabled(key) {
        const p = this.state.pick;
        return { group: true, family: !!p.group, classifier: !!p.family, brand: !!p.classifier }[key];
    }

    options(key) {
        const q = this.state.pickerSearch.trim().toLowerCase();
        let list = [];
        if (key === "group") {
            list = this.groups.map((g) => ({ id: g.id, code: g.code, name: g.name, note: g.axis || g.division || "" }));
        } else if (key === "family") {
            list = (this.selectedGroup?.families || []).map((f) => ({ id: f.id, code: f.code, name: f.name, note: f.composite || "" }));
        } else if (key === "classifier") {
            list = (this.selectedFamily?.classifiers || []).map((c) => ({ id: c.id, code: c.code, name: c.name, note: this.selectedGroup?.axis || "" }));
        } else if (key === "brand") {
            const hints = this.state.brandHints;
            list = this.state.brands.map((b) => ({ id: b.id, code: b.code, name: b.name, note: hints.includes(b.id) ? _t("Ya usada en este clasificador") : "" }));
            list.sort((a, b) => (hints.includes(b.id) ? 1 : 0) - (hints.includes(a.id) ? 1 : 0));
        }
        return q ? list.filter((o) => o.name.toLowerCase().includes(q) || (o.code || "").toLowerCase().includes(q)) : list;
    }

    get openLevel() { return LEVELS.find((l) => l.key === this.state.openPicker) || null; }

    /** Etiqueta del nivel que falta resolver antes de poder abrir este. */
    previousLabel(key) {
        const index = LEVELS.findIndex((l) => l.key === key);
        return index > 0 ? LEVELS[index - 1].label.toLowerCase() : "";
    }

    async togglePicker(key) {
        if (!this.levelEnabled(key)) return;
        this.state.pickerSearch = "";
        this.state.openPicker = this.state.openPicker === key ? null : key;
        if (this.state.openPicker === "brand") {
            this.state.brandHints = await this.orm.call(MODEL, "workspace_brand_hints", [this.state.pick.family, this.state.pick.classifier]);
        }
    }

    onPickerSearch(ev) { this.state.pickerSearch = ev.target.value; }

    async select(key, option) {
        const p = this.state.pick;
        const downstream = { group: ["family", "classifier", "brand"], family: ["classifier", "brand"], classifier: ["brand"], brand: [] };
        p[key] = option.id;
        for (const k of downstream[key]) p[k] = false;
        this.state.openPicker = null;
        this.state.pickerSearch = "";
        // avanza sola al siguiente nivel pendiente: un clic por nivel, sin botones intermedios
        const next = LEVELS.map((l) => l.key).find((k) => !p[k]);
        if (next) {
            await this.togglePicker(next);
        } else {
            await this.persistClassification();
        }
    }

    get classificationComplete() { return LEVELS.every((l) => !!this.state.pick[l.key]); }

    async persistClassification() {
        if (!this.classificationComplete) return;
        this.state.busy = true;
        try {
            const p = this.state.pick;
            // el servidor trabaja con los nombres reales de los campos
            const vals = { group_id: p.group, family_id: p.family, classifier_id: p.classifier, brand_id: p.brand };
            const data = await this.orm.call(MODEL, "workspace_set_classification", [this.state.session?.id || false, vals]);
            if (data) {
                this.applySession(data);
                await this.runSearch(0);
            } else {
                // la clasificación está completa en pantalla: si el servidor no devuelve sesión, algo falló
                this.notification.add(_t("No se pudo guardar la clasificación. Vuelva a elegir la marca."), { type: "danger" });
            }
        } catch (e) {
            this.notify(e);
        } finally {
            this.state.busy = false;
        }
    }

    /** Segmentos coloreados de la clave, en el orden real GG-MMMM-FFF-CCC. */
    get codeSegments() {
        return CODE_ORDER.map((key) => {
            const sel = this.selection(key);
            const level = LEVELS.find((l) => l.key === key);
            return sel ? { text: sel.code, tone: level.tone } : null;
        }).filter(Boolean);
    }

    // ================================================================= etapas
    get lines() { return this.state.session?.lines || []; }
    get confirmed() { return this.state.session?.state === "confirmed"; }

    stageReachable(stage) {
        if (stage <= 1) return true;
        if (stage === 2) return this.classificationComplete && !!this.state.session;
        return this.lines.length > 0;
    }

    goStage(stage) {
        if (!this.stageReachable(stage)) {
            this.notification.add(
                stage === 2 ? _t("Elija grupo, familia, clasificador y marca para continuar.")
                            : _t("Agregue al menos un producto para continuar."),
                { type: "warning" });
            return;
        }
        this.state.stage = stage;
        this.state.collapsed[1] = stage > 1;
        this.state.collapsed[2] = stage > 2;
        this.state.openPicker = null;
    }

    toggleCollapse(stage) { this.state.collapsed[stage] = !this.state.collapsed[stage]; }
    next() { if (this.state.stage < 3) this.goStage(this.state.stage + 1); else this.confirm(); }
    previous() { if (this.state.stage > 1) this.goStage(this.state.stage - 1); }

    // ================================================================= etapa 2: búsqueda
    onSearchInput(ev) {
        this.state.search.query = ev.target.value;
        this.debouncedSearch();
    }

    /** Un lector de código de barras es un teclado: escribe y manda Enter. Aquí lo aprovechamos. */
    async onSearchKeydown(ev) {
        if (ev.key !== "Enter") return;
        ev.preventDefault();
        await this.runSearch(0);
        if (this.state.scan && this.state.search.records.length === 1 && !this.state.search.records[0].added) {
            await this.addProduct(this.state.search.records[0]);
            this.state.search.query = "";
            ev.target.value = "";
        }
    }

    toggleScan() { this.state.scan = !this.state.scan; }

    async runSearch(offset) {
        if (!this.state.session) return;
        this.state.search.loading = true;
        try {
            const res = await this.orm.call(MODEL, "workspace_search_products", [[this.state.session.id]], {
                query: this.state.search.query, offset, limit: PAGE_SIZE,
            });
            Object.assign(this.state.search, { records: res.records, total: res.total, offset: res.offset });
        } catch (e) {
            this.notify(e);
        } finally {
            this.state.search.loading = false;
        }
    }

    get pageFrom() { return this.state.search.total ? this.state.search.offset + 1 : 0; }
    get pageTo() { return Math.min(this.state.search.offset + PAGE_SIZE, this.state.search.total); }
    get hasPrevPage() { return this.state.search.offset > 0; }
    get hasNextPage() { return this.pageTo < this.state.search.total; }
    prevPage() { this.runSearch(Math.max(0, this.state.search.offset - PAGE_SIZE)); }
    nextPage() { this.runSearch(this.state.search.offset + PAGE_SIZE); }

    async addProduct(record) {
        if (record.added || this.state.busy) return;
        this.state.busy = true;
        try {
            const data = await this.orm.call(MODEL, "workspace_add_products", [[this.state.session.id]], { product_ids: [record.id] });
            this.applySession(data);
            record.added = true;
            if (this.state.stage === 2 && this.lines.length === 1) {
                this.notification.add(_t("Producto agregado. Ya puede revisarlo en la etapa 3."), { type: "success" });
            }
        } catch (e) {
            this.notify(e);
        } finally {
            this.state.busy = false;
        }
    }

    // ================================================================= etapa 3: lista de trabajo
    async removeLine(line) {
        this.state.busy = true;
        try {
            const data = await this.orm.call(MODEL, "workspace_remove_line", [[this.state.session.id]], { line_id: line.id });
            this.applySession(data);
            const record = this.state.search.records.find((r) => r.id === line.product_id);
            if (record) record.added = false;
        } catch (e) {
            this.notify(e);
        } finally {
            this.state.busy = false;
        }
    }

    onLineInput(line, field, ev) { line[field] = ev.target.value; }

    async saveLine(line, vals) {
        try {
            await this.orm.call(MODEL, "workspace_update_line", [[this.state.session.id]], { line_id: line.id, vals });
        } catch (e) {
            this.notify(e);
        }
    }

    onNameChange(line, ev) {
        line.new_name = ev.target.value;
        this.saveLine(line, { new_name: line.new_name });
    }

    onUomChange(line, ev) {
        const id = parseInt(ev.target.value, 10) || false;
        line.uom_id = id;
        line.uom_name = this.state.uoms.find((u) => u.id === id)?.name || "";
        this.saveLine(line, { uom_id: id });
    }

    editLine(line) {
        // El modal captura a fondo un producto y devuelve la sesión ya persistida: la etapa 3
        // se refresca sin recargar la pantalla ni perder el contexto de la clasificación.
        this.dialog.add(BiotexLineEditorDialog, {
            lineId: line.id,
            sessionId: this.state.session.id,
            classCode: this.state.session.class_code,
            readonly: this.confirmed,
            onSaved: (session) => this.applySession(session),
        });
    }

    // ----------------------------------------------------------------- arrastrar para ordenar
    // El asa es lo arrastrable, no la fila: así los inputs de la fila siguen seleccionándose con el ratón.
    onDragStart(line, ev) {
        this.state.dragId = line.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(line.id));
    }

    onDragOver(line) {
        if (this.state.dragId && this.state.dragId !== line.id) this.state.overId = line.id;
    }

    async onDrop(line) {
        const from = this.lines.findIndex((l) => l.id === this.state.dragId);
        const to = this.lines.findIndex((l) => l.id === line.id);
        this.onDragEnd();
        if (from < 0 || to < 0 || from === to) return;
        const lines = this.lines;
        lines.splice(to, 0, lines.splice(from, 1)[0]);
        try {
            await this.orm.call(MODEL, "workspace_reorder", [[this.state.session.id]], { line_ids: lines.map((l) => l.id) });
        } catch (e) {
            this.notify(e);
        }
    }

    onDragEnd() { Object.assign(this.state, { dragId: null, overId: null }); }

    // ================================================================= cierre
    confirm() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Generar claves"),
            body: _t("Se escribirá la clave definitiva en %s producto(s) y se aplicarán los nombres y unidades de esta lista. Esta acción no se deshace.", this.lines.length),
            confirmLabel: _t("Generar claves"),
            confirm: async () => {
                this.state.busy = true;
                try {
                    const data = await this.orm.call(MODEL, "workspace_confirm", [[this.state.session.id]]);
                    this.applySession(data);
                    this.notification.add(_t("%s producto(s) clasificados.", this.lines.length), { type: "success" });
                } catch (e) {
                    this.notify(e);
                } finally {
                    this.state.busy = false;
                }
            },
        });
    }

    async saveAndExit() {
        // cada acción ya se guardó en el servidor; salir solo cierra la pantalla
        this.action.doAction("biotex_catalog.action_biotex_classification_sessions", { clearBreadcrumbs: true });
    }

    cancel() {
        if (!this.state.session) {
            this.action.doAction("biotex_catalog.action_biotex_classification_sessions", { clearBreadcrumbs: true });
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Cancelar clasificación"),
            body: this.lines.length
                ? _t("La sesión quedará cancelada con sus %s producto(s). Ningún producto se modifica.", this.lines.length)
                : _t("Se descartará la sesión. Ningún producto se modifica."),
            confirmLabel: _t("Cancelar sesión"),
            confirmClass: "btn-danger",
            cancelLabel: _t("Seguir trabajando"),
            confirm: async () => {
                await this.orm.call(MODEL, "workspace_discard", [[this.state.session.id]]);
                this.action.doAction("biotex_catalog.action_biotex_classification_sessions", { clearBreadcrumbs: true });
            },
        });
    }

    async startNew() {
        this.state.loading = true;
        Object.assign(this.state, {
            session: null, pick: { group: false, family: false, classifier: false, brand: false },
            stage: 1, collapsed: { 1: false, 2: false }, search: { query: "", offset: 0, total: 0, records: [], loading: false },
        });
        await this.bootstrap(null);
    }

    openProducts() {
        this.action.doAction({
            type: "ir.actions.act_window", name: _t("Productos clasificados"), res_model: "product.template",
            view_mode: "list,form", views: [[false, "list"], [false, "form"]],
            domain: [["id", "in", this.lines.map((l) => l.product_id)]],
        });
    }

    notify(error) {
        this.notification.add(error.data?.message || error.message || String(error), { type: "danger", sticky: true });
    }
}

registry.category("actions").add("biotex_catalog.classification_workspace", BiotexClassificationWorkspace);
