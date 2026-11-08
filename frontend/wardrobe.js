// The pet's looks: swappable parts, original accessory art, and the drag-and-drop wardrobe (pointer events only)
const INK = "#3a2440";
const eye = (cx, body) => `<g class="eye">${body}</g>`;
const shine = (a, b) => `<g class="pupil-shine"><circle cx="${a}" cy="122" r="4.500" fill="#fff"/><circle cx="${b}" cy="134" r="2" fill="#fff"/></g>`;
const EYE_ART = {
  round: eye(74, `<ellipse cx="74" cy="128" rx="11" ry="14" fill="${INK}"/>${shine(78, 71)}`) +
         eye(126, `<ellipse cx="126" cy="128" rx="11" ry="14" fill="${INK}"/>${shine(130, 123)}`),
  sparkly: [74, 126].map((x) => eye(x, `<ellipse cx="${x}" cy="128" rx="13" ry="16" fill="${INK}"/><ellipse cx="${x}" cy="136" rx="9" ry="6" fill="#8d5bd6" opacity=".75"/>
    <g class="pupil-shine"><circle cx="${x + 5}" cy="120" r="5.500" fill="#fff"/><circle cx="${x - 5}" cy="133" r="3" fill="#fff"/><circle cx="${x + 4}" cy="136" r="1.800" fill="#fff"/></g>`)).join(""),
  sleepy: [74, 126].map((x) => eye(x, `<ellipse cx="${x}" cy="132" rx="11" ry="10" fill="${INK}"/><path d="M${x - 13} 127 q13 -6 26 0 v-9 h-26 z" fill="var(--pet-2)"/>
    <path d="M${x - 13} 127 q13 -6 26 0" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/><g class="pupil-shine"><circle cx="${x + 4}" cy="131" r="3" fill="#fff"/></g>`)).join(""),
  almond: [74, 126].map((x) => eye(x, `<path d="M${x - 15} 129 q15 -19 30 0 q-15 13 -30 0 z" fill="${INK}"/><g class="pupil-shine"><circle cx="${x + 4}" cy="125" r="4" fill="#fff"/></g>`)).join(""),
  button: [74, 126].map((x) => eye(x, `<circle cx="${x}" cy="129" r="7" fill="${INK}"/><g class="pupil-shine"><circle cx="${x + 2.500}" cy="126" r="2.200" fill="#fff"/></g>`)).join(""),
  lash: [[74, -1], [126, 1]].map(([x, d]) => eye(x, `<ellipse cx="${x}" cy="128" rx="11" ry="14" fill="${INK}"/>
    <path d="M${x + d * 10} 118 l${d * 7} -6 M${x + d * 12} 124 l${d * 8} -3 M${x + d * 5} 114 l${d * 4} -7" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>${shine(x + 4, x - 3)}`)).join(""),
};
const MOUTH_ART = { smile: "M90 156 q10 10 20 0", tiny: "M95 158 q5 5 10 0", cat: "M88 156 q6 8 12 0 q6 8 12 0", wide: "M84 154 q16 16 32 0" };
const CHEEK_ART = { oval: [13, 7], round: [9, 9], wide: [17, 6], tiny: [8, 4] };
const COLOR_ART = {
  pink: ["#ffe3e6", "#ffb8c6", "#f58fab", "#f7a1b6", "#ff7aa2"], peach: ["#fff0e0", "#ffcda8", "#f7a878", "#f9b78e", "#ff8d70"],
  lilac: ["#f3e8ff", "#d9bfff", "#b892ef", "#c6a6f3", "#ef7fc0"], mint: ["#e6fbf0", "#b4ecd0", "#7fd1ab", "#94dcba", "#ff8ea0"],
  sky: ["#e6f4ff", "#b6dcfb", "#84bdee", "#9acaf2", "#ff8fb1"], butter: ["#fff9dc", "#ffe9a0", "#f5cf6b", "#f8d983", "#ff9d7a"],
  berry: ["#ffd8ea", "#f08abc", "#c9568f", "#d96ea3", "#a82a6a"], pearl: ["#ffffff", "#ece6f2", "#cfc5de", "#dbd3e6", "#ffa8c0"],
};
const ACC_ART = {
  bow: `<path d="M128 60 l-16 -10 l2 18 z M128 60 l16 -12 l-1 20 z" fill="#c86bf0"/><circle cx="128" cy="60" r="5" fill="#a94fd6"/>`,
  flower: `<g fill="#ffd0e0"><circle cx="128" cy="52" r="6"/><circle cx="137" cy="59" r="6"/><circle cx="133" cy="69" r="6"/><circle cx="122" cy="69" r="6"/><circle cx="118" cy="59" r="6"/></g><circle cx="128" cy="61" r="5" fill="#ffc94d"/>`,
  towel: `<path d="M70 92 Q100 62 130 92 L136 104 Q100 76 64 104 Z" fill="#fff" stroke="#e8d8e4" stroke-width="2"/><path d="M84 84 q-6 -14 8 -16 q2 -12 16 -8 q14 -2 12 12 q8 6 2 14" fill="#fff" stroke="#e8d8e4" stroke-width="2"/>`,
  beret: `<ellipse cx="100" cy="52" rx="36" ry="13" fill="#b5476b" transform="rotate(-8 100 52)"/><ellipse cx="100" cy="58" rx="27" ry="6" fill="#8e3454" transform="rotate(-8 100 58)"/><circle cx="96" cy="38" r="3" fill="#8e3454"/>`,
  cat_ears: `<path d="M74 66 L66 34 L96 50 Z M126 66 L134 34 L104 50 Z" fill="var(--pet-3)"/><path d="M76 58 L72 42 L88 51 Z M124 58 L128 42 L112 51 Z" fill="#ffd3e0"/>`,
  bunny_ears: `<ellipse cx="82" cy="30" rx="10" ry="30" fill="var(--pet-3)" transform="rotate(-12 82 30)"/><ellipse cx="118" cy="30" rx="10" ry="30" fill="var(--pet-3)" transform="rotate(12 118 30)"/><ellipse cx="82" cy="32" rx="5" ry="21" fill="#ffd3e0" transform="rotate(-12 82 32)"/><ellipse cx="118" cy="32" rx="5" ry="21" fill="#ffd3e0" transform="rotate(12 118 32)"/>`,
  daisy_crown: [[70, 84], [82, 74], [94, 69], [106, 69], [118, 74], [130, 84]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="7" fill="#fff" stroke="#f2e3ea"/><circle cx="${x}" cy="${y}" r="3" fill="#ffc94d"/>`).join(""),
  sun_hat: `<ellipse cx="100" cy="66" rx="58" ry="13" fill="#f4dfae"/><path d="M68 64 Q70 28 100 26 Q130 28 132 64 Z" fill="#f8e8c2"/><path d="M68 58 Q100 68 132 58 L132 65 Q100 75 68 65 Z" fill="#e8638f"/>`,
  crown: `<path d="M80 38 l6 -16 l8 10 l6 -14 l6 14 l8 -10 l6 16 z" fill="url(#crownGrad)" stroke="#d99a2b" stroke-width="1.500"/><circle cx="100" cy="30" r="2.500" fill="#ff6fa0"/>`,
  round_glasses: `<g fill="#fff" fill-opacity=".16" stroke="#4a2c4f" stroke-width="3.500"><circle cx="74" cy="128" r="20"/><circle cx="126" cy="128" r="20"/></g><path d="M94 126 q6 -4 12 0" fill="none" stroke="#4a2c4f" stroke-width="3.500" stroke-linecap="round"/>`,
  heart_glasses: [74, 126].map((x) => `<path d="M${x} 150 l-20 -19 a11 11 0 0 1 20 -13 a11 11 0 0 1 20 13 z" fill="#ff5c8a" fill-opacity=".35" stroke="#e8638f" stroke-width="3.500" stroke-linejoin="round"/>`).join("") + `<path d="M94 126 h12" stroke="#e8638f" stroke-width="3.500" stroke-linecap="round"/>`,
  star_stickers: [[50, 118, 1], [150, 116, 1], [58, 170, .7]].map(([x, y, s]) => `<path transform="translate(${x} ${y}) scale(${s})" d="M0 -9 l2.600 6 l6.400 .7 l-4.800 4.300 l1.400 6.300 l-5.600 -3.300 l-5.600 3.300 l1.400 -6.300 l-4.800 -4.300 l6.400 -.7 z" fill="#ffd66b" stroke="#e8a92e"/>`).join(""),
  blush_hearts: [62, 138].map((x) => `<path d="M${x} 160 l-8 -8 a4.800 4.800 0 0 1 8 -5 a4.800 4.800 0 0 1 8 5 z" fill="#ff5c8a" opacity=".85"/>`).join(""),
  sheet_mask: `<path fill-rule="evenodd" fill="#fff" fill-opacity=".78" stroke="#ece0ea" d="M52 118 Q100 92 148 118 Q156 158 130 178 Q100 192 70 178 Q44 158 52 118 Z M74 112 a13 16 0 1 0 .1 0 Z M126 112 a13 16 0 1 0 .1 0 Z M86 152 h28 a6 8 0 0 1 0 16 h-28 a6 8 0 0 1 0 -16 Z"/>`,
  ribbon: `<path d="M56 180 Q100 198 144 180 L144 188 Q100 206 56 188 Z" fill="#e8638f"/><path d="M100 194 l-16 -9 v18 z M100 194 l16 -9 v18 z" fill="#c23a6f"/><circle cx="100" cy="194" r="4" fill="#fff"/>`,
  scarf: `<path d="M50 172 Q100 196 150 172 L152 186 Q100 210 48 186 Z" fill="#9f7bff"/><path d="M118 192 l20 -4 l6 30 l-20 3 z" fill="#8560e6"/><path d="M124 216 v6 M132 214 v6 M140 213 v6" stroke="#8560e6" stroke-width="2.500" stroke-linecap="round"/>`,
  bandana: `<path d="M56 176 Q100 192 144 176 L100 212 Z" fill="#ff8fb1"/><g fill="#fff"><circle cx="90" cy="190" r="2"/><circle cx="110" cy="190" r="2"/><circle cx="100" cy="200" r="2"/></g>`,
  pearls: Array.from({ length: 11 }, (_, i) => { const x = 58 + i * 8.400, y = 184 + 10 * Math.sin(Math.PI * i / 10); return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.500" fill="#fffaf4" stroke="#e3d6cd"/>`; }).join(""),
  cotton_pad: `<circle cx="172" cy="138" r="14" fill="#fff" stroke="#ece0ea" stroke-width="2"/><circle cx="172" cy="138" r="8" fill="none" stroke="#f3e8ee" stroke-width="2"/>`,
  mirror: `<rect x="168" y="150" width="6" height="26" rx="3" fill="#c86bf0"/><circle cx="171" cy="134" r="17" fill="#c86bf0"/><circle cx="171" cy="134" r="12" fill="#e8f6ff"/><path d="M164 130 l8 -6" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`,
  lipstick: `<rect x="163" y="146" width="16" height="24" rx="3" fill="#3a2440"/><rect x="165" y="132" width="12" height="16" fill="#e0b64f"/><path d="M166 132 V118 l10 -6 V132 Z" fill="#e8326f"/>`,
  serum: `<rect x="160" y="128" width="24" height="42" rx="5" fill="#f4e4d2" stroke="#dcc6ad" stroke-width="1.500"/><rect x="166" y="118" width="12" height="11" fill="#b08c63"/><rect x="169" y="106" width="6" height="13" rx="3" fill="#3a2440"/><rect x="164" y="142" width="16" height="14" rx="2" fill="#fff"/>`,
};
const SLOT_VIEW = { head: "48 8 104 104", face: "40 88 120 104", neck: "40 164 120 62", hand: "148 102 48 76" };
const wd = { catalog: null, tab: "accessories", drag: null };

