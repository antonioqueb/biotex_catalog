"""Run with python3 -m unittest discover -s tools -p test_catalog_workbook.py."""
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from catalog_workbook import identifiers, plan_rows, read_products, value


class CatalogWorkbookTest(unittest.TestCase):
    def workbook(self, path):
        book = Workbook()
        old = book.active
        old.title = 'RECLASIFICACION'
        headers = [None] * 56
        headers[5:7] = ['CLAVE', 'DESCRIPCION']
        headers[21:24] = ['CLAVE', 'CLAVE ALTERNA', 'DESCRIPCION']
        old.append(headers)
        row = [None] * 56
        row[21], row[23], row[48] = 'OLD-001', 'Legacy product without new classification', '#REF!'
        old.append(row)
        new = book.create_sheet('NUEVAS')
        new.append(headers[:21])
        row = [None] * 21
        row[5], row[6] = 'MC-BRND-SND-SON-01', 'New product without old data'
        new.append(row)
        new.append([None] * 21)
        book.save(path)

    def test_legacy_only_rows_and_new_rows_with_absent_old_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.xlsx'
            self.workbook(path)
            data = read_products(path)
        self.assertEqual(data['sheet_counts'], {'RECLASIFICACION': 1, 'NUEVAS': 1})
        old, new = data['rows']
        self.assertIsNone(value(old, 6))
        self.assertEqual(value(old, 48), '#REF!')  # Stock errors are reference data only.
        self.assertEqual(len(new['values']), 21)
        self.assertIsNone(value(new, 21))
        self.assertIsNone(value(new, 23))
        self.assertEqual(identifiers(old), [('reference', 'OLD-001')])

    def test_historical_aliases_prevent_duplicate_and_repeat_is_noop(self):
        old = {'values': [None] * 24, 'worksheet': 'RECLASIFICACION', 'worksheet_row': 2}
        old['values'][21] = 'ORIGINAL-SECOND-ROW'
        product = {'id': 50, 'code': 'REMAPPED-CODE', 'source': {'rows': [old]}}
        plan = plan_rows({'rows': [old]}, [product])
        self.assertEqual(plan[0]['status'], 'existing')
        self.assertEqual(plan[0]['product_id'], 50)

    def test_shared_manufacturer_reference_is_not_identity(self):
        rows = []
        for number in (1, 2):
            values = [None] * 21
            values[5], values[6], values[12] = 'CODE-%s' % number, 'Same label', 'SAME-MANUFACTURER-REF'
            rows.append({'values': values, 'worksheet': 'NUEVAS', 'worksheet_row': number + 1})
        self.assertEqual([r['status'] for r in plan_rows({'rows': rows}, [])], ['create', 'create'])
        products = [{'id': i, 'code': r['values'][5], 'source': {'rows': [r]}}
                    for i, r in enumerate(rows, 1)]
        self.assertTrue(all(r['status'] == 'existing' for r in plan_rows({'rows': rows}, products)))

    def test_conflicting_identifiers_and_duplicate_new_keys_require_review(self):
        values = [None] * 24
        values[5], values[21] = 'KEY-A', 'KEY-B'
        row = {'values': values, 'worksheet': 'RECLASIFICACION', 'worksheet_row': 2}
        with self.assertRaisesRegex(ValueError, 'varios productos'):
            plan_rows({'rows': [row]}, [{'id': 1, 'code': 'KEY-A'}, {'id': 2, 'code': 'KEY-B'}])
        with self.assertRaisesRegex(ValueError, 'repetido entre altas'):
            plan_rows({'rows': [row, dict(row, worksheet_row=3)]}, [])


if __name__ == '__main__':
    unittest.main()
