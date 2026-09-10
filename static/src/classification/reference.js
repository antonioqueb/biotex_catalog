/** @odoo-module **/

/** La clave es GG-FFF-CCC-MMMM-NN: grupo, familia, clasificador, marca y consecutivo. */
export const CODE_ORDER = ["group", "family", "classifier", "brand"];

/**
 * Tono de cada segmento de una referencia ya generada. Las claves anteriores a septiembre de 2026
 * llevan la marca (4 caracteres) en el segundo segmento; se reconocen por su forma y se pintan igual.
 */
export function referenceTones(code) {
    const segments = (code || "").split("-");
    const legacy = segments.length > 1 && segments[1].length === 4;
    const order = legacy ? ["group", "brand", "family", "classifier"] : CODE_ORDER;
    return segments.map((text, i) => ({ text, tone: order[i] || "consecutive" }));
}
