// Run with: node --test tests/classification_search.test.cjs
// Service doubles exercise the real workspace methods; browser checks cover OWL rendering.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function workspace(call) {
    const notifications = [];
    const input = { focus() {}, select() {} };
    const services = { orm: { call }, action: {}, dialog: {}, notification: { add: (message) => notifications.push(message) } };
    const context = {
        Component: class {}, useState: (state) => state, useRef: () => ({ el: input }),
        onWillStart() {}, onWillUnmount() {}, useService: (name) => services[name],
        useDebounced: () => Object.assign(() => {}, { cancel() {} }),
        _t: (text) => text, registry: { category: () => ({ add() {} }) },
    };
    const source = fs.readFileSync(path.join(__dirname, '../static/src/classification/classification.js'), 'utf8')
        .replace(/^import .*;\n/gm, '').replace('export class ', 'class ');
    vm.runInNewContext(source + '\nthis.Workspace = BiotexClassificationWorkspace;', context);
    const app = new context.Workspace();
    app.setup();
    app.state.session = { id: 1, state: 'draft', lines: [] };
    return { app, notifications };
}

function deferred() {
    let resolve;
    const promise = new Promise((r) => { resolve = r; });
    return { promise, resolve };
}
const result = (id, total = 1) => ({ records: [{ id, name: `Product ${id}` }], total, offset: 0 });

test('a slow previous query cannot replace a newer result', async () => {
    const old = deferred();
    const latest = deferred();
    const { app } = workspace((_model, _method, _args, kwargs) => kwargs.query === 'old' ? old.promise : latest.promise);
    app.state.search.query = 'old';
    const first = app.runSearch(0);
    app.state.search.query = 'latest';
    const second = app.runSearch(0);
    latest.resolve(result(2));
    await second;
    old.resolve(result(1));
    assert.equal(await first, false);
    assert.equal(app.state.search.records[0].id, 2);
    assert.equal(app.state.search.loading, false);
});

test('typing invalidates a response even before the debounce fires', async () => {
    const request = deferred();
    const { app } = workspace(() => request.promise);
    const pending = app.runSearch(0);
    app.onSearchInput({ target: { value: 'another query' } });
    request.resolve(result(1));
    assert.equal(await pending, false);
    assert.equal(app.state.search.records.length, 0);
    assert.equal(app.state.search.loading, true);
});

test('adding removes the result, refreshes the page, and prevents repeat additions', async () => {
    let adds = 0;
    const { app } = workspace(async (_model, method) => {
        if (method === 'workspace_add_products') {
            adds++;
            return { id: 1, state: 'draft', lines: [{ id: 10, product_id: 1 }] };
        }
        return result(2);
    });
    app.state.search.records = result(1).records;
    await app.addProduct({ id: 1 });
    await app.addProduct({ id: 1 });
    assert.equal(adds, 1);
    assert.equal(app.state.search.records.length, 1);
    assert.equal(app.state.search.records[0].id, 2);
    assert.equal(app.lines.length, 1);
});

test('a stale server result cannot reintroduce an already added product', async () => {
    const { app } = workspace(async () => result(1));
    app.state.session.lines = [{ id: 10, product_id: 1 }];
    await app.runSearch(0);
    assert.equal(app.state.search.records.length, 0);
});

test('Enter with a selected row adds it without requiring scan mode', async () => {
    let addedId;
    const { app } = workspace(async () => ({ records: [{ id: 1 }, { id: 2 }], total: 2, offset: 0 }));
    app.state.search.selectedId = 2;
    app.addProduct = async (record) => { addedId = record.id; };
    await app.onSearchKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(addedId, 2);
});

test('scan mode requires one match in the entire result set, not just one visible row', async () => {
    let added = false;
    const { app } = workspace(async () => result(1, 21));
    app.state.scan = true;
    app.addProduct = async () => { added = true; };
    await app.onSearchKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(added, false);
});

test('failed scan addition preserves the entered code', async () => {
    const { app } = workspace(async (_model, method) => {
        if (method === 'workspace_add_products') throw new Error('Access denied');
        return result(1);
    });
    app.state.scan = true;
    app.state.search.query = 'BARCODE-1';
    await app.onSearchKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(app.state.search.query, 'BARCODE-1');
    assert.equal(app.lines.length, 0);
});

test('Enter never substitutes a different row if the selected product is no longer available', async () => {
    let added = false;
    const { app } = workspace(async () => result(2));
    app.state.search.selectedId = 1;
    app.addProduct = async () => { added = true; };
    await app.onSearchKeydown({ key: 'Enter', preventDefault() {} });
    assert.equal(added, false);
});

test('inline edits are saved in order and failures prevent silent confirmation', async () => {
    const first = deferred();
    const calls = [];
    const { app, notifications } = workspace(async (_model, method, _args, kwargs) => {
        calls.push(method);
        if (kwargs.vals.new_name === 'First') return first.promise;
        throw new Error('Invalid unit');
    });
    app.saveLine({ id: 10 }, { new_name: 'First' });
    app.saveLine({ id: 10 }, { uom_id: false });
    await Promise.resolve();
    assert.equal(calls.length, 1);
    first.resolve();
    await app.saveQueue;
    assert.equal(calls.length, 2);
    await app.confirm();
    assert.equal(calls.length, 2);
    assert.ok(notifications.some((text) => text.includes('no se pudieron guardar')));
});
