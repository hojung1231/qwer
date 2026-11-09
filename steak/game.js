import * as P from './physics.js';

const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const DPR = Math.min(2, window.devicePixelRatio || 1);
const REST_SPEED = 30;

// ---------- 색 ----------
const DONE_STOPS = [
  [0, [124, 20, 40]], [40, [138, 24, 44]], [48, [166, 32, 52]], [53, [188, 46, 60]],
  [57, [204, 76, 82]], [61, [214, 112, 108]], [65, [204, 146, 132]], [69, [180, 142, 126]],
  [75, [154, 122, 106]], [90, [134, 104, 88]],
];
const CRUST_STOPS = [[0.3, [178, 124, 86]], [1, [166, 94, 46]], [2.2, [124, 62, 26]], [3.6, [88, 40, 16]], [5, [48, 23, 11]], [7, [20, 12, 8]]];
const DRY = [160, 114, 80];
const HEAT_STOPS = [
  [0, [36, 54, 150]], [25, [40, 140, 200]], [45, [70, 196, 140]], [55, [190, 214, 70]], [62, [246, 196, 52]],
  [75, [240, 128, 40]], [100, [216, 48, 40]], [150, [140, 20, 70]], [210, [250, 236, 236]],
];
function lerpStops(stops, v) {
  if (v <= stops[0][0]) return stops[0][1].slice();
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [a, ca] = stops[i - 1], [b, cb] = stops[i];
      const t = (v - a) / (b - a);
      return [ca[0] + (cb[0] - ca[0]) * t, ca[1] + (cb[1] - ca[1]) * t, ca[2] + (cb[2] - ca[2]) * t];
    }
  }
  return stops[stops.length - 1][1].slice();
}
const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const rgb = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
function cellColor(tp, b, w) {
  let c = lerpStops(DONE_STOPS, tp);
  const d = clamp((0.7 * P.W0 - w) / (0.5 * P.W0), 0, 1);
  if (d > 0) c = mix(c, DRY, d);
  if (b > 0.01) c = b < 0.3 ? mix(c, CRUST_STOPS[0][1], b / 0.3) : lerpStops(CRUST_STOPS, b);
  return c;
}

let theme = {};
function readTheme() {
  const s = getComputedStyle(document.documentElement);
  for (const k of ['ink', 'muted', 'line', 'heat', 'good', 'flame', 'surface', 'chart-grid', 'warn']) theme[k] = s.getPropertyValue('--' + k).trim();
}

// ---------- 캔버스 ----------
function setup2d(canvas) {
  const w = canvas.width, h = canvas.height;
  canvas.width = w * DPR;
  canvas.height = h * DPR;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  return {ctx, w, h};
}
const scene = setup2d($('scene'));
const section = setup2d($('section'));
const profile = setup2d($('profile'));
const history = setup2d($('history'));
const resCut = setup2d($('resCut'));
const resProfile = setup2d($('resProfile'));

function offscreen(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

// 시드 고정 난수
function rng(seed) {
  return () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

// 마블링 텍스처
const marbling = (() => {
  const c = offscreen(240, 280), g = c.getContext('2d'), r = rng(7);
  g.lineCap = 'round';
  for (let i = 0; i < 26; i++) {
    g.strokeStyle = `rgba(255,240,228,${0.18 + r() * 0.35})`;
    g.lineWidth = 0.6 + r() * 2.4;
    g.beginPath();
    let x = r() * 240, y = r() * 280;
    g.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      const nx = x + (r() - 0.5) * 90, ny = y + (r() - 0.3) * 70;
      g.quadraticCurveTo(x + (r() - 0.5) * 60, y + (r() - 0.5) * 60, nx, ny);
      x = nx; y = ny;
    }
    g.stroke();
  }
  for (let i = 0; i < 160; i++) {
    g.fillStyle = `rgba(255,236,222,${0.15 + r() * 0.35})`;
    g.beginPath();
    g.arc(r() * 240, r() * 280, 0.5 + r() * 1.6, 0, 7);
    g.fill();
  }
  return c;
})();

// 결 텍스처 (단면용 근섬유)
const grain = (() => {
  const c = offscreen(400, 120), g = c.getContext('2d'), r = rng(11);
  for (let i = 0; i < 260; i++) {
    const y = r() * 120;
    g.strokeStyle = r() < 0.8 ? `rgba(0,0,0,${0.03 + r() * 0.05})` : `rgba(255,238,226,${0.05 + r() * 0.1})`;
    g.lineWidth = 0.5 + r() * 1.2;
    g.beginPath();
    g.moveTo(r() * 400 - 60, y);
    g.bezierCurveTo(100, y + (r() - 0.5) * 8, 300, y + (r() - 0.5) * 8, 460, y + (r() - 0.5) * 6);
    g.stroke();
  }
  return c;
})();

// 도마 나뭇결
const woodTex = (() => {
  const c = offscreen(280, 340), g = c.getContext('2d'), r = rng(3);
  const grd = g.createLinearGradient(0, 0, 280, 0);
  grd.addColorStop(0, '#9b6a3e');
  grd.addColorStop(1, '#8a5a32');
  g.fillStyle = grd;
  g.fillRect(0, 0, 280, 340);
  for (let i = 0; i < 70; i++) {
    g.strokeStyle = `rgba(${r() < 0.5 ? '60,34,14' : '190,140,90'},${0.08 + r() * 0.12})`;
    g.lineWidth = 0.6 + r() * 2;
    const x = r() * 280;
    g.beginPath();
    g.moveTo(x, 0);
    g.bezierCurveTo(x + (r() - 0.5) * 30, 110, x + (r() - 0.5) * 30, 230, x + (r() - 0.5) * 20, 340);
    g.stroke();
  }
  return c;
})();

// 스테이크 외곽 (정규화 좌표)
const steakShape = (() => {
  const pts = [], r = rng(5), ph = r() * 6, ph2 = r() * 6;
  for (let i = 0; i < 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    const c = Math.cos(a), s = Math.sin(a);
    const n = 3.4;
    let x = Math.sign(c) * Math.abs(c) ** (2 / n), y = Math.sign(s) * Math.abs(s) ** (2 / n);
    const k = 1 + 0.035 * Math.sin(3 * a + ph) + 0.02 * Math.sin(7 * a + ph2);
    pts.push([x * k * 0.5, y * k * 0.5]);
  }
  return pts;
})();
function steakPath(g, cx, cy, w, h) {
  g.beginPath();
  steakShape.forEach(([x, y], i) => (i ? g.lineTo(cx + x * w, cy + y * h) : g.moveTo(cx + x * w, cy + y * h)));
  g.closePath();
}

// ---------- 상태 ----------
const BOARD = {x: 26, y: 112, w: 270, h: 330, cx: 161, cy: 277};
const PAN = {cx: 548, cy: 268, r: 190};
const STEAK_W = (100 / 130) * PAN.r;
const STEAK_H = (120 / 130) * PAN.r;

const PAN_LOOK = {
  castiron: {base: '#2b2a2a', rim: '#3a3837', inner: '#1f1e1e', handle: '#2b2a2a'},
  stainless: {base: '#b8bdc2', rim: '#d9dde0', inner: '#a7adb3', handle: '#c9ced2'},
  nonstick: {base: '#242629', rim: '#5c6066', inner: '#1b1d1f', handle: '#1d1d1d'},
};

let cfg = {target: P.DONENESS[1], pan: 'castiron', start: 4, probe: true};
let sim = P.createSim({pan: cfg.pan, startTemp: cfg.start});
let running = false;
let speed = 4;
let view = 'side';
let soundOn = true;
let steakPos = {x: BOARD.cx, y: BOARD.cy};
let tween = null;
let flipAnim = null;
let particles = [];
let hist = [];
let histNext = 0;
let pullTime = null;
let resultShown = false;
let lastUi = 0;
let lastThemeRead = 0;

// ---------- 설정 화면 ----------
function buildSetup() {
  $('pickDone').innerHTML = P.DONENESS.map((d, i) => {
    const c = rgb(cellColor(d.target + 1, 0, P.W0));
    return `<label><input type="radio" name="done" id="done-${d.id}" value="${i}" ${i === 1 ? 'checked' : ''}><span><i class="swatch" style="background:${c}"></i>${d.name}<small>${d.target}°C</small></span></label>`;
  }).join('');
  $('pickPan').innerHTML = Object.entries(P.PANS).map(([id, p], i) =>
    `<label><input type="radio" name="pan" id="pan-${id}" value="${id}" ${i === 0 ? 'checked' : ''}><span>${p.name}<em>${p.note}</em></span></label>`).join('');
  try {
    const last = JSON.parse(localStorage.getItem('even-steak-cfg') || 'null');
    if (last) {
      const d = $(`done-${P.DONENESS[last.target]?.id}`); if (d) d.checked = true;
      const p = $(`pan-${last.pan}`); if (p) p.checked = true;
      const s = $(`start${last.start}`); if (s) s.checked = true;
      $('optProbe').checked = last.probe !== false;
    }
  } catch {}
}

$('setupForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const ti = Number(f.get('done'));
  cfg = {target: P.DONENESS[ti], pan: f.get('pan'), start: Number(f.get('start')), probe: $('optProbe').checked};
  try { localStorage.setItem('even-steak-cfg', JSON.stringify({target: ti, pan: cfg.pan, start: cfg.start, probe: cfg.probe})); } catch {}
  initAudio();
  newGame();
});

