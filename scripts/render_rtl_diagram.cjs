#!/usr/bin/env node
// Reusable RTL block, interface, FSM and timing figures from declarative sources.
// Usage: node render_rtl_diagram.cjs source.json output.svg [output.png]
const fs = require('node:fs');
const path = require('node:path');
const [sourcePath, svgPath, pngPath] = process.argv.slice(2);
if (sourcePath === '--help') {
  console.log(`Usage: node render_rtl_diagram.cjs source.json output.svg [output.png]

Interface diagram input:
  { "kind": "interface", "name": "module_name", "ports": [
      { "name": "clk", "direction": "in", "width": 1 },
      { "name": "data", "direction": "out", "width": 8 }
    ] }
Inputs appear at the left; outputs and bidirectional ports at the right.
Array order determines port order. The template calculates all positions.

System diagram input:
  width, height: canvas dimensions; optional fontSize (default 16).
  nodes: [{ id, name, x, y, width, height, ports: [
    { id, direction: "in"|"out"|"inout", side: "left"|"right"|"top"|"bottom", at }
  ] }]. "at" is the port offset from the top or left of the module side.
  connections: [{ from: "module.port", to: "module.port", label,
    via: [{x,y}], labelAt: {x,y}, bidirectional: false }].
Endpoints can instead be {x,y} for external connections. Signals with no
bends must be aligned. For bends specify orthogonal waypoints in "via".
Labels are placed above a horizontal segment with sufficient free space.
  frame: { name, x, y, width, height } for the top-level boundary.
  globals: [{ x, label }] for common clock/reset inputs into that boundary.
  notes: [{ text, x, y, fontSize }] to state which modules use global nets.
  junctions: [{ x, y }] for intentional connections where a net branches.
Each signal uses a separate connection. Widths appear in labels as data[7:0].
Choose module positions and port order before rendering; automatic graph
layout is not used. Geometry checks catch several common drawing defects;
Line/label overlaps produce warnings for a readability check, without blocking output.
inspect the rendered diagram at its normal document size as well.

FSM input:
  { "kind":"fsm", "states":[{"id":"IDLE","action":"wait"}, ...],
    "transitions":[{"from":"IDLE","to":"RUN","when":"start"}, ...],
    "reset":{"to":"IDLE","when":"!rst_n (any state)"} }
All states use equal circles on one ring, following states array order.
Optional layout:{flow:[state ids]} sets that order. The fixed SVG template
draws complete paths with attached arrow markers, outward self-loops and
reset entry. It places condition labels; no manual coordinates are needed.
Optional legend explains abbreviated conditions. Prefer this JSON format.
Existing .dot input is imported for state/transition relationships and drawn
with the same fixed template; its manual positions and styles are not used.

Timing interval-table input (model export or manual cycle table):
  { "kind":"timing", "provenance":{"kind":"manual","source":"cycle table"},
    "clockPeriodNs":10, "signals":[{"name":"valid","type":"bit"},
      {"name":"data[7:0]","type":"bus","format":"hex","width":8}],
    "intervals":[{"start":0,"end":1,"values":{"valid":1,"data[7:0]":85}},
      {"start":1,"end":2,"values":{"valid":0}},
      {"start":2,"end":102,"gap":true}, ...] }
Values hold AFTER start, BEFORE end; end is the sampling edge. Omitted
fields keep the previous value. Explicit gap intervals compress waiting
and preserve its clock count. Provenance records model/manual/RTL source;
the renderer does not calculate design behavior. Raw WaveDrom JSON is
also accepted, including display_edges and existing metadata.

Run --check to verify the pinned dependencies under scripts/diagram-runtime.
SVG block and JSON FSM diagrams need no packages. DOT import uses Graphviz,
timing uses WaveDrom, and optional PNG output uses sharp. Missing packages can be restored with
npm ci --prefix scripts/diagram-runtime --ignore-scripts --no-audit --no-fund.`);
  process.exit(0);
}
if (sourcePath === '--check') {
  try { console.log(JSON.stringify(require('./rtl_figure_tools.cjs').checkRuntime(), null, 2)); }
  catch (error) { console.error(error.message); process.exit(1); }
  process.exit(0);
}
if (!sourcePath || !svgPath) {
  console.error('Usage: node render_rtl_diagram.cjs source.json output.svg [output.png]');
  process.exit(2);
}
const escape = value => String(value).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' }[c]));
const number = (value, label) => {
  if (!Number.isFinite(value)) throw new Error(label + ' must be a finite number');
  return value;
};
const labelWidth = (text, font) => [...text].reduce((sum, c) =>
  sum + (c.charCodeAt(0) > 255 ? font : font * 0.6), 0);
