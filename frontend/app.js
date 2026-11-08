// Glowbi front-end: animations, speech-to-text, text-to-speech, onboarding, chat
const $ = (id) => document.getElementById(id);
const pet = $("pet");
document.querySelectorAll("[data-icon]").forEach((el) =>
  el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon, +el.dataset.size || 20)));
const state = {
  lang: localStorage.getItem("glowbi-lang") || "en",
  voice: localStorage.getItem("glowbi-voice") !== "off",
  busy: false, baseEmotion: "happy", petData: null,
  onboarding: null,          // current onboarding step, or null when chatting normally
  multi: new Set(),          // selected chips for multi-choice steps
  cfg: { stt_mode: "auto", server_stt: false, tts_engine: "kokoro", tts_rate: 1.12 },
  userGestured: false, pendingSpeech: null,
};
const T = (en, fr) => (state.lang === "fr" ? fr : en);

const POKE_LINES = {
  en: ["Hehe, that tickles!", "Boop!", "Did you drink water today?", "SPF is my love language",
       "Squishy squish!", "You're glowing today", "Hey! I'm dewy, not a stress ball!", "Ask me anything pretty"],
  fr: ["Hihi, ça chatouille !", "Boop !", "Tu as bu de l'eau aujourd'hui ?", "La crème solaire, c'est la vie",
       "Squish squish !", "Tu rayonnes aujourd'hui", "Hé ! Je suis une goutte, pas une balle anti-stress !", "Pose-moi une question beauté"],
};

// ================= expressions =================
function setEmotion(e, ms) {
  pet.dataset.emotion = e;
  if (ms) setTimeout(() => { if (!state.busy) pet.dataset.emotion = state.baseEmotion; }, ms);
}
function play(cls) { pet.classList.remove(cls); void pet.offsetWidth; pet.classList.add(cls);
  setTimeout(() => pet.classList.remove(cls), 1000); }
function floaters(kinds, n = 5) {
  for (let i = 0; i < n; i++) {
    const f = document.createElement("span");
    f.className = "floater"; f.innerHTML = floaterShape(kinds[Math.floor(Math.random() * kinds.length)]);
    f.style.left = 25 + Math.random() * 50 + "%"; f.style.top = 20 + Math.random() * 30 + "%";
    f.style.animationDelay = i * 0.12 + "s";
    $("floaters").appendChild(f); setTimeout(() => f.remove(), 2200);
  }
}
(function blinkLoop() {
  setTimeout(() => { pet.classList.add("blink"); setTimeout(() => pet.classList.remove("blink"), 130); blinkLoop(); },
             2500 + Math.random() * 3000);
})();
document.addEventListener("pointermove", (ev) => {
  const r = pet.getBoundingClientRect();
  const dx = Math.max(-1, Math.min(1, (ev.clientX - (r.left + r.width / 2)) / 300));
  const dy = Math.max(-1, Math.min(1, (ev.clientY - (r.top + r.height * 0.55)) / 300));
  if (pet.dataset.emotion !== "thinking")
    document.querySelectorAll(".pupil-shine").forEach((p) => (p.style.transform = `translate(${dx * 3}px, ${dy * 3}px)`));
});

