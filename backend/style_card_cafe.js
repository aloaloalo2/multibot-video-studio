// The animated style card's title and PNG props (user, 20 November 2026: «PNG асети нічого не змінюють»): the café scene of the
// kit's example had no picture props, so «PNG-асети» on and off drew the same card. This file loads after the example's
// shots and draws a bicycle, a menu board, a cat and a cake over the café shot at the card's moment, in the style's own
// grade, when the card is drawn with assets; without them it draws nothing.
import { E, getShot, registerShot } from '/engine/core.js';

let names = [];
try { names = await (await fetch('/project/assets/index.json')).json(); } catch {}
const images = {};
for (const name of names) {
  const image = new Image();
  image.src = `/project/assets/${name}.png`;
  images[name] = image;
}
await Promise.all(Object.values(images).map(image => image.decode().catch(() => {})));

function picture(g, name, x, y, height) {
  const image = images[name];
  if (!image || !image.naturalWidth) return;
  const w = height * image.naturalWidth / image.naturalHeight;
  g.drawImage(image, x - w / 2, y - height, w, height);
}

// the channel's font shows on the café's own sign (examples/reaction-time/scenes/sets/cafe.js; user, 20 November 2026:
// «Я шрифт міняю, він не змінюється на картинці… там ж є заголовок кафе»)
const original = getShot('s004');
if (original) {
  registerShot('s004', { ...original, draw(g, t, info) {
    original.draw(g, t, info);
    const W = E.W, H = E.H, ground = H * 0.835;
    picture(g, 'city_bicycle', W * 0.1, ground, H * 0.24);
    picture(g, 'chalkboard', W * 0.255, ground, H * 0.15);
    picture(g, 'cat_sitting', W * 0.85, ground, H * 0.13);
    picture(g, 'cake', W * 0.465, H * 0.678, H * 0.07);
  } });
}
