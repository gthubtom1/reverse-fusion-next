import * as app from './core.mjs';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

const results = [];
let checks = 0;
function test(label, fn, input) {
  const before = JSON.stringify(input);
  let result;
  try { result = {ok: fn()}; } catch (error) { result = {error: error.message}; }
  assert.equal(JSON.stringify(input), before, 'input mutation: ' + label);
  results.push({label, ...result});
  checks++;
  return result;
}
const empty = app.initial();
assert.deepEqual(empty, {version: 1, next: 1, entries: []});
assert.notEqual(app.initial(), app.initial());
assert.equal(test('required', () => app.change(empty, {type:'add',name:' ',quantity:1}), empty).error, '请填写名称');
const names = [undefined, null, '', ' ', ' a ', 'A', '苹果', 'a'.repeat(32), 'a'.repeat(33), '😀'.repeat(16), '😀'.repeat(17), 42, false, '<img src=x onerror=alert(1)>'];
const quantities = [undefined, null, '', ' ', 0, -1, 1, 99, 100, 1.5, '1', '1.0', '01', '1e1', '0x10', 'abc', true, false, Infinity, NaN];
for (const name of names) for (const quantity of quantities) for (const tag of ['', ' 文具 ']) {
  test('add:' + results.length, () => app.change(empty, {type:'add',name,quantity,tag}), empty);
}
let state = app.initial();
for (const [name,tag,quantity] of [[' 苹果 ',' 水果 ',2],['Banana','水果',99],['apple','办公',3],['APPLE','其他',1],['阿胶','',5],['apple','水果',4]]) {
  const result = test('sequence-add', () => app.change(state,{type:'add',name,tag,quantity}),state);
  assert.ok(result.ok);
  state = result.ok;
}
assert.equal(test('case-duplicate', () => app.change(state,{type:'add',name:'APPLE',tag:'办公',quantity:1}),state).error, '该分类中已有同名条目');
for (const query of ['', ' ', 'a', 'APP', '办公', '不存在', '水果', '\n', 'e\n办', null, 42]) {
  for (const order of ['newest','name','unknown',undefined]) test('view:' + results.length, () => app.view(state,query,order),state);
}
for (const id of [1, 3, 6, 7, 0, '1', null, undefined]) test('remove:'+id, () => app.change(state,{type:'remove',id}),state);
test('clear', () => app.change(state,{type:'clear'}),state);
test('unknown', () => app.change(state,{type:'other'}),state);
const valid = {version:1,next:2,entries:[{id:1,name:'A',tag:'T',quantity:1}]};
const restoreCases = [null, undefined, '', 'bad', 'null', '[]', 'true', '1', '{}', JSON.stringify(valid), JSON.stringify({...valid, extra:42})];
for (const next of [0,-1,1,1.5,2,Number.MAX_SAFE_INTEGER,Number.MAX_SAFE_INTEGER+1,'2',null]) restoreCases.push(JSON.stringify({...valid,next}));
for (const entry of [null,{},...[-1,0,1.5,2,'1',null,Number.MAX_SAFE_INTEGER+1].map(id=>({...valid.entries[0],id})),...[-1,0,1.5,100,'1',null].map(quantity=>({...valid.entries[0],quantity})),{...valid.entries[0],name:null},{...valid.entries[0],tag:4},{...valid.entries[0],name:'',tag:'',extra:'kept'}]) restoreCases.push(JSON.stringify({...valid,entries:[entry]}));
restoreCases.push(JSON.stringify({...valid,entries:[...valid.entries,...valid.entries]}));
restoreCases.push(JSON.stringify({...valid,version:2}));
for (const text of restoreCases) test('restore:'+results.length, () => app.restore(text),text);
// Deterministic long-lived sequence exercises numbering, clearing, filtering and deletes.
let seed = 0x73a51;
const random = n => {seed = (Math.imul(seed,1664525)+1013904223)>>>0; return seed%n;};
state = app.initial();
for (let i=0;i<1500;i++) {
  const type = random(15);
  const action = type===0 ? {type:'clear'} : type<5 ? {type:'remove',id:random(state.next+2)} :
    {type:'add',name:['A','a','苹果','香蕉','充电线','😀',' 笔 '][random(7)],tag:['文具','办公','Other','other',''][random(5)],quantity:random(103)-1};
  const result = test('random:'+i,()=>app.change(state,action),state);
  if (result.ok) state=result.ok;
  test('random-view:'+i,()=>app.view(state,['','a','文具','Other','无'][random(5)],random(2)?'name':'newest'),state);
  test('random-restore:'+i,()=>app.restore(JSON.stringify(state)),state);
}
console.log(JSON.stringify({checks,sha256:createHash('sha256').update(JSON.stringify(results)).digest('hex')}));
