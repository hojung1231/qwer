// 3cm 소고기 스테이크 열전달 시뮬레이션.
// 고기 단면(폭 10cm × 두께 3cm)을 2차원 유한체적 격자로 나누고,
// 셀 사이 전도, 팬 접촉 열전달, 공기 대류, 표면 증발, 비등에 의한 크러스트 건조,
// 단백질 수축에 의한 육즙 손실, 마이야르 갈변을 함께 계산한다.
// 팬은 하나의 열용량 덩어리로 보고 버너 입력, 대류·복사 손실, 고기로 빠져나가는 열을 계산한다.

export const NX = 50; // 폭 방향 셀 (2mm)
export const NZ = 30; // 두께 방향 셀 (1mm), z=0 이 팬에 닿는 아랫면
export const DX = 0.002;
export const DZ = 0.001;
export const DEPTH = 0.12; // 단면에 수직인 고기 길이 (m). 접촉 면적 = 0.10 × 0.12 m²
export const THICKNESS_MM = NZ * DZ * 1000;
export const WIDTH_MM = NX * DX * 1000;

const V = DX * DZ; // 단위 길이당 셀 부피 (m²)
export const W0 = 780; // 생고기 수분 농도 kg/m³ (수분 약 73%)
const SOLIDS = 290; // 단백질·지방 등 고형분 kg/m³
const CW = 4180; // 물 비열 J/kgK
const CS = 1700; // 고형분 비열
const LV = 2.257e6; // 물 증발 잠열 J/kg
const W_RES = 0.06 * W0; // 100°C 근처에서 잘 빠지지 않는 결합수
const SIGMA = 5.670e-8;
const T_AMB = 22;
const RHO_V_AMB = rhoVapor(T_AMB) * 0.5; // 상대습도 50%
const PAN_AREA = Math.PI * 0.13 * 0.13; // 지름 26cm
const STEAK_AREA = NX * DX * DEPTH;
const BURNER_MAX = 900; // 팬에 실제로 들어가는 최대 열량 (가스 약 2.7kW × 효율 1/3)
export const OIL_SMOKE = 230;
export const PLACES = ['board', 'pan']; // 도마(휴지), 팬

export const PANS = {
  castiron: {name: '무쇠 팬', note: '열용량이 커서 고기를 올려도 온도가 덜 떨어짐. 예열이 느림', mass: 3.0, c: 460, eps: 0.65, maxSafe: Infinity},
  stainless: {name: '3중 스테인리스', note: '중간 열용량. 반응이 빠른 편', mass: 1.5, c: 500, eps: 0.35, maxSafe: Infinity},
  nonstick: {name: '코팅 알루미늄', note: '가볍고 빨리 식음. 260°C 이상은 코팅 손상', mass: 0.9, c: 900, eps: 0.85, maxSafe: 260},
};

export const DONENESS = [
  {id: 'rare', name: '레어', target: 52},
  {id: 'mediumrare', name: '미디엄 레어', target: 56},
  {id: 'medium', name: '미디엄', target: 61},
  {id: 'mediumwell', name: '미디엄 웰', target: 66},
  {id: 'well', name: '웰던', target: 71},
];

export function rhoVapor(t) {
  const tc = Math.min(t, 99.5);
  const p = 610.94 * Math.exp((17.625 * tc) / (tc + 243.04)); // Magnus 포화수증기압 (Pa)
  return (p * 0.018) / (8.314 * (tc + 273.15));
}

// 단백질 수축 후 남을 수 있는 수분 (최고 도달 온도 기준)
export function waterHolding(tPeak) {
  return W0 * (1 - 0.19 / (1 + Math.exp(-(tPeak - 56) / 4.5)));
}

// 마이야르 반응 속도 (1/s). 150°C 에서 약 60초에 노릇한 갈색(B=1)
export function browningRate(t) {
  if (t <= 101) return 0;
  return Math.exp(12000 * (1 / 423.15 - 1 / (t + 273.15))) / 60;
}

