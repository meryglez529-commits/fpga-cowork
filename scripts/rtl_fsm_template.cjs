// Fixed circular FSM figures. Every arrow belongs to its complete SVG path.
const escape = value => String(value).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' }[c]));
const add = (a, b) => ({ x: a.x + b.x, y: a.y + b.y });
const sub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y });
const scale = (p, n) => ({ x: p.x * n, y: p.y * n });
const length = p => Math.hypot(p.x, p.y);
const unit = p => scale(p, 1 / (length(p) || 1));
const perpendicular = p => ({ x: -p.y, y: p.x });
const coordinate = p => p.x.toFixed(2) + ',' + p.y.toFixed(2);
const textWidth = (value, font) => [...value].reduce((n, c) =>
  n + font * (c.charCodeAt(0) > 255 ? 1 : 0.6), 0);
function wrap(value, limit) {
  return String(value).split('\n').flatMap(line => {
    const result = [];
    let current = '';
    for (const word of line.split(/\s+/)) {
      if (current && textWidth(current + ' ' + word, 1) > limit * 0.6) {
        result.push(current); current = word;
      } else current += (current ? ' ' : '') + word;
    }
    return result.concat(current);
  });
}
function intersection(a, b) {
  return Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)) *
    Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
}
function renderCycleFsm(source) {
  if (!Array.isArray(source.states) || !source.states.length) throw new Error('FSM needs states');
  if (!Array.isArray(source.transitions)) throw new Error('FSM needs transitions');
  const font = source.fontSize || 14, edgeFont = font - 1;
  if (!Number.isFinite(font) || font < 8 || font > 40) throw new Error('Invalid FSM font size');
  const states = source.states.map(state => {
    if (typeof state.id !== 'string' || !state.id) throw new Error('State needs a nonempty string id');
    return { ...state, lines: [state.id, ...(state.action ? wrap(state.action, 20) : [])] };
  });
  const ids = new Set(states.map(state => state.id));
  if (ids.size !== states.length) throw new Error('Duplicate FSM state id');
  const flow = source.layout?.flow || states.map(state => state.id);
  if (!Array.isArray(flow) || flow.length !== states.length || new Set(flow).size !== states.length ||
      flow.some(id => !ids.has(id))) throw new Error('FSM flow must list every state once');
  for (const edge of source.transitions) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) throw new Error('Transition names an unknown state');
    if (typeof edge.when !== 'string' || !edge.when.trim()) throw new Error('Transition needs a condition');
  }
  if (source.reset && !ids.has(source.reset.to)) throw new Error('Reset names an unknown state');
  const radius = Math.max(44, ...states.map(state => Math.max(
    ...state.lines.map(line => (textWidth(line, font) + 24) / 2),
    (state.lines.length * font * 1.25 + 18) / 2)));
  const widestCondition = Math.max(65, ...source.transitions.flatMap(edge =>
    wrap(edge.when, 28).map(line => textWidth(line, edgeFont))));
  const ringRadius = states.length === 1 ? 0 : Math.max(radius * 2.8,
    (2 * radius + Math.min(widestCondition, 210) + 64) /
      (2 * Math.sin(Math.PI / Math.max(3, states.length))));
  const order = new Map(flow.map((id, i) => [id, i]));
  for (const state of states) {
    state.angle = -Math.PI / 2 + order.get(state.id) * 2 * Math.PI / states.length;
    state.radial = { x: Math.cos(state.angle), y: Math.sin(state.angle) };
    state.center = scale(state.radial, ringRadius);
  }
  const byId = new Map(states.map(state => [state.id, state]));
  const nodeBoxes = states.map(state => ({ x: state.center.x - radius, y: state.center.y - radius,
    width: 2 * radius, height: 2 * radius }));
  const boxes = [...nodeBoxes], labelBoxes = [], labels = [], paths = [];
  const include = point => boxes.push({ x: point.x, y: point.y, width: 0, height: 0 });
  const text = (lines, center, size, attributes = '') =>
    '<text text-anchor="middle" font-size="' + size + '" ' + attributes + '>' +
    lines.map((line, i) => '<tspan x="' + center.x.toFixed(2) + '" y="' +
      (center.y + (i - (lines.length - 1) / 2) * size * 1.25 + size * 0.34).toFixed(2) +
      '">' + escape(line) + '</tspan>').join('') + '</text>';
  function placeLabel(lines, samples, normal, side = 1) {
    const width = Math.max(...lines.map(line => textWidth(line, edgeFont))) + 8;
    const height = lines.length * edgeFont * 1.25 + 6;
    let best;
    for (const sample of samples) {
      for (const direction of [side, -side]) {
        for (const extra of [0, 14, 28]) {
          const distance = (Math.abs(normal.x) * width + Math.abs(normal.y) * height) / 2 + 8 + extra;
          const center = add(sample, scale(normal, direction * distance));
          const box = { x: center.x - width / 2, y: center.y - height / 2, width, height };
          const score = nodeBoxes.reduce((n, node) => n + 100 * intersection(box, node), 0) +
            labelBoxes.reduce((n, other) => n + intersection(box, other), 0);
          if (!best || score < best.score) best = { box, center, score };
          if (score === 0) break;
        }
        if (best.score === 0) break;
      }
      if (best.score === 0) break;
    }
    labelBoxes.push(best.box); boxes.push(best.box);
    labels.push(text(lines, best.center, edgeFont, 'class="condition"'));
  }
  function arrow(edge, start, controls, finish, samples, normal, labelSide = 1, reset = false) {
    for (const point of [start, ...controls, finish]) include(point);
    const command = controls.length === 2 ? 'C' + controls.map(coordinate).join(' ') + ' '
      : controls.length === 1 ? 'Q' + coordinate(controls[0]) + ' ' : 'L';
    paths.push('<path class="' + (reset ? 'reset' : 'transition') + '" data-from="' +
      escape(edge.from || '') + '" data-to="' + escape(edge.to) + '" d="M' + coordinate(start) +
      command + coordinate(finish) + '" marker-end="url(#arrow)"><title>' +
      escape((edge.from ? edge.from + ' → ' : '') + edge.to + ': ' + edge.when) + '</title></path>');
    placeLabel(wrap(edge.when, 28), samples, normal, labelSide);
  }
  const selfCounts = new Map();
  for (const edge of source.transitions) {
    const from = byId.get(edge.from), to = byId.get(edge.to);
    if (edge.from === edge.to) {
      const lane = selfCounts.get(edge.from) || 0;
      selfCounts.set(edge.from, lane + 1);
      const angle = from.angle + lane * 0.55;
      const radial = { x: Math.cos(angle), y: Math.sin(angle) }, tangent = perpendicular(radial);
      const outward = add(from.center, scale(radial, radius * 0.82));
      const start = add(outward, scale(tangent, radius * 0.572));
      const finish = add(outward, scale(tangent, -radius * 0.572));
      const c1 = add(start, add(scale(radial, radius * 1.1), scale(tangent, radius * 0.65)));
      const c2 = add(finish, add(scale(radial, radius * 1.1), scale(tangent, -radius * 0.65)));
      arrow(edge, start, [c1, c2], finish,
        [add(from.center, scale(radial, radius * 1.75))], radial);
      continue;
    }
    const delta = sub(to.center, from.center), midpoint = scale(add(from.center, to.center), 0.5);
    const steps = (order.get(edge.to) - order.get(edge.from) + states.length) % states.length;
    const adjacent = steps === 1 || steps === states.length - 1;
    const outward = length(midpoint) > 0.01 ? unit(midpoint) : unit(perpendicular(delta));
    const bend = adjacent ? (steps === 1 ? 30 : -36) : 0;
    const control = adjacent ? add(midpoint, scale(outward, bend)) : scale(midpoint, 0.68);
    const start = add(from.center, scale(unit(sub(control, from.center)), radius));
    const finish = add(to.center, scale(unit(sub(control, to.center)), radius));
    const sample = t => add(add(scale(start, (1 - t) ** 2),
      scale(control, 2 * (1 - t) * t)), scale(finish, t ** 2));
    const normal = adjacent ? outward : unit(perpendicular(delta));
    arrow(edge, start, [control], finish, [0.5, 0.35, 0.65, 0.25, 0.75].map(sample),
      normal, adjacent && steps !== 1 ? -1 : 1);
  }
  let resetStart;
  if (source.reset) {
    const target = byId.get(source.reset.to), angle = target.angle - 0.72;
    const outward = { x: Math.cos(angle), y: Math.sin(angle) };
    resetStart = add(target.center, scale(outward, radius + 105));
    const finish = add(target.center, scale(outward, radius));
    arrow({ to: target.id, when: source.reset.when || '!rst_n (any state)' },
      resetStart, [], finish, [scale(add(resetStart, finish), 0.5)], perpendicular(outward), 1, true);
  }
  let left = Math.min(...boxes.map(b => b.x)), top = Math.min(...boxes.map(b => b.y));
  let right = Math.max(...boxes.map(b => b.x + b.width)), bottom = Math.max(...boxes.map(b => b.y + b.height));
  let legend = '';
  if (source.legend) {
    const lines = wrap(source.legend, 80);
    const center = { x: (left + right) / 2, y: bottom + 24 + lines.length * edgeFont * 0.625 };
    const width = Math.max(...lines.map(line => textWidth(line, edgeFont)));
    left = Math.min(left, center.x - width / 2); right = Math.max(right, center.x + width / 2);
    bottom = center.y + lines.length * edgeFont * 0.625;
    legend = text(lines, center, edgeFont, 'fill="#52616b"');
  }
  left -= 22; top -= 22; right += 22; bottom += 22;
  const width = Math.ceil(right - left), height = Math.ceil(bottom - top);
  const nodes = states.map(state => '<g class="state"><circle data-state="' + escape(state.id) +
    '" cx="' + state.center.x.toFixed(2) + '" cy="' + state.center.y.toFixed(2) + '" r="' +
    radius.toFixed(2) + '" fill="#e0eef1" stroke="#344348"/>' +
    text(state.lines, state.center, font) + '</g>').join('\n');
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height +
    '" viewBox="' + [left, top, width, height].map(n => n.toFixed(2)).join(' ') + '" role="img"><title>' +
    escape(source.name || 'FSM') + '</title><defs><marker id="arrow" viewBox="0 0 8 7" refX="8" refY="3.5" ' +
    'markerWidth="8" markerHeight="7" orient="auto" markerUnits="userSpaceOnUse">' +
    '<path d="M0,0L8,3.5L0,7Z" fill="#25353a"/></marker></defs>' +
    '<rect x="' + left + '" y="' + top + '" width="' + width + '" height="' + height + '" fill="white"/>' +
    '<g font-family="Consolas,Microsoft YaHei,monospace" fill="#172429">' +
    '<g fill="none" stroke="#25353a" stroke-width="1.1">' + paths.join('\n') + '</g>' +
    (resetStart ? '<circle cx="' + resetStart.x + '" cy="' + resetStart.y + '" r="2.2"/>' : '') +
    nodes + labels.join('\n') + legend + '</g></svg>\n';
  return { svg, metrics: { kind: 'fsm', engine: 'fixed-svg', layout: 'cycle', width, height,
    states: states.length, transitions: source.transitions.length, reset: Boolean(source.reset), warnings: [] } };
}
module.exports = { renderCycleFsm };
