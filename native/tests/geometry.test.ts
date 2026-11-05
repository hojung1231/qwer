import {test} from 'node:test';
import assert from 'node:assert/strict';
import {THUMB_WIDTH,THUMB_STEP,hitShape,translateShape,renumber,resizeFromTouches,pinchFromTouches,pinchAxis,movedPastHold,centeredCrop} from '../src/geometry.ts';
import type {TwoPointState} from '../src/geometry.ts';
import type {Annotation} from '../src/model.ts';
const box:Annotation={id:'1',number:1,kind:'rectangle',color:'#ed4d4d',x1:.2,y1:.2,x2:.5,y2:.6};

for(const kind of ['circle','rectangle','arrow'] as const){
 test(`${kind}: 바깥 두 점을 대도 위치와 크기는 유지되고 간격 비율로 확대 축소`,()=>{
  const shape={...box,kind},state:TwoPointState={ids:null,finished:false};
  assert.deepEqual(pinchFromTouches(shape,[{id:1,x:0,y:.1},{id:2,x:1,y:.9}],state,800,600),shape);
  const smaller=pinchFromTouches(shape,[{id:2,x:.9,y:.82},{id:1,x:.1,y:.18}],state,800,600);
  assert.ok(Math.abs((smaller.x2-smaller.x1)/.3-.8)<1e-9);
  assert.ok(Math.abs((smaller.y2-smaller.y1)/.4-.8)<1e-9);
  assert.ok(Math.abs((smaller.x1+smaller.x2)/2-.35)<1e-9);
  assert.deepEqual(pinchFromTouches(smaller,[{id:1,x:.2,y:.4}],state,800,600),smaller);
 });
}
test('같은 이동 거리라도 넓게 잡으면 작은 비율로 변환',()=>{
 const pinch=(grip:number)=>{const state:TwoPointState={ids:null,finished:false};pinchFromTouches(box,[{id:1,x:.5-grip/2,y:.4},{id:2,x:.5+grip/2,y:.4}],state,800,600);return pinchFromTouches(box,[{id:1,x:.5-grip/2+.05,y:.4},{id:2,x:.5+grip/2-.05,y:.4}],state,800,600);};
 const wide=pinch(.8),narrow=pinch(.4);
 assert.ok(Math.abs((wide.x2-wide.x1)/.3-.875)<1e-9);
 assert.ok(Math.abs((narrow.x2-narrow.x1)/.3-.75)<1e-9);
});
test('핀치 확대와 두 손가락 이동은 최초 개체를 기준으로 계산',()=>{
 const state:TwoPointState={ids:null,finished:false};pinchFromTouches(box,[{id:1,x:.3,y:.3},{id:2,x:.5,y:.3}],state,800,600);
 const bigger=pinchFromTouches(box,[{id:1,x:.2,y:.3},{id:2,x:.6,y:.3}],state,800,600);
 assert.ok(Math.abs((bigger.x2-bigger.x1)-.6)<1e-9);
 const moved=pinchFromTouches(bigger,[{id:1,x:.4,y:.4},{id:2,x:.6,y:.4}],state,800,600);
 assert.ok(Math.abs(moved.x1-.3)<1e-9);assert.ok(Math.abs(moved.y1-.3)<1e-9);
});
test('휴지통 길게 누르기 판정은 미세 떨림을 허용하고 이동 시 취소',()=>{
 assert.equal(movedPastHold({x:.3,y:.3},{x:.303,y:.303},800,600),false);
 assert.equal(movedPastHold({x:.3,y:.3},{x:.32,y:.3},800,600),true);
});
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

test('세로 촬영은 원본에서 실제 가로3 세로4 픽셀로 자름',()=>{
 const crop=centeredCrop(4096,3072,3/4);
 assert.deepEqual(crop,{originX:896,originY:0,width:2304,height:3072});
});
test('가로 촬영은 원본에서 실제 가로4 세로3 픽셀로 자름',()=>{
 const crop=centeredCrop(3072,4096,4/3);
 assert.deepEqual(crop,{originX:0,originY:896,width:3072,height:2304});
});