export function createSim({pan = 'castiron', startTemp = 4, ambient = T_AMB} = {}) {
  const n = NX * NZ;
  const sim = {
    T: new Float64Array(n).fill(startTemp),
    W: new Float64Array(n).fill(W0),
    Tpeak: new Float64Array(n).fill(startTemp),
    B: new Float64Array(n),
    k: new Float64Array(n),
    C: new Float64Array(n),
    dE: new Float64Array(n),
    panType: pan,
    panT: ambient,
    ambient,
    level: 0,
    oil: false,
    basting: false,
    place: 'board',
    phase: 'prep', // prep(도마 위 생고기) → cooking(팬과 도마를 자유롭게 오감) → done(자름)
    time: 0,
    cookTime: 0,
    placeTime: {board: 0, pan: 0},
    panVisits: 0,
    log: [], // [{t, place}] 처음 불에 올린 뒤의 이동 기록
    flips: 0,
    face: 0, // 원래 면 0/1 중 지금 팬에 닿는 면
    faceTime: [0, 0],
    dripped: 0,
    evaporated: 0,
    water0: W0 * n * V * DEPTH,
    // 화면 효과용 순간값
    sizzle: 0,
    steam: 0,
    panToMeat: 0,
  };
  return sim;
}

const idx = (x, z) => z * NX + x;

function boundaryConductance(h, k, area, half) {
  return 1 / (1 / (h * area) + half / (k * area));
}