function newGame() {
  sim = P.createSim({pan: cfg.pan, startTemp: cfg.start});
  sim.level = Number($('burner').value);
  steakPos = {x: BOARD.cx, y: BOARD.cy};
  tween = null; flipAnim = null; particles = []; hist = []; histNext = 0; pullTime = null; resultShown = false;
  running = true;
  $('setup').hidden = true;
  $('result').hidden = true;
  $('chipTarget').textContent = `목표 ${cfg.target.name} ${cfg.target.target}°C`;
  $('chipPan').textContent = P.PANS[cfg.pan].name;
  $('noProbe').hidden = cfg.probe;
  for (const id of ['profile', 'history']) $(id).closest('.chart-card').hidden = !cfg.probe;
  $('viewCut').disabled = $('viewHeat').disabled = !cfg.probe;
  if (!cfg.probe) setView('side');
  updateButtons();
}

// ---------- 조작 ----------
function mainAction() {
  if (!running) return;
  if (sim.phase === 'preheat') {
    P.placeSteak(sim);
    tween = {from: {...steakPos}, to: {x: PAN.cx, y: PAN.cy}, t: 0};
    hist = []; histNext = 0;
  } else if (sim.phase === 'cooking') {
    if (flipAnim) return;
    flipAnim = {t: 0, before: topFaceColor()};
    P.flip(sim);
  } else if (sim.phase === 'done') {
    showResult();
  }
  updateButtons();
}
function rest() {
  if (sim.phase !== 'cooking') return;
  pullTime = sim.cookTime;
  P.removeToRest(sim);
  tween = {from: {...steakPos}, to: {x: BOARD.cx, y: BOARD.cy}, t: 0};
  updateButtons();
}
function setBaste(on) {
  sim.basting = on && sim.phase === 'cooking';
  $('btnBaste').classList.toggle('active', sim.basting);
}

$('btnMain').addEventListener('click', mainAction);
$('btnRest').addEventListener('click', rest);
$('btnOil').addEventListener('click', () => { sim.oil = true; updateButtons(); });
const baste = $('btnBaste');
baste.addEventListener('pointerdown', (e) => { e.preventDefault(); baste.setPointerCapture?.(e.pointerId); setBaste(true); });
for (const ev of ['pointerup', 'pointercancel', 'lostpointercapture']) baste.addEventListener(ev, () => setBaste(false));
baste.addEventListener('contextmenu', (e) => e.preventDefault());
$('burner').addEventListener('input', (e) => { sim.level = Number(e.target.value); $('burnerVal').textContent = e.target.value; });
$('speedSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-speed]');
  if (b) setSpeed(Number(b.dataset.speed));
});
function setSpeed(s) {
  speed = s;
  for (const b of $('speedSeg').querySelectorAll('button')) b.setAttribute('aria-checked', String(Number(b.dataset.speed) === s));
}
for (const b of document.querySelectorAll('[data-view]')) b.addEventListener('click', () => setView(b.dataset.view));
function setView(v) {
  view = v;
  for (const b of document.querySelectorAll('[data-view]')) b.setAttribute('aria-selected', String(b.dataset.view === v));
  $('viewHint').textContent = {
    side: '옆면은 실제 요리사가 보는 정보입니다. 익은 띠가 아래에서 올라옵니다.',
    cut: '연습용 투시 화면. 지금 잘랐을 때의 단면 색입니다.',
    heat: '연습용 열화상. 셀마다 현재 온도를 색으로 보여 줍니다.',
  }[v];
  buildLegend();
}
$('btnSound').addEventListener('click', (e) => {
  soundOn = !soundOn;
  e.currentTarget.setAttribute('aria-pressed', String(soundOn));
  e.currentTarget.textContent = soundOn ? '소리 켬' : '소리 끔';
});
$('btnAgain').addEventListener('click', () => { $('result').hidden = true; $('setup').hidden = false; running = false; });

