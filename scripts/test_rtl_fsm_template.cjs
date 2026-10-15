const assert = require('node:assert/strict');
const { renderCycleFsm } = require('./rtl_fsm_template.cjs');
const { renderFsm } = require('./rtl_figure_tools.cjs');
const decode = value => value.replace(/&(?:amp|lt|gt|quot|apos);/g,
  entity => ({'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&apos;':"'"}[entity]));
const attributes = tag => Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)]
  .map(match => [match[1], decode(match[2])]));
function verify(source, result) {
  const circles = new Map([...result.svg.matchAll(/<circle data-state="[^"]*"[^>]*\/>/g)].map(match => {
    const a = attributes(match[0]);
    return [a['data-state'], {x:Number(a.cx),y:Number(a.cy),r:Number(a.r)}];
  }));
  assert.equal(circles.size, source.states.length);
  const actual = [];
  const paths = [...result.svg.matchAll(/<path class="(transition|reset)"[^>]*>/g)];
  for (const match of paths) {
    const a = attributes(match[0]), numbers = a.d.match(/-?\d+(?:\.\d+)?/g).map(Number);
    assert.equal(a['marker-end'], 'url(#arrow)', 'Arrow must be attached to its path');
    const start = {x:numbers[0],y:numbers[1]};
    const end = {x:numbers.at(-2),y:numbers.at(-1)};
    const target = circles.get(a['data-to']);
    assert.ok(target);
    assert.ok(Math.abs(Math.hypot(end.x-target.x,end.y-target.y)-target.r)<0.1,
      'Path must reach its target state boundary');
    if (match[1] === 'transition') {
      const from = circles.get(a['data-from']);
      assert.ok(from);
      assert.ok(Math.abs(Math.hypot(start.x-from.x,start.y-from.y)-from.r)<0.1,
        'Path must start at its source state boundary');
      actual.push(a['data-from']+'>'+a['data-to']);
    } else assert.equal(a['data-to'],source.reset.to);
  }
  assert.deepEqual(actual.sort(),source.transitions.map(edge=>edge.from+'>'+edge.to).sort(),
    'Every transition must keep its source, target and arrow');
  assert.equal(paths.filter(match=>match[1]==='reset').length,source.reset?1:0);
  const points=[...circles.values()];
  const center={x:points.reduce((s,p)=>s+p.x,0)/points.length,y:points.reduce((s,p)=>s+p.y,0)/points.length};
  const radii=points.map(p=>Math.hypot(p.x-center.x,p.y-center.y));
  assert.ok(Math.max(...radii)-Math.min(...radii)<0.1,'All states must stay on the ring');
}
function fixture(count) {
  const states=Array.from({length:count},(_,i)=>({id:'S'+i,action:'step '+i}));
  const transitions=states.flatMap((state,i)=>[
    {from:state.id,to:states[(i+1)%count].id,when:'advance'},
    {from:state.id,to:state.id,when:'!advance'}
  ]);
  if(count===8) for(let i=0;i<5;i++)
    transitions.push({from:'S'+i,to:'S6',when:'error '+i});
  return {kind:'fsm',states,transitions,reset:{to:'S0',when:'!rst_n (any state)'},
    layout:{flow:states.map(state=>state.id)}};
}
(async()=>{
  for(const count of [1,2,4,6,8]) {
    const source=fixture(count);
    verify(source,renderCycleFsm(source));
  }
  const source=fixture(4);
  source.transitions.push({from:'S1',to:'S0',when:'ready & retry < limit'});
  const result=renderCycleFsm(source);
  verify(source,result);
  assert.ok(result.svg.includes('ready &amp; retry &lt; limit'));
  assert.throws(()=>renderCycleFsm({...source,transitions:[{from:'S0',to:'absent',when:'go'}]}));
  assert.throws(()=>renderCycleFsm({...source,transitions:[{from:'S0',to:'S1',when:''}]}));
  assert.throws(()=>renderCycleFsm({...source,states:[source.states[0],source.states[0]]}));
  assert.throws(()=>renderCycleFsm({...source,reset:{to:'absent'}}));
  const dot = `digraph regression {
    graph [splines=true]; node [shape=circle];
    IDLE [label="IDLE\\naccept"]; SEND [label="SEND\\noffer"];
    WAIT_BYTE [label="WAIT_BYTE\\nwait"]; WAIT_LAST [label="WAIT_LAST\\nfinish"];
    reset [shape=plaintext,label="reset (any state)"];
    {rank=same; reset; IDLE; SEND; WAIT_BYTE;}
    reset -> IDLE:w [label="!rst_n"];
    IDLE:e -> SEND:w [label="desc"];
    SEND:e -> WAIT_BYTE:w [label="byte & !last"];
    WAIT_BYTE:n -> SEND:n [label="tx_done",constraint=false];
    SEND:sw -> WAIT_LAST:ne [label="byte & last"];
    WAIT_LAST:n -> IDLE:s [label="tx_done",constraint=false];
    IDLE -> WAIT_LAST [style=invis];
  }`;
  const imported=await renderFsm({dot});
  verify({states:['IDLE','SEND','WAIT_BYTE','WAIT_LAST'].map(id=>({id})),
    transitions:[['IDLE','SEND'],['SEND','WAIT_BYTE'],['WAIT_BYTE','SEND'],
      ['SEND','WAIT_LAST'],['WAIT_LAST','IDLE']].map(([from,to])=>({from,to})),
    reset:{to:'IDLE'}}, imported);
  process.stdout.write('Passed: 1/2/4/6/8-state rings, branches, return edges, attached arrows, reset, escaping, invalid input, and DOT regression.\n');
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1;});