export function step(sim, dt) {
  const {T, W, Tpeak, B, k, C, dE} = sim;
  const n = NX * NZ;
  const pan = PANS[sim.panType];
  const amb = sim.ambient;
  const onPan = sim.place === 'pan';
  for (let i = 0; i < n; i++) {
    const w = W[i];
    k[i] = 0.12 + 0.36 * Math.min(w, W0) / W0;
    C[i] = w * CW + SOLIDS * CS;
    dE[i] = 0;
  }
  // 내부 전도
  for (let z = 0; z < NZ; z++) {
    for (let x = 0; x < NX - 1; x++) {
      const i = idx(x, z), j = i + 1;
      const q = ((2 * k[i] * k[j]) / (k[i] + k[j])) * (DZ / DX) * (T[i] - T[j]);
      dE[i] -= q;
      dE[j] += q;
    }
  }
  for (let z = 0; z < NZ - 1; z++) {
    for (let x = 0; x < NX; x++) {
      const i = idx(x, z), j = i + NX;
      const q = ((2 * k[i] * k[j]) / (k[i] + k[j])) * (DX / DZ) * (T[i] - T[j]);
      dE[i] -= q;
      dE[j] += q;
    }
  }
  let panFlux = 0; // W/m (단위 길이당)
  let evapRate = 0; // kg/s/m
  // 표면 증발. 마른 크러스트는 안쪽 젖은 층의 수분이 크러스트를 통해 천천히 빠져나간다고 본다
  const evaporate = (i, h, area, inward) => {
    const drive = rhoVapor(T[i]) - RHO_V_AMB;
    if (drive <= 0) return;
    let src = i, f = 1;
    if (W[i] <= W_RES) {
      src = i + inward;
      f = 0.35;
      if (W[src] <= W_RES) return;
    }
    const mdot = Math.min((h / 1400) * f * drive * area, ((W[src] - W_RES) * V) / dt);
    W[src] -= (mdot * dt) / V;
    dE[i] -= mdot * LV;
    evapRate += mdot;
  };
  // 아랫면: 팬 접촉 또는 도마
  for (let x = 0; x < NX; x++) {
    const i = idx(x, 0);
    if (onPan) {
      const wet = Math.max(0, Math.min(1, (W[i] - W_RES) / (0.6 * W0 - W_RES)));
      const h = (sim.oil ? 520 : 330) * (0.35 + 0.65 * wet); // 표면이 마르면 접촉이 줄어듦
      const q = boundaryConductance(h, k[i], DX, DZ / 2) * (sim.panT - T[i]);
      dE[i] += q;
      panFlux += q;
    } else {
      const q = boundaryConductance(22, k[i], DX, DZ / 2) * (amb - T[i]); // 도마로 빠지는 열 + 공기
      dE[i] += q;
      evaporate(i, 8, DX, NX);
    }
  }
  // 윗면: 공기 또는 버터 베이스팅
  for (let x = 0; x < NX; x++) {
    const i = idx(x, NZ - 1);
    if (onPan && sim.basting) {
      const tf = Math.min(sim.panT, 165); // 거품 낸 버터는 약 165°C 이상 오르지 않음
      const q = boundaryConductance(230, k[i], DX, DZ / 2) * (tf - T[i]);
      dE[i] += q;
      panFlux += q;
    } else {
      const tf = amb + (onPan ? (sim.panT - amb) * 0.06 : 0);
      const h = onPan ? 12 : 16; // 자연대류 + 복사
      const q = boundaryConductance(h, k[i], DX, DZ / 2) * (tf - T[i]);
      dE[i] += q;
      evaporate(i, h, DX, -NX);
    }
  }
  // 옆면: 팬 위 뜨거운 공기층
  for (let z = 0; z < NZ; z++) {
    const tf = amb + (onPan ? (sim.panT - amb) * 0.35 * Math.exp(-((z + 0.5) * DZ) / 0.005) : 0);
    for (const [x, inward] of [[0, 1], [NX - 1, -1]]) {
      const i = idx(x, z);
      dE[i] += boundaryConductance(16, k[i], DZ, DX / 2) * (tf - T[i]);
      evaporate(i, 16, DZ, inward);
    }
  }
  let boil = 0;
  let drip = 0;
  for (let i = 0; i < n; i++) {
    let t = T[i] + (dE[i] * dt) / (C[i] * V);
    // 100°C 를 넘는 에너지는 물을 끓여 날려 보냄 → 크러스트가 마르며 안쪽으로 자람
    if (t > 100 && W[i] > W_RES) {
      const excess = (t - 100) * C[i] * V;
      const m = Math.min(excess / LV, (W[i] - W_RES) * V);
      W[i] -= m / V;
      const cNew = W[i] * CW + SOLIDS * CS;
      t = 100 + (excess - m * LV) / (cNew * V);
      boil += m;
    }
    T[i] = t;
    if (t > Tpeak[i]) Tpeak[i] = t;
    // 단백질 수축으로 짜여 나오는 육즙
    const hold = waterHolding(Tpeak[i]);
    if (W[i] > hold) {
      const m = Math.min(W[i] - hold, (W[i] - hold) * 0.006 * dt);
      W[i] -= m;
      drip += m * V;
    }
    B[i] += browningRate(t) * dt;
  }
  sim.dripped += drip * DEPTH;
  sim.evaporated += (boil + evapRate * dt) * DEPTH;
  // 팬 에너지 수지
  const tk = sim.panT + 273.15, ta = amb + 273.15;
  const exposed = PAN_AREA * 1.6 - (onPan ? STEAK_AREA : 0);
  const loss = exposed * (10 * (sim.panT - amb) + pan.eps * SIGMA * (tk ** 4 - ta ** 4));
  const juice = onPan && sim.panT > 100 ? (drip * DEPTH * LV) / dt : 0; // 팬에 떨어진 육즙 증발
  const pin = (sim.level / 10) * BURNER_MAX;
  sim.panT += ((pin - loss - panFlux * DEPTH - juice) * dt) / (pan.mass * pan.c);
  sim.panToMeat = panFlux * DEPTH;
  const sizz = onPan ? (boil * DEPTH) / dt + (juice > 0 ? (drip * DEPTH) / dt : 0) : 0;
  sim.sizzle += (sizz - sim.sizzle) * Math.min(1, dt * 2);
  sim.steam += ((boil * DEPTH) / dt + evapRate * DEPTH - sim.steam) * Math.min(1, dt * 2);

  sim.time += dt;
  if (sim.phase === 'cooking') {
    sim.cookTime += dt;
    sim.placeTime[sim.place] += dt;
    if (onPan) sim.faceTime[sim.face] += dt;
  }
}

