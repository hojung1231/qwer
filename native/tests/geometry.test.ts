import {test} from 'node:test';
import assert from 'node:assert/strict';
import {THUMB_WIDTH,THUMB_STEP,hitShape,translateShape} from '../src/geometry.ts';
import type {Annotation} from '../src/model.ts';
const box:Annotation={id:'1',number:1,kind:'rectangle',color:'#ed4d4d',x1:.2,y1:.2,x2:.5,y2:.6};
test('썸네일 노출 간격은 너비의 80%',()=>assert.equal(THUMB_STEP/THUMB_WIDTH,.8));
test('겹친 개체는 나중에 추가된 것이 선택됨',()=>assert.equal(hitShape([box,{...box,id:'2'}],.3,.3,800,600)?.id,'2'));
test('이동 시 이미지 경계를 넘지 않고 크기 유지',()=>{const moved=translateShape(box,2,-2);assert.equal(moved.x2,1);assert.equal(moved.y1,0);assert.ok(Math.abs((moved.x2-moved.x1)-.3)<.00001);});
test('화살표 선택은 선 부근에 한정',()=>{const arrow:Annotation={...box,kind:'arrow',x1:.1,y1:.1,x2:.9,y2:.9};assert.ok(hitShape([arrow],.5,.5,800,600));assert.equal(hitShape([arrow],.1,.9,800,600),undefined);});