// ================= stats =================
function renderPet(p) {
  if (!p) return;
  state.petData = p;
  $("lvl").textContent = p.level;
  $("coins").textContent = p.coins;
  applyAppearance(p.appearance);
  applySoundSettings(p.settings);
  if (p.pet_name !== document.title) { document.title = p.pet_name; renderLang(); }
  $("xpBar").style.width = p.xp_in_level + "%";
  $("happyBar").style.width = p.happiness + "%";
  pet.classList.toggle("has-sparkles", p.accessories.includes("sparkles"));
  state.baseEmotion = p.mood === "sad" ? "sad" : "happy";
  if (!state.busy && !pet.classList.contains("talking")) pet.dataset.emotion = state.baseEmotion;
}
const api = async (url, body) => {
  const r = await fetch(url, body === undefined ? {} : { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};

// ================= bubble / UI =================
function escapeHtml(s) { return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function showBubble(text) {
  $("bubble").classList.remove("hidden");
  $("bubbleText").textContent = text;
  $("chips").innerHTML = "";
  $("bubble").style.animation = "none"; void $("bubble").offsetWidth; $("bubble").style.animation = "";
}
function renderProducts(list) {
  const box = $("productCards"); box.innerHTML = "";
  box.classList.toggle("hidden", !list?.length);
  (list || []).forEach((p) => {
    const card = document.createElement("article"); card.className = "pcard";
    const art = document.createElement("div"); art.className = "pcard-art"; art.innerHTML = icon("bottle", 32);
    if (p.image_url) {
      const img = new Image(); img.alt = ""; img.referrerPolicy = "no-referrer";
      img.onload = () => art.replaceChildren(img);
      img.src = p.image_url;
    }
    const brand = document.createElement("p"); brand.className = "pcard-brand"; brand.textContent = p.brand;
    const name = document.createElement("p"); name.className = "pcard-name"; name.textContent = p.name; name.title = p.why || "";
    const links = document.createElement("div"); links.className = "pcard-links";
    [[p.url, T("View", "Voir")], [p.buy_url, T("Find it", "Trouver")]].forEach(([href, text]) => {
      const a = document.createElement("a"); a.href = href; a.textContent = text; a.target = "_blank"; a.rel = "noopener noreferrer"; links.appendChild(a); });
    card.append(art, brand, name);
    if (p.check_label) { const n = document.createElement("p"); n.className = "pcard-note"; n.textContent = T("Check the label", "Vérifie l'étiquette"); card.appendChild(n); }
    card.appendChild(links); box.appendChild(card);
  });
}
function renderCheck(c) {
  const box = $("checkCard"); box.innerHTML = "";
  box.classList.toggle("hidden", !c);
  if (!c) return;
  const v = c.verdict_for_me;
  const head = document.createElement("header"); head.className = `check-head ${v.level}`;
  head.textContent = { green: T("Fine for you", "Bien pour toi"), amber: T("Good to know", "Bon à savoir"), red: T("Avoid for you", "À éviter pour toi") }[v.level];
  box.appendChild(head);
  if (c.product) { const p = document.createElement("p"); p.className = "check-product"; p.textContent = c.product; box.appendChild(p); }
  c.flags.forEach((f) => {
    const d = document.createElement("details"); d.className = `check-flag ${f.severity === "info" ? "green" : f.severity}`;
    const s = document.createElement("summary"); const dot = document.createElement("span"); dot.className = "dot";
    const name = document.createElement("span"); name.className = "check-name"; name.textContent = f.ingredient;
    const tag = document.createElement("span"); tag.className = "check-tag"; tag.textContent = f.label;
    s.append(dot, name, tag);
    const body = document.createElement("p"); body.textContent = f.explanation;
    d.append(s, body); box.appendChild(d);
  });
  const foot = document.createElement("p"); foot.className = "check-foot";
  const clean = c.ingredients.length - new Set(c.flags.map((f) => f.ingredient)).size;
  foot.textContent = T(`${c.ingredients.length} ingredients read, ${Math.max(0, clean)} with nothing to flag`, `${c.ingredients.length} ingrédients lus, ${Math.max(0, clean)} sans remarque`) +
    (c.eu_checked < c.eu_total ? T(`. EU check: ${c.eu_checked} of ${c.eu_total} so far.`, `. Contrôle UE : ${c.eu_checked} sur ${c.eu_total} pour l'instant.`) : "");
  box.appendChild(foot);
}
function showTyping() { $("bubble").classList.remove("hidden"); $("chips").innerHTML = "";
  $("bubbleText").innerHTML = '<span class="typing"><span></span><span></span><span></span></span>'; }
function toast(t, ms = 2600) { const el = $("toast"); el.textContent = t; el.classList.remove("hidden");
  clearTimeout(el._t); el._t = setTimeout(() => el.classList.add("hidden"), ms); }
function log(who, text) { const d = document.createElement("div"); d.className = "msg " + who; d.textContent = text;
  $("logList").appendChild(d); $("logList").scrollTop = 1e9; }
function heard(text, final = false) {
  $("heard").classList.remove("hidden"); $("heard").classList.toggle("final", final);
  $("heardText").textContent = text;
  clearTimeout(heard._t); if (final) heard._t = setTimeout(() => $("heard").classList.add("hidden"), 3500);
}
function hideHeard() { $("heard").classList.add("hidden"); }

// ================= text to speech (Glowbi's voice) =================
// Server voice first, one sentence at a time so she starts quickly. Browser speechSynthesis is the fallback.
const tts = { audio: null, ctx: null, analyser: null, buf: null, run: 0, abort: null, finish: null, raf: 0 };
let mouthTimer = null;
function startTalking() { pet.classList.add("talking"); clearInterval(mouthTimer);
  mouthTimer = setInterval(() => pet.classList.toggle("mouth-on"), 140); }
function stopTalking() { clearInterval(mouthTimer); cancelAnimationFrame(tts.raf); pet.classList.remove("talking", "mouth-on"); }
function ttsAudio() {
  if (tts.audio) return tts.audio;
  const a = (tts.audio = new Audio());
  a.preservesPitch = a.mozPreservesPitch = a.webkitPreservesPitch = false;   // the cute lift
  try {
    tts.ctx = new AudioContext();
    tts.analyser = tts.ctx.createAnalyser();
    tts.analyser.fftSize = 512; tts.analyser.smoothingTimeConstant = 0.2;
    tts.buf = new Uint8Array(tts.analyser.fftSize);
    tts.ctx.createMediaElementSource(a).connect(tts.analyser);
    tts.analyser.connect(tts.ctx.destination);
  } catch (e) { console.warn("no WebAudio lip sync", e); }
  return a;
}
function lipSync() {   // the mouth follows the real loudness of the audio
  pet.classList.add("talking"); cancelAnimationFrame(tts.raf);
  if (!tts.analyser) { startTalking(); return; }
  let open = false;
  const tick = () => {
    tts.analyser.getByteTimeDomainData(tts.buf);
    const rms = Math.sqrt(tts.buf.reduce((s, v) => s + (v - 128) ** 2, 0) / tts.buf.length) / 128;
    open = rms > (open ? 0.02 : 0.035);   // two thresholds, so it doesn't flicker on a steady sound
    pet.classList.toggle("mouth-on", open);
    pet.style.setProperty("--mouth", Math.min(1.25, 0.55 + rms * 4).toFixed(2));
    tts.raf = requestAnimationFrame(tick);
  };
  tick();
}
function playBlob(blob) {
  return new Promise((resolve, reject) => {
    const a = ttsAudio(), url = URL.createObjectURL(blob);
    let settled = false;
    const done = (fn) => () => { if (settled) return; settled = true;
      URL.revokeObjectURL(url); a.onended = a.onerror = null; tts.finish = null; fn(); };
    tts.finish = done(resolve);
    a.onended = tts.finish; a.onerror = done(() => reject(new Error("audio error")));
    a.src = url; a.defaultPlaybackRate = a.playbackRate = petRate();
    tts.ctx?.resume();
    a.play().then(lipSync, (e) => { done(() => reject(e))(); });
  });
}
// A speech is a queue of clips: sentences go in as they arrive, clips play back-to-back as they're ready
const look = () => state.petData?.appearance || {};
const petRate = () => look().pitch || state.cfg.tts_rate || 1;
const orpheusVoice = (v) => wd.catalog?.orpheus_voices.includes(v);
const usesGroq = () => state.cfg.tts_engine === "groq" && state.lang === "en" && (!look().voice || orpheusVoice(look().voice));
function fetchClip(text, signal) {
  const voice = state.lang === "en" ? look().voice : null;
  const engine = voice ? (orpheusVoice(voice) ? "groq" : "kokoro") : undefined;
  return fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang: state.lang, voice: voice || undefined, engine, speed: look().speed || undefined }), signal })
    .then((r) => {
      if (!r.ok) throw new Error(`tts ${r.status}`);
      // Orpheus quota used up: send the next clips one at a time, so Kokoro works through them in order
      if (usesGroq() && r.headers.get("X-TTS-Engine") === "kokoro") state.cfg.tts_engine = "kokoro";
      return r.blob();
    });
}
function addClip(s, text) {
  // Groq clips run in parallel. Kokoro runs one at a time, in order, so the server builds a buffer ahead of her
  const clip = usesGroq() ? fetchClip(text, s.ctrl.signal) : (s.tail = s.tail.then(() => fetchClip(text, s.ctrl.signal)));
  clip.catch(() => {});
  s.clips.push({ clip, text }); s.wake?.();
}
function startSpeech() {
  shutUp();
  const s = { run: tts.run, ctrl: new AbortController(), clips: [], buf: "", closed: false, wake: null, tail: Promise.resolve() };
  tts.abort = s.ctrl; playClips(s);
  return s;
}
function pushSpeech(s, sentence) {
  // One clip per reply when it fits: joins between clips are what she pauses at. 185 = Orpheus's 200 minus her direction
  if (s.buf && s.buf.length + sentence.length >= 185) { addClip(s, s.buf); s.buf = ""; }
  s.buf = `${s.buf} ${sentence}`.trim();
}
function endSpeech(s) {
  if (s.buf) { addClip(s, s.buf); s.buf = ""; }
  s.closed = true; s.wake?.();
}
async function playClips(s) {
  for (let i = 0; ; i++) {
    while (i >= s.clips.length) {
      if (s.closed) { if (s.run === tts.run) { stopTalking(); stopThinking(); } return; }
      await new Promise((resolve) => { s.wake = resolve; });
      if (s.run !== tts.run) return;
    }
    const rest = () => s.clips.slice(i).map((c) => c.text).join(" ");
    try {
      const blob = await s.clips[i].clip;
      if (s.run !== tts.run) return;
      stopThinking();
      await playBlob(blob);
    } catch (e) {
      if (s.run === tts.run && e.name !== "AbortError") { console.warn(e); stopThinking(); speakBrowser(rest()); }
      return;
    }
    if (s.run !== tts.run) return;
  }
}
const canSpeak = () => state.voice && state.userGestured && state.cfg.tts_engine !== "browser";