document.addEventListener('keydown', (e) => {
  if (!$('setup').hidden || !$('result').hidden) return;
  if (e.code === 'Space') {
    e.preventDefault();
    if (!e.repeat) mainAction();
  } else if (e.code === 'KeyB') {
    if (!e.repeat) setBaste(true);
  } else if ((e.code === 'ArrowUp' || e.code === 'ArrowRight') && e.target.id !== 'burner') {
    nudgeBurner(1);
  } else if ((e.code === 'ArrowDown' || e.code === 'ArrowLeft') && e.target.id !== 'burner') {
    nudgeBurner(-1);
  } else if (/^Digit[1-5]$/.test(e.code)) {
    setSpeed([1, 2, 4, 8, 16][Number(e.code.slice(5)) - 1]);
  }
});
document.addEventListener('keyup', (e) => {
  if (e.code === 'Space') e.preventDefault();
  if (e.code === 'KeyB') setBaste(false);
});
function nudgeBurner(d) {
  const r = $('burner');
  r.value = clamp(Number(r.value) + d, 0, 10);
  r.dispatchEvent(new Event('input'));
}

function updateButtons() {
  const ph = sim.phase;
  const main = $('btnMain');
  const label = {preheat: '고기 올리기', cooking: '뒤집기', resting: '레스팅 중', done: '결과 보기'}[ph];
  main.innerHTML = `${label}${ph === 'resting' ? '' : ' <kbd>Space</kbd>'}`;
  main.disabled = !running || ph === 'resting';
  $('btnOil').disabled = !running || sim.oil || ph === 'resting' || ph === 'done';
  $('btnOil').textContent = sim.oil ? '기름 두름' : '기름 두르기';
  $('btnBaste').disabled = !running || ph !== 'cooking';
  $('btnRest').disabled = !running || ph !== 'cooking';
  const chip = $('chipPhase');
  chip.dataset.phase = ph;
  chip.textContent = {preheat: '예열', cooking: '굽는 중', resting: '레스팅', done: '완료'}[ph];
}

// ---------- 소리 ----------
let audio = null;
function initAudio() {
  if (audio) { audio.ac.resume?.(); return; }
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const len = ac.sampleRate * 2;
    const buf = ac.createBuffer(1, len, ac.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) {
      const pop = Math.random() < 0.0025 ? (Math.random() * 2 - 1) * 2.5 : 0;
      d[i] = (Math.random() * 2 - 1) * 0.3 + pop;
    }
    const src = ac.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const hp = ac.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 1800;
    const lp = ac.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 9000;
    const g = ac.createGain();
    g.gain.value = 0;
    src.connect(hp).connect(lp).connect(g).connect(ac.destination);
    src.start();
    audio = {ac, g};
  } catch {}
}
function updateAudio() {
  if (!audio) return;
  const v = soundOn && running ? Math.min(0.4, Math.sqrt(Math.max(0, sim.sizzle)) * 15) : 0;
  audio.g.gain.setTargetAtTime(v * (0.75 + Math.random() * 0.5), audio.ac.currentTime, 0.06);
}

// ---------- 그리기: 조리대 ----------
function topFaceColor() {
  let s = [0, 0, 0], n = 0;
  const z = P.NZ - 1;
  for (let x = 3; x < P.NX - 3; x++) {
    const i = z * P.NX + x;
    const c = cellColor(sim.Tpeak[i], sim.B[i], sim.W[i]);
    s[0] += c[0]; s[1] += c[1]; s[2] += c[2]; n++;
  }
  return [s[0] / n, s[1] / n, s[2] / n];
}
function sideColor() {
  let s = [0, 0, 0];
  for (let z = 0; z < P.NZ; z++) {
    const i = z * P.NX;
    const c = cellColor(sim.Tpeak[i], sim.B[i], sim.W[i]);
    s[0] += c[0]; s[1] += c[1]; s[2] += c[2];
  }
  return [s[0] / P.NZ, s[1] / P.NZ, s[2] / P.NZ];
}

