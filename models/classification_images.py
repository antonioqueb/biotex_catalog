"""Stage product photos in the existing classification session until confirmation."""
import base64
import binascii
import hashlib
from urllib.parse import urlencode

from odoo import api, fields, models
from odoo.exceptions import UserError

PHOTOS = {'image_1920': 'Imagen principal', 'biotex_image_2': 'Imagen 2', 'biotex_image_3': 'Imagen 3'}
# Etiquetas cortas de la galería de la etapa 3 (columna "Imagen"): la principal y las dos secundarias.
GALLERY_LABELS = {'image_1920': 'Principal', 'biotex_image_2': 'Secundaria 1', 'biotex_image_3': 'Secundaria 2'}
MAX_GALLERY_IMAGES = 3
THUMB_SIZE = 96
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_PHOTO_WRITE = object()


def image_url(record, field, label, size=None):
    """URL de /web/image para un campo binario del registro, o False si está vacío.

    Se llama con ``bin_size=True`` en el registro para no leer el binario: solo interesa si existe.
    ``size`` pide al servidor una miniatura cuadrada en lugar de la imagen completa.
    """
    if not record[field]:
        return False
    params = {'unique': str(record.write_date or ''), 'filename': label}
    if size:
        params.update(width=size, height=size)
    return '/web/image/%s/%s/%s?%s' % (record._name, record.id, field, urlencode(params))


def checksum(value):
    if isinstance(value, str):
        value = value.encode('ascii')
    return hashlib.sha256(value or b'').hexdigest()


class ClassificationSession(models.Model):
    _inherit = 'biotex.classification.session'

    def workspace_update_line(self, line_id, vals):
        self.ensure_one()
        self._lock_workspace()
        self._check_editable()
        line = self.line_ids.filtered(lambda item: item.id == line_id)
        if not line:
            raise UserError('La línea ya no pertenece a esta sesión.')
        changes = vals.get('image_changes', {})
        if not isinstance(changes, dict) or set(changes) - PHOTOS.keys():
            raise UserError('Seleccione una de las tres imágenes del producto.')
        with self.env.cr.savepoint():
            super().workspace_update_line(line_id, {k: v for k, v in vals.items() if k != 'image_changes'})
            if changes:
                line._save_photos(changes)
        return self._workspace_session()


class ClassificationLine(models.Model):
    _inherit = 'biotex.classification.session.line'

    image_1920 = fields.Image(string='Imagen principal pendiente', max_width=1920, max_height=1920, copy=False)
    biotex_image_2 = fields.Image(string='Imagen 2 pendiente', max_width=1920, max_height=1920, copy=False)
    biotex_image_3 = fields.Image(string='Imagen 3 pendiente', max_width=1920, max_height=1920, copy=False)
    photo_baselines = fields.Json(string='Versiones originales de imágenes', copy=False, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if any(set(vals) & (PHOTOS.keys() | {'photo_baselines'}) for vals in vals_list):
            raise UserError('Agregue las imágenes desde el editor de la sesión.')
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) & (PHOTOS.keys() | {'photo_baselines'}) and self.env.context.get('_classification_photo_write') is not _PHOTO_WRITE:
            raise UserError('Guarde las imágenes desde el editor de la sesión.')
        return super().write(vals)

    def _save_photos(self, changes):
        self.ensure_one()
        self.check_access('write')
        self.product_id.check_access('read')
        baselines = dict(self.photo_baselines or {})
        values = {}
        for name, value in changes.items():
            if value is False:  # Discard a staged replacement; never delete the catalog's photo.
                baselines.pop(name, None)
                values[name] = False
                continue
            if not isinstance(value, str) or not value or len(value) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
                raise UserError('Cada imagen debe ser un archivo válido de hasta 10 MB.')
            try:
                decoded = base64.b64decode(value, validate=True)
            except (ValueError, binascii.Error):
                raise UserError('No se pudo leer la imagen. Seleccione el archivo nuevamente.')
            if not decoded or len(decoded) > MAX_IMAGE_BYTES:
                raise UserError('Cada imagen debe ser un archivo válido de hasta 10 MB.')
            baselines.setdefault(name, checksum(self.product_id.with_context(bin_size=False)[name]))
            values[name] = value
        values['photo_baselines'] = baselines
        self.with_context(_classification_photo_write=_PHOTO_WRITE).write(values)

    def _photo_source(self, name):
        """Registro del que se muestra la foto ``name``: la línea si tiene un reemplazo pendiente, si no el producto."""
        pending = name in (self.photo_baselines or {}) and self.state != 'applied'
        source = (self if pending else self.product_id).with_context(bin_size=True)
        return source, pending

    def _workspace_line(self, moved=None):
        """Añade ``images`` (máximo 3) para la columna "Imagen" de la etapa 3.

        Se calcula aquí, en el mismo RPC que devuelve las líneas, para que la tabla no haga una
        consulta por fila. La fuente es la ficha del producto (``image_1920`` más las dos fotos
        secundarias del catálogo) y, como respaldo, ``product.image`` cuando la instancia tiene
        eCommerce instalado. Un reemplazo pendiente en la línea se muestra en lugar de la foto actual.
        """
        data = super()._workspace_line(moved=moved)
        images = []
        for name, label in GALLERY_LABELS.items():
            source, pending = self._photo_source(name)
            url = image_url(source, name, label)
            if url:
                images.append({'field': name, 'label': label, 'url': url,
                               'thumb_url': image_url(source, name, label, THUMB_SIZE), 'pending': pending})
        if len(images) < MAX_GALLERY_IMAGES and 'product_template_image_ids' in self.product_id._fields:
            extra = self.product_id.product_template_image_ids.sorted(lambda i: (i.sequence, i.id)).with_context(bin_size=True)
            for image in extra[:MAX_GALLERY_IMAGES - len(images)]:
                label = list(GALLERY_LABELS.values())[len(images)]  # etiqueta del hueco que ocupa
                images.append({'field': 'product_image_%d' % image.id, 'label': label, 'url': image_url(image, 'image_1920', label),
                               'thumb_url': image_url(image, 'image_1920', label, THUMB_SIZE), 'pending': False})
        data['images'] = images[:MAX_GALLERY_IMAGES]
        return data

    def _workspace_detail(self):
        data = super()._workspace_detail()
        product = self.product_id.with_context(bin_size=True)
        baselines = self.photo_baselines or {}
        photos = []
        for name, label in PHOTOS.items():
            source, pending = self._photo_source(name)
            photos.append({'field': name, 'label': label, 'url': image_url(source, name, label), 'original_url': image_url(product, name, label),
                'pending': pending, 'conflict': pending and baselines[name] != checksum(self.product_id.with_context(bin_size=False)[name])})
        data['photos'] = photos
        return data

    def _apply(self):
        self.ensure_one()
        changes = {}
        for name, original in (self.photo_baselines or {}).items():
            if original != checksum(self.product_id.with_context(bin_size=False)[name]):
                raise UserError('La %s de "%s" cambió en el catálogo. Abra el lápiz, revise las imágenes y use la imagen actual antes de seleccionar un nuevo cambio.' % (PHOTOS[name].lower(), self.product_id.display_name))
            changes[name] = self.with_context(bin_size=False)[name]
        result = super()._apply()
        if changes:
            self.product_id.write(changes)
        return result