// "mmh" while she thinks, so she never seems frozen. Generated once with her own voice, then cached
const think = { url: null, audio: null, timer: 0 };
async function loadThinkSound() {
  if (think.url || state.cfg.tts_engine === "browser") return;
  try {
    const r = await fetch("/api/sfx/mmh");
    if (r.ok) { think.url = URL.createObjectURL(await r.blob()); think.audio = null; }
  } catch {}
}
function startThinking() {
  stopThinking();
  if (!think.url || !state.voice || !state.userGestured) return;
  const hum = () => {
    const a = (think.audio = think.audio || new Audio(think.url));
    a.preservesPitch = a.mozPreservesPitch = a.webkitPreservesPitch = false;
    a.defaultPlaybackRate = a.playbackRate = petRate();
    a.volume = 0.6 * sound.settings.sfx_volume; a.currentTime = 0; a.play().catch(() => {});
    think.timer = setTimeout(hum, 3500);
  };
  think.timer = setTimeout(hum, 250);
}
function stopThinking() { clearTimeout(think.timer); think.audio?.pause(); }

function speak(text) {
  const clean = text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, "").trim();
  if (!clean) return;
  if (!state.userGestured) { state.pendingSpeech = text; }   // browsers block audio before the first click
  if (!state.voice || !state.userGestured) {
    startTalking(); setTimeout(stopTalking, Math.min(6000, clean.length * 45)); return;
  }
  if (state.cfg.tts_engine === "browser") { shutUp(); speakBrowser(clean); return; }
  const s = startSpeech();
  clean.split(/(?<=[.!?…])\s+/).filter(Boolean).forEach((sentence) => pushSpeech(s, sentence));
  endSpeech(s);
}
function speakBrowser(clean) {
  stopTalking();
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(clean);
  u.voice = pickVoice(); u.lang = state.lang === "fr" ? "fr-FR" : "en-US";
  u.pitch = 1.22; u.rate = 1.02;
  u.onstart = startTalking; u.onend = stopTalking; u.onerror = stopTalking;
  speechSynthesis.speak(u);
}
function pickVoice() {
  const lang = state.lang === "fr" ? "fr" : "en";
  const voices = speechSynthesis.getVoices();
  const matching = voices.filter((voice) => voice.lang.toLowerCase().startsWith(lang));
  const preferred = ["Samantha", "Ava", "Karen", "Jenny", "Aria", "Google US English", "Microsoft Zira"];
  return matching.sort((a, b) => {
    const ai = preferred.findIndex((name) => a.name.includes(name));
    const bi = preferred.findIndex((name) => b.name.includes(name));
    return (bi < 0 ? preferred.length : bi) - (ai < 0 ? preferred.length : ai);
  })[0] || null;
}
function shutUp() {   // barge-in: the mic button, a new message or the voice toggle all land here
  tts.run++; tts.abort?.abort();
  tts.audio?.pause(); tts.finish?.(); stopThinking();
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  stopTalking();
}
document.addEventListener("pointerdown", () => {
  if (state.userGestured) return;
  state.userGestured = true;
  initAudio();
  loadThinkSound();
  if (state.pendingSpeech && !rec.active) { const t = state.pendingSpeech; state.pendingSpeech = null; setTimeout(() => speak(t), 150); }
}, { capture: true });

