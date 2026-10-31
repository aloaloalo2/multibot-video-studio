// engine/styles.js — colour moods + switchable visual styles.
// A MOOD is the lighting situation of a location (day, dusk, night, storm, interiors, void).
// A STYLE re-grades every mood (palette overrides + a lift/gamma/gain colour grade on the final frame + post settings).
// grade: contrast (around mid-grey), sat (saturation), lift/gamma/gain per RGB channel (lift tints shadows, gain tints highlights).
// Scenes must take colours from mood()/S() so a style switch re-themes the whole video.

export const BASE_MOODS = {
  day:          { sky: ['#8fb0d8', '#cfdcea', '#efe3d2'], ambient: '#6f7d96', key: '#fff3dc', rim: '#fff1d6', wall: '#8d8496', floor: '#5f5866', dark: '#2f2a36', practical: '#ffe2a8', grass: '#4f8a55', road: '#5d5a66', fog: '#dfe4f0' },
  golden:       { sky: ['#6b5a8e', '#e89a6a', '#f9d49c'], ambient: '#4a3a50', key: '#ffcf8f', rim: '#ffc68a', wall: '#5a3a34', floor: '#45302a', dark: '#2a1814', practical: '#ffe7b0', grass: '#4d6b3c', road: '#4a3c40', fog: '#f0c49a' },
  dusk:         { sky: ['#3d3360', '#8a5a86', '#e8956b', '#f7cf98'], ambient: '#3b2b3d', key: '#ffc68a', rim: '#ffc68a', wall: '#4a3646', floor: '#3d2c38', dark: '#231a27', practical: '#ffd59a', grass: '#3d5a48', road: '#3a3040', fog: '#c08a8a' },
  night:        { sky: ['#0b1028', '#1d2550', '#3a3570'], ambient: '#1e2444', key: '#c9d4ff', rim: '#a9b8ff', wall: '#262a46', floor: '#1b1e33', dark: '#0f1122', practical: '#ffb860', grass: '#22433a', road: '#24263a', fog: '#3a4270' },
  storm:        { sky: ['#141a33', '#2a3358', '#3d4670'], ambient: '#232a48', key: '#dfe6ff', rim: '#cfd9ff', wall: '#2b3150', floor: '#1c2238', dark: '#0d1020', practical: '#bcd0ff', grass: '#25483e', road: '#232838', fog: '#4a5580' },
  interiorWarm: { sky: ['#c98a74', '#f2b585', '#f7cf98'], ambient: '#4a3646', key: '#ffd59a', rim: '#ffcf8f', wall: '#4f3a40', floor: '#3a2a2e', dark: '#21171c', practical: '#ffd28a', grass: '#3d5a48', road: '#3a3040', fog: '#a87a70' },
  interiorCool: { sky: ['#2a3560', '#5a6aa0'], ambient: '#2a2c48', key: '#cbd6ff', rim: '#b8c6ff', wall: '#2e3150', floor: '#22243a', dark: '#121426', practical: '#9fe0ff', grass: '#22433a', road: '#24263a', fog: '#4a5080' },
  void:         { sky: ['#0a0e1a', '#121a2e'], ambient: '#151c30', key: '#ffffff', rim: '#8fb8e8', wall: '#121a2e', floor: '#0d1322', dark: '#070a12', practical: '#ffd47e', grass: '#1d3a33', road: '#151a28', fog: '#1d2740' },
};

const UI = { card: 'rgba(18,28,48,.94)', cardLine: 'rgba(150,180,230,.25)', text: '#9fb6d8', sub: '#6f84a6', accent: '#ff6f61', gold: '#ffd47e', cream: '#fff1dc', blueprint: '#8fb8e8', bpBg: '#0b1324', good: '#5fd39a' };

