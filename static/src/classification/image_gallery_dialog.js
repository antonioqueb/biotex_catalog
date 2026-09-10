/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * Vista ampliada de las imágenes de un producto desde la columna "Imagen" de la etapa 3.
 *
 * Solo visualiza: recibe las URLs ya calculadas por el servidor (máximo 3, imagen completa y
 * miniatura) y no hace ninguna llamada adicional. La imagen grande usa `image_1920`; las
 * miniaturas piden al servidor una versión reducida para no descargar tres imágenes completas.
 */
export class BiotexImageGalleryDialog extends Component {
    static template = "biotex_catalog.ClassificationImageGallery";
    static components = { Dialog };
    static props = { close: Function, title: String, images: Array };

    setup() {
        this.state = useState({ index: 0, loading: true, failed: false });
    }

    get images() { return this.props.images.slice(0, 3); }
    get active() { return this.images[this.state.index] || this.images[0]; }

    select(index) {
        if (index === this.state.index || !this.images[index]) return;
        this.state.index = index;
        this.state.loading = true;
        this.state.failed = false;
    }

    onLoad() { this.state.loading = false; }
    onError() { this.state.loading = false; this.state.failed = true; }

    onKeydown(ev) {
        if (this.images.length < 2) return;
        if (ev.key === "ArrowRight") this.select((this.state.index + 1) % this.images.length);
        else if (ev.key === "ArrowLeft") this.select((this.state.index - 1 + this.images.length) % this.images.length);
        else return;
        ev.preventDefault();
    }
}
