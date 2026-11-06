// The style card of a regular channel (backend/style_lab.py card_scene): an explainer infographic with no characters.
// A carrot, a brain and an eye joined by glowing arrows, labels and a title; every colour comes from the style
// (mood, ui), so the same board shows each style's palette, light and texture.
import { E, V, S, registerShot, mood, backdrop, seg, circle, rr, poly, glow, alpha, text, FONTS, linGrad, radGrad, shade, mix } from '/engine/core.js';
import { brainGlyph } from '/engine/scenekit.js';

const props = {};
let names = [];
try { names = await (await fetch('/project/assets/index.json')).json(); } catch {}
await Promise.all(names.map(name => new Promise(done => {
  const image = new Image(); image.onload = () => { props[name] = image; done(); }; image.onerror = done;
  image.src = `/project/assets/${name}.png`;
})));
function picture(g, name, x, y, height) {
  const image = props[name]; if (!image) return false;
  const width = height * image.width / image.height;
  g.drawImage(image, x - width / 2, y - height / 2, width, height); return true;
}

function carrot(g, x, y, r, M) {
  const tip = [x - r * 0.5, y + r * 1.25], top = [x + r * 0.35, y - r * 0.85];
  glow(g, x, y, r * 2.2, '#ff8a2a', 0.18);
  // leaves: three blades with their own light side
  [[-0.5, -1.65, -0.5], [0.15, -1.85, 0], [0.75, -1.5, 0.45]].forEach(([dx, dy, k]) => {
    const ex = top[0] + dx * r, ey = top[1] + dy * r * 0.55;
    g.beginPath(); g.moveTo(top[0] - r * 0.12, top[1]); g.quadraticCurveTo(ex - r * 0.35 + k * r * 0.2, ey + r * 0.3, ex, ey);
    g.quadraticCurveTo(ex + r * 0.3, ey + r * 0.45, top[0] + r * 0.14, top[1]); g.closePath();
    g.fillStyle = linGrad(g, ex, ey, top[0], top[1], ['#8fe36a', '#3f9a3a', '#24602a']); g.fill();
  });
  // the root: an orange cone with light on one side, shade on the other, and its ridges
  g.save(); g.translate(x, y); g.rotate(-0.55);
  const body = new Path2D(); body.moveTo(-r * 0.62, -r * 1.05); body.quadraticCurveTo(-r * 0.7, r * 0.2, 0, r * 1.55); body.quadraticCurveTo(r * 0.7, r * 0.2, r * 0.62, -r * 1.05); body.quadraticCurveTo(0, -r * 1.3, -r * 0.62, -r * 1.05);
  g.fillStyle = linGrad(g, -r * 0.7, 0, r * 0.7, 0, ['#ffb15a', '#ff8a2a', '#d4561c', '#9a3812']); g.fill(body);
  g.save(); g.clip(body); g.strokeStyle = alpha('#7a2a0a', 0.55); g.lineWidth = Math.max(2, r * 0.05); g.lineCap = 'round';
  for (let i = 0; i < 6; i++) { const yy = -r * 0.7 + i * r * 0.36, w = r * (0.5 - i * 0.06); g.beginPath(); g.moveTo(-w, yy); g.quadraticCurveTo(-w * 0.4, yy + r * 0.06, -w * 0.05, yy); g.stroke(); }
  g.fillStyle = alpha('#fff3dc', 0.35); g.beginPath(); g.ellipse(-r * 0.3, -r * 0.45, r * 0.12, r * 0.55, 0.1, 0, Math.PI * 2); g.fill();
  g.restore(); g.restore();
}

function eye(g, x, y, r, M) {
  const ui = S().ui;
  glow(g, x, y, r * 2, ui.accent, 0.2);
  g.save(); g.beginPath(); g.moveTo(x - r * 1.3, y); g.quadraticCurveTo(x, y - r * 1.15, x + r * 1.3, y); g.quadraticCurveTo(x, y + r * 1.15, x - r * 1.3, y); g.closePath();
  g.fillStyle = radGrad(g, x - r * 0.2, y - r * 0.3, r * 0.1, r * 1.4, ['#ffffff', '#e8ecf4', '#9aa4b8']); g.fill(); g.clip();
  circle(g, x, y, r * 0.55, ui.accent); g.fillStyle = radGrad(g, x, y, r * 0.05, r * 0.55, [alpha('#000', 0), alpha('#000', 0.45)]); g.beginPath(); g.arc(x, y, r * 0.55, 0, Math.PI * 2); g.fill();
  circle(g, x, y, r * 0.24, '#06070a'); circle(g, x - r * 0.16, y - r * 0.18, r * 0.11, '#ffffff');
  g.restore();
  g.strokeStyle = shade(S().ink, 0.2); g.lineWidth = Math.max(3, r * 0.07); g.beginPath(); g.moveTo(x - r * 1.3, y); g.quadraticCurveTo(x, y - r * 1.15, x + r * 1.3, y); g.stroke();
}

