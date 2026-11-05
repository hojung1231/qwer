import {test} from 'node:test';
import assert from 'node:assert/strict';
import {THUMB_WIDTH,THUMB_STEP,hitShape,translateShape,renumber,resizeFromTouches} from '../src/geometry.ts';
import type {TwoPointState} from '../src/geometry.ts';
import type {Annotation} from '../src/model.ts';
const box:Annotation={id:'1',number:1,kind:'rectangle',color:'#ed4d4d',x1:.2,y1:.2,x2:.5,y2:.6};
test('썸네일 노출 간격은 너비의 70%',()=>assert.equal(THUMB_STEP/THUMB_WIDTH,.7));
test('겹친 개체는 나중에 추가된 것이 선택됨',()=>assert.equal(hitShape([box,{...box,id:'2'}],.3,.3,800,600)?.id,'2'));
test('이동 시 이미지 경계를 넘지 않고 크기 유지',()=>{const moved=translateShape(box,2,-2);assert.equal(moved.x2,1);assert.equal(moved.y1,0);assert.ok(Math.abs((moved.x2-moved.x1)-.3)<.00001);});
test('화살표 선택은 선 부근에 한정',()=>{const arrow:Annotation={...box,kind:'arrow',x1:.1,y1:.1,x2:.9,y2:.9};assert.ok(hitShape([arrow],.5,.5,800,600));assert.equal(hitShape([arrow],.1,.9,800,600),undefined);});

for(const kind of ['circle','rectangle'] as const){
 test(`${kind}: 한 손가락을 뗀 뒤 남은 손가락이 움직여도 크기 고정`,()=>{
  const state:TwoPointState={ids:null,finished:false};
  const resized=resizeFromTouches({...box,kind},[{id:7,x:.1,y:.2},{id:9,x:.8,y:.9}],state);
  const lifted=resizeFromTouches(resized,[{id:7,x:.4,y:.4}],state);
  assert.deepEqual(lifted,resized);assert.equal(state.finished,true);
  assert.deepEqual(resizeFromTouches(lifted,[{id:7,x:.5,y:.5},{id:10,x:.6,y:.6}],state),resized);
 });
 test(`${kind}: 터치 배열 순서가 바뀌어도 동일한 손가락이 같은 꼭짓점을 제어`,()=>{
  const state:TwoPointState={ids:null,finished:false};
  resizeFromTouches({...box,kind},[{id:7,x:.1,y:.2},{id:9,x:.8,y:.9}],state);
  const resized=resizeFromTouches({...box,kind},[{id:9,x:.7,y:.8},{id:7,x:.2,y:.3}],state);
  assert.equal(resized.x1,.2);assert.equal(resized.y1,.3);assert.equal(resized.x2,.7);assert.equal(resized.y2,.8);
 });
}
test('중간 번호 삭제 및 되돌리기 후 연속 번호',()=>{
 const shapes=[box,{...box,id:'2',number:2},{...box,id:'3',number:3}];
 assert.deepEqual(renumber(shapes.filter(s=>s.id!=='2')).map(s=>s.number),[1,2]);
 assert.deepEqual(renumber(shapes).map(s=>s.number),[1,2,3]);
});

test('화살표는 첫 터치가 축의 시작점이며 터치 배열 순서에 영향받지 않음',()=>{
 const state:TwoPointState={ids:null,firstId:9,finished:false};
 const arrow=resizeFromTouches({...box,kind:'arrow'},[{id:3,x:.8,y:.2},{id:9,x:.2,y:.8}],state);
 assert.deepEqual([arrow.x1,arrow.y1,arrow.x2,arrow.y2],[.2,.8,.8,.2]);
});