// ================= speech to text (you talking) =================
// 1) Browser Web Speech API: live words as you speak (Chrome, Edge, Safari)
// 2) Fallback: record audio and transcribe with Whisper on the server (any browser)
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const rec = { active: false, stop: null };

function listenBrowser() {
  return new Promise((resolve, reject) => {
    const r = new SR();
    r.lang = state.lang === "fr" ? "fr-FR" : "en-US";
    r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
    let finalText = "", failed = false;
    r.onresult = (ev) => {
      let interim = ""; finalText = "";
      for (const res of ev.results) (res.isFinal ? (finalText += res[0].transcript) : (interim += res[0].transcript));
      heard((finalText + " " + interim).trim() || "…");
    };
    r.onerror = (e) => { failed = e.error;
      if (["network", "service-not-allowed", "language-not-supported"].includes(e.error)) reject(new Error("fallback"));
      else if (e.error === "not-allowed") reject(new Error(T("Mic permission denied", "Micro refusé")));
      else if (e.error === "no-speech") resolve(""); };
    r.onend = () => { if (!failed || failed === "no-speech" || failed === "aborted") resolve(finalText.trim()); };
    rec.stop = () => r.stop();
    r.start();
    heard(T("I'm listening…", "Je t'écoute…"));
  });
}

async function listenServer() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const mime = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
  const chunks = []; mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);

  // auto-stop after ~1.4 s of silence (once you've started talking), max 20 s
  const ctx = new AudioContext(); const an = ctx.createAnalyser(); an.fftSize = 512;
  ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Uint8Array(an.fftSize); let spoke = false, quietSince = performance.now(); const t0 = performance.now();
  const vad = setInterval(() => {
    an.getByteTimeDomainData(buf);
    const rms = Math.sqrt(buf.reduce((s, v) => s + (v - 128) ** 2, 0) / buf.length);
    if (rms > 6) { spoke = true; quietSince = performance.now(); heard(T("I'm listening…", "Je t'écoute…")); }
    const now = performance.now();
    if ((spoke && now - quietSince > 1400) || now - t0 > 20000 || (!spoke && now - t0 > 7000)) stop();
  }, 100);
  let stopped = false;
  function stop() { if (stopped) return; stopped = true; clearInterval(vad); mr.state !== "inactive" && mr.stop(); }
  rec.stop = stop;

  const done = new Promise((res) => (mr.onstop = res));
  mr.start(250); heard(T("I'm listening… (tap the mic to stop)", "Je t'écoute… (touche le micro pour arrêter)"));
  await done;
  stream.getTracks().forEach((t) => t.stop()); ctx.close();
  if (!spoke) return "";
  heard(T("Writing down what you said…", "J'écris ce que tu as dit…"));
  const fd = new FormData();
  fd.append("audio", new Blob(chunks, { type: mr.mimeType || "audio/webm" }), "speech");
  fd.append("lang", state.lang);
  const r = await fetch("/api/stt", { method: "POST", body: fd });
  if (!r.ok) throw new Error(T("Transcription failed", "La transcription a échoué"));
  return (await r.json()).text || "";
}

