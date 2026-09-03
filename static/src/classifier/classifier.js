/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const STEPS = [
    { key: "group", label: "Grupo" },
    { key: "family", label: "Familia" },
    { key: "description", label: "Descripción" },
    { key: "brand", label: "Marca y compatibilidad" },
    { key: "photos", label: "Fotos" },
    { key: "review", label: "Revisión" },
];

const EMPTY = () => ({
    id: false, name: "", biotex_name: "", biotex_measure: "", biotex_content: "", biotex_usage_notes: "",
    biotex_group_id: false, biotex_family_id: false, biotex_brand_id: false, biotex_model: "",
    biotex_manufacturer_id: false, biotex_reference: "", biotex_equipment_ids: [],
    image_1920: null, biotex_image_2: null, biotex_image_3: null,
});

export class BiotexClassifier extends Component {
    static template = "biotex_catalog.Classifier";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.steps = STEPS;
        this.state = useState({
            step: 0,
            tree: [],
            queue: [],
            queueIndex: 0,
            product: EMPTY(),
            familySearch: "",
            brands: [],
            brandSearch: "",
            brandSimilar: [],
            manufacturers: [],
            equipments: [],
            equipmentSearch: "",
            saving: false,
            done: 0,
            hasChanges: false,
        });
        onWillStart(async () => {
            const ctx = this.props.action?.context || {};
            const [tree, queue, brands] = await Promise.all([
                this.orm.call("product.category", "biotex_get_tree", []),
                this.orm.call("product.template", "biotex_classifier_queue", [ctx.biotex_product_ids || null]),
                this.orm.searchRead("biotex.brand", [], ["id", "name"], { limit: 500, order: "name" }),
            ]);
            this.state.tree = tree;
            this.state.queue = queue;
            this.state.brands = brands;
            this.loadCurrent();
        });
    }

    // ------------------------------------------------------------ cola
    get current() { return this.state.queue[this.state.queueIndex]; }
    get progress() {
        return this.state.queue.length ? Math.round((this.state.done / this.state.queue.length) * 100) : 0;
    }
    loadCurrent() {
        const p = this.current;
        const prod = EMPTY();
        if (p) {
            Object.assign(prod, {
                id: p.id, name: p.name, biotex_name: p.biotex_name || "", biotex_measure: p.biotex_measure || "",
                biotex_content: p.biotex_content || "", biotex_usage_notes: p.biotex_usage_notes || "",
                biotex_group_id: p.biotex_group_id ? p.biotex_group_id[0] : false,
                biotex_family_id: p.biotex_family_id ? p.biotex_family_id[0] : false,
                biotex_brand_id: p.biotex_brand_id ? p.biotex_brand_id[0] : false,
                biotex_model: p.biotex_model || "", biotex_reference: p.biotex_reference || "",
                biotex_manufacturer_id: p.biotex_manufacturer_id ? p.biotex_manufacturer_id[0] : false,
                biotex_equipment_ids: p.biotex_equipment_ids || [],
                image_128: p.image_128, existingPhotos: p.biotex_photo_count || 0, description: p.description,
            });
            // si no tiene nombre base, sugerir el nombre actual como punto de partida
            if (!prod.biotex_name && p.name) prod.biotex_name = p.name;
        }
        this.state.product = prod;
        this.state.step = 0;
        this.state.hasChanges = false;
        this.state.familySearch = "";
    }
    newProduct() {
        this.state.queue.splice(this.state.queueIndex + 1, 0, { id: false, name: _t("Nuevo producto") });
        this.state.queueIndex += 1;
        this.loadCurrent();
    }
    skip() {
        if (this.state.queueIndex < this.state.queue.length - 1) {
            this.state.queueIndex += 1;
            this.loadCurrent();
        }
    }
    previous() {
        if (this.state.queueIndex > 0) {
            this.state.queueIndex -= 1;
            this.loadCurrent();
        }
    }

    // ------------------------------------------------------------ pasos
    get stepKey() { return STEPS[this.state.step].key; }
    canGo(i) { return i <= this.state.step || this.stepValid(this.state.step); }
    stepValid(i) {
        const p = this.state.product;
        switch (STEPS[i].key) {
            case "group": return !!p.biotex_group_id;
            case "family": return !!p.biotex_family_id;
            case "description": return !!p.biotex_name && !!p.biotex_measure;
            case "brand": return !!p.biotex_brand_id;
            default: return true;
        }
    }
    goTo(i) { if (this.canGo(i)) this.state.step = i; }
    next() {
        if (!this.stepValid(this.state.step)) {
            this.notification.add(_t("Complete los campos obligatorios de este paso."), { type: "warning" });
            return;
        }
        if (this.state.step < STEPS.length - 1) this.state.step += 1;
    }
    back() { if (this.state.step > 0) this.state.step -= 1; }

    // ------------------------------------------------------------ grupo / familia
    get group() { return this.state.tree.find((g) => g.id === this.state.product.biotex_group_id); }
    get families() {
        const g = this.group;
        if (!g) return [];
        const q = this.state.familySearch.toLowerCase();
        return g.families.filter((f) => !q || f.name.toLowerCase().includes(q) || (f.code || "").toLowerCase().includes(q));
    }
    get family() { return this.group?.families.find((f) => f.id === this.state.product.biotex_family_id); }
    selectGroup(g) {
        this.state.product.biotex_group_id = g.id;
        this.state.product.biotex_family_id = false;
        this.state.hasChanges = true;
        this.state.step = 1;
    }
    selectFamily(f) {
        this.state.product.biotex_family_id = f.id;
        this.state.hasChanges = true;
        this.state.step = 2;
    }

    // ------------------------------------------------------------ descripción
    get previewName() {
        const p = this.state.product;
        return [p.biotex_name, p.biotex_measure, p.biotex_content].map((x) => (x || "").trim()).filter(Boolean).join(" ");
    }
    onInput(field, ev) {
        this.state.product[field] = ev.target.value;
        this.state.hasChanges = true;
    }

    // ------------------------------------------------------------ marca
    get filteredBrands() {
        const q = this.state.brandSearch.toLowerCase();
        return this.state.brands.filter((b) => !q || b.name.toLowerCase().includes(q)).slice(0, 12);
    }
    get brandName() {
        const b = this.state.brands.find((b) => b.id === this.state.product.biotex_brand_id);
        return b ? b.name : "";
    }
    async onBrandSearch(ev) {
        this.state.brandSearch = ev.target.value;
        this.state.brandSimilar = this.state.brandSearch.length > 2
            ? await this.orm.call("biotex.brand", "find_similar", [this.state.brandSearch]) : [];
    }
    selectBrand(b) {
        this.state.product.biotex_brand_id = b.id;
        this.state.brandSearch = "";
        this.state.brandSimilar = [];
        this.state.hasChanges = true;
    }
    async createBrand() {
        const name = this.state.brandSearch.trim();
        if (!name) return;
        const exact = this.state.brandSimilar.find((b) => b.exact);
        if (exact) {
            this.notification.add(_t("La marca ya existe como \"%s\"; se usará esa.", exact.name), { type: "info" });
            this.selectBrand(exact);
            return;
        }
        try {
            const [id] = await this.orm.create("biotex.brand", [{ name }]);
            const brand = { id, name };
            this.state.brands.push(brand);
            this.state.brands.sort((a, b) => a.name.localeCompare(b.name));
            this.selectBrand(brand);
        } catch (e) {
            this.notification.add(e.data?.message || e.message, { type: "danger" });
        }
    }
    async onEquipmentSearch(ev) {
        this.state.equipmentSearch = ev.target.value;
        if (this.state.equipmentSearch.length < 2) { this.state.equipments = []; return; }
        this.state.equipments = await this.orm.searchRead(
            "biotex.equipment", [["display_name", "ilike", this.state.equipmentSearch]], ["id", "display_name"], { limit: 8 });
    }
    toggleEquipment(eq) {
        const ids = this.state.product.biotex_equipment_ids;
        const i = ids.indexOf(eq.id);
        if (i >= 0) ids.splice(i, 1); else ids.push(eq.id);
        if (!this.state.equipmentLabels) this.state.equipmentLabels = {};
        this.state.equipmentLabels[eq.id] = eq.display_name;
        this.state.hasChanges = true;
    }
    equipmentLabel(id) { return (this.state.equipmentLabels || {})[id] || `#${id}`; }
    async onManufacturerSearch(ev) {
        const q = ev.target.value;
        this.state.manufacturers = q.length > 1
            ? await this.orm.searchRead("res.partner", [["name", "ilike", q], ["is_company", "=", true]], ["id", "name"], { limit: 8 }) : [];
    }
    selectManufacturer(m) {
        this.state.product.biotex_manufacturer_id = m.id;
        this.state.manufacturerName = m.name;
        this.state.manufacturers = [];
        this.state.hasChanges = true;
    }

    // ------------------------------------------------------------ fotos
    get photoSlots() { return ["image_1920", "biotex_image_2", "biotex_image_3"]; }
    onPhoto(field, ev) {
        const file = ev.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            this.state.product[field] = reader.result.split(",")[1];
            this.state.hasChanges = true;
        };
        reader.readAsDataURL(file);
    }
    clearPhoto(field) { this.state.product[field] = null; this.state.hasChanges = true; }
    get photoCount() {
        return this.photoSlots.filter((f) => this.state.product[f]).length + (this.state.product.existingPhotos || 0);
    }

    // ------------------------------------------------------------ guardar
    async save(andNext = true) {
        const p = this.state.product;
        for (let i = 0; i < STEPS.length; i++) {
            if (!this.stepValid(i)) { this.state.step = i; this.next(); return; }
        }
        if (this.photoCount === 0 && this.family?.photo_required) {
            this.notification.add(_t("Esta familia exige foto. El producto quedará como 'Clasificado sin foto'."), { type: "warning" });
        }
        this.state.saving = true;
        const vals = {
            biotex_name: p.biotex_name, biotex_measure: p.biotex_measure, biotex_content: p.biotex_content,
            biotex_usage_notes: p.biotex_usage_notes, biotex_family_id: p.biotex_family_id,
            biotex_brand_id: p.biotex_brand_id, biotex_model: p.biotex_model, biotex_reference: p.biotex_reference || false,
            biotex_manufacturer_id: p.biotex_manufacturer_id || false,
            biotex_equipment_ids: [[6, 0, p.biotex_equipment_ids]],
            name: this.previewName,
        };
        for (const f of this.photoSlots) if (p[f]) vals[f] = p[f];
        try {
            const res = await this.orm.call("product.template", "biotex_classifier_save", [p.id || false, vals]);
            this.state.queue[this.state.queueIndex] = { ...this.current, id: res.id, name: res.name, default_code: res.default_code, saved: true };
            this.state.done += 1;
            this.notification.add(_t("Guardado: %s → %s", res.default_code, res.name), { type: "success" });
            if (andNext) this.skip();
        } catch (e) {
            this.notification.add(e.data?.message || e.message, { type: "danger", sticky: true });
        } finally {
            this.state.saving = false;
        }
    }
    openForm() {
        if (!this.current?.id) return;
        this.action.doAction({ type: "ir.actions.act_window", res_model: "product.template", res_id: this.current.id, views: [[false, "form"]], target: "current" });
    }
}

registry.category("actions").add("biotex_catalog.classifier", BiotexClassifier);