function drawScene(now) {
  const g = scene.ctx, W = scene.w, H = scene.h;
  // 조리대 상판
  const bg = g.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, '#2b2e31');
  bg.addColorStop(1, '#1b1d20');
  g.fillStyle = bg;
  g.fillRect(0, 0, W, H);
  // 가스레인지 상판
  g.fillStyle = '#121315';
  roundRect(g, 318, 40, 470, 456, 18);
  g.fill();
  g.strokeStyle = '#2a2c30';
  g.lineWidth = 6;
  for (let a = 0; a < 4; a++) {
    const ang = (a / 4) * Math.PI * 2 + Math.PI / 4;
    g.beginPath();
    g.moveTo(PAN.cx + Math.cos(ang) * 40, PAN.cy + Math.sin(ang) * 40);
    g.lineTo(PAN.cx + Math.cos(ang) * 225, PAN.cy + Math.sin(ang) * 225);
    g.stroke();
  }
  // 도마
  g.save();
  g.shadowColor = 'rgba(0,0,0,.45)';
  g.shadowBlur = 18;
  g.shadowOffsetY = 6;
  roundRect(g, BOARD.x, BOARD.y, BOARD.w, BOARD.h, 16);
  g.fillStyle = '#8f5f36';
  g.fill();
  g.restore();
  g.save();
  roundRect(g, BOARD.x, BOARD.y, BOARD.w, BOARD.h, 16);
  g.clip();
  g.drawImage(woodTex, BOARD.x, BOARD.y, BOARD.w, BOARD.h);
  g.restore();
  // 불꽃
  drawFlames(g, now);
  // 팬
  const look = PAN_LOOK[sim.panType];
  g.save();
  g.translate(PAN.cx, PAN.cy);
  g.fillStyle = look.handle;
  roundRect(g, PAN.r - 8, -17, 270, 34, 12);
  g.fill();
  g.shadowColor = 'rgba(0,0,0,.6)';
  g.shadowBlur = 20;
  g.beginPath();
  g.arc(0, 0, PAN.r, 0, Math.PI * 2);
  g.fillStyle = look.rim;
  g.fill();
  g.shadowBlur = 0;
  const pg = g.createRadialGradient(-40, -50, 20, 0, 0, PAN.r - 10);
  pg.addColorStop(0, look.base);
  pg.addColorStop(1, look.inner);
  g.beginPath();
  g.arc(0, 0, PAN.r - 12, 0, Math.PI * 2);
  g.fillStyle = pg;
  g.fill();
  // 스테인리스 열변색
  if (sim.panType === 'stainless' && sim.panT > 200) {
    g.fillStyle = `rgba(190,150,60,${clamp((sim.panT - 200) / 300, 0, 0.35)})`;
    g.fill();
  }
  // 기름
  if (sim.oil) {
    const og = g.createRadialGradient(0, 0, 30, 0, 0, PAN.r - 20);
    og.addColorStop(0, 'rgba(214,170,60,.20)');
    og.addColorStop(1, 'rgba(214,170,60,.05)');
    g.fillStyle = og;
    g.beginPath();
    g.arc(0, 0, PAN.r - 16, 0, Math.PI * 2);
    g.fill();
    if (sim.panT > 140) {
      g.strokeStyle = `rgba(255,236,190,${clamp((sim.panT - 140) / 300, 0.05, 0.25)})`;
      g.lineWidth = 1.2;
      for (let k = 0; k < 6; k++) {
        const rr = 40 + k * 24 + Math.sin(now / 400 + k) * 4;
        g.beginPath();
        g.arc(0, 0, rr, now / 1500 + k, now / 1500 + k + 0.7);
        g.stroke();
      }
    }
  }
  // 육즙 자국 (퐁드)
  if (sim.dripped > 0.0005) {
    const a = clamp(sim.dripped * 18, 0, 0.6);
    const r = rng(9);
    for (let k = 0; k < 14; k++) {
      const ang = r() * Math.PI * 2;
      const rad = STEAK_W * 0.55 + r() * 30;
      g.fillStyle = `rgba(92,46,20,${a * (0.4 + r() * 0.6)})`;
      g.beginPath();
      g.ellipse(Math.cos(ang) * rad, Math.sin(ang) * rad * 1.15, 10 + r() * 22, 6 + r() * 12, ang, 0, Math.PI * 2);
      g.fill();
    }
  }
  // 버터 거품
  if (sim.basting) {
    g.fillStyle = 'rgba(240,206,120,.55)';
    for (let k = 0; k < 22; k++) {
      const ang = (k / 22) * Math.PI * 2 + now / 900;
      const rad = STEAK_W * 0.62 + Math.sin(now / 200 + k) * 6;
      g.beginPath();
      g.arc(Math.cos(ang) * rad, Math.sin(ang) * rad * 1.15, 8 + (k % 3) * 3, 0, Math.PI * 2);
      g.fill();
    }
  }
  g.restore();

  // 고기
  if (tween) {
    tween.t = Math.min(1, tween.t + 1 / 36);
    const e = 1 - (1 - tween.t) ** 3;
    steakPos = {x: tween.from.x + (tween.to.x - tween.from.x) * e, y: tween.from.y + (tween.to.y - tween.from.y) * e - Math.sin(Math.PI * tween.t) * 40};
    if (tween.t >= 1) tween = null;
  }
  let sy = 1, top = topFaceColor(), lift = 0;
  if (flipAnim) {
    flipAnim.t = Math.min(1, flipAnim.t + 1 / 22);
    sy = Math.abs(Math.cos(Math.PI * flipAnim.t));
    lift = Math.sin(Math.PI * flipAnim.t) * 30;
    if (flipAnim.t < 0.5) top = flipAnim.before;
    if (flipAnim.t >= 1) flipAnim = null;
  }
  if (tween) lift = Math.max(lift, Math.sin(Math.PI * tween.t) * 30);
  const {x, y} = steakPos;
  g.save();
  g.translate(x, y);
  // 그림자
  g.fillStyle = `rgba(0,0,0,${0.35 + lift / 200})`;
  steakPath(g, 6 + lift * 0.3, 8 + lift * 0.6, STEAK_W, STEAK_H * Math.max(sy, 0.2));
  g.fill();
  g.translate(0, -lift);
  g.scale(1, Math.max(sy, 0.04));
  // 옆면 (두께감)
  const side = sideColor();
  steakPath(g, 0, 7, STEAK_W, STEAK_H);
  g.fillStyle = rgb(mix(side, [40, 20, 14], 0.25));
  g.fill();
  steakPath(g, 0, 0, STEAK_W, STEAK_H);
  g.fillStyle = rgb(top);
  g.fill();
  g.save();
  g.clip();
  const topB = avgRow(sim.B, P.NZ - 1);
  g.globalAlpha = clamp(0.85 - topB * 0.25, 0.15, 0.85) * (flipAnim && flipAnim.t < 0.5 ? 0.5 : 1);
  g.drawImage(marbling, -STEAK_W / 2, -STEAK_H / 2, STEAK_W, STEAK_H);
  g.globalAlpha = 1;
  const sh = g.createRadialGradient(-20, -30, 10, 0, 0, STEAK_H * 0.7);
  sh.addColorStop(0, 'rgba(255,255,255,.10)');
  sh.addColorStop(1, 'rgba(0,0,0,.28)');
  g.fillStyle = sh;
  g.fillRect(-STEAK_W, -STEAK_H, STEAK_W * 2, STEAK_H * 2);
  g.restore();
  g.restore();

  // 입자
  spawnParticles();
  drawParticles(g);
}

function avgRow(a, z) {
  let s = 0;
  for (let x = 10; x < P.NX - 10; x++) s += a[z * P.NX + x];
  return s / (P.NX - 20);
}