async function onMic() {
  if (rec.active) { rec.stop?.(); return; }
  shutUp();
  const useServer = state.cfg.server_stt && (state.cfg.stt_mode === "server" || !SR);
  if (!SR && !state.cfg.server_stt) return toast(T("Voice needs Chrome/Edge, or install faster-whisper on the server",
                                                     "La voix nécessite Chrome/Edge, ou faster-whisper sur le serveur"), 4000);
  rec.active = true; updateDuck(); $("micBtn").classList.add(useServer ? "recording" : "listening"); setEmotion("surprised");
  let text = "";
  try {
    try { text = useServer ? await listenServer() : await listenBrowser(); }
    catch (e) {
      if (e.message === "fallback" && state.cfg.server_stt) { $("micBtn").classList.add("recording"); text = await listenServer(); }
      else throw e;
    }
  } catch (e) { toast(e.message === "fallback" ? T("Browser voice unavailable here", "Voix du navigateur indisponible") : e.message, 3500); }
  finally { rec.active = false; updateDuck(); rec.stop = null; $("micBtn").classList.remove("listening", "recording"); }

  text = text.trim();
  if (!text) { hideHeard(); setEmotion(state.baseEmotion);
    if (!state.busy) toast(T("I didn't hear anything", "Je n'ai rien entendu")); return; }
  heard(text, true);
  handleUserText(text);
}
$("micBtn").addEventListener("click", onMic);