export function advance(sim, seconds, dt = 0.2) {
  let left = seconds;
  while (left > 1e-9) {
    const h = Math.min(dt, left);
    step(sim, h);
    left -= h;
    if (sim.phase === 'done') break;
  }
}

// 고기를 도마와 팬 사이로 옮긴다. 몇 번이든 오갈 수 있다.
// 그릴 수비드: 짧게 시어링하고 도마에서 쉬기를 반복해, 겉은 식히고 잔열로 안쪽만 천천히 익힌다
export function moveTo(sim, place) {
  if (sim.phase === 'done' || sim.place === place || !PLACES.includes(place)) return false;
  sim.place = place;
  sim.basting = false;
  if (sim.phase === 'prep' && place !== 'board') sim.phase = 'cooking';
  if (place === 'pan') sim.panVisits++;
  if (sim.phase === 'cooking') sim.log.push({t: sim.cookTime, place});
  return true;
}
export const placeSteak = (sim) => moveTo(sim, 'pan');
export const removeToRest = (sim) => moveTo(sim, 'board');

// 팬 밖에 있을 때만 자를 수 있다. 자르는 순간의 상태로 채점
export function cut(sim) {
  if (sim.phase !== 'cooking' || sim.place === 'pan') return false;
  sim.phase = 'done';
  sim.basting = false;
  return true;
}

// 이동 기록을 [{place, from, to}] 구간으로 정리
export function segments(sim) {
  const out = [];
  sim.log.forEach((e, i) => {
    const to = i + 1 < sim.log.length ? sim.log[i + 1].t : sim.cookTime;
    if (to > e.t) out.push({place: e.place, from: e.t, to});
  });
  return out;
}

export function flip(sim) {
  if (sim.phase === 'done') return;
  for (const a of [sim.T, sim.W, sim.Tpeak, sim.B]) {
    for (let z = 0; z < NZ / 2; z++) {
      for (let x = 0; x < NX; x++) {
        const i = idx(x, z), j = idx(x, NZ - 1 - z);
        const tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
      }
    }
  }
  sim.face = 1 - sim.face;
  sim.flips++;
}

// 가운데 탐침 온도계 위치 (두께 중앙)
export function coreTemp(sim) {
  const x = NX / 2;
  const z = NZ / 2;
  return (sim.T[idx(x, z)] + sim.T[idx(x - 1, z)] + sim.T[idx(x, z - 1)] + sim.T[idx(x - 1, z - 1)]) / 4;
}

export function surfaceTemp(sim, top) {
  const z = top ? NZ - 1 : 0;
  let s = 0;
  for (let x = 10; x < NX - 10; x++) s += sim.T[idx(x, z)];
  return s / (NX - 20);
}

export function columnProfile(sim, field = 'T') {
  const a = sim[field];
  const out = new Float64Array(NZ);
  const x0 = Math.floor(NX * 0.3), x1 = Math.ceil(NX * 0.7);
  for (let z = 0; z < NZ; z++) {
    let s = 0;
    for (let x = x0; x < x1; x++) s += a[idx(x, z)];
    out[z] = s / (x1 - x0);
  }
  return out;
}

export function warnings(sim) {
  const w = [];
  const pan = PANS[sim.panType];
  if (sim.oil && sim.panT > OIL_SMOKE) w.push('oil-smoke');
  if (sim.panT > pan.maxSafe) w.push('coating');
  const surf = columnProfile(sim, 'B');
  if (surf[0] > 5 || surf[NZ - 1] > 5) w.push('burning');
  return w;
}

export const grayThreshold = (target) => Math.max(68, target + 6);

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const ramp = (v, full, zero) => clamp01((zero - v) / (zero - full));