function drawFlames(g, now) {
  if (sim.level <= 0) return;
  const n = 40;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const flick = Math.sin(now / 70 + i * 2.3) * 0.5 + Math.sin(now / 37 + i) * 0.5;
    const len = 8 + sim.level * 2.6 + flick * 3;
    const r0 = PAN.r - 14;
    const x0 = PAN.cx + Math.cos(a) * r0, y0 = PAN.cy + Math.sin(a) * r0;
    const x1 = PAN.cx + Math.cos(a) * (r0 + len + 14), y1 = PAN.cy + Math.sin(a) * (r0 + len + 14);
    const fg = g.createLinearGradient(x0, y0, x1, y1);
    fg.addColorStop(0, 'rgba(80,140,255,.95)');
    fg.addColorStop(0.6, 'rgba(60,110,255,.55)');
    fg.addColorStop(1, 'rgba(120,90,255,0)');
    g.strokeStyle = fg;
    g.lineWidth = 7;
    g.lineCap = 'round';
    g.beginPath();
    g.moveTo(x0, y0);
    g.lineTo(x1, y1);
    g.stroke();
  }
}

function spawnParticles() {
  const onPan = sim.onPan && !tween;
  const realDt = 1 / 60;
  const steamRate = Math.min(30, sim.steam * 6e4);
  let k = steamRate * realDt;
  while (k > 0) {
    if (Math.random() < k) {
      const ang = Math.random() * Math.PI * 2;
      particles.push({
        kind: 'steam',
        x: steakPos.x + Math.cos(ang) * STEAK_W * (onPan ? 0.55 : 0.3) * Math.random(),
        y: steakPos.y + Math.sin(ang) * STEAK_H * 0.5 * Math.random(),
        vx: (Math.random() - 0.5) * 0.4, vy: -0.6 - Math.random() * 0.8, life: 1, r: 8 + Math.random() * 10,
      });
    }
    k -= 1;
  }
  const w = P.warnings(sim);
  if (onPan && (w.includes('oil-smoke') || w.includes('burning'))) {
    const rate = w.includes('burning') ? 0.6 : 0.3;
    if (Math.random() < rate) {
      particles.push({kind: 'smoke', x: PAN.cx + (Math.random() - 0.5) * 220, y: PAN.cy + (Math.random() - 0.5) * 200, vx: (Math.random() - 0.5) * 0.3, vy: -0.4 - Math.random() * 0.5, life: 1, r: 14 + Math.random() * 16});
    }
  }
  if (onPan && sim.sizzle > 1e-4 && Math.random() < Math.min(0.9, sim.sizzle * 3000)) {
    const ang = Math.random() * Math.PI * 2;
    particles.push({kind: 'spat', x: steakPos.x + Math.cos(ang) * STEAK_W * 0.55, y: steakPos.y + Math.sin(ang) * STEAK_H * 0.55, vx: Math.cos(ang) * 2.5, vy: Math.sin(ang) * 2.5 - 1, life: 1, r: 1.5});
  }
  if (particles.length > 400) particles.splice(0, particles.length - 400);
}
function drawParticles(g) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  particles = particles.filter((p) => p.life > 0);
  for (const p of particles) {
    p.x += p.vx; p.y += p.vy;
    if (p.kind === 'steam') { p.life -= 0.012; p.r += 0.3; g.fillStyle = `rgba(240,240,240,${0.07 * p.life * p.life})`; }
    else if (p.kind === 'smoke') { p.life -= 0.006; p.r += 0.4; g.fillStyle = `rgba(110,110,115,${0.22 * p.life})`; }
    else { p.life -= 0.08; p.vy += 0.15; g.fillStyle = `rgba(255,232,180,${p.life})`; }
    if (reduce && p.kind === 'spat') continue;
    g.beginPath();
    g.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    g.fill();
  }
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

// ---------- 그리기: 단면 ----------
const cellCanvas = offscreen(P.NX, P.NZ);
const cellCtx = cellCanvas.getContext('2d');
const cellImg = cellCtx.createImageData(P.NX, P.NZ);
function paintCells(mode) {
  const d = cellImg.data;
  for (let z = 0; z < P.NZ; z++) {
    for (let x = 0; x < P.NX; x++) {
      const i = z * P.NX + x;
      const c = mode === 'heat' ? lerpStops(HEAT_STOPS, sim.T[i]) : cellColor(sim.Tpeak[i], sim.B[i], sim.W[i]);
      const o = ((P.NZ - 1 - z) * P.NX + x) * 4; // 위가 윗면
      d[o] = c[0]; d[o + 1] = c[1]; d[o + 2] = c[2]; d[o + 3] = 255;
    }
  }
  cellCtx.putImageData(cellImg, 0, 0);
}

function drawSection() {
  const g = section.ctx, W = section.w, H = section.h;
  g.clearRect(0, 0, W, H);
  const x0 = 64, x1 = W - 24, y0 = 26, y1 = H - 34;
  const onPan = sim.onPan;
  // 팬 / 도마
  g.fillStyle = onPan ? '#3a3a3c' : '#94643a';
  g.fillRect(x0 - 20, y1, x1 - x0 + 40, onPan ? 10 : 14);
  if (onPan) {
    g.fillStyle = `rgba(255,${clamp(200 - (sim.panT - 100), 60, 200) | 0},60,${clamp((sim.panT - 120) / 300, 0, 0.5)})`;
    g.fillRect(x0 - 20, y1, x1 - x0 + 40, 4);
  }
  g.save();
  roundRect(g, x0, y0, x1 - x0, y1 - y0, 10);
  g.clip();
  g.imageSmoothingEnabled = true;
  if (view === 'side') {
    // 가장자리 열(x=0)을 옆면으로 펼침
    const d = cellImg.data;
    for (let z = 0; z < P.NZ; z++) {
      const i = z * P.NX;
      const c = cellColor(sim.Tpeak[i], sim.B[i], sim.W[i]);
      for (let x = 0; x < P.NX; x++) {
        const o = ((P.NZ - 1 - z) * P.NX + x) * 4;
        const jitter = Math.sin(x * 1.7 + z * 0.3) * 4;
        d[o] = c[0] + jitter; d[o + 1] = c[1] + jitter; d[o + 2] = c[2] + jitter; d[o + 3] = 255;
      }
    }
    cellCtx.putImageData(cellImg, 0, 0);
  } else {
    paintCells(view);
  }
  g.drawImage(cellCanvas, x0, y0, x1 - x0, y1 - y0);
  if (view !== 'heat') g.drawImage(grain, x0, y0, x1 - x0, y1 - y0);
  g.restore();
  // 눈금
  g.fillStyle = theme.muted;
  g.font = '11px "JetBrains Mono", monospace';
  g.textAlign = 'right';
  g.textBaseline = 'middle';
  for (const mm of [0, 10, 20, 30]) {
    const yy = y1 - ((y1 - y0) * mm) / 30;
    g.fillText(`${mm}mm`, x0 - 8, yy);
    g.fillRect(x0 - 5, yy - 0.5, 4, 1);
  }
  g.textAlign = 'left';
  g.textBaseline = 'alphabetic';
  g.font = '12px "IBM Plex Sans KR", sans-serif';
  const faceUp = sim.face === 0 ? 'B' : 'A', faceDown = sim.face === 0 ? 'A' : 'B';
  g.fillText(`윗면 · 면 ${faceUp}`, x0, y0 - 8);
  g.fillText(onPan ? `팬 접촉 · 면 ${faceDown}` : `도마 · 면 ${faceDown}`, x0, H - 6);
  if (view !== 'side') {
    g.textAlign = 'right';
    g.fillText('폭 100mm', x1, H - 6);
  }
}

