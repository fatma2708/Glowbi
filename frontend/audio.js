// Background music (generated here, so it has no licence to worry about) and sound effects
const sound = {
  ctx: null, music: null, duck: null, sfx: null, settings: { music_on: true, music_volume: 0.3, music_track: "generated", sfx_volume: 0.7 },
  voices: {}, timer: 0, nextBar: 0, bar: 0, progression: null, file: null, ducked: false,
};
const BEAT = 60 / 80, BAR = BEAT * 4;
const midi = (n) => 440 * 2 ** ((n - 69) / 12);
const PROGRESSIONS = [[[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]],
                      [[53, 57, 60], [55, 59, 62], [52, 55, 59], [57, 60, 64]],
                      [[57, 60, 64], [53, 57, 60], [60, 64, 67], [55, 59, 62]],
                      [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]];
const SCALE = [72, 74, 76, 79, 81, 84, 86, 88];   // C major pentatonic
const RHYTHMS = [[0, 1, 2, 3], [0, 1.5, 2, 3.5], [0, 0.5, 2, 3], [0, 2, 2.5], [1, 2, 3.5]];

function initAudio() {
  if (sound.ctx) { sound.ctx.resume(); return; }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  const ctx = (sound.ctx = new Ctx());
  sound.music = ctx.createGain(); sound.duck = ctx.createGain(); sound.sfx = ctx.createGain();
  sound.music.connect(sound.duck); sound.duck.connect(ctx.destination); sound.sfx.connect(ctx.destination);
  applySoundSettings();
  startMusic();
  new MutationObserver(updateDuck).observe($("pet"), { attributes: true, attributeFilter: ["class"] });
}
function applySoundSettings(patch) {
  Object.assign(sound.settings, patch || {});
  if (!sound.ctx) return;
  const s = sound.settings, now = sound.ctx.currentTime;
  sound.music.gain.setTargetAtTime(s.music_on ? s.music_volume : 0, now, 0.05);
  sound.sfx.gain.setTargetAtTime(s.sfx_volume, now, 0.02);
}
function updateDuck() {   // music drops to 20% while she speaks or the mic listens
  if (!sound.ctx) return;
  const on = $("pet").classList.contains("talking") || rec.active;
  if (on === sound.ducked) return;
  sound.ducked = on;
  const g = sound.duck.gain, now = sound.ctx.currentTime;
  g.cancelScheduledValues(now); g.setValueAtTime(g.value, now); g.linearRampToValueAtTime(on ? 0.2 : 1, now + 0.3);
}

// ---------- generated music: a music-box melody over a soft pad ----------
function kalimba(freq, t, velocity, out) {
  const ctx = sound.ctx, env = ctx.createGain();
  env.gain.setValueAtTime(0, t); env.gain.linearRampToValueAtTime(velocity, t + 0.008);
  env.gain.exponentialRampToValueAtTime(0.0001, t + 1.6);
  env.connect(out);
  [[1, "sine", 1], [3, "sine", 0.18], [5.4, "sine", 0.05]].forEach(([ratio, type, level]) => {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.value = freq * ratio; g.gain.value = level;
    o.connect(g); g.connect(env); o.start(t); o.stop(t + 1.7);
  });
}
function pad(chord, t, length) {
  const ctx = sound.ctx, env = ctx.createGain(), filter = ctx.createBiquadFilter();
  filter.type = "lowpass"; filter.frequency.value = 700;
  env.gain.setValueAtTime(0, t); env.gain.linearRampToValueAtTime(0.05, t + 0.9);
  env.gain.setValueAtTime(0.05, t + length - 0.9); env.gain.linearRampToValueAtTime(0, t + length + 0.3);
  filter.connect(env); env.connect(sound.music);
  chord.forEach((note, i) => {
    const o = ctx.createOscillator();
    o.type = "triangle"; o.frequency.value = midi(note); o.detune.value = i * 3 - 3;
    o.connect(filter); o.start(t); o.stop(t + length + 0.4);
  });
}
function scheduleBar(t) {
  if (sound.bar % 8 === 0) sound.progression = PROGRESSIONS[Math.floor(Math.random() * PROGRESSIONS.length)];
  const chord = sound.progression[sound.bar % 4];
  pad(chord, t, BAR);
  const quiet = sound.bar % 8 === 7;   // a breath every 8 bars, so the loop doesn't feel mechanical
  let step = Math.floor(Math.random() * SCALE.length);
  const rhythm = quiet ? [0] : RHYTHMS[Math.floor(Math.random() * RHYTHMS.length)];
  rhythm.forEach((beat) => {
    step = Math.max(0, Math.min(SCALE.length - 1, step + Math.floor(Math.random() * 5) - 2));
    kalimba(midi(SCALE[step]), t + beat * BEAT, 0.07 + Math.random() * 0.03, sound.music);
  });
  sound.bar++;
}
function startMusic() {
  stopMusic();
  const track = sound.settings.music_track;
  if (track && track !== "generated") {
    const el = (sound.file = new Audio(`/static/music/${encodeURIComponent(track)}`));
    el.loop = true;
    sound.ctx.createMediaElementSource(el).connect(sound.music);
    el.play().catch((e) => console.warn("music", e));
    return;
  }
  sound.nextBar = sound.ctx.currentTime + 0.2;
  sound.timer = setInterval(() => {
    if (!sound.settings.music_on || sound.settings.music_volume === 0) { sound.nextBar = sound.ctx.currentTime + 0.2; return; }
    while (sound.nextBar < sound.ctx.currentTime + 0.6) { scheduleBar(sound.nextBar); sound.nextBar += BAR; }
  }, 200);
}
function stopMusic() { clearInterval(sound.timer); sound.file?.pause(); sound.file = null; }

// ---------- sound effects ----------
function chirp(from, to, length, type = "sine", level = 0.25) {
  if (!sound.ctx) return;
  const ctx = sound.ctx, t = ctx.currentTime, o = ctx.createOscillator(), g = ctx.createGain();
  o.type = type; o.frequency.setValueAtTime(from, t); o.frequency.exponentialRampToValueAtTime(to, t + length);
  g.gain.setValueAtTime(level, t); g.gain.exponentialRampToValueAtTime(0.0001, t + length);
  o.connect(g); g.connect(sound.sfx); o.start(t); o.stop(t + length + 0.02);
}
const sfxBoop = () => chirp(520, 300, 0.13);
const sfxPop = () => chirp(900, 220, 0.09, "triangle", 0.3);
function sfxChime() {
  if (!sound.ctx) return;
  [84, 88, 91, 96].forEach((n, i) => kalimba(midi(n), sound.ctx.currentTime + i * 0.09, 0.22, sound.sfx));
}
async function voiceSound(kind) {   // giggles, yay, ooh, yawn: her own voice, generated and cached by the server
  if (!sound.ctx) return;
  try {
    if (!sound.voices[kind]) {
      const r = await fetch(`/api/sfx/${kind}`);
      if (!r.ok) return;
      sound.voices[kind] = await sound.ctx.decodeAudioData(await r.arrayBuffer());
    }
    const src = sound.ctx.createBufferSource();
    src.buffer = sound.voices[kind]; src.playbackRate.value = petRate();
    src.connect(sound.sfx); src.start();
  } catch (e) { console.warn("sound", kind, e); }
}