function crustScore(b) {
  if (b < 1.2) return clamp01(b / 1.2);
  if (b <= 3.8) return 1;
  return clamp01((6 - b) / 2.2);
}

export function evaluate(sim, target) {
  const peak = columnProfile(sim, 'Tpeak');
  const water = columnProfile(sim, 'W');
  const brown = columnProfile(sim, 'B');
  let crustBottom = 0, crustTop = 0;
  while (crustBottom < NZ / 2 && water[crustBottom] < 0.5 * W0) crustBottom++;
  while (crustTop < NZ / 2 && water[NZ - 1 - crustTop] < 0.5 * W0) crustTop++;
  let core = Infinity;
  for (let z = crustBottom; z < NZ - crustTop; z++) core = Math.min(core, peak[z]);
  let band = 0;
  // 회색 띠: 미오글로빈이 다 변성돼 분홍기가 사라진 층 (최고 온도 68°C 이상, 목표가 높으면 목표 +6°C)
  const grayT = grayThreshold(target);
  for (let z = crustBottom; z < NZ - crustTop; z++) if (peak[z] > grayT) band++;
  let sym = 0;
  for (let z = 0; z < NZ / 2; z++) sym += Math.abs(peak[z] - peak[NZ - 1 - z]);
  sym /= NZ / 2;
  // 지금 아래(z=0)가 어느 원래 면인지에 따라 면 A/B 를 정한다
  const bDown = brown[0], bUp = brown[NZ - 1];
  const faceB = sim.face === 0 ? [bDown, bUp] : [bUp, bDown];
  let water1 = 0;
  for (let i = 0; i < sim.W.length; i++) water1 += sim.W[i];
  water1 *= V * DEPTH;
  const totalMass0 = sim.water0 + SOLIDS * NX * NZ * V * DEPTH;
  const lossPct = ((sim.water0 - water1) / totalMass0) * 100;
  const parts = {
    core: Math.round(35 * ramp(Math.abs(core - target), 1.5, 10)),
    band: Math.round(20 * ramp(band, 2, 10)),
    symmetry: Math.round(10 * ramp(sym, 2, 12)),
    crustA: Math.round(10 * crustScore(faceB[0])),
    crustB: Math.round(10 * crustScore(faceB[1])),
    juicy: Math.round(15 * ramp(lossPct, 12, 26)),
  };
  const score = Object.values(parts).reduce((a, b) => a + b, 0);
  return {
    score,
    parts,
    core,
    target,
    bandMm: band * DZ * 1000,
    grayT,
    symmetry: sym,
    crustMm: [crustBottom, crustTop],
    browning: faceB,
    lossPct,
    flips: sim.flips,
    cookTime: sim.cookTime,
    placeTime: {...sim.placeTime},
    panVisits: sim.panVisits,
    segments: segments(sim),
    faceTime: [...sim.faceTime],
    profile: [...peak],
    verdict: verdict(score, core, target, faceB, band, sym),
  };
}

function verdict(score, core, target, faceB, band, sym) {
  if (core < 40) return '속이 아직 날것입니다.';
  if (Math.max(...faceB) > 6) return '겉이 탔어요. 불이 너무 셌습니다.';
  if (score >= 90) return '완벽합니다. 이븐하게 익었어요.';
  if (sym > 8) return '한쪽 면만 오래 익었어요. 이븐하게 익지 않았어요.';
  if (core > target + 4) return '목표보다 더 익었습니다. 잔열까지 계산해서 일찍 내리세요.';
  if (core < target - 4) return '덜 익었습니다. 조금 더 굽거나 레스팅을 충분히 하세요.';
  if (band > 6) return '회색 띠가 두껍습니다. 짧게 굽고 쉬기를 반복하며 불을 점점 줄여 보세요.';
  if (Math.min(...faceB) < 1) return '크러스트가 약합니다. 처음 몇 번은 센 불로 겉부터 잡으세요.';
  return '좋습니다. 조금만 다듬으면 완벽해요.';
}
