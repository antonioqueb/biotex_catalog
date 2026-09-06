/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

export class BiotexClassificationReviewDialog extends Component {
    static template = "biotex_catalog.ClassificationReviewDialog";
    static components = { Dialog };
    static props = { close: Function, preview: Object, onConfirm: Function };

    setup() {
        this.notification = useService("notification");
        this.state = useState({ acknowledged: false, saving: false });
    }

    async confirm() {
        if (this.state.saving || (this.props.preview.changes.length && !this.state.acknowledged)) return;
        this.state.saving = true;
        try {
            await this.props.onConfirm();
            this.props.close();
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "danger", sticky: true });
            this.props.close(); // A new preview is required after a conflict.
        } finally {
            this.state.saving = false;
        }
    }
}
