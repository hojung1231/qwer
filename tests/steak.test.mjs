import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as P from '../steak/physics.js';

function cook({level = 6, preheat = 250, flipEvery = 60, pullAt = 47, target = 56} = {}) {
  const s = P.createSim({pan: 'castiron', startTemp: 4});
  s.oil = true;
  s.level = 10;
  while (s.panT < preheat) P.advance(s, 1);
  s.level = level;
  const panBefore = s.panT;
  P.placeSteak(s);
  P.advance(s, 30);
  const panDrop = panBefore - s.panT;
  let last = 0;
  while (P.coreTemp(s) < pullAt && s.cookTime < 1800) {
    P.advance(s, 1);
    if (s.cookTime - last >= flipEvery) { P.flip(s); last = s.cookTime; }
  }
  const pulled = P.coreTemp(s);
  P.moveTo(s, 'board');
  restUntilPeak(s);
  assert.ok(P.cut(s));
  return {s, panDrop, pulled, result: P.evaluate(s, target)};
}

// 잔열로 중심 온도가 최고점을 지나 내려가기 시작할 때까지 휴지
function restUntilPeak(s) {
  let max = -Infinity;
  for (let t = 0; t < 900; t += 5) {
    P.advance(s, 5);
    const c = P.coreTemp(s);
    if (c > max) max = c;
    else if (t > 90 && c < max - 0.3) break;
  }
}

test('스테이크 물리: 젖은 셀은 비등점 근처에서 멈추고 마른 크러스트만 100°C 를 넘음', () => {
  const s = P.createSim({});
  s.panT = 240; s.level = 6; s.oil = true;
  P.placeSteak(s);
  P.advance(s, 120);
  for (let i = 0; i < s.T.length; i++) if (s.W[i] > 0.2 * P.W0) assert.ok(s.T[i] <= 100.5, `wet cell ${i} at ${s.T[i]}`);
  const bottom = P.surfaceTemp(s, false);
  assert.ok(bottom > 100 && bottom < 240, `bottom surface ${bottom}`);
  assert.ok(s.evaporated > 0 && s.sizzle > 0);
});

test('스테이크 물리: 뒤집기는 온도 분포를 위아래로 뒤바꿈', () => {
  const s = P.createSim({});
  s.panT = 220; P.placeSteak(s); P.advance(s, 60);
  const before = P.columnProfile(s);
  P.flip(s);
  const after = P.columnProfile(s);
  for (let z = 0; z < P.NZ; z++) assert.ok(Math.abs(before[z] - after[P.NZ - 1 - z]) < 1e-9);
  assert.equal(s.face, 1);
});

test('스테이크 물리: 정상적인 굽기는 잔열로 목표 굽기에 도달', () => {
  const {panDrop, pulled, result} = cook();
  assert.ok(panDrop > 5, `팬 온도 하강 ${panDrop}`);
  assert.ok(result.core > pulled + 3, `잔열 상승 ${pulled} → ${result.core}`);
  assert.ok(Math.abs(result.core - 56) < 3, `중심 ${result.core}`);
  assert.ok(result.cookTime > 300 && result.cookTime < 1200, `조리 시간 ${result.cookTime}`);
  assert.ok(result.score >= 80, `점수 ${result.score}`);
});

test('스테이크 물리: 한 면만 오래 구우면 대칭 점수가 깎임', () => {
  const {result} = cook({flipEvery: 100000, level: 5, preheat: 230});
  assert.ok(result.symmetry > 5, `대칭 편차 ${result.symmetry}`);
  assert.ok(result.parts.symmetry < 6);
});

test('스테이크 물리: 리버스 시어링 (오븐 → 도마 → 팬 → 도마)', () => {
  const s = P.createSim({startTemp: 4});
  s.ovenT = 120;
  s.oil = true;
  assert.ok(P.moveTo(s, 'oven'));
  while (P.coreTemp(s) < 46) P.advance(s, 5);
  const ovenMinutes = s.cookTime / 60;
  assert.ok(ovenMinutes > 25 && ovenMinutes < 90, `오븐 ${ovenMinutes}분`);
  P.moveTo(s, 'board');
  s.level = 10;
  while (s.panT < 270) P.advance(s, 1);
  s.level = 8;
  P.moveTo(s, 'pan');
  assert.equal(P.cut(s), false, '팬 위에서는 자를 수 없음');
  for (let k = 0; k < 4; k++) { P.advance(s, 45); P.flip(s); }
  P.moveTo(s, 'board');
  restUntilPeak(s);
  assert.ok(P.cut(s));
  assert.equal(P.moveTo(s, 'pan'), false, '자른 뒤에는 옮길 수 없음');
  const r = P.evaluate(s, 56);
  assert.deepEqual(r.segments.map((g) => g.place), ['oven', 'board', 'pan', 'board']);
  assert.equal(r.panVisits, 1);
  assert.ok(Math.abs(r.core - 56) < 3, `중심 ${r.core}`);
  assert.ok(Math.min(...r.browning) > 1, `크러스트 ${r.browning}`);
  assert.ok(r.score >= 85, `점수 ${r.score}`);
});

test('스테이크 물리: 팬과 도마를 여러 번 오가도 시간이 위치별로 쌓임', () => {
  const s = P.createSim({});
  s.panT = 240;
  s.level = 6;
  for (let k = 0; k < 3; k++) {
    P.moveTo(s, 'pan');
    P.advance(s, 60);
    P.moveTo(s, 'board');
    P.advance(s, 30);
  }
  assert.equal(s.panVisits, 3);
  assert.ok(Math.abs(s.placeTime.pan - 180) < 1 && Math.abs(s.placeTime.board - 90) < 1);
  assert.equal(P.segments(s).length, 6);
});
