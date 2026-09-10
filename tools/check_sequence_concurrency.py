"""Run from a QA Odoo shell after TransactionCase releases registry locks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from odoo import api, sql_db
from odoo.service.model import retrying


def check_sequence_concurrency(env):
    assert env['ir.config_parameter'].sudo().get_param('bioteczac.environment') == 'qa'
    connection = sql_db.db_connect(env.cr.dbname)
    uid = env.uid
    results = []
    for initial in (None, 10):
        prefix = 'ZZ-%s-TST-TST' % uuid4().hex[:4].upper()
        with connection.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '5s'")
            cr.execute('SELECT id FROM biotex_product_sequence WHERE prefix=%s', (prefix,))
            assert not cr.fetchone(), 'Temporary test prefix already exists'
            if initial is not None:
                api.Environment(cr, uid, {})['biotex.product.sequence']._advance(prefix, initial)
                cr.commit()
        barrier = Barrier(2)

        def allocate():
            with connection.cursor() as cr:
                worker_env = api.Environment(cr, uid, {})
                attempts = 0

                def operation():
                    nonlocal attempts
                    attempts += 1
                    cr.execute("SET LOCAL lock_timeout = '5s'")
                    cr.execute("SET LOCAL statement_timeout = '20s'")
                    if attempts == 1:
                        cr.execute('SELECT count(*) FROM biotex_product_sequence WHERE prefix=%s', (prefix,))
                        barrier.wait(timeout=15)
                    return worker_env['biotex.product.sequence']._next(prefix, reserve=True)

                return retrying(operation, worker_env), attempts

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(allocate) for _ in range(2)]
                allocations = [future.result(timeout=45) for future in futures]
            numbers = sorted(number for number, attempts in allocations)
            assert numbers == ([1, 2] if initial is None else [11, 12]), numbers
            assert max(attempts for number, attempts in allocations) > 1, 'Race did not exercise a transaction retry'
            results.append({'existing_counter': initial is not None, 'numbers': numbers,
                            'attempts': [attempts for number, attempts in allocations]})
        finally:
            with connection.cursor() as cr:
                cr.execute('DELETE FROM biotex_product_sequence WHERE prefix=%s', (prefix,))
                cr.commit()
    return results
