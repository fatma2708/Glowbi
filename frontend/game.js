// Play: tap, tickle, idle sounds, and the skincare routine quest. Pointer events only, so touch works too.
const play2 = { meter: 0, down: false, moved: 0, lastX: 0, lastY: 0, lastT: 0, zone: "belly", lastGiggle: 0, overload: 0, cooldown: 0, raf: 0, tickled: false };
const TICKLE_LINES = {
  head: { en: ["Hehe, not my head!", "That tickles my dewdrop tip!"], fr: ["Hihi, pas ma tête !", "Ça chatouille ma petite pointe !"] },
  belly: { en: ["Hihi, my tummy!", "Stop, stop, hehehe!"], fr: ["Hihi, mon ventre !", "Arrête, arrête, hihihi !"] },
};
const GIVE_UP = { en: "Okay okay, I give up!", fr: "D'accord, d'accord, j'abandonne !" };

function tapPet() {
  play("squish"); setEmotion("giggle", 1200); sfxBoop(); voiceSound("hehe"); floaters(["heart", "dot"], 3);
  if (state.onboarding) { speak(state.onboarding.question); return; }   // tap = repeat the question
  const lines = POKE_LINES[state.lang];
  showBubble(lines[Math.floor(Math.random() * lines.length)]);
  api("/api/pet/poke", {}).then(renderPet).catch(() => {});
}
function setMeter(v) {
  play2.meter = Math.max(0, Math.min(1, v));
  $("tickleFill").style.width = play2.meter * 100 + "%";
  $("tickleMeter").classList.toggle("hidden", play2.meter < 0.02);
  $("pet").style.setProperty("--wiggle", `${2 + play2.meter * 7}deg`);
  $("pet").classList.toggle("deep-blush", play2.meter > 0.5);
}
function giggle() {
  const now = performance.now();
  if (now - play2.lastGiggle < (play2.meter > 0.7 ? 1500 : 900)) return;
  play2.lastGiggle = now;
  voiceSound(play2.meter < 0.35 ? "hihi" : play2.meter < 0.75 ? "hehehe" : "breathless");
  floaters(["heart"], play2.meter > 0.6 ? 3 : 1);
}
function tickleLoop() {
  if (play2.down && play2.tickled) {
    if (play2.meter >= 1) play2.overload += 16; else play2.overload = 0;
    if (play2.overload > 1200) return giveUp();
  } else {
    setMeter(play2.meter - 0.012);
    if (play2.meter <= 0) { endTickle(); return; }
  }
  play2.raf = requestAnimationFrame(tickleLoop);
}
function giveUp() {
  endTickle();
  play2.cooldown = performance.now() + 1500;
  const pet = $("pet");
  pet.classList.add("squirm"); setTimeout(() => pet.classList.remove("squirm"), 1000);
  setEmotion("giggle", 1400); showBubble(GIVE_UP[state.lang]); speak(GIVE_UP[state.lang]);
}
function endTickle() {
  cancelAnimationFrame(play2.raf); play2.raf = 0; play2.down = false; play2.overload = 0;
  const was = play2.tickled;
  play2.tickled = false; setMeter(0);
  $("pet").classList.remove("tickling");
  if (was && !state.busy) setEmotion(state.baseEmotion);
  if (was) api("/api/pet/tickle", {}).then((r) => renderPet(r.pet)).catch(() => {});
}
function initTickle() {
  const wrap = $("petWrap");
  wrap.addEventListener("pointerdown", (e) => {
    if (state.busy || rec.active || routine.active || performance.now() < play2.cooldown) return;
    wrap.setPointerCapture(e.pointerId);
    const r = $("pet").getBoundingClientRect();
    Object.assign(play2, { down: true, moved: 0, lastX: e.clientX, lastY: e.clientY, lastT: performance.now(),
      zone: (e.clientY - r.top) / r.height < 0.42 ? "head" : "belly" });
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!play2.down) return;
    const now = performance.now(), d = Math.hypot(e.clientX - play2.lastX, e.clientY - play2.lastY), dt = Math.max(1, now - play2.lastT);
    Object.assign(play2, { lastX: e.clientX, lastY: e.clientY, lastT: now });
    play2.moved += d;
    if (play2.moved < 14) return;
    if (!play2.tickled) {
      play2.tickled = true; $("pet").classList.add("tickling"); setEmotion("giggle");
      const lines = TICKLE_LINES[play2.zone][state.lang];
      showBubble(lines[Math.floor(Math.random() * lines.length)]);
      play2.raf = requestAnimationFrame(tickleLoop);
    }
    setMeter(play2.meter + Math.min(2, d / dt) * (play2.zone === "belly" ? 0.012 : 0.008));
    giggle();
  });
  const up = () => {
    if (!play2.down) return;
    play2.down = false;
    if (!play2.tickled && play2.moved < 14) tapPet();
  };
  wrap.addEventListener("pointerup", up);
  wrap.addEventListener("pointercancel", up);
}