function applyAppearance(a) {
  if (!a) return;
  const pet = $("pet"), [c1, c2, c3, arm, blush] = COLOR_ART[a.color] || COLOR_ART.pink;
  Object.entries({ "--pet-1": c1, "--pet-2": c2, "--pet-3": c3, "--pet-arm": arm, "--blush": blush })
    .forEach(([k, v]) => document.documentElement.style.setProperty(k, v));   // thumbnails use her colors too
  const eyes = pet.querySelector(".eyes-normal");
  if (eyes.dataset.set !== a.eyes) { eyes.innerHTML = EYE_ART[a.eyes] || EYE_ART.round; eyes.dataset.set = a.eyes; }
  pet.querySelector(".mouth-smile").setAttribute("d", MOUTH_ART[a.mouth] || MOUTH_ART.smile);
  const [rx, ry] = CHEEK_ART[a.cheeks] || CHEEK_ART.oval;
  pet.querySelectorAll(".cheek").forEach((c) => { c.setAttribute("rx", rx); c.setAttribute("ry", ry); });
  Object.entries(a.slots).forEach(([slot, id]) => {
    const g = $(`slot-${slot}`);
    if (g.dataset.item !== (id || "")) { g.innerHTML = id ? ACC_ART[id] : ""; g.dataset.item = id || ""; }
  });
}
const label = (entry) => entry[state.lang] || entry.en;
const entryKey = (entry) => (entry.slot === "head" || entry.slot === "face" || entry.slot === "neck" || entry.slot === "hand") ? entry.id : `${entry.slot}:${entry.id}`;
function isUnlocked(entry) {
  const p = state.petData;
  return p.level >= entry.level && (entry.price === 0 || p.owned.includes(entryKey(entry)));
}
function lockText(entry) { return entry.price ? `${entry.price}` : `${T("Lv", "Niv.")} ${entry.level}`; }
const thumb = (entry) => `<svg viewBox="${SLOT_VIEW[entry.slot]}" aria-hidden="true">${ACC_ART[entry.id]}</svg>`;