const zones:Record<number,{x:number;y:number}>={1:{x:.1,y:.1},2:{x:.35,y:.1},3:{x:.8,y:.1},4:{x:.1,y:.4},5:{x:.8,y:.4},6:{x:.1,y:.9},7:{x:.35,y:.9},8:{x:.8,y:.9}};
for(const kind of ['rectangle','circle','arrow'] as const){
 test(`${kind}: 그림의 28가지 영역 조합과 역순 터치를 모두 분류하고 축 고정 확대/축소/이동`,()=>{
  for(let a=1;a<=8;a++)for(let b=a+1;b<=8;b++)for(const reversed of [false,true]){
   const pair=`${a},${b}`,axis=['1,6','2,7','3,8'].includes(pair)?'vertical':['1,3','4,5','6,8'].includes(pair)?'horizontal':'both';
   const shape={...box,kind},p=[{id:10,...zones[a]},{id:20,...zones[b]}];if(reversed)p.reverse();
   assert.equal(pinchAxis(shape,p[0],p[1]),axis,pair);
   const state:TwoPointState={ids:null,finished:false};assert.deepEqual(pinchFromTouches(shape,p,state,800,600),shape);
   const midX=(p[0].x+p[1].x)/2,midY=(p[0].y+p[1].y)/2;
   for(const factor of [.75,1.2]){
    const moved=p.map(t=>({...t,x:midX+(t.x-midX)*factor+.03,y:midY+(t.y-midY)*factor+.02})).reverse();
    const result=pinchFromTouches(shape,moved,state,800,600);
    assert.ok(Math.abs((result.x2-result.x1)/.3-(axis==='vertical'?1:factor))<1e-9,`${pair}: width`);
    assert.ok(Math.abs((result.y2-result.y1)/.4-(axis==='horizontal'?1:factor))<1e-9,`${pair}: height`);
    assert.ok(Math.abs((result.x1+result.x2)/2-.38)<1e-9,`${pair}: pan x`);
    assert.ok(Math.abs((result.y1+result.y2)/2-.42)<1e-9,`${pair}: pan y`);
   }
   assert.equal(state.baseline?.axis,axis);
  }
 });
}
test('손가락이 영역 경계를 넘어도 시작 시 결정한 세로 축 유지',()=>{
 const state:TwoPointState={ids:null,finished:false};pinchFromTouches(box,[{id:1,...zones[2]},{id:2,...zones[7]}],state,800,600);
 const changed=pinchFromTouches(box,[{id:1,x:.1,y:.25},{id:2,x:.7,y:.75}],state,800,600);
 assert.ok(Math.abs((changed.x2-changed.x1)-.3)<1e-9);assert.equal(state.baseline?.axis,'vertical');
 assert.deepEqual(pinchFromTouches(changed,[{id:1,x:.4,y:.5}],state,800,600),changed);
});

test('수평/수직 화살표도 길이가 0인 축으로 펼칠 수 있고 시작 시 튀지 않음',()=>{
 const arrow:Annotation={...box,kind:'arrow',y1:.4,y2:.4},state:TwoPointState={ids:null,finished:false};
 assert.deepEqual(pinchFromTouches(arrow,[{id:1,x:.35,y:.2},{id:2,x:.35,y:.6}],state,800,600),arrow);
 const expanded=pinchFromTouches(arrow,[{id:1,x:.35,y:.1},{id:2,x:.35,y:.7}],state,800,600);
 assert.ok(Math.abs((expanded.x2-expanded.x1)-.3)<1e-9);assert.ok(Math.abs((expanded.y2-expanded.y1)-.2)<1e-9);
 const vertical:Annotation={...box,kind:'arrow',x1:.4,x2:.4},other:TwoPointState={ids:null,finished:false};
 assert.deepEqual(pinchFromTouches(vertical,[{id:1,x:.2,y:.4},{id:2,x:.6,y:.4}],other,800,600),vertical);
 const wider=pinchFromTouches(vertical,[{id:1,x:.1,y:.4},{id:2,x:.7,y:.4}],other,800,600);
 assert.ok(Math.abs((wider.y2-wider.y1)-.4)<1e-9);assert.ok(Math.abs((wider.x2-wider.x1)-.15)<1e-9);
});