// ================= onboarding (Glowbi asks about you) =================
function renderStep(step) {
  state.onboarding = step; state.multi = new Set();
  $("progress").classList.remove("hidden"); $("progressFill").style.width = (step.progress || 0) + "%";
  setEmotion(step.emotion || "happy");
  showBubble(step.question); speak(step.question);
  const chips = $("chips");
  const add = (label, cls, onClick) => { const b = document.createElement("button"); b.className = "chip " + (cls || "");
    b.textContent = label; b.onclick = (e) => { e.stopPropagation(); onClick(b); }; chips.appendChild(b); };
  if (step.type === "names") {
    const card = document.createElement("form"); card.className = "names-card";
    const field = (en, fr, value, name) => { const l = document.createElement("label"); l.textContent = T(en, fr);
      const i = document.createElement("input"); i.name = name; i.value = value; i.maxLength = 24; i.autocomplete = "off"; l.appendChild(i); card.appendChild(l); return i; };
    const you = field("Your name", "Ton prénom", step.user_name || "", "you");
    const her = field("Name your pet", "Nomme ton animal", step.pet_name || "Glowbi", "pet");
    const go = document.createElement("button"); go.className = "pill"; go.textContent = T("Continue", "Continuer"); card.appendChild(go);
    card.onsubmit = (e) => { e.preventDefault();
      if (!you.value.trim()) { toast(T("Type your name first", "Écris d'abord ton prénom")); return you.focus(); }
      answerStep({ values: [you.value, her.value], label: you.value }).then(() => api("/api/pet")).then(renderPet); };
    chips.appendChild(card);
    $("msg").placeholder = T("Type your names above", "Écris vos noms au-dessus");
    return;
  }
  if (step.type === "single" || step.type === "text") {
    step.options.forEach((o) => add(o.label, "", () => answerStep({ values: [o.value], label: o.label })));
  } else if (step.type === "multi") {
    step.options.forEach((o) => add(o.label, "", (b) => {
      state.multi.has(o.value) ? state.multi.delete(o.value) : state.multi.add(o.value); b.classList.toggle("on"); }));
    add(T("None", "Aucun"), "", () => answerStep({ values: [], label: T("None", "Aucun") }));
    add(T("Done", "Valider"), "done", () => {
      const labels = step.options.filter((o) => state.multi.has(o.value)).map((o) => o.label);
      answerStep({ values: [...state.multi], label: labels.join(", ") || T("None", "Aucun") });
    });
  }
  $("msg").placeholder = step.type === "text" ? T("Type or say your answer…", "Écris ou dis ta réponse…")
                                              : T("Tap an answer, type, or just say it", "Touche une réponse, écris, ou dis-le");
}

async function answerStep({ text = "", values = null, label = "" }) {
  if (state.busy) return;
  state.busy = true; shutUp(); log("me", label || text);
  try {
    const res = await api("/api/onboarding/answer", { text, values, lang: state.lang });
    if (res.done) {
      state.onboarding = null; $("progress").classList.add("hidden"); renderLang();
      if (res.finished_now) {
        renderPet(res.pet); setEmotion("love", 5000); play("jump"); floaters(["heart", "sparkle", "dot"], 8);
        showBubble(res.question); speak(res.question); log("pet", res.question);
      }
    } else { renderStep(res); log("pet", res.question); }
  } catch (e) { console.error(e); toast(T("Oops, server hiccup", "Oups, souci serveur")); }
  finally { state.busy = false; }
}

async function startOnboarding(restart = false) {
  const step = restart ? await api("/api/onboarding/restart", {}) : await api(`/api/onboarding?lang=${state.lang}`);
  if (step.done) return false;
  renderStep(step);
  return true;
}