export const STYLES = {
  dusk: {
    name: 'Cinematic Dusk', desc: 'Reference look: mauve-purple shadows, amber key light, cream rim light, soft grain, 2:1 letterbox.',
    ink: '#0e0b12', inkFar: '#2b2333', feature: '#f4efe6', rimWidth: 4, ui: UI,
    grade: { contrast: 1.0, sat: 1.0, lift: [0, 0, 0], gamma: [1, 1, 1], gain: [1, 1, 1], vignette: 0.55, grain: 0.055, bloom: 0.55 },
    moods: {},
  },
  midnight: {
    name: 'Midnight Blue', desc: 'Cold navy world, blue-white rim light, sodium-orange practical lights, rain-friendly, higher contrast.',
    ink: '#0a0c16', inkFar: '#232a40', feature: '#eef3ff', rimWidth: 4, ui: { ...UI, accent: '#ff8a5c', gold: '#ffc66e' },
    grade: { contrast: 1.06, sat: 0.8, lift: [0.0, 0.025, 0.09], gamma: [0.92, 0.98, 1.08], gain: [0.84, 0.95, 1.15], vignette: 0.65, grain: 0.06, bloom: 0.7 },
    moods: { dusk: { sky: ['#141a3a', '#2c3470', '#5a5aa0', '#c08aa0'], key: '#d8dcff', rim: '#b8c8ff', wall: '#2a2c4a', floor: '#1e2036' }, golden: { rim: '#ffd6a8' }, interiorWarm: { wall: '#3a3448', sky: ['#5a5a90', '#c09ab0'] } },
  },
  golden: {
    name: 'Golden Hour', desc: 'Warm orange-and-teal daylight, big sun glows, brighter mid-tones, warm cream rim light.',
    ink: '#120c0a', inkFar: '#3a2a26', feature: '#fff6e6', rimWidth: 4.5, ui: { ...UI, card: 'rgba(30,26,40,.92)', accent: '#ff7a4a' },
    grade: { contrast: 1.04, sat: 1.18, lift: [0.035, 0.015, 0.0], gamma: [1.1, 1.04, 0.94], gain: [1.12, 1.02, 0.8], vignette: 0.45, grain: 0.045, bloom: 0.75 },
    moods: { night: { sky: ['#14183a', '#2e2c5a', '#6a4a6a'], rim: '#ffcf9a' }, dusk: { sky: ['#4a3a6a', '#d0786a', '#f2a46a', '#fbd8a0'] } },
  },
  neon: {
    name: 'Neon Noir', desc: 'Deep blacks, magenta + teal two-tone rim lights, glowing signage, strong bloom, cool shadows.',
    ink: '#07060c', inkFar: '#1e1830', feature: '#f6f0ff', rimWidth: 4, ui: { ...UI, card: 'rgba(14,10,28,.94)', cardLine: 'rgba(200,120,255,.3)', text: '#c9a8ff', accent: '#ff4fa3', gold: '#5ff2e8', blueprint: '#7fe8ff' },
    grade: { contrast: 1.15, sat: 1.4, lift: [0.01, 0.0, 0.04], gamma: [1.0, 0.9, 1.06], gain: [1.12, 0.86, 1.18], vignette: 0.7, grain: 0.06, bloom: 0.9 },
    moods: { dusk: { sky: ['#120a2a', '#3a1a5a', '#a03a8a', '#ff7a9a'], rim: '#ff6ac8', key: '#ff8ad0', practical: '#5ff2e8' }, night: { sky: ['#06061a', '#140f3a', '#2a1a5a'], rim: '#5ff2e8', practical: '#ff4fa3' }, interiorWarm: { rim: '#ff7ab8', practical: '#5ff2e8', wall: '#2a1e3a' }, day: { rim: '#7ff0ff' } },
  },
  storybook: {
    name: 'Soft Storybook', desc: 'Lighter pastel palette, lower contrast, lavender shadows, gentle paper grain — friendlier, family tone.',
    ink: '#1a1622', inkFar: '#4a4258', feature: '#fffaf0', rimWidth: 5, ui: { ...UI, card: 'rgba(40,36,60,.9)', accent: '#ff8a7a', gold: '#ffd98a' },
    grade: { contrast: 0.92, sat: 0.92, lift: [0.07, 0.055, 0.085], gamma: [1.12, 1.1, 1.06], gain: [1.06, 1.03, 0.98], vignette: 0.3, grain: 0.07, bloom: 0.45 },
    moods: { night: { sky: ['#2a2f5a', '#4a4f80', '#6a6aa0'], wall: '#3e4266' }, dusk: { sky: ['#6a5a90', '#c08aa8', '#f2b0a0', '#fbe0b8'] } },
  },
};
// Styles with their own drawing manner (engine/manner.js): the shapes themselves are drawn differently, not only re-graded.
const every = (m) => Object.fromEntries(Object.keys(BASE_MOODS).map((k) => [k, m]));
const NOGRADE = { contrast: 1.0, sat: 1.0, lift: [0, 0, 0], gamma: [1, 1, 1], gain: [1, 1, 1], vignette: 0.12, grain: 0, bloom: 0 };
Object.assign(STYLES, {
  doodle: {
    name: 'Doodle Notebook', desc: 'Hand-drawn marker doodle on paper: trembling ink lines that boil, flat pastel fills, no glow.',
    ink: '#1b1b1f', inkFar: '#4a4a52', feature: '#ffffff', rimWidth: 0, ui: { ...UI, card: '#fffaf0', cardLine: '#1b1b1f', text: '#1b1b1f', sub: '#55555c', accent: '#e8453c', gold: '#f2b632', cream: '#1b1b1f' },
    grade: NOGRADE,
    moods: every({ sky: ['#fbf7ee', '#f3ecdc'], ambient: '#d8d0bf', key: '#ffd76a', rim: '#1b1b1f', wall: '#f6c98a', floor: '#e6dcc6', dark: '#3a3a40', practical: '#ffe58a', grass: '#9ed38b', road: '#d9cfba', fog: '#d6e9f5' }),
    manner: { wobble: 2.2, boil: 8, outline: { color: '#1b1b1f', width: 3.2 }, flat: true, glow: false, paper: { color: '#f7f2e6', amount: 0.35 } },
  },
  ink: {
    name: 'Ink Monochrome', desc: 'Black ink on cream paper: four ink tones instead of colour, fine outlines, props in ink too.',
    ink: '#0d0c0b', inkFar: '#4f4b45', feature: '#f2efe8', rimWidth: 0, ui: { ...UI, card: '#f2efe8', cardLine: '#0d0c0b', text: '#0d0c0b', sub: '#4f4b45', accent: '#0d0c0b', gold: '#0d0c0b', cream: '#0d0c0b' },
    grade: { ...NOGRADE, sat: 0, contrast: 1.12 },
    moods: every({ sky: ['#f4f1ea', '#e9e4d9'], ambient: '#bdb8ae', key: '#f2efe8', rim: '#0d0c0b', wall: '#d9d4c9', floor: '#bdb8ae', dark: '#3a3733', practical: '#f2efe8', grass: '#9c978d', road: '#e2ddd2', fog: '#e9e4d9' }),
    manner: { wobble: 0.8, boil: 0, outline: { color: '#0d0c0b', width: 2.6 }, flat: true, glow: false, tones: ['#f2efe8', '#bdb8ae', '#6e6a64', '#0d0c0b'], imageFilter: 'grayscale(1) contrast(1.35)', paper: { color: '#efeae0', amount: 0.3 } },
  },
  cutout: {
    name: 'Paper Cut-out', desc: 'Flat coloured paper layers with hard cast shadows, as if cut from card and stacked; paper grain.',
    ink: '#2a1e18', inkFar: '#5a4636', feature: '#fff6e8', rimWidth: 0, ui: { ...UI, card: '#fff3dd', cardLine: '#2a1e18', text: '#2a1e18', sub: '#6a5444', accent: '#d9482b', gold: '#e8a92e', cream: '#2a1e18' },
    grade: { ...NOGRADE, sat: 1.05 },
    moods: every({ sky: ['#8fcbe0', '#c9e7ee'], ambient: '#a9c9cf', key: '#ffd27a', rim: '#fff6e8', wall: '#e8a94a', floor: '#8a6a45', dark: '#3a2a20', practical: '#ffe08a', grass: '#5fa84f', road: '#b89a76', fog: '#e9f4f4' }),
    manner: { flat: true, glow: false, shadow: { x: 6, y: 8, color: 'rgba(40,22,10,.32)' }, lineScale: 1.15, paper: { color: '#f1e6d2', amount: 0.45 } },
  },
  chalk: {
    name: 'Chalkboard', desc: 'White chalk on a green school board: outline drawing with faint fills, a chalk character, chalk dust.',
    ink: '#f3f1e7', inkFar: '#b9c2b8', feature: '#2b3a33', rimWidth: 0, ui: { ...UI, card: 'rgba(43,58,51,.9)', cardLine: '#f3f1e7', text: '#f3f1e7', sub: '#c6cfc5', accent: '#f6d76b', gold: '#f6d76b', cream: '#f3f1e7' },
    grade: { ...NOGRADE, sat: 0.7, vignette: 0.35 },
    moods: every({ sky: ['#2b3a33', '#26342e'], ambient: '#33443c', key: '#f6d76b', rim: '#f3f1e7', wall: '#e9e6da', floor: '#3a4b42', dark: '#1f2a25', practical: '#f6d76b', grass: '#cfe3c4', road: '#e9e6da', fog: '#e9e6da' }),
    manner: { wobble: 1.6, boil: 6, outline: { color: 'rgba(243,241,231,.92)', width: 3 }, flat: true, glow: false, fillAlpha: 0.2, tones: ['#2b3a33', '#cfe3c4', '#f3a6a0', '#f6d76b', '#f3f1e7'], imageFilter: 'grayscale(1) brightness(1.5) contrast(0.85)', paper: { color: '#ffffff', amount: 0.1, mode: 'overlay' } },
  },
});
export const STYLE_IDS = Object.keys(STYLES);