function buildLegend() {
  const el = $('scaleLegend');
  if (view === 'heat') {
    el.innerHTML = [0, 25, 45, 55, 62, 75, 100, 150, 210].map((t) => `<span><i style="background:${rgb(lerpStops(HEAT_STOPS, t))}"></i>${t}°</span>`).join('');
  } else {
    const items = [['생고기', 20], ['레어', 52], ['미디엄 레어', 56], ['미디엄', 61], ['미디엄 웰', 66], ['웰던', 72]];
    el.innerHTML = items.map(([n, t]) => `<span><i style="background:${rgb(cellColor(t, 0, P.W0))}"></i>${n}</span>`).join('') +
      `<span><i style="background:${rgb(cellColor(110, 2, 0))}"></i>크러스트</span><span><i style="background:${rgb(cellColor(110, 6.5, 0))}"></i>탄 부분</span>`;
  }
}

// ---------- 그래프 ----------
function axes(g, W, H, pad, yMin, yMax, yTicks) {
  g.strokeStyle = theme['chart-grid'];
  g.fillStyle = theme.muted;
  g.lineWidth = 1;
  g.font = '11px "JetBrains Mono", monospace';
  g.textAlign = 'right';
  g.textBaseline = 'middle';
  for (const t of yTicks) {
    const y = pad.t + (H - pad.t - pad.b) * (1 - (t - yMin) / (yMax - yMin));
    g.beginPath();
    g.moveTo(pad.l, y);
    g.lineTo(W - pad.r, y);
    g.stroke();
    g.fillText(`${t}°`, pad.l - 6, y);
  }
}
function drawProfile(ctxObj, data, peak, target, yMax = 180) {
  const g = ctxObj.ctx, W = ctxObj.w, H = ctxObj.h;
  g.clearRect(0, 0, W, H);
  const pad = {l: 40, r: 10, t: 10, b: 26};
  axes(g, W, H, pad, 0, yMax, yMax > 120 ? [0, 50, 100, 150] : [0, 30, 60, 90, 120]);
  const X = (z) => pad.l + ((W - pad.l - pad.r) * (z + 0.5)) / P.NZ;
  const Y = (t) => pad.t + (H - pad.t - pad.b) * (1 - clamp(t, 0, yMax) / yMax);
  // 마른 크러스트 영역
  if (data.water) {
    g.fillStyle = 'rgba(160,100,50,.16)';
    for (let z = 0; z < P.NZ; z++) if (data.water[z] < 0.5 * P.W0) g.fillRect(X(z) - (W - pad.l - pad.r) / P.NZ / 2, pad.t, (W - pad.l - pad.r) / P.NZ, H - pad.t - pad.b);
  }
  g.strokeStyle = theme.good;
  g.setLineDash([]);
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(pad.l, Y(target));
  g.lineTo(W - pad.r, Y(target));
  g.stroke();
  if (yMax > 120) {
    g.fillStyle = theme.muted;
    g.textAlign = 'right';
    g.textBaseline = 'bottom';
    g.fillText('끓는점', W - pad.r - 2, Y(100) - 2);
  }
  const line = (arr, color, dash, width) => {
    g.strokeStyle = color;
    g.setLineDash(dash);
    g.lineWidth = width;
    g.beginPath();
    arr.forEach((t, z) => (z ? g.lineTo(X(z), Y(t)) : g.moveTo(X(z), Y(t))));
    g.stroke();
    g.setLineDash([]);
  };
  if (peak) line(peak, theme.muted, [4, 3], 1.5);
  if (data.temp) line(data.temp, theme.heat, [], 2.5);
  g.fillStyle = theme.muted;
  g.textBaseline = 'alphabetic';
  g.textAlign = 'left';
  g.font = '11px "IBM Plex Sans KR", sans-serif';
  g.fillText('아랫면', pad.l, H - 8);
  g.textAlign = 'center';
  g.fillText('15mm', pad.l + (W - pad.l - pad.r) / 2, H - 8);
  g.textAlign = 'right';
  g.fillText('윗면', W - pad.r, H - 8);
}

