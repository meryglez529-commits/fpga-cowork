// Shared backends for FSM and timing figures. No design behavior is simulated.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createRequire } = require('node:module');
function loadPackage(name) {
  const roots = [
    path.join(__dirname, 'diagram-runtime'),
    process.env.CODEX_DIAGRAM_NODE_MODULES,
    path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules')
  ].filter(Boolean);
  for (const root of roots) {
    try { return createRequire(path.join(root, '_rtl_figure_loader.cjs'))(name); } catch {}
  }
  throw new Error('Missing diagram package ' + name +
    '. Run npm ci --prefix "' + path.join(__dirname, 'diagram-runtime') + '" --ignore-scripts --no-audit --no-fund');
}
function checkRuntime() {
  const versions = {};
  for (const name of ['@viz-js/viz', 'sharp', 'wavedrom', 'onml']) {
    loadPackage(name);
    const local = path.join(__dirname, 'diagram-runtime/node_modules', name, 'package.json');
    versions[name] = fs.existsSync(local) ? JSON.parse(fs.readFileSync(local, 'utf8')).version : 'external';
  }
  return versions;
}
async function renderFsm(source) {
  if (source.dot) {
    // Read DOT relationships only; fixed SVG geometry draws the finished figure.
    const viz = await loadPackage('@viz-js/viz').instance();
    const result = viz.render(source.dot, { format: 'json', engine: source.engine || 'dot' });
    if (result.status !== 'success') throw new Error(JSON.stringify(result.errors));
    const graph = JSON.parse(result.output);
    const objects = (graph.objects || []).filter(node => node.pos && !Array.isArray(node.nodes));
    const invisible = value => /(^|,)\s*invis\s*(,|$)/.test(value || '');
    const resetNodes = new Set(objects.filter(node => !invisible(node.style) &&
      (node.shape === 'point' || /^_*reset$/i.test(node.name) ||
       (node.shape === 'plaintext' && /reset|复位/i.test(node.label || '')))).map(node => node._gvid));
    const nodes = objects.filter(node => !resetNodes.has(node._gvid) && !invisible(node.style));
    const names = new Map(nodes.map(node => [node._gvid, node.name]));
    const lines = (value, name = '') => String(value || name).replace(/\\N/g, name)
      .split(/\\[nlr]|\n/).filter(Boolean);
    const states = nodes.map(node => {
      const label = lines(node.label, node.name);
      return { id: node.name, action: (label[0] === node.name ? label.slice(1) : label).join('\n') };
    });
    const transitions = [];
    let reset = source.reset;
    for (const edge of graph.edges || []) {
      if (invisible(edge.style)) continue;
      if (resetNodes.has(edge.tail)) {
        if (!names.has(edge.head)) throw new Error('DOT reset does not target a state');
        if (reset && reset.to !== names.get(edge.head)) throw new Error('FSM needs one reset state');
        reset = { to: names.get(edge.head), when: lines(edge.label || '!rst_n').join('\n') };
      } else {
        if (!names.has(edge.tail) || !names.has(edge.head))
          throw new Error('DOT contains an unsupported hidden routing node; use explicit JSON transitions');
        transitions.push({ from: names.get(edge.tail), to: names.get(edge.head),
          when: lines(edge.label || 'always').join('\n') });
      }
    }
    source = { ...source, name: source.name || graph.name, states, transitions, reset,
      legend: source.legend || (graph.label ? lines(graph.label).join('\n') : undefined) };
  }
  return require('./rtl_fsm_template.cjs').renderCycleFsm(source);
}
function formatValue(value, signal) {
  if (value === null) return null;
  if (signal.type === 'bit') {
    if (![0, 1, false, true, '0', '1', 'x', 'z'].includes(value))
      throw new Error('Bit value must be 0, 1, null, x or z: ' + signal.name);
    return value === false ? '0' : value === true ? '1' : String(value);
  }
  if (!['hex', 'bin', 'dec', undefined, 'text'].includes(signal.format))
    throw new Error('Unknown bus format: ' + signal.format);
  if (typeof value === 'string') return value;
  if (!Number.isSafeInteger(value) || value < 0) throw new Error('Bus value must be a string or unsigned integer');
  if (signal.width && (value >= 2 ** signal.width || !Number.isInteger(signal.width) || signal.width < 1))
    throw new Error('Bus value exceeds declared width: ' + signal.name);
  if (signal.format === 'hex') return value.toString(16).toUpperCase().padStart(Math.ceil((signal.width || 1) / 4), '0');
  if (signal.format === 'bin') return value.toString(2).padStart(signal.width || 1, '0');
  return String(value);
}
function intervalWave(source) {
  if (!Array.isArray(source.signals) || !source.signals.length ||
      !Array.isArray(source.intervals) || !source.intervals.length) throw new Error('Timing table needs signals and intervals');
  const names = new Set([source.clock || 'sys_clk']);
  for (const signal of source.signals) {
    if (!signal.name || names.has(signal.name) || !['bit', 'bus'].includes(signal.type))
      throw new Error('Timing signals need unique names and type bit or bus');
    if (signal.width !== undefined && (!Number.isInteger(signal.width) || signal.width < 1))
      throw new Error('Signal width must be a positive integer');
    names.add(signal.name);
  }
  let previousEnd;
  for (const interval of source.intervals) {
    if (!Number.isInteger(interval.start) || !Number.isInteger(interval.end) ||
        interval.end <= interval.start || (previousEnd !== undefined && interval.start !== previousEnd))
      throw new Error('Timing intervals must be ordered, contiguous integer clock boundaries');
    if (interval.gap ? interval.end - interval.start < 2 : interval.end - interval.start !== 1)
      throw new Error('Each visible interval spans one clock; longer intervals need gap:true');
    previousEnd = interval.end;
  }
  const signals = [{ name: source.clock || 'sys_clk',
    wave: source.intervals.map(interval => interval.gap ? '|' : 'p').join('') }];
  for (const signal of source.signals) {
    let wave = '', previous, data = [];
    for (const interval of source.intervals) {
      if (interval.gap) { wave += '|'; continue; }
      const values = interval.values || {};
      const raw = Object.prototype.hasOwnProperty.call(values, signal.name)
        ? values[signal.name] : previous;
      if (raw === undefined) throw new Error('First visible interval needs a value: ' + signal.name);
      const value = formatValue(raw, signal);
      if (value === previous) wave += '.';
      else if (value === null) wave += 'x';
      else if (signal.type === 'bit') wave += value;
      else { wave += '='; data.push(value); }
      previous = value;
    }
    signals.push({ name: signal.name, wave, ...(data.length ? { data } : {}) });
  }
  const edges = source.intervals.map(interval => 'E' + interval.start);
  edges.push('E' + source.intervals.at(-1).end);
  return { signal: signals, config: { hscale: source.hscale || 2, skin: 'default' },
    head: { tick: 0, ...(source.title ? { text: source.title } : {}) }, display_edges: edges,
    _metadata: { ...source.provenance, clock_period_ns: source.clockPeriodNs,
      sampling: 'Values are stable after start and sampled at end; the renderer does not simulate behavior.',
      omitted_intervals: source.intervals.filter(interval => interval.gap).map(interval =>
        ({ start: interval.start, end: interval.end, cycles: interval.end - interval.start })) } };
}
function replaceTicks(tree, labels) {
  let changed = 0;
  function visit(item, marks = false) {
    if (!Array.isArray(item)) return;
    const attrs = item[1] && typeof item[1] === 'object' && !Array.isArray(item[1]) ? item[1] : {};
    const underMarks = marks || attrs.id === 'gmarks_0';
    if (underMarks && item[0] === 'text') {
      const text = item.slice(2).join('');
      if (/^\d+$/.test(text) && Number(text) < labels.length) {
        item.splice(2, item.length - 2, String(labels[Number(text)])); changed++;
      }
    }
    for (const child of item.slice(2)) visit(child, underMarks);
  }
  visit(tree);
  if (changed !== labels.length) throw new Error('Timing labels do not match axis length');
}
async function renderTiming(input) {
  const source = input.intervals ? intervalWave(input) : structuredClone(input);
  if (!Array.isArray(source.signal) || !source.signal.length) throw new Error('WaveDrom input needs signal lanes');
  const wavedrom = loadPackage('wavedrom');
  const onml = loadPackage('onml');
  const skins = { ...loadPackage('wavedrom/skins/default.js'), ...loadPackage('wavedrom/skins/narrow.js'),
    ...loadPackage('wavedrom/skins/lowkey.js') };
  if (source.display_edges) {
    if (!Array.isArray(source.display_edges) || !source.display_edges.length)
      throw new Error('display_edges needs a nonempty list of axis labels');
    source.head = { ...source.head, tick: 0 };
  }
  const tree = wavedrom.renderAny(0, source, structuredClone(skins));
  if (source.display_edges) replaceTicks(tree, source.display_edges);
  const width = Number(tree[1].width), height = Number(tree[1].height);
  tree[1].width = width + 200; tree[1].height = height + 24;
  tree[1].viewBox = '-100 -12 ' + (width + 200) + ' ' + (height + 24);
  tree.splice(2, 0, ['rect', { x: -100, y: -12, width: width + 200, height: height + 24, fill: 'white' }]);
  tree.push(['style', { type: 'text/css' }, 'text{font-family:Arial;font-size:16px}.info{fill:#172429}.muted{fill:#5a6872}']);
  return { svg: onml.stringify(tree), metrics: { kind: 'timing', width: width + 200, height: height + 24,
    signals: source.signal.length, provenance: input.provenance || source._metadata,
    omittedIntervals: source._metadata?.omitted_intervals } };
}
module.exports = { loadPackage, checkRuntime, renderFsm, renderTiming, intervalWave };