async function patchAppearance(patch) {
  try {
    const r = await fetch("/api/pet/appearance", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    if (!r.ok) throw new Error(r.status);
    renderPet(await r.json());
    return true;
  } catch (e) { console.warn(e); toast(T("That didn't save", "Ça n'a pas été enregistré")); return false; }
}
async function buyEntry(entry) {
  if (state.petData.level < entry.level) return toast(T(`Reach level ${entry.level} to unlock this`, `Atteins le niveau ${entry.level} pour débloquer ça`));
  if (state.petData.coins < entry.price) return toast(T(`You need ${entry.price} coins. Try the routine quest!`, `Il te faut ${entry.price} pièces. Essaie la routine !`));
  if (!confirm(T(`Unlock ${label(entry)} for ${entry.price} coins?`, `Débloquer ${label(entry)} pour ${entry.price} pièces ?`))) return;
  renderPet(await api("/api/pet/unlock", { id: entryKey(entry) }));
  sfxChime(); renderWardrobe();
}
function celebrateSnap() {
  const pet = $("pet");
  pet.classList.remove("snap"); void pet.getBoundingClientRect(); pet.classList.add("snap");
  setTimeout(() => pet.classList.remove("snap"), 500);
  sfxPop(); floaters(["sparkle"], 4);
}

// ---------- dragging ----------
function overPet(x, y) {
  const r = $("pet").getBoundingClientRect();
  return x > r.left && x < r.right && y > r.top && y < r.bottom;
}
function startDrag(ev, html, onDrop) {
  ev.preventDefault();
  wd.dragging = true;
  const ghost = document.createElement("div");
  ghost.className = "drag-ghost"; ghost.innerHTML = html;
  document.body.appendChild(ghost);
  const move = (e) => { ghost.style.transform = `translate(${e.clientX - 32}px, ${e.clientY - 32}px)`; $("pet").classList.toggle("drop-target", overPet(e.clientX, e.clientY)); };
  const end = (e) => {
    document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", end); document.removeEventListener("pointercancel", end);
    wd.dragging = false; ghost.remove(); $("pet").classList.remove("drop-target");
    if (e.type === "pointerup") onDrop(e.clientX, e.clientY);
  };
  move(ev);
  document.addEventListener("pointermove", move); document.addEventListener("pointerup", end); document.addEventListener("pointercancel", end);
}
// Touch: press and hold lifts the item, a quick swipe scrolls the drawer. A mouse drags straight away.
function pressItem(ev, entry) {
  if (!isUnlocked(entry)) return;
  if (ev.pointerType !== "touch") return dragItem(ev, entry);
  const tile = ev.currentTarget;
  const cancel = () => { clearTimeout(timer); tile.removeEventListener("pointermove", moved); tile.removeEventListener("pointerup", cancel); tile.removeEventListener("pointercancel", cancel); };
  const moved = (e) => { if (Math.hypot(e.clientX - ev.clientX, e.clientY - ev.clientY) > 8) cancel(); };
  const timer = setTimeout(() => { cancel(); navigator.vibrate?.(10); dragItem(ev, entry); }, 180);
  tile.addEventListener("pointermove", moved); tile.addEventListener("pointerup", cancel); tile.addEventListener("pointercancel", cancel);
}
function dragItem(ev, entry) {
  startDrag(ev, thumb(entry), async (x, y) => {
    if (!overPet(x, y)) return;
    if (await patchAppearance({ slots: { [entry.slot]: entry.id } })) { celebrateSnap(); renderWardrobe(); }
  });
}
function dragOffPet(ev, slot) {
  const id = $(`slot-${slot}`).dataset.item;
  if (!id) return;
  ev.stopPropagation();
  const entry = wd.catalog.items.find((i) => i.id === id);
  $(`slot-${slot}`).style.opacity = 0.3;
  startDrag(ev, thumb(entry), async (x, y) => {
    $(`slot-${slot}`).style.opacity = "";
    if (overPet(x, y)) return;
    if (await patchAppearance({ slots: { [slot]: null } })) { sfxBoop(); renderWardrobe(); }
  });
}

// ---------- drawer ----------
function tile(html, name, entry, active, onUse) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "tile" + (active ? " on" : "") + (isUnlocked(entry) ? "" : " locked");
  b.innerHTML = `<span class="tile-art">${html}</span><span class="tile-name"></span>`;
  b.querySelector(".tile-name").textContent = name;
  if (!isUnlocked(entry)) b.insertAdjacentHTML("beforeend", `<span class="tile-lock">${icon("lock", 12)}${lockText(entry)}</span>`);
  onUse(b);
  return b;
}
function renderWardrobe() {
  if (!wd.catalog || !state.petData) return;
  const a = state.petData.appearance, box = $("wardrobeBody");
  document.querySelectorAll("#wardrobeTabs button").forEach((t) => t.classList.toggle("on", t.dataset.tab === wd.tab));
  box.innerHTML = "";
  const grid = () => { const g = document.createElement("div"); g.className = "tile-grid"; box.appendChild(g); return g; };
  const heading = (en, fr) => { const h = document.createElement("h4"); h.textContent = T(en, fr); box.appendChild(h); };
  const tap = (entry, patch) => (b) => { b.onclick = async () => { if (!isUnlocked(entry)) return buyEntry(entry); if (await patchAppearance(patch)) { sfxPop(); renderWardrobe(); } }; };
  if (wd.tab === "accessories") {
    [["head", "Head", "Tête"], ["face", "Face", "Visage"], ["neck", "Neck", "Cou"], ["hand", "Hand", "Main"]].forEach(([slot, en, fr]) => {
      heading(en, fr);
      const g = grid();
      wd.catalog.items.filter((i) => i.slot === slot).forEach((i) => g.appendChild(tile(thumb(i), label(i), i, a.slots[slot] === i.id,
        (b) => { b.classList.add("draggable"); b.addEventListener("pointerdown", (e) => pressItem(e, i));
                 if (!isUnlocked(i)) b.onclick = () => buyEntry(i); })));
    });
    const hint = document.createElement("p"); hint.className = "hint";
    hint.textContent = T("Drag an item onto her. Drag it off to remove it.", "Glisse un objet sur elle. Retire-le en le faisant glisser dehors.");
    box.prepend(hint);
  } else if (wd.tab === "eyes") {
    heading("Eyes", "Yeux");
    const g = grid();
    wd.catalog.eyes.forEach((e) => g.appendChild(tile(`<svg viewBox="50 104 100 50" aria-hidden="true">${EYE_ART[e.id]}</svg>`, label(e), e, a.eyes === e.id, tap(e, { eyes: e.id }))));
    heading("Mouth", "Bouche");
    const m = grid();
    wd.catalog.mouth.forEach((e) => m.appendChild(tile(`<svg viewBox="76 146 48 24" aria-hidden="true"><path d="${MOUTH_ART[e.id]}" fill="none" stroke="${INK}" stroke-width="4" stroke-linecap="round"/></svg>`, label(e), e, a.mouth === e.id, tap(e, { mouth: e.id }))));
    heading("Cheeks", "Joues");
    const c = grid();
    wd.catalog.cheeks.forEach((e) => c.appendChild(tile(`<svg viewBox="-20 -12 40 24" aria-hidden="true"><ellipse rx="${CHEEK_ART[e.id][0]}" ry="${CHEEK_ART[e.id][1]}" fill="var(--blush)" opacity=".6"/></svg>`, label(e), e, a.cheeks === e.id, tap(e, { cheeks: e.id }))));
  } else if (wd.tab === "colors") {
    heading("Body color", "Couleur");
    const g = grid();
    wd.catalog.color.forEach((e) => { const [c1, c2, c3] = COLOR_ART[e.id];
      g.appendChild(tile(`<span class="swatch" style="background:radial-gradient(circle at 40% 35%, ${c1}, ${c2} 55%, ${c3})"></span>`, label(e), e, a.color === e.id, tap(e, { color: e.id }))); });
  } else renderVoiceTab(box, a);
}
function renderVoiceTab(box, a) {
  const current = a.voice;
  const row = (name, value, note) => {
    const d = document.createElement("div"); d.className = "voice-row" + (current === value ? " on" : "");
    const title = document.createElement("button"); title.type = "button"; title.className = "voice-name";
    title.textContent = name; title.title = note || "";
    title.onclick = async () => { if (await patchAppearance({ voice: value })) { sound.voices = {}; think.url = null; loadThinkSound(); renderWardrobe(); } };
    const play = document.createElement("button"); play.type = "button"; play.className = "icon-btn small";
    play.innerHTML = icon("play", 16); play.title = T("Play sample", "Écouter"); play.setAttribute("aria-label", play.title);
    play.onclick = () => sampleVoice(value, play);
    d.append(title, play); box.appendChild(d);
  };
  const h = (en, fr) => { const e = document.createElement("h4"); e.textContent = T(en, fr); box.appendChild(e); };
  row(T("Default voice", "Voix par défaut"), null);
  h("Orpheus (English, limited per day)", "Orpheus (anglais, limité par jour)");
  wd.catalog.orpheus_voices.forEach((v) => row(v[0].toUpperCase() + v.slice(1), v));
  h("Kokoro (local)", "Kokoro (local)");
  wd.catalog.kokoro_voices.forEach((v) => row(v.replaceAll("af_", "").replaceAll(":50", "").replaceAll(":60", "").replaceAll(":40", "").replace(",", " + "), v));
  const slider = (en, fr, field, min, max, step, fallback) => {
    const l = document.createElement("label"); l.className = "slider";
    const out = document.createElement("b"); const value = a[field] ?? fallback; out.textContent = (+value).toFixed(2);
    l.append(T(en, fr), out);
    const i = document.createElement("input"); i.type = "range"; i.min = min; i.max = max; i.step = step; i.value = value;
    i.oninput = () => { out.textContent = (+i.value).toFixed(2); };
    i.onchange = async () => { await patchAppearance({ [field]: +i.value }); };
    l.appendChild(i); box.appendChild(l);
  };
  slider("Pitch", "Hauteur", "pitch", 1, 1.4, 0.01, state.cfg.tts_rate);
  slider("Speed (Kokoro only)", "Vitesse (Kokoro seulement)", "speed", 0.7, 1.3, 0.01, 1);
}
async function sampleVoice(voice, btn) {
  btn.disabled = true;
  const isOrpheus = wd.catalog.orpheus_voices.includes(voice);
  const name = state.petData.user_name ? `, ${state.petData.user_name}` : "";
  try {
    const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      text: T(`Hi${name}! This is how I sound.`, `Coucou${name} ! Voilà ma voix.`), lang: state.lang, voice: voice || undefined,
      engine: voice ? (isOrpheus ? "groq" : "kokoro") : undefined, speed: state.petData.appearance.speed || undefined }) });
    if (!r.ok) throw new Error(r.status);
    shutUp();
    await playBlob(await r.blob());
    stopTalking();
  } catch (e) { console.warn(e); toast(T("Couldn't play that voice", "Impossible de jouer cette voix")); }
  btn.disabled = false;
}
function randomize() {
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  const open = (list) => list.filter(isUnlocked);
  const slots = {};
  ["head", "face", "neck", "hand"].forEach((s) => {
    const items = open(wd.catalog.items.filter((i) => i.slot === s));
    slots[s] = Math.random() < 0.6 && items.length ? pick(items).id : null;
  });
  patchAppearance({ color: pick(open(wd.catalog.color)).id, eyes: pick(open(wd.catalog.eyes)).id, mouth: pick(open(wd.catalog.mouth)).id,
    cheeks: pick(open(wd.catalog.cheeks)).id, slots }).then((ok) => { if (ok) { celebrateSnap(); renderWardrobe(); } });
}
function resetLook() {
  patchAppearance({ color: "pink", eyes: "round", mouth: "smile", cheeks: "oval", slots: { head: null, face: null, neck: null, hand: null } })
    .then((ok) => { if (ok) { sfxBoop(); renderWardrobe(); } });
}
function showWardrobe(open) {   // on phones the pet moves up, so there's always somewhere to drop things
  $("wardrobe").classList.toggle("hidden", !open);
  document.body.classList.toggle("wardrobe-open", open);
}
async function initWardrobe() {
  wd.catalog = await api("/api/wardrobe");
  $("wardrobeBtn").addEventListener("click", () => { showWardrobe($("wardrobe").classList.contains("hidden")); $("soundPanel").classList.add("hidden"); renderWardrobe(); });
  $("wardrobeClose").addEventListener("click", () => showWardrobe(false));
  document.addEventListener("touchmove", (e) => { if (wd.dragging) e.preventDefault(); }, { passive: false });
  document.querySelectorAll("#wardrobeTabs button").forEach((t) => t.addEventListener("click", () => { wd.tab = t.dataset.tab; renderWardrobe(); }));
  $("randomizeBtn").addEventListener("click", randomize);
  $("resetBtn").addEventListener("click", resetLook);
  ["head", "face", "neck", "hand"].forEach((s) => $(`slot-${s}`).addEventListener("pointerdown", (e) => dragOffPet(e, s)));
}