function drawHistory() {
  const g = history.ctx, W = history.w, H = history.h;
  g.clearRect(0, 0, W, H);
  const pad = {l: 40, r: 12, t: 10, b: 24};
  const yMax = 80;
  axes(g, W, H, pad, 0, yMax, [0, 20, 40, 60, 80]);
  const tMax = Math.max(600, ...hist.map((h) => h.t)) * 1.05;
  const X = (t) => pad.l + ((W - pad.l - pad.r) * t) / tMax;
  const Y = (v) => pad.t + (H - pad.t - pad.b) * (1 - clamp(v, 0, yMax) / yMax);
  g.strokeStyle = theme.good;
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(pad.l, Y(cfg.target.target));
  g.lineTo(W - pad.r, Y(cfg.target.target));
  g.stroke();
  if (pullTime != null) {
    g.strokeStyle = theme.muted;
    g.setLineDash([3, 3]);
    g.beginPath();
    g.moveTo(X(pullTime), pad.t);
    g.lineTo(X(pullTime), H - pad.b);
    g.stroke();
    g.setLineDash([]);
    g.fillStyle = theme.muted;
    g.font = '11px "IBM Plex Sans KR", sans-serif';
    g.textAlign = 'left';
    g.textBaseline = 'top';
    g.fillText('레스팅', X(pullTime) + 4, pad.t);
  }
  if (hist.length > 1) {
    g.strokeStyle = theme.heat;
    g.lineWidth = 2.5;
    g.beginPath();
    hist.forEach((h, i) => (i ? g.lineTo(X(h.t), Y(h.core)) : g.moveTo(X(h.t), Y(h.core))));
    g.stroke();
    const last = hist[hist.length - 1];
    g.fillStyle = theme.heat;
    g.beginPath();
    g.arc(X(last.t), Y(last.core), 4, 0, Math.PI * 2);
    g.fill();
  }
  g.fillStyle = theme.muted;
  g.font = '11px "JetBrains Mono", monospace';
  g.textBaseline = 'alphabetic';
  g.textAlign = 'center';
  for (let m = 0; m * 60 <= tMax; m += tMax > 1500 ? 5 : 2) g.fillText(`${m}분`, X(m * 60), H - 6);
}

// ---------- 계기 ----------
const fmtTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const fmtShort = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

function updateUi() {
  const core = P.coreTemp(sim);
  const bottom = P.surfaceTemp(sim, false), top = P.surfaceTemp(sim, true);
  $('gPan').textContent = `${Math.round(sim.panT)}°`;
  $('gPanSub').textContent = panLabel(sim.panT);
  $('gCore').textContent = cfg.probe ? `${core.toFixed(1)}°` : '—';
  const left = cfg.target.target - core;
  $('gCoreSub').textContent = cfg.probe ? (left > 0 ? `목표까지 ${left.toFixed(1)}°` : `목표 +${(-left).toFixed(1)}°`) : '탐침 없음';
  $('gBottom').textContent = cfg.probe ? `${Math.round(bottom)}°` : '—';
  $('gTop').textContent = `${Math.round(top)}°`;
  $('gBottomSub').textContent = `면 ${sim.face === 0 ? 'A' : 'B'}${sim.onPan ? ' · 팬 접촉' : ''}`;
  $('gTopSub').textContent = `면 ${sim.face === 0 ? 'B' : 'A'}${sim.basting ? ' · 버터' : ''}`;
  const [fa, fb] = sim.faceTime;
  $('faceA').textContent = fmtShort(fa);
  $('faceB').textContent = fmtShort(fb);
  const tot = Math.max(1, fa + fb);
  $('faceABar').style.width = `${(fa / tot) * 100}%`;
  $('faceBBar').style.width = `${(fb / tot) * 100}%`;
  $('flipCount').textContent = `${sim.flips}회`;
  const ph = sim.phase;
  $('clock').textContent = fmtTime(ph === 'preheat' ? sim.time : ph === 'cooking' ? sim.cookTime : sim.restTime);
  $('clockLabel').textContent = ph === 'preheat' ? '예열' : ph === 'cooking' ? `굽는 중 · ${speed}×` : ph === 'resting' ? `레스팅 · ${REST_SPEED}×` : '완료';
  // 안내
  const msg = advice(core);
  const t = $('toast');
  t.hidden = !msg;
  if (msg) {
    t.textContent = msg.text;
    t.dataset.tone = msg.tone || '';
  }
  if (cfg.probe) {
    drawProfile(profile, {temp: P.columnProfile(sim, 'T'), water: P.columnProfile(sim, 'W')}, P.columnProfile(sim, 'Tpeak'), cfg.target.target);
    drawHistory();
  }
}
function panLabel(t) {
  if (t < 60) return '상온';
  if (t < 150) return '데워지는 중';
  if (t < 200) return '중불 정도';
  if (t < 260) return '시어링 온도';
  if (t < 320) return '아주 뜨거움';
  return '과열';
}
function advice(core) {
  if (!running) return null;
  const w = P.warnings(sim);
  const ph = sim.phase;
  if (ph === 'preheat') {
    if (!sim.oil && sim.panT > 150) return {text: '기름을 두르면 팬과 고기의 접촉이 좋아져 크러스트가 고르게 생깁니다.'};
    if (sim.panT < 150) return {text: '팬을 예열하는 중입니다. 시어링에는 200~250°C 가 알맞습니다. 배속을 올려도 됩니다.'};
    if (sim.panT < 200) return {text: '거의 다 데워졌습니다.'};
    if (w.includes('coating')) return {text: '코팅 팬이 손상되는 온도입니다. 불을 줄이세요.', tone: 'bad'};
    if (w.includes('oil-smoke')) return {text: '기름에서 연기가 납니다. 고기를 올리거나 불을 줄이세요.', tone: 'bad'};
    return {text: '고기를 올릴 때입니다. Space 또는 고기 올리기.'};
  }
  if (ph === 'cooking') {
    if (w.includes('burning')) return {text: '겉면이 타고 있습니다. 불을 줄이고 뒤집으세요.', tone: 'bad'};
    if (w.includes('coating')) return {text: '코팅 팬이 손상되는 온도입니다.', tone: 'bad'};
    if (w.includes('oil-smoke')) return {text: '기름 발연점(230°C)을 넘었습니다.', tone: 'bad'};
    const bDown = avgRow(sim.B, 0);
    if (bDown > 3.4) return {text: '아랫면 크러스트가 충분히 진합니다. 뒤집을 때입니다.'};
    if (sim.panT < 150) return {text: '팬 온도가 떨어졌습니다. 지글거림이 약해지면 크러스트가 안 생깁니다.'};
    if (cfg.probe && core >= cfg.target.target - 9 && core < cfg.target.target) return {text: '잔열을 생각하면 곧 꺼낼 때입니다.'};
    if (cfg.probe && core >= cfg.target.target) return {text: '이미 목표 온도입니다. 레스팅하면 더 오릅니다.', tone: 'bad'};
    return null;
  }
  if (ph === 'resting') return {text: `레스팅 중. 잔열이 중심으로 퍼지고 있습니다 (${REST_SPEED}× 빨리 감기).`};
  return null;
}

