/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const STEPS = [
    { key: "group", label: "Grupo" },
    { key: "family", label: "Familia" },
    { key: "classifier", label: "Clasificador" },
    { key: "brand", label: "Marca" },
    { key: "description", label: "Descripción" },
    { key: "usage", label: "Uso y origen" },
    { key: "photos", label: "Fotos" },
    { key: "review", label: "Revisión" },
];

const EMPTY = () => ({
    id: false, name: "", biotex_name: "", biotex_measure: "", biotex_content: "", biotex_package_type: "", biotex_package_qty: 1,
    biotex_usage_notes: "", biotex_group_id: false, biotex_family_id: false, biotex_classifier_id: false, biotex_brand_id: false,
    biotex_model: "", biotex_reference: "", biotex_manufacturer_id: false, biotex_country_id: false, biotex_primary_distributor_id: false,
    biotex_equipment_ids: [], biotex_main_equipment_id: false, biotex_specialty_ids: [], biotex_main_specialty_id: false,
    image_1920: null, biotex_image_2: null, biotex_image_3: null,
});

/**
 * Asistente de clasificación v2. Sigue el orden de la clave GG-MMMM-FFF-CCC-NN:
 * grupo (eje) → familia → clasificador autorizado → marca (código) → descripción → uso y origen → fotos → revisión.
 */
