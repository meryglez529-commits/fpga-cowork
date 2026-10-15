// CLI regressions for readable overlaps and structural block-diagram errors.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'rtl-block-test-'));
const source = {
  width: 800, height: 300,
  nodes: [
    { id: 'source', x: 30, y: 80, width: 120, height: 120,
      ports: [{ id: 'out', direction: 'out', side: 'right', at: 70 }] },
    { id: 'sink', x: 650, y: 80, width: 120, height: 120,
      ports: [{ id: 'in', direction: 'in', side: 'left', at: 70 }] }
  ],
  connections: [{ from: 'source.out', to: 'sink.in', label: 'valid',
    labelAt: { x: 400, y: 144 } }]
};
function render(name, input) {
  const file = path.join(temporary, name + '.json');
  const svg = path.join(temporary, name + '.svg');
  fs.writeFileSync(file, JSON.stringify(input));
  const result = spawnSync(process.execPath,
    [path.join(__dirname, 'render_rtl_diagram.cjs'), file, svg], { encoding: 'utf8' });
  assert.ifError(result.error);
  return { ...result, svg };
}
try {
  const clear = render('clear', source);
  assert.equal(clear.status, 0, clear.stderr);
  assert.deepEqual(JSON.parse(clear.stdout).warnings, []);
  const overlap = render('overlap', { ...source, connections: [...source.connections,
    { from: { x: 400, y: 145 }, to: { x: 400, y: 250 } }] });
  assert.equal(overlap.status, 0, overlap.stderr);
  assert.ok(fs.readFileSync(overlap.svg, 'utf8').includes('<svg'));
  assert.deepEqual(JSON.parse(overlap.stdout).warnings, ['Signal line overlaps label: valid']);
  const wrongDirection = render('wrong-direction', { ...source,
    connections: [{ from: 'sink.in', to: 'source.out' }] });
  assert.equal(wrongDirection.status, 1);
  assert.match(wrongDirection.stderr, /direction conflicts/);
  assert.ok(!fs.existsSync(wrongDirection.svg));
  const incomplete = render('incomplete', { ...source,
    connections: [{ from: 'source.out', to: 'missing.in' }] });
  assert.equal(incomplete.status, 1);
  assert.match(incomplete.stderr, /Unknown port/);
  process.stdout.write('Passed: clear blocks, readable-overlap warning, wrong direction, and missing endpoint.\n');
} finally {
  assert.ok(path.resolve(temporary).startsWith(path.resolve(os.tmpdir()) + path.sep));
  fs.rmSync(temporary, { recursive: true, force: true });
}