function interfaceSource(source) {
  const input = source.ports.filter(p => p.direction === 'in');
  const output = source.ports.filter(p => p.direction === 'out');
  const bidirectional = source.ports.filter(p => p.direction === 'inout');
  if (input.length + output.length + bidirectional.length !== source.ports.length)
    throw new Error('Port directions must be in, out or inout');
  const height = Math.max(input.length, output.length + bidirectional.length) * 36 + 48;
  const node = { id: 'module', name: source.name, x: 280, y: 70,
    width: 230, height, ports: [] };
  const connections = [];
  for (const [side, list] of [['left', input], ['right', output.concat(bidirectional)]]) {
    list.forEach((p, index) => {
      const id = 'p' + node.ports.length;
      node.ports.push({ id, side, at: 34 + index * 36, direction: p.direction });
      if (!Number.isInteger(p.width) || p.width < 1)
        throw new Error('Port width must be a positive integer: ' + p.name);
      const label = p.width > 1 ? p.name + '[' + (p.width - 1) + ':0]' : p.name;
      const stub = { x: side === 'left' ? 36 : 754, y: 104 + index * 36 };
      connections.push(p.direction === 'in'
        ? { from: stub, to: 'module.' + id, label }
        : { from: 'module.' + id, to: stub, label, bidirectional: p.direction === 'inout' });
    });
  }
  return { width: 790, height: height + 122, nodes: [node], connections,
    title: source.title };
}
function render(input) {
  const source = input.kind === 'interface' ? interfaceSource(input) : input;
  const width = number(source.width, 'width');
  const height = number(source.height, 'height');
  const font = source.fontSize || 16;
  const nodeFont = source.nodeFontSize || font;
  const nodes = new Map();
  const ports = new Map();
  const labelRects = [];
  const lineSegments = [];
  const warnings = new Set();
  let labelCount = 0;
  let portCount = 0;
  const pieces = ['<rect width="100%" height="100%" fill="white"/>'];
  const text = (value, x, y, options = {}) => {
    const size = options.size || font;
    const anchor = options.anchor || 'middle';
    const span = labelWidth(value, size);
    const x0 = anchor === 'middle' ? x - span / 2 : anchor === 'end' ? x - span : x;
    const rect = { x: x0, y: y - size, width: span, height: size + 2,
      owner: options.owner };
    if (x0 < 0 || x0 + span > width || y - size < 0 || y + 2 > height)
      throw new Error('Text outside canvas: ' + value);
    if (options.signal) labelRects.push({ ...rect, value });
    pieces.push('<text x="' + x + '" y="' + y + '" font-size="' + size +
      '" text-anchor="' + anchor + '">' + escape(value) + '</text>');
    labelCount++;
  };
  if (source.frame) {
    const f = source.frame;
    pieces.push('<rect x="' + f.x + '" y="' + f.y + '" width="' + f.width +
      '" height="' + f.height + '" fill="none" stroke="#495457" stroke-width="1.1"/>');
    const corners = [
      { x: f.x, y: f.y }, { x: f.x + f.width, y: f.y },
      { x: f.x + f.width, y: f.y + f.height }, { x: f.x, y: f.y + f.height }
    ];
    corners.forEach((a, i) => lineSegments.push({ a, b: corners[(i + 1) % 4], owner: 'frame' }));
    if (f.name) text(f.name, f.x + f.width / 2, f.y - 8, { size: 18 });
  }
  if (source.title) text(source.title, width / 2, 30, { size: 18 });
  for (const node of source.nodes || []) {
    if (!node.id || nodes.has(node.id)) throw new Error('Duplicate or missing module id');
    const n = { ...node };
    for (const key of ['x', 'y', 'width', 'height']) number(n[key], n.id + '.' + key);
    if (n.x < 0 || n.y < 0 || n.width <= 0 || n.height <= 0 ||
        n.x + n.width > width || n.y + n.height > height)
      throw new Error('Module outside canvas: ' + n.id);
    if (labelWidth(n.name || n.id, nodeFont) > n.width - 8)
      throw new Error('Module too narrow for name: ' + n.id);
    nodes.set(n.id, n);
    pieces.push('<rect x="' + n.x + '" y="' + n.y + '" width="' + n.width +
      '" height="' + n.height + '" fill="#e0eef1" stroke="#344348" stroke-width="1.1"/>');
    text(n.name || n.id, n.x + n.width / 2, n.y + n.height / 2 + nodeFont * 0.35,
      { size: nodeFont, owner: n.id });
    for (const p of n.ports || []) {
      const key = n.id + '.' + p.id;
      if (ports.has(key)) throw new Error('Duplicate port: ' + key);
      const at = number(p.at, key + '.at');
      if (!['in', 'out', 'inout'].includes(p.direction)) throw new Error('Invalid port direction: ' + key);
      let point;
      if (['left', 'right'].includes(p.side)) {
        if (at < 0 || at > n.height) throw new Error('Port beyond module side: ' + key);
        point = { x: n.x + (p.side === 'right' ? n.width : 0), y: n.y + at };
      } else if (['top', 'bottom'].includes(p.side)) {
        if (at < 0 || at > n.width) throw new Error('Port beyond module side: ' + key);
        point = { x: n.x + at, y: n.y + (p.side === 'bottom' ? n.height : 0) };
      } else throw new Error('Invalid port side: ' + key);
      if ([...ports.values()].some(q => q.owner === n.id && q.x === point.x && q.y === point.y))
        throw new Error('Two ports share one position: ' + key);
      ports.set(key, { ...point, direction: p.direction, owner: n.id });
      portCount++;
    }
  }
  const endpoint = (value, role) => {
    if (typeof value === 'string') {
      const p = ports.get(value);
      if (!p) throw new Error('Unknown port: ' + value);
      if ((role === 'from' && p.direction === 'in') ||
          (role === 'to' && p.direction === 'out'))
        throw new Error('Signal direction conflicts with port: ' + value);
      return p;
    }
    return { x: number(value.x, 'endpoint.x'), y: number(value.y, 'endpoint.y') };
  };
  for (const [index, connection] of (source.connections || []).entries()) {
    const start = endpoint(connection.from, 'from');
    const end = endpoint(connection.to, 'to');
    const points = [start, ...(connection.via || []), end];
    const segments = [];
    points.forEach(p => {
      number(p.x, 'route.x'); number(p.y, 'route.y');
      if (p.x < 0 || p.y < 0 || p.x > width || p.y > height) throw new Error('Route outside canvas');
    });
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i];
      if (a.x !== b.x && a.y !== b.y) throw new Error('Route needs an explicit orthogonal bend: ' + index);
      if (a.x === b.x && a.y === b.y) throw new Error('Zero-length route segment: ' + index);
      const segment = { a, b, owner: index };
      for (const n of nodes.values()) {
        const crosses = a.y === b.y
          ? a.y > n.y && a.y < n.y + n.height &&
            Math.max(Math.min(a.x, b.x), n.x) < Math.min(Math.max(a.x, b.x), n.x + n.width)
          : a.x > n.x && a.x < n.x + n.width &&
            Math.max(Math.min(a.y, b.y), n.y) < Math.min(Math.max(a.y, b.y), n.y + n.height);
        if (crosses) throw new Error('Signal runs through module: ' + n.id + ' (' + connection.label + ')');
      }
      segments.push(segment); lineSegments.push(segment);
    }
    pieces.push('<path d="' + points.map((p, i) => (i ? 'L' : 'M') + p.x + ',' + p.y).join(' ') +
      '" fill="none" stroke="#25353a" stroke-width="1.1" marker-end="url(#arrow)"' +
      (connection.bidirectional ? ' marker-start="url(#arrow-start)"' : '') + '/>');
    if (connection.label) {
      const size = connection.fontSize || font;
      const candidates = segments.filter(s => s.a.y === s.b.y &&
        Math.abs(s.a.x - s.b.x) >= labelWidth(connection.label, size) + 12)
        .sort((a, b) => Math.abs(b.a.x - b.b.x) - Math.abs(a.a.x - a.b.x));
      const selected = candidates[0];
      const placement = connection.labelAt || (selected ? {
        x: (selected.a.x + selected.b.x) / 2, y: selected.a.y - 6
      } : null);
      if (!placement) throw new Error('No room for signal label: ' + connection.label);
      text(connection.label, placement.x, placement.y,
        { size, signal: true, owner: index, anchor: placement.anchor });
    }
  }
  for (const junction of source.junctions || []) {
    const x = number(junction.x, 'junction.x'), y = number(junction.y, 'junction.y');
    if (x < 0 || y < 0 || x > width || y > height) throw new Error('Junction outside canvas');
    pieces.push('<circle cx="' + x + '" cy="' + y + '" r="2.2" fill="#25353a"/>');
  }
  const overlap = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x &&
    a.y < b.y + b.height && a.y + a.height > b.y;
  for (let i = 0; i < labelRects.length; i++) {
    const label = labelRects[i];
    for (const n of nodes.values()) {
      if (overlap(label, n)) throw new Error('Signal label overlaps module: ' + label.value);
    }
    for (let j = 0; j < i; j++) {
      if (overlap(label, labelRects[j])) throw new Error('Signal labels overlap: ' + label.value);
    }
    for (const s of lineSegments) {
      const crosses = s.a.y === s.b.y
        ? s.a.y > label.y && s.a.y < label.y + label.height &&
          Math.max(Math.min(s.a.x, s.b.x), label.x) < Math.min(Math.max(s.a.x, s.b.x), label.x + label.width)
        : s.a.x > label.x && s.a.x < label.x + label.width &&
          Math.max(Math.min(s.a.y, s.b.y), label.y) < Math.min(Math.max(s.a.y, s.b.y), label.y + label.height);
      if (crosses) warnings.add((s.owner === 'frame' ? 'Frame' : 'Signal line') +
        ' overlaps label: ' + label.value);
    }
  }
  for (const global of source.globals || []) {
    if (!source.frame) throw new Error('Global inputs need a frame');
    if (global.x < source.frame.x || global.x > source.frame.x + source.frame.width)
      throw new Error('Global input outside frame');
    pieces.push('<path d="M' + global.x + ',' + (source.frame.y - 42) + 'V' + source.frame.y +
      '" fill="none" stroke="#25353a" stroke-width="1.1" marker-end="url(#arrow)"/>');
    text(global.label, global.x, source.frame.y - 50, { size: font });
  }
  for (const note of source.notes || []) text(note.text, note.x, note.y,
    { size: note.fontSize || 14, anchor: note.anchor });
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height +
    '" viewBox="0 0 ' + width + ' ' + height + '" role="img"><title>' +
    escape(source.title || source.frame?.name || source.nodes[0]?.name || 'RTL block diagram') +
    '</title><defs><marker id="arrow" viewBox="0 0 8 6" refX="8" refY="3" markerWidth="7" markerHeight="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0L8 3L0 6Z" fill="#25353a"/></marker><marker id="arrow-start" viewBox="0 0 8 6" refX="0" refY="3" markerWidth="7" markerHeight="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M8 0L0 3L8 6Z" fill="#25353a"/></marker></defs><g font-family="Consolas,Liberation Mono,monospace" fill="#172429">' +
    pieces.join('\n') + '</g></svg>\n';
  return { svg, metrics: { width, height, modules: nodes.size, ports: portCount,
    connections: (source.connections || []).length, labels: labelCount,
    warnings: [...warnings] } };
}
async function main() {
  const raw = fs.readFileSync(sourcePath, 'utf8');
  const source = path.extname(sourcePath).toLowerCase() === '.dot'
    ? { kind: 'fsm', dot: raw } : JSON.parse(raw);
  const tools = require('./rtl_figure_tools.cjs');
  const { svg, metrics } = source.kind === 'fsm' ? await tools.renderFsm(source)
    : source.kind === 'timing' || Array.isArray(source.signal) ? await tools.renderTiming(source)
    : render(source);
  const sharp = pngPath ? tools.loadPackage('sharp') : undefined;
  fs.mkdirSync(path.dirname(path.resolve(svgPath)), { recursive: true });
  fs.writeFileSync(svgPath, svg, 'utf8');
  if (pngPath) {
    fs.mkdirSync(path.dirname(path.resolve(pngPath)), { recursive: true });
    await sharp(Buffer.from(svg)).png().toFile(pngPath);
  }
  console.log(JSON.stringify({ source: path.resolve(sourcePath), svg: path.resolve(svgPath),
    png: pngPath ? path.resolve(pngPath) : undefined, ...metrics }, null, 2));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