export class BiotexClassifier extends Component {
    static template = "biotex_catalog.Classifier";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.steps = STEPS;
        this.state = useState({
            step: 0, tree: [], queue: [], queueIndex: 0, product: EMPTY(), familySearch: "", classifierSearch: "",
            brands: [], brandSearch: "", brandSimilar: [], newBrandCode: "", manufacturers: [], manufacturerName: "",
            distributors: [], distributorName: "", countries: [], countryName: "", equipments: [], equipmentSearch: "", equipmentLabels: {},
            specialties: [], preview: { clave: "", generic: "" }, saving: false, done: 0,
        });
        onWillStart(async () => {
            const ctx = this.props.action?.context || {};
            const [tree, queue, brands, specialties, countries] = await Promise.all([
                this.orm.call("product.category", "biotex_get_tree", []),
                this.orm.call("product.template", "biotex_classifier_queue", [ctx.biotex_product_ids || null]),
                this.orm.searchRead("biotex.brand", [], ["id", "name", "code"], { limit: 1000, order: "name" }),
                this.orm.searchRead("biotex.specialty", [], ["id", "name", "code"], { order: "name" }),
                this.orm.searchRead("res.country", [], ["id", "name"], { order: "name" }),
            ]);
            Object.assign(this.state, { tree, queue, brands, specialties, countries });
            this.loadCurrent();
        });
    }

    // ------------------------------------------------------------ cola
    get current() { return this.state.queue[this.state.queueIndex]; }
    get progress() { return this.state.queue.length ? Math.round((this.state.done / this.state.queue.length) * 100) : 0; }
    m2o(v) { return v ? v[0] : false; }
    loadCurrent() {
        const p = this.current;
        const prod = EMPTY();
        if (p) {
            Object.assign(prod, {
                id: p.id, name: p.name, biotex_name: p.biotex_name || p.name || "", biotex_measure: p.biotex_measure || "", biotex_content: p.biotex_content || "",
                biotex_package_type: p.biotex_package_type || "", biotex_package_qty: p.biotex_package_qty || 1, biotex_usage_notes: p.biotex_usage_notes || "",
                biotex_group_id: this.m2o(p.biotex_group_id), biotex_family_id: this.m2o(p.biotex_family_id), biotex_classifier_id: this.m2o(p.biotex_classifier_id),
                biotex_brand_id: this.m2o(p.biotex_brand_id), biotex_model: p.biotex_model || "", biotex_reference: p.biotex_reference || "",
                biotex_manufacturer_id: this.m2o(p.biotex_manufacturer_id), biotex_country_id: this.m2o(p.biotex_country_id), biotex_primary_distributor_id: this.m2o(p.biotex_primary_distributor_id),
                biotex_equipment_ids: p.biotex_equipment_ids || [], biotex_main_equipment_id: this.m2o(p.biotex_main_equipment_id),
                biotex_specialty_ids: p.biotex_specialty_ids || [], biotex_main_specialty_id: this.m2o(p.biotex_main_specialty_id),
                image_128: p.image_128, existingPhotos: p.biotex_photo_count || 0, description: p.description, legacy: p.biotex_legacy_code,
            });
            this.state.manufacturerName = p.biotex_manufacturer_id ? p.biotex_manufacturer_id[1] : "";
            this.state.distributorName = p.biotex_primary_distributor_id ? p.biotex_primary_distributor_id[1] : "";
            this.state.countryName = p.biotex_country_id ? p.biotex_country_id[1] : "";
            if (p.biotex_main_equipment_id) this.state.equipmentLabels[p.biotex_main_equipment_id[0]] = p.biotex_main_equipment_id[1];
        }
        this.state.product = prod;
        this.state.step = 0;
        this.state.familySearch = this.state.classifierSearch = "";
        this.state.preview = { clave: "", generic: "" };
    }
    newProduct() { this.state.queue.splice(this.state.queueIndex + 1, 0, { id: false, name: _t("Nuevo producto") }); this.state.queueIndex += 1; this.loadCurrent(); }
    skip() { if (this.state.queueIndex < this.state.queue.length - 1) { this.state.queueIndex += 1; this.loadCurrent(); } }
    previous() { if (this.state.queueIndex > 0) { this.state.queueIndex -= 1; this.loadCurrent(); } }

    // ------------------------------------------------------------ pasos
    get stepKey() { return STEPS[this.state.step].key; }
    canGo(i) { return i <= this.state.step || this.stepValid(this.state.step); }
    stepValid(i) {
        const p = this.state.product;
        switch (STEPS[i].key) {
            case "group": return !!p.biotex_group_id;
            case "family": return !!p.biotex_family_id;
            case "classifier": return !!p.biotex_classifier_id;
            case "brand": return !!p.biotex_brand_id;
            case "description": return !!p.biotex_name && !!p.biotex_measure && !!p.biotex_content;
            default: return true;
        }
    }
    goTo(i) { if (this.canGo(i)) { this.state.step = i; if (STEPS[i].key === "review") this.refreshPreview(); } }
    next() {
        if (!this.stepValid(this.state.step)) { this.notification.add(_t("Complete los campos obligatorios de este paso."), { type: "warning" }); return; }
        if (this.state.step < STEPS.length - 1) { this.state.step += 1; if (this.stepKey === "review") this.refreshPreview(); }
    }
    back() { if (this.state.step > 0) this.state.step -= 1; }
    onInput(field, ev) { this.state.product[field] = ev.target.value; }

    // ------------------------------------------------------------ grupo / familia / clasificador
    get group() { return this.state.tree.find((g) => g.id === this.state.product.biotex_group_id); }
    get families() {
        const g = this.group; if (!g) return [];
        const q = this.state.familySearch.toLowerCase();
        return g.families.filter((f) => !q || f.name.toLowerCase().includes(q) || (f.code || "").toLowerCase().includes(q));
    }
    get family() { return this.group?.families.find((f) => f.id === this.state.product.biotex_family_id); }
    get classifiers() {
        const f = this.family; if (!f) return [];
        const q = this.state.classifierSearch.toLowerCase();
        return f.classifiers.filter((c) => !q || c.name.toLowerCase().includes(q) || c.code.toLowerCase().includes(q));
    }
    get classifier() { return this.family?.classifiers.find((c) => c.id === this.state.product.biotex_classifier_id); }
    selectGroup(g) { Object.assign(this.state.product, { biotex_group_id: g.id, biotex_family_id: false, biotex_classifier_id: false }); this.state.step = 1; }
    selectFamily(f) { Object.assign(this.state.product, { biotex_family_id: f.id, biotex_classifier_id: false }); this.state.step = 2; }
    selectClassifier(c) { this.state.product.biotex_classifier_id = c.id; this.state.step = 3; }

    // ------------------------------------------------------------ marca
    get filteredBrands() {
        const q = this.state.brandSearch.toLowerCase();
        return this.state.brands.filter((b) => !q || b.name.toLowerCase().includes(q) || (b.code || "").toLowerCase().includes(q)).slice(0, 12);
    }
    get brand() { return this.state.brands.find((b) => b.id === this.state.product.biotex_brand_id); }
    async onBrandSearch(ev) {
        this.state.brandSearch = ev.target.value;
        if (this.state.brandSearch.length > 2) {
            const [similar, code] = await Promise.all([
                this.orm.call("biotex.brand", "find_similar", [this.state.brandSearch]),
                this.orm.call("biotex.brand", "suggest_code", [this.state.brandSearch]),
            ]);
            this.state.brandSimilar = similar; this.state.newBrandCode = code;
        } else { this.state.brandSimilar = []; this.state.newBrandCode = ""; }
    }
    selectBrand(b) { this.state.product.biotex_brand_id = b.id; this.state.brandSearch = ""; this.state.brandSimilar = []; }
    async createBrand() {
        const name = this.state.brandSearch.trim(); if (!name) return;
        const exact = this.state.brandSimilar.find((b) => b.exact);
        if (exact) { this.notification.add(_t("La marca ya existe como \"%s\"; se usará esa.", exact.name), { type: "info" }); this.selectBrand(exact); return; }
        try {
            const code = (this.state.newBrandCode || "").toUpperCase();
            const [id] = await this.orm.create("biotex.brand", [{ name, code }]);
            const brand = { id, name, code };
            this.state.brands.push(brand); this.state.brands.sort((a, b) => a.name.localeCompare(b.name));
            this.selectBrand(brand);
        } catch (e) { this.notification.add(e.data?.message || e.message, { type: "danger" }); }
    }

    // ------------------------------------------------------------ uso y origen
    async onEquipmentSearch(ev) {
        this.state.equipmentSearch = ev.target.value;
        this.state.equipments = this.state.equipmentSearch.length < 2 ? [] :
            await this.orm.searchRead("biotex.equipment", [["display_name", "ilike", this.state.equipmentSearch]], ["id", "display_name"], { limit: 8 });
    }
    toggleEquipment(eq) {
        const ids = this.state.product.biotex_equipment_ids; const i = ids.indexOf(eq.id);
        if (i >= 0) ids.splice(i, 1); else ids.push(eq.id);
        this.state.equipmentLabels[eq.id] = eq.display_name;
        if (!this.state.product.biotex_main_equipment_id && ids.length) this.state.product.biotex_main_equipment_id = ids[0];
        if (!ids.includes(this.state.product.biotex_main_equipment_id)) this.state.product.biotex_main_equipment_id = ids[0] || false;
    }
    equipmentLabel(id) { return this.state.equipmentLabels[id] || `#${id}`; }
    noop() {}
    clearBrand() { this.state.product.biotex_brand_id = false; }
    onBrandCode(ev) { this.state.newBrandCode = ev.target.value.toUpperCase(); }
    setMainEquipment(id) { this.state.product.biotex_main_equipment_id = id; }
    setMainSpecialty(s) {
        if (!this.state.product.biotex_specialty_ids.includes(s.id)) this.state.product.biotex_specialty_ids.push(s.id);
        this.state.product.biotex_main_specialty_id = s.id;
    }
    toggleSpecialty(s) {
        const ids = this.state.product.biotex_specialty_ids; const i = ids.indexOf(s.id);
        if (i >= 0) ids.splice(i, 1); else ids.push(s.id);
        if (!ids.includes(this.state.product.biotex_main_specialty_id)) this.state.product.biotex_main_specialty_id = ids[0] || false;
    }
    async onPartnerSearch(kind, ev) {
        const q = ev.target.value; const dom = kind === "distributors" ? [["name", "ilike", q], ["supplier_rank", ">", 0]] : [["name", "ilike", q], ["is_company", "=", true]];
        this.state[kind] = q.length > 1 ? await this.orm.searchRead("res.partner", dom, ["id", "name"], { limit: 8 }) : [];
    }
    selectPartner(kind, m) {
        if (kind === "manufacturers") { this.state.product.biotex_manufacturer_id = m.id; this.state.manufacturerName = m.name; }
        else { this.state.product.biotex_primary_distributor_id = m.id; this.state.distributorName = m.name; }
        this.state[kind] = [];
    }
    onCountry(ev) { const id = parseInt(ev.target.value) || false; this.state.product.biotex_country_id = id; this.state.countryName = (this.state.countries.find((c) => c.id === id) || {}).name || ""; }

    // ------------------------------------------------------------ fotos
    get photoSlots() { return ["image_1920", "biotex_image_2", "biotex_image_3"]; }
    onPhoto(field, ev) {
        const file = ev.target.files[0]; if (!file) return;
        const reader = new FileReader();
        reader.onload = () => { this.state.product[field] = reader.result.split(",")[1]; };
        reader.readAsDataURL(file);
    }
    clearPhoto(field) { this.state.product[field] = null; }
    get photoCount() { return this.photoSlots.filter((f) => this.state.product[f]).length + (this.state.product.existingPhotos || 0); }

    // ------------------------------------------------------------ revisión / guardar
    get previewName() {
        const p = this.state.product;
        return [p.biotex_name, p.biotex_measure, p.biotex_content].map((x) => (x || "").trim()).filter(Boolean).join(" ");
    }
    async refreshPreview() {
        const p = this.state.product;
        this.state.preview = await this.orm.call("product.template", "biotex_classifier_preview", [{ id: p.id, biotex_family_id: p.biotex_family_id, biotex_classifier_id: p.biotex_classifier_id, biotex_brand_id: p.biotex_brand_id }]);
    }
    vals() {
        const p = this.state.product;
        const v = {
            biotex_name: p.biotex_name, biotex_measure: p.biotex_measure, biotex_content: p.biotex_content, biotex_package_type: p.biotex_package_type,
            biotex_package_qty: parseFloat(p.biotex_package_qty) || 1, biotex_usage_notes: p.biotex_usage_notes, biotex_family_id: p.biotex_family_id,
            biotex_classifier_id: p.biotex_classifier_id, biotex_brand_id: p.biotex_brand_id, biotex_model: p.biotex_model, biotex_reference: p.biotex_reference || false,
            biotex_manufacturer_id: p.biotex_manufacturer_id || false, biotex_country_id: p.biotex_country_id || false, biotex_primary_distributor_id: p.biotex_primary_distributor_id || false,
            biotex_equipment_ids: [[6, 0, p.biotex_equipment_ids]], biotex_main_equipment_id: p.biotex_main_equipment_id || false,
            biotex_specialty_ids: [[6, 0, p.biotex_specialty_ids]], biotex_main_specialty_id: p.biotex_main_specialty_id || false, name: this.previewName,
        };
        for (const f of this.photoSlots) if (p[f]) v[f] = p[f];
        return v;
    }
    async save(andNext = true) {
        for (let i = 0; i < STEPS.length; i++) if (!this.stepValid(i)) { this.state.step = i; this.next(); return; }
        if (this.photoCount === 0 && this.family?.photo_required) this.notification.add(_t("Esta familia exige foto: el producto quedará como 'Clasificado sin foto'."), { type: "warning" });
        this.state.saving = true;
        try {
            const res = await this.orm.call("product.template", "biotex_classifier_save", [this.state.product.id || false, this.vals()]);
            this.state.queue[this.state.queueIndex] = { ...this.current, id: res.id, name: res.name, default_code: res.default_code, saved: true };
            this.state.done += 1;
            this.notification.add(_t("Guardado: %s → %s (%s)", res.default_code, res.name, res.generic), { type: "success" });
            if (andNext) this.skip();
        } catch (e) { this.notification.add(e.data?.message || e.message, { type: "danger", sticky: true }); }
        finally { this.state.saving = false; }
    }
    openForm() {
        if (!this.current?.id) return;
        this.action.doAction({ type: "ir.actions.act_window", res_model: "product.template", res_id: this.current.id, views: [[false, "form"]], target: "current" });
    }
}

registry.category("actions").add("biotex_catalog.classifier", BiotexClassifier);