// ---------- 결과 ----------
function showResult() {
  const r = P.evaluate(sim, cfg.target.target);
  $('resTarget').textContent = `${cfg.target.name} 목표 · ${cfg.target.target}°C · ${P.PANS[cfg.pan].name}${cfg.probe ? '' : ' · 탐침 없음'}`;
  $('resVerdict').textContent = r.verdict;
  $('resScore').textContent = r.score;
  const bar = (name, got, max, detail) => {
    const p = got / max;
    return `<li><span>${name}</span><b>${got} / ${max}</b><div class="track"><div class="fill ${p < 0.4 ? 'low' : p < 0.8 ? 'mid' : ''}" style="width:${p * 100}%"></div></div><small>${detail}</small></li>`;
  };
  const crustWord = (b) => (b < 0.6 ? '창백함' : b < 1.2 ? '연한 갈색' : b <= 3.8 ? '진한 갈색' : b <= 6 ? '거의 탐' : '탐');
  $('resBars').innerHTML = [
    bar('목표 굽기', r.parts.core, 40, `중심 최저 ${r.core.toFixed(1)}°C · 목표 ${r.target}°C`),
    bar('회색 띠', r.parts.band, 15, `목표 +5°C 를 넘게 익은 층 ${r.bandMm.toFixed(0)}mm`),
    bar('위아래 대칭', r.parts.symmetry, 10, `양쪽 같은 깊이의 온도 차 평균 ${r.symmetry.toFixed(1)}°C`),
    bar('크러스트 면 A', r.parts.crustA, 10, `갈변 지수 ${r.browning[0].toFixed(1)} · ${crustWord(r.browning[0])}`),
    bar('크러스트 면 B', r.parts.crustB, 10, `갈변 지수 ${r.browning[1].toFixed(1)} · ${crustWord(r.browning[1])}`),
    bar('육즙', r.parts.juicy, 15, `중량 손실 ${r.lossPct.toFixed(1)}%`),
  ].join('');
  let best = null;
  try {
    const key = `even-steak-best-${cfg.target.id}`;
    best = Number(localStorage.getItem(key)) || null;
    if (!best || r.score > best) localStorage.setItem(key, String(r.score));
  } catch {}
  const stats = [
    ['굽기 시간', fmtShort(r.cookTime)],
    ['레스팅', fmtShort(r.restTime)],
    ['뒤집기', `${r.flips}회`],
    ['면 A / 면 B', `${fmtShort(r.faceTime[0])} / ${fmtShort(r.faceTime[1])}`],
    ['크러스트 두께', `${r.crustMm[0]}mm / ${r.crustMm[1]}mm`],
    ['이 굽기 최고점', best && best > r.score ? `${best}점` : `${r.score}점 (새 기록)`],
  ];
  $('resStats').innerHTML = stats.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join('');
  $('result').hidden = false;
  drawCut();
  drawProfile(resProfile, {}, r.profile, cfg.target.target, 120);
}

function drawCut() {
  const g = resCut.ctx, W = resCut.w, H = resCut.h;
  g.clearRect(0, 0, W, H);
  g.drawImage(woodTex, 0, 0, W, H);
  paintCells('cut');
  const x0 = 50, x1 = W - 50, y0 = 60, y1 = H - 60;
  g.save();
  g.shadowColor = 'rgba(0,0,0,.4)';
  g.shadowBlur = 14;
  g.shadowOffsetY = 6;
  roundRect(g, x0, y0, x1 - x0, y1 - y0, 18);
  g.fillStyle = '#5a2a14';
  g.fill();
  g.restore();
  g.save();
  roundRect(g, x0, y0, x1 - x0, y1 - y0, 18);
  g.clip();
  g.imageSmoothingEnabled = true;
  g.drawImage(cellCanvas, x0, y0, x1 - x0, y1 - y0);
  g.globalAlpha = 0.9;
  g.drawImage(grain, x0, y0, x1 - x0, y1 - y0);
  g.globalAlpha = 1;
  // 육즙 광택
  const gl = g.createLinearGradient(0, y0, 0, y1);
  gl.addColorStop(0, 'rgba(255,255,255,.08)');
  gl.addColorStop(0.5, 'rgba(255,255,255,0)');
  gl.addColorStop(1, 'rgba(0,0,0,.08)');
  g.fillStyle = gl;
  g.fillRect(x0, y0, x1 - x0, y1 - y0);
  g.restore();
  g.fillStyle = 'rgba(255,248,240,.92)';
  g.font = '600 15px "IBM Plex Sans KR", sans-serif';
  g.textBaseline = 'alphabetic';
  g.textAlign = 'left';
  const up = sim.face === 0 ? 'B' : 'A', down = sim.face === 0 ? 'A' : 'B';
  g.fillText(`면 ${up}`, x0, y0 - 14);
  g.fillText(`면 ${down}`, x0, y1 + 30);
  g.textAlign = 'right';
  g.font = '13px "JetBrains Mono", monospace';
  g.fillText('30mm × 100mm 단면', x1, y1 + 30);
}

// ---------- 루프 ----------
let last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (running && sim.phase !== 'done') {
    const mult = sim.phase === 'resting' ? REST_SPEED : speed;
    const before = sim.phase;
    P.advance(sim, dt * mult);
    if (sim.phase !== 'preheat' && sim.cookTime + sim.restTime >= histNext) {
      hist.push({t: sim.cookTime + sim.restTime, core: P.coreTemp(sim)});
      histNext = sim.cookTime + sim.restTime + 4;
    }
    if (before !== sim.phase) updateButtons();
  }
  if (running && sim.phase === 'done' && !resultShown) {
    resultShown = true;
    updateButtons();
    setTimeout(showResult, 700);
  }
  if (now - lastThemeRead > 1500) { readTheme(); lastThemeRead = now; }
  drawScene(now);
  if (now - lastUi > 90) {
    lastUi = now;
    drawSection();
    updateUi();
    updateAudio();
  }
  requestAnimationFrame(frame);
}

readTheme();
buildSetup();
buildLegend();
setSpeed(4);
// 설정 화면 뒤로 보이는 예시 장면: 달궈지는 팬과 도마 위 생고기
sim.panT = 180;
sim.level = 10;
updateButtons();
updateUi();
requestAnimationFrame(frame);
