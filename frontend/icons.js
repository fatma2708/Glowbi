// One icon style everywhere: 24px grid, 1.75px stroke, rounded caps. Floaters are small filled shapes.
const ICONS = {
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>',
  send: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  speakerOn: '<path d="M4 10v4h3l5 4V6L7 10z"/><path d="M16 9.5a3.5 3.5 0 0 1 0 5"/><path d="M18.5 7a7 7 0 0 1 0 10"/>',
  speakerOff: '<path d="M4 10v4h3l5 4V6L7 10z"/><path d="m16 10 4 4"/><path d="m20 10-4 4"/>',
  chat: '<path d="M20 11.5a7.5 7.5 0 0 1-11 6.6L4 20l1.9-5A7.5 7.5 0 1 1 20 11.5z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>',
  heart: '<path d="M12 20s-7.5-4.6-8.7-9.4C2.5 7.300 4.700 5 7.300 5c1.900 0 3.500 1 4.700 2.800C13.200 6 14.800 5 16.700 5c2.600 0 4.800 2.300 4 5.600C19.500 15.400 12 20 12 20z"/>',
  sparkle: '<path d="M12 4l1.900 5.100L19 11l-5.100 1.900L12 18l-1.900-5.100L5 11l5.100-1.900z"/>',
  bottle: '<path d="M10 3h4v4l2 3v9a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-9l2-3z"/><path d="M8 13h8"/>',
  hanger: '<path d="M12 8V7a2 2 0 1 0-2-2"/><path d="M12 8 3 15a1.500 1.500 0 0 0 1 3h16a1.500 1.500 0 0 0 1-3z"/>',
  drop: '<path d="M12 3s7 7 7 12a7 7 0 0 1-14 0c0-5 7-12 7-12z"/>',
  note: '<path d="M9 18V6l10-2v12"/><circle cx="6.500" cy="18" r="2.500"/><circle cx="16.500" cy="16" r="2.500"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  play: '<path d="M8 5.500v13l10-6.500z"/>',
  close: '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
  shuffle: '<path d="M3 7h3c4 0 6 10 10 10h5"/><path d="M3 17h3c1.500 0 2.700-1.400 3.800-3"/><path d="M14 9c.8-1.200 1.700-2 3-2h4"/><path d="m18 4 3 3-3 3"/><path d="m18 14 3 3-3 3"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14.300-4L4 9"/><path d="M4 4v5h5"/><path d="M4 13a8 8 0 0 0 14.300 4L20 15"/><path d="M20 20v-5h-5"/>',
};

const FLOATER_SHAPES = {
  heart: '<path d="M12 21C5 15.500 2 12 2 8.200 2 5.300 4.300 3 7.200 3c1.900 0 3.700 1 4.800 2.700C13.100 4 14.900 3 16.800 3 19.700 3 22 5.300 22 8.200 22 12 19 15.500 12 21z"/>',
  sparkle: '<path d="M12 2l2.400 7.600L22 12l-7.600 2.400L12 22l-2.400-7.600L2 12l7.600-2.400z"/>',
  dot: '<circle cx="12" cy="12" r="7"/>',
};
const FLOATER_COLORS = ["#ff8fb1", "#e8638f", "#c9a7ff", "#ffc2d6"];

function icon(name, size = 20) {
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
}

function floaterShape(kind) {
  const color = FLOATER_COLORS[Math.floor(Math.random() * FLOATER_COLORS.length)];
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="${color}" aria-hidden="true">${FLOATER_SHAPES[kind]}</svg>`;
}