// ---------- idle sounds: at most one every ~45 s, never while you're talking or typing ----------
function initIdle() {
  let lastSound = performance.now();
  setInterval(() => {
    const quiet = !state.busy && !rec.active && !routine.active && !play2.down && !$("pet").classList.contains("talking") && !$("msg").value;
    if (!quiet || performance.now() - lastSound < 45000 || Math.random() > 0.35) return;
    lastSound = performance.now();
    const kind = ["hihi", "mmh", "yawn"][Math.floor(Math.random() * 3)];
    voiceSound(kind);
    if (kind === "yawn") setEmotion("sleepy", 2200);
  }, 5000);
}

// ---------- routine quest ----------
const routine = { active: false, plan: null, next: 0, mode: "morning" };
const bottle = (cap, body) => `<svg viewBox="0 0 48 64" aria-hidden="true"><rect x="16" y="4" width="16" height="12" rx="3" fill="${cap}"/><rect x="9" y="15" width="30" height="45" rx="7" fill="${body}"/><rect x="14" y="30" width="20" height="16" rx="3" fill="#fff" opacity=".85"/></svg>`;
const tube = (cap, body) => `<svg viewBox="0 0 48 64" aria-hidden="true"><path d="M11 6 h26 l-4 40 h-18 z" fill="${body}"/><rect x="15" y="45" width="18" height="14" rx="3" fill="${cap}"/><rect x="16" y="16" width="16" height="14" rx="3" fill="#fff" opacity=".85"/></svg>`;
const jar = (cap, body) => `<svg viewBox="0 0 48 64" aria-hidden="true"><rect x="7" y="20" width="34" height="11" rx="4" fill="${cap}"/><rect x="9" y="30" width="30" height="26" rx="6" fill="${body}"/><rect x="15" y="37" width="18" height="12" rx="3" fill="#fff" opacity=".85"/></svg>`;
const dropper = (cap, body) => `<svg viewBox="0 0 48 64" aria-hidden="true"><rect x="20" y="3" width="8" height="12" rx="4" fill="#3a2440"/><rect x="17" y="14" width="14" height="8" fill="${cap}"/><rect x="11" y="22" width="26" height="38" rx="6" fill="${body}"/><rect x="16" y="34" width="16" height="14" rx="3" fill="#fff" opacity=".85"/></svg>`;
const PRODUCT_ART = {
  cleanser: tube("#7ec4e8", "#c9e8f7"), toner: bottle("#b892ef", "#e4d6fb"), serum: dropper("#c49a6c", "#f4e4d2"),
  eye_cream: jar("#e8a4c0", "#fbe2ec"), moisturizer: jar("#7fd1ab", "#d0f2e0"), sunscreen: tube("#f5b84b", "#ffe9b8"),
  retinol: dropper("#7a5bd0", "#d9cdf7"), oil_cleanser: bottle("#e0b64f", "#fbeec2"),
};
async function openRoutine(mode = routine.mode) {
  if (state.busy || state.onboarding) return;
  shutUp();
  routine.mode = mode;
  routine.plan = await api(`/api/routine?mode=${mode}&lang=${state.lang}`);
  Object.assign(routine, { active: true, next: 0 });
  showWardrobe(false); $("soundPanel").classList.add("hidden");
  $("routineBar").classList.remove("hidden"); $("chatForm").classList.add("hidden");
  $("fxTowel").innerHTML = ACC_ART.towel; $("slot-head").style.display = "none"; $("fxGloss").classList.remove("on");
  document.querySelectorAll("#routineModes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  renderRoutineProducts();
  showBubble(T(mode === "morning" ? "Good morning! Help me with my routine: drag each product onto my face, in the right order."
                                  : "Bedtime! Help me with my routine: drag each product onto my face, in the right order.",
               mode === "morning" ? "Bonjour ! Aide-moi pour ma routine : glisse chaque produit sur mon visage, dans le bon ordre."
                                  : "C'est l'heure ! Aide-moi pour ma routine : glisse chaque produit sur mon visage, dans le bon ordre."));
}
function renderRoutineProducts() {
  const row = $("routineProducts"); row.innerHTML = "";
  routine.plan.products.forEach((p) => {
    const b = document.createElement("button");
    const done = routine.plan.steps.slice(0, routine.next).some((s) => s.id === p.id);
    b.type = "button"; b.className = "product" + (done ? " used" : ""); b.dataset.id = p.id;
    b.innerHTML = `${PRODUCT_ART[p.id]}<span></span>`; b.querySelector("span").textContent = p.label;
    if (!done) b.addEventListener("pointerdown", (e) => startDrag(e, PRODUCT_ART[p.id], (x, y) => { if (overPet(x, y)) applyProduct(p.id); }));
    row.appendChild(b);
  });
  $("routineProgress").textContent = `${routine.next} / ${routine.plan.steps.length}`;
}
function faceEffect(id) {
  if (id === "cleanser" || id === "oil_cleanser") {
    $("fxFoam").classList.add("on"); setTimeout(() => $("fxFoam").classList.remove("on"), 1600);
  }
  if (id === "moisturizer" || id === "sunscreen") $("fxGloss").classList.add("on");
}
function applyProduct(id) {
  const step = routine.plan.steps[routine.next];
  if (id !== step.id) {
    const name = routine.plan.products.find((p) => p.id === step.id).label;
    setEmotion("giggle", 1500); voiceSound("hihi");
    showBubble(routine.plan.wrong[id] || routine.plan.wrong_order.replace("{next}", name));
    return;
  }
  routine.next++;
  faceEffect(id); setEmotion("love", 1500); play("squish"); sfxPop(); voiceSound("ooh"); floaters(["sparkle", "dot"], 3);
  showBubble(step.tip);
  renderRoutineProducts();
  if (routine.next === routine.plan.steps.length) setTimeout(finishRoutine, 1800);
}
async function finishRoutine() {
  const r = await api("/api/routine/complete", { mode: routine.mode });
  renderPet(r.pet); setEmotion("excited", 2500); play("jump"); sfxChime(); voiceSound("yay"); floaters(["heart", "sparkle"], 8);
  if (r.leveled_up) toast(T(`Level up! Level ${r.pet.level}`, `Niveau ${r.pet.level} !`), 4000);
  showBubble(r.already_done
    ? T("All done! You already earned today's reward for this routine.", "Terminé ! Tu as déjà gagné la récompense du jour pour cette routine.")
    : T(`All done! +${r.coins} coins, and a ${r.streak}-day streak. Did you do your own routine today?`,
        `Terminé ! +${r.coins} pièces, et ${r.streak} jour(s) de suite. Tu as fait ta routine aujourd'hui ?`));
  if (r.already_done) return;
  const chips = $("chips");
  [[T("Yes!", "Oui !"), () => { closeRoutine(); showBubble(T("Proud of you!", "Fière de toi !")); setEmotion("love", 2000); }],
   [T("Not yet", "Pas encore"), () => { closeRoutine();
     send(T(`Suggest a simple ${routine.mode} skincare routine for me, based on my profile.`, `Propose-moi une routine simple pour ${routine.mode === "morning" ? "le matin" : "le soir"}, selon mon profil.`)); }]]
    .forEach(([text, fn]) => { const b = document.createElement("button"); b.className = "chip"; b.textContent = text; b.onclick = fn; chips.appendChild(b); });
}
function closeRoutine() {
  routine.active = false;
  $("routineBar").classList.add("hidden"); $("chatForm").classList.remove("hidden");
  $("fxTowel").innerHTML = ""; $("slot-head").style.display = ""; $("fxGloss").classList.remove("on"); $("fxFoam").classList.remove("on");
}
function initRoutine() {
  $("routineBtn").addEventListener("click", () => openRoutine());
  $("routineClose").addEventListener("click", closeRoutine);
  document.querySelectorAll("#routineModes button").forEach((b) => b.addEventListener("click", () => openRoutine(b.dataset.mode)));
}

// ---------- sound panel ----------
async function initSoundPanel() {
  const tracks = await api("/api/music").catch(() => []);
  const select = $("musicTrack");
  tracks.forEach((t) => { const o = document.createElement("option"); o.value = t; o.textContent = t.replace(/\.\w+$/, ""); select.appendChild(o); });
  const save = (patch) => { applySoundSettings(patch); api("/api/pet/settings", patch).catch(() => {}); };
  $("soundBtn").addEventListener("click", () => { $("soundPanel").classList.toggle("hidden"); showWardrobe(false); });
  $("musicOn").addEventListener("change", (e) => save({ music_on: e.target.checked }));
  $("musicVolume").addEventListener("input", (e) => applySoundSettings({ music_volume: +e.target.value }));
  $("musicVolume").addEventListener("change", (e) => save({ music_volume: +e.target.value }));
  $("sfxVolume").addEventListener("input", (e) => applySoundSettings({ sfx_volume: +e.target.value }));
  $("sfxVolume").addEventListener("change", (e) => { save({ sfx_volume: +e.target.value }); sfxBoop(); });
  select.addEventListener("change", (e) => { save({ music_track: e.target.value }); if (sound.ctx) startMusic(); });
}
function renderSoundPanel(s) {
  $("musicOn").checked = s.music_on; $("musicVolume").value = s.music_volume; $("sfxVolume").value = s.sfx_volume;
  if ([...$("musicTrack").options].some((o) => o.value === s.music_track)) $("musicTrack").value = s.music_track;
}
function initGame() { initTickle(); initIdle(); initRoutine(); initSoundPanel().then(() => renderSoundPanel(state.petData.settings)); }