// ================= chat =================
async function send(text) {
  if (state.busy) return;
  state.busy = true; log("me", text); shutUp();
  setEmotion("thinking"); showTyping(); renderProducts([]); renderCheck(null);
  const speech = canSpeak() ? startSpeech() : null;
  startThinking();
  let shown = "";
  const onEvent = (ev) => {
    if (ev.emotion) setEmotion(ev.emotion);
    if (ev.sentence) {
      if (!shown) showBubble(ev.sentence); else $("bubbleText").textContent = `${shown} ${ev.sentence}`;
      shown = `${shown} ${ev.sentence}`.trim();
      if (speech) pushSpeech(speech, ev.sentence);
    }
    if (!ev.done) return;
    const d = ev.done;
    setEmotion(d.emotion); log("pet", d.reply); renderProducts(d.products);
    if (speech) endSpeech(speech); else { stopThinking(); speak(d.reply); }
    if (d.emotion === "love") floaters(["heart"]);
    if (d.emotion === "excited") { play("jump"); floaters(["sparkle"]); }
    if (d.leveled_up) { toast(T(`Level up! Level ${d.pet.level}`, `Niveau ${d.pet.level} !`), 4000); sfxChime(); }
    renderPet(d.pet);
    setTimeout(() => { if (!pet.classList.contains("talking") && !state.busy) setEmotion(state.baseEmotion); }, 8000);
  };
  try {
    const r = await fetch("/api/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }) });
    if (!r.ok) throw new Error(`chat ${r.status}`);
    const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      const lines = buf.split("\n"); buf = lines.pop();
      lines.filter(Boolean).forEach((line) => onEvent(JSON.parse(line)));
    }
  } catch (e) {
    console.error(e); setEmotion("concerned"); stopThinking(); if (speech) endSpeech(speech);
    showBubble(T("Oops, my brain glitched… can you try again?", "Oups, mon cerveau a buggé… tu peux réessayer ?"));
  } finally { state.busy = false; }
}

// ================= photos and ingredient checks =================
function showResult(d) {
  setEmotion(d.emotion || "happy"); showBubble(d.reply); log("pet", d.reply); speak(d.reply);
  renderProducts(d.products); renderCheck(d.check);
  if (d.pet) renderPet(d.pet);
  if (d.offer) {
    const line = document.createElement("p"); line.className = "offer";
    line.textContent = T(`Want me to remember that ${d.offer.en}?`, `Je retiens que ${d.offer.fr} ?`);
    const yes = document.createElement("button"); yes.className = "chip"; yes.textContent = T("Yes", "Oui");
    const no = document.createElement("button"); no.className = "chip"; no.textContent = T("No", "Non");
    yes.onclick = async () => { renderPet(await api("/api/pet/remember", { field: d.offer.field, value: d.offer.value })); $("chips").innerHTML = ""; toast(T("Saved", "C'est noté")); };
    no.onclick = () => { $("chips").innerHTML = ""; };
    $("chips").append(line, yes, no);
  }
}
async function busyTask(label, task) {
  if (state.busy) return;
  state.busy = true; shutUp(); log("me", label);
  setEmotion("thinking"); showTyping(); renderProducts([]); renderCheck(null); startThinking();
  try { const d = await task(); stopThinking(); showResult(d); }
  catch (e) { console.error(e); stopThinking(); setEmotion("concerned");
    showBubble(T("Oops, I couldn't read that, can you try again?", "Oups, je n'ai pas pu lire ça, tu peux réessayer ?")); }
  finally { state.busy = false; }
}
async function shrinkPhoto(file) {   // max 1280 px JPEG, so uploads stay small and the vision quota lasts longer
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1280 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
}
function sendPhoto(file) {
  return busyTask(T("Sent a photo", "Photo envoyée"), async () => {
    const fd = new FormData();
    fd.append("image", await shrinkPhoto(file), "photo.jpg");
    fd.append("question", $("msg").value.trim()); fd.append("lang", state.lang);
    $("msg").value = "";
    const r = await fetch("/api/vision", { method: "POST", body: fd });
    if (!r.ok) throw new Error(`vision ${r.status}`);
    return r.json();
  });
}
$("photoBtn").addEventListener("click", () => $("photoInput").click());
$("photoInput").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) sendPhoto(f); });
const CHECK_TEXT = /^\s*(?:check|v[ée]rifie|analyse)\s*:?\s+(.{2,})$/is;

