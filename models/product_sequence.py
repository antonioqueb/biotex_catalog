"""One durable, transactionally allocated counter per catalog prefix."""
import re

from odoo import api, fields, models
from odoo.exceptions import UserError


PREFIX = r'(?:[A-Z]{2}-[A-Z0-9]{4}-[A-Z0-9]{3}-[A-Z0-9]{3}|G-[A-Z]{2}-[A-Z0-9]{3}-[A-Z0-9]{3})'
CODE = re.compile(r'^(' + PREFIX + r')-([0-9]+)$')


class BiotexProductSequence(models.Model):
    _name = 'biotex.product.sequence'
    _description = 'Último consecutivo reservado de catálogo'
    _rec_name = 'prefix'

    prefix = fields.Char(required=True, readonly=True)
    last_number = fields.Integer(required=True, default=0, readonly=True)

    _prefix_unique = models.Constraint('UNIQUE(prefix)', 'Cada clasificación tiene un solo contador.')
    _number_positive = models.Constraint('CHECK(last_number >= 0)', 'El consecutivo no puede ser negativo.')

    @api.model
    def _split_code(self, code):
        match = CODE.fullmatch(code or '')
        return (match[1], int(match[2])) if match else None

    @api.model
    def _validate_prefix(self, prefix):
        prefix = prefix.rstrip('-')
        if not re.fullmatch(PREFIX, prefix):
            raise UserError('Complete la clasificación antes de generar una clave.')
        return prefix

    @api.model
    def _observed_max(self, prefix):
        """Read actual suffixes, including archived/restricted products and old reservations.

        This intentionally bypasses record rules for the numeric watermark only;
        it never returns another company's product details to the caller.
        """
        self.env['product.template'].flush_model(['default_code', 'biotex_consecutive'])
        self.env['product.product'].flush_model(['default_code'])
        self.env['biotex.generic'].flush_model(['code', 'consecutive'])
        self.env['biotex.classification.session'].flush_model(['class_code'])
        self.env['biotex.classification.session.line'].flush_model([
            'consecutive', 'reference', 'old_reference', 'applied_reference_before', 'applied_reference_after'])
        self.env['biotex.product.code.history'].flush_model(['prefix','consecutive'])
        pattern = '^' + re.escape(prefix) + r'-([0-9]+)$'
        self.env.cr.execute('''
            SELECT coalesce(max(number), 0) FROM (
                SELECT greatest(substring(default_code from %(pattern)s)::numeric,
                                coalesce(biotex_consecutive, 0)) AS number
                  FROM product_template WHERE default_code ~ %(pattern)s
                UNION ALL
                SELECT substring(default_code from %(pattern)s)::numeric
                  FROM product_product WHERE default_code ~ %(pattern)s
                UNION ALL
                SELECT greatest(substring(code from %(pattern)s)::numeric, coalesce(consecutive, 0))
                  FROM biotex_generic WHERE code ~ %(pattern)s
                UNION ALL
                SELECT l.consecutive FROM biotex_classification_session_line l
                  JOIN biotex_classification_session s ON s.id = l.session_id
                  WHERE s.class_code = %(prefix)s
                UNION ALL
                SELECT substring(code from %(pattern)s)::numeric
                  FROM biotex_classification_session_line l
                  CROSS JOIN LATERAL unnest(ARRAY[l.reference, l.old_reference,
                    l.applied_reference_before, l.applied_reference_after]) AS codes(code)
                  WHERE code ~ %(pattern)s
                UNION ALL
                SELECT consecutive FROM biotex_product_code_history WHERE prefix = %(prefix)s
            ) observed
        ''', {'pattern': pattern, 'prefix': prefix})
        return int(self.env.cr.fetchone()[0])

    @api.model
    def _advance(self, prefix, floor, *, reserve=False):
        prefix = self._validate_prefix(prefix)
        floor = int(floor)
        if floor < 0 or floor + int(reserve) > 2147483647:
            raise UserError('El consecutivo de esta clasificación excede el rango disponible.')
        # ON CONFLICT also serializes creation of a previously unseen prefix.
        # Under Odoo's repeatable-read isolation a competing stale transaction
        # receives SerializationFailure, which the RPC layer retries in full.
        self.env.cr.execute('''
            INSERT INTO biotex_product_sequence
                (prefix, last_number, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, %s, %s, now() at time zone 'UTC', now() at time zone 'UTC')
            ON CONFLICT (prefix) DO UPDATE SET
                last_number = greatest(biotex_product_sequence.last_number, %s) + %s,
                write_uid = excluded.write_uid, write_date = excluded.write_date
            RETURNING id, last_number
        ''', (prefix, floor + int(reserve), self.env.uid, self.env.uid, floor, int(reserve)))
        identifier, number = self.env.cr.fetchone()
        self.browse(identifier).invalidate_recordset()
        return number

    @api.model
    def _next(self, prefix, *, reserve=False):
        prefix = self._validate_prefix(prefix)
        floor = self._observed_max(prefix)
        if reserve:
            return self._advance(prefix, floor, reserve=True)
        self.env.cr.execute('SELECT last_number FROM biotex_product_sequence WHERE prefix = %s', (prefix,))
        row = self.env.cr.fetchone()
        return max(floor, row[0] if row else 0) + 1

    @api.model
    def _observe_codes(self, codes):
        floors = {}
        for code in codes:
            parts = self._split_code(code)
            if parts:
                prefix, number = parts
                floors[prefix] = max(floors.get(prefix, 0), number)
        for prefix, number in sorted(floors.items()):
            self._advance(prefix, number)

    @api.model
    def _seed_existing(self):
        """Preserve all currently known prefixes before records can be removed."""
        self.env.flush_all()
        self.env.cr.execute('''
            SELECT default_code FROM product_template WHERE default_code IS NOT NULL
            UNION SELECT default_code FROM product_product WHERE default_code IS NOT NULL
            UNION SELECT code FROM biotex_generic WHERE code IS NOT NULL
            UNION SELECT reference FROM biotex_classification_session_line WHERE reference IS NOT NULL
            UNION SELECT old_reference FROM biotex_classification_session_line WHERE old_reference IS NOT NULL
            UNION SELECT applied_reference_before FROM biotex_classification_session_line WHERE applied_reference_before IS NOT NULL
            UNION SELECT applied_reference_after FROM biotex_classification_session_line WHERE applied_reference_after IS NOT NULL
        ''')
        prefixes = {parts[0] for code, in self.env.cr.fetchall() if (parts := self._split_code(code))}
        for prefix in sorted(prefixes):
            self._advance(prefix, self._observed_max(prefix))
        return len(prefixes)