// a glowing curved arrow from a to b, bent by k, with a label on its middle
function link(g, a, b, k, color, str) {
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2 - k, w = V(7, 8);
  g.save(); g.globalCompositeOperation = 'lighter'; g.strokeStyle = alpha(color, 0.25); g.lineWidth = w * 4; g.lineCap = 'round';
  g.beginPath(); g.moveTo(...a); g.quadraticCurveTo(mx, my, ...b); g.stroke(); g.restore();
  g.strokeStyle = color; g.lineWidth = w; g.lineCap = 'round'; g.setLineDash([w * 2.4, w * 1.8]);
  g.beginPath(); g.moveTo(...a); g.quadraticCurveTo(mx, my, ...b); g.stroke(); g.setLineDash([]);
  const ang = Math.atan2(b[1] - my, b[0] - mx), s = w * 3.4;
  poly(g, [b, [b[0] - Math.cos(ang - 0.45) * s, b[1] - Math.sin(ang - 0.45) * s], [b[0] - Math.cos(ang + 0.45) * s, b[1] - Math.sin(ang + 0.45) * s]], color);
  const lx = (a[0] + 2 * mx + b[0]) / 4, ly = (a[1] + 2 * my + b[1]) / 4, ui = S().ui, size = V(26, 30);
  g.save(); g.font = `900 ${size}px "${FONTS.ui}", "Nunito", sans-serif`; const tw = g.measureText(str).width; g.restore();
  rr(g, lx - tw / 2 - 20, ly - size * 0.95, tw + 40, size * 1.9, size * 0.95); g.fillStyle = ui.card; g.fill(); g.strokeStyle = alpha(color, 0.7); g.lineWidth = 2; g.stroke();
  text(g, str, lx, ly + 1, { size, color, font: FONTS.ui, weight: 900, spacing: 1.5 });
}

function caption(g, str, sub, x, y) {
  const ui = S().ui;
  text(g, str, x, y, { size: V(40, 44), color: ui.cream, font: FONTS.ui, weight: 900, spacing: 2 });
  text(g, sub, x, y + V(44, 48), { size: V(28, 30), color: mix(ui.sub, ui.cream, 0.35), font: FONTS.ui, weight: 800 });
}

registerShot('s001', { draw(g, t) {
  const M = mood('dusk'), ui = S().ui;
  backdrop(g, M.sky);
  g.fillStyle = alpha(shade(M.dark, -0.25), 0.62); g.fillRect(0, 0, E.W, E.H);   // the board darkens the sky but keeps its gradient
  g.strokeStyle = alpha(ui.blueprint, 0.06); g.lineWidth = 1;
  for (let x = 0; x <= E.W; x += 60) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, E.H); g.stroke(); }
  for (let y = 0; y <= E.H; y += 60) { g.beginPath(); g.moveTo(0, y); g.lineTo(E.W, y); g.stroke(); }
  glow(g, E.W * 0.5, E.H * 0.5, E.W * 0.45, M.key, 0.1);
  const r = E.H * 0.13, cy = E.H * 0.56;
  const C = [E.W * 0.19, cy], B = [E.W * 0.5, cy - E.H * 0.02], Y = [E.W * 0.81, cy];
  link(g, [C[0] + r * 0.9, C[1] - r * 0.6], [B[0] - r * 1.25, B[1] - r * 0.3], E.H * 0.12, ui.gold, 'ВІТАМІН А');
  link(g, [B[0] + r * 1.25, B[1] - r * 0.3], [Y[0] - r * 1.45, Y[1] - r * 0.2], E.H * 0.12, ui.accent, 'ЧІТКИЙ ЗІР');
  if (!picture(g, 'carrots', C[0], C[1], r * 2.7)) carrot(g, C[0], C[1], r, M);
  if (!picture(g, 'brain', B[0], B[1], r * 2.6)) brainGlyph(g, B[0], B[1], r * 1.15, t, { seed: 4 });
  if (!picture(g, 'eye_model', Y[0], Y[1], r * 2.3)) eye(g, Y[0], Y[1], r * 0.95, M);
  caption(g, 'МОРКВА', 'бета-каротин', C[0], cy + r * 1.95);
  caption(g, 'МОЗОК', 'перетворює сигнал', B[0], cy + r * 1.95);
  caption(g, 'ОЧІ', 'бачать у темряві', Y[0], cy + r * 1.95);
  text(g, 'ЯК МОРКВА ДОПОМАГАЄ ЗОРУ', E.W / 2, E.H * 0.14, { size: V(62, 64), color: ui.cream, font: FONTS.title, weight: 700, glow: 18, glowColor: alpha(ui.accent, 0.45), spacing: 1 });
} });