function handleUserText(text) {
  text = text.trim(); if (!text) return;
  $("msg").value = "";
  if (state.onboarding?.type === "names") return toast(T("Type your names in the card", "Écris vos noms dans la carte"));
  const pasted = !state.onboarding && text.match(CHECK_TEXT);
  if (pasted) return busyTask(text.slice(0, 60), () => api("/api/ingredients/check", { text: pasted[1], lang: state.lang }));
  state.onboarding ? answerStep({ text }) : send(text);
}
$("chatForm").addEventListener("submit", (e) => { e.preventDefault(); handleUserText($("msg").value); });

// ================= settings =================
function renderVoiceBtn() {
  $("voiceBtn").innerHTML = icon(state.voice ? "speakerOn" : "speakerOff", 16) +
    `<span>${state.voice ? T("Voice on", "Voix activée") : T("Voice off", "Voix coupée")}</span>`;
}
function renderLang() {
  document.documentElement.lang = state.lang;
  $("langBtn").textContent = state.lang.toUpperCase();
  const named = (t) => t.replaceAll("{pet}", state.petData?.pet_name || "Glowbi");
  document.querySelectorAll("[data-en]").forEach((el) => { el.textContent = named(el.dataset[state.lang]); });
  document.querySelectorAll("[data-ph-en]").forEach((el) => { el.placeholder = T(el.dataset.phEn, el.dataset.phFr); });
  document.querySelectorAll("[data-title-en]").forEach((el) => {
    el.title = named(T(el.dataset.titleEn, el.dataset.titleFr)); el.setAttribute("aria-label", el.title); });
  renderVoiceBtn();
  if (!state.onboarding) $("msg").placeholder = T("Ask about skin, makeup, hair…", "Peau, maquillage, cheveux…");
}
$("langBtn").addEventListener("click", async () => {
  state.lang = state.lang === "en" ? "fr" : "en";
  localStorage.setItem("glowbi-lang", state.lang); renderLang();
  await api("/api/profile", { lang: state.lang });
  if (state.onboarding) renderStep(await api(`/api/onboarding?lang=${state.lang}`));
});
$("voiceBtn").addEventListener("click", () => { state.voice = !state.voice;
  localStorage.setItem("glowbi-voice", state.voice ? "on" : "off");
  renderVoiceBtn(); if (!state.voice) shutUp(); });
$("logBtn").addEventListener("click", () => $("log").classList.toggle("hidden"));

$("profileBtn").addEventListener("click", () => {
  const p = state.petData?.profile || {}; const f = $("profileForm");
  f.user_name.value = state.petData?.user_name || ""; f.pet_name.value = state.petData?.pet_name || "";
  f.skin_type.value = p.skin_type || ""; f.hair_type.value = p.hair_type || "";
  f.concerns.value = (p.concerns || []).join(", "); f.avoid.value = (p.avoid || []).join(", ");
  $("profileDlg").showModal();
});
$("profileDlg").addEventListener("close", async () => {
  const v = $("profileDlg").returnValue;
  if (v === "redo") { await startOnboarding(true); return; }
  if (v !== "save") return;
  const f = $("profileForm"); const list = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
  await api("/api/pet/names", { user_name: f.user_name.value.trim() || null, pet_name: f.pet_name.value.trim() || null });
  renderPet(await api("/api/profile", { skin_type: f.skin_type.value || null, hair_type: f.hair_type.value || null,
    concerns: list(f.concerns.value), avoid: list(f.avoid.value) }));
  setEmotion("love", 2500); floaters(["heart"], 4);
  showBubble(T("Thank you! Now I know you better", "Merci ! Maintenant je te connais mieux"));
});

// ================= boot =================
(async function boot() {
  renderLang();
  try { state.cfg = await api("/api/config"); } catch {}
  const p = await api("/api/pet"); renderPet(p);
  await initWardrobe(); initGame();
  if (await startOnboarding()) return;
  const name = p.profile.name ? " " + p.profile.name : "";
  const hi = T(`Hiii${name}! What beauty question do you have for me today?`,
               `Coucou${name} ! Quelle question beauté pour moi aujourd'hui ?`);
  showBubble(hi); speak(hi);
})();
setInterval(async () => {
  if (state.busy) return;
  renderPet(await api("/api/pet"));
  state.cfg = await api("/api/config");
}, 60000);
