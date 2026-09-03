/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const META = {
    unclassified: { label: "Sin clasificar", icon: "fa-question-circle", cls: "text-bg-danger" },
    no_photo: { label: "Sin foto", icon: "fa-camera", cls: "text-bg-warning" },
    complete: { label: "Completo", icon: "fa-check-circle", cls: "text-bg-success" },
};

export class BiotexClassBadge extends Component {
    static template = "biotex_catalog.ClassBadge";
    static props = { ...standardFieldProps };
    get meta() {
        return META[this.props.record.data[this.props.name]] || META.unclassified;
    }
    get missing() {
        return this.props.record.data.biotex_missing || "";
    }
}

registry.category("fields").add("biotex_class_badge", {
    component: BiotexClassBadge,
    supportedTypes: ["selection"],
    fieldDependencies: [{ name: "biotex_missing", type: "char" }],
});
