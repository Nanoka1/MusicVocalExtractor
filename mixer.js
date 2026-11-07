const find = (selector) => element.querySelector(selector);
const message = find("[data-message]");
const controls = find("[data-controls]");
const play = find("[data-play]");
const seek = find("[data-seek]");
const time = find("[data-time]");
const rows = find("[data-tracks]");
const master = find("[data-master]");
const masterValue = find("[data-master-value]");
let context, masterGain, mix, request;
let tracks = [];
let sources = [];
let offset = 0;
let startedAt = 0;
let animation = 0;
let scrubbing = false;

function position() {
  if (!sources.length) return offset;
  return Math.min(mix.duration, offset + Math.max(0, context.currentTime - startedAt));
}

function clock(seconds) {
  const whole = Math.floor(seconds);
  return Math.floor(whole / 60) + ":" + String(whole % 60).padStart(2, "0");
}

function paint() {
  if (!mix) return;
  if (!scrubbing) seek.value = position();
  time.textContent = clock(Number(seek.value)) + " / " + clock(mix.duration);
  play.textContent = sources.length ? "暂停" : "播放";
}

function stopSources() {
  cancelAnimationFrame(animation);
  for (const source of sources) {
    source.stop();
    source.disconnect();
  }
  sources = [];
}

function tick() {
  if (position() >= mix.duration) {
    stopSources();
    offset = mix.duration;
  } else {
    animation = requestAnimationFrame(tick);
  }
  paint();
}

function startSources() {
  if (offset >= mix.duration) return;
  // 一批音源共享 AudioContext 的同一个开始时间和采样偏移。
  sources = tracks.map((track) => {
    const source = context.createBufferSource();
    source.buffer = track.buffer;
    source.connect(track.gain);
    return source;
  });
  startedAt = context.currentTime + 0.025;
  for (const source of sources) {
    source.start(startedAt, offset, mix.duration - offset);
  }
  tick();
}

function applyVolumes() {
  const solo = tracks.some((track) => track.solo);
  for (const track of tracks) {
    const volume = Number(track.slider.value);
    const audible = volume > 0 && (!solo || track.solo);
    if (track.gain) track.gain.gain.value = audible ? volume / 100 : 0;
    track.row.classList.toggle("mve-quiet", !audible);
    track.value.textContent = volume + "%";
    track.soloButton.setAttribute("aria-pressed", String(track.solo));
  }
  if (masterGain) masterGain.gain.value = Number(master.value) / 100;
  masterValue.textContent = master.value + "%";
}

function createTrack(track) {
  const row = document.createElement("div");
  row.className = "mve-track";
  const label = document.createElement("label");
  const icons = { Vocals: "🎤", LeadVocals: "🎤", BackingVocals: "🎙", Instrumental: "♫" };
  label.textContent = (icons[track.id] || "♫") + " " + track.label;
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = 0;
  slider.max = 100;
  slider.value = 100;
  slider.id = element.id + "-volume-" + track.id;
  label.htmlFor = slider.id;
  slider.addEventListener("input", applyVolumes);
  const value = document.createElement("output");
  value.setAttribute("for", slider.id);
  const soloButton = document.createElement("button");
  soloButton.type = "button";
  soloButton.textContent = "Solo";
  soloButton.setAttribute("aria-label", track.label + " Solo");
  const state = { ...track, slider, row, value, soloButton, solo: false };
  soloButton.addEventListener("click", () => {
    state.solo = !state.solo;
    applyVolumes();
  });
  row.append(label, slider, value, soloButton);
  rows.append(row);
  return state;
}

function loadMix() {
  if (request) request.abort();
  stopSources();
  for (const track of tracks) track.gain?.disconnect();
  request = null;
  offset = 0;
  scrubbing = false;
  rows.replaceChildren();
  mix = props.value ? JSON.parse(props.value) : null;
  tracks = mix ? mix.tracks.map(createTrack) : [];
  controls.hidden = !mix;
  play.disabled = false;
  master.value = 100;
  seek.max = mix ? mix.duration : 1;
  message.textContent = mix ? mix.title : "分离完成后，音轨会显示在这里。";
  applyVolumes();
  paint();
}

play.addEventListener("click", async () => {
  if (sources.length) {
    offset = position();
    stopSources();
    paint();
    return;
  }
  const pending = new AbortController();
  request = pending;
  play.disabled = true;
  try {
    if (!context) {
      context = new AudioContext();
      masterGain = context.createGain();
      masterGain.connect(context.destination);
    }
    await context.resume();
    for (const track of tracks) {
      if (pending.signal.aborted) return;
      if (track.buffer) continue;
      message.textContent = "正在载入 " + track.label + "…";
      const response = await fetch(track.url, { signal: pending.signal });
      if (!response.ok) throw new Error("无法读取 " + track.label);
      const buffer = await context.decodeAudioData(await response.arrayBuffer());
      if (pending.signal.aborted) return;
      if (Math.abs(buffer.duration - mix.duration) > 2 / buffer.sampleRate) {
        throw new Error(track.label + "的时长与混音时间轴不一致");
      }
      track.buffer = buffer;
      track.gain = context.createGain();
      track.gain.connect(masterGain);
    }
    if (pending.signal.aborted) return;
    if (offset >= mix.duration) offset = 0;
    applyVolumes();
    startSources();
    message.textContent = mix.title;
  } catch (error) {
    if (!pending.signal.aborted) {
      stopSources();
      paint();
      message.textContent = "播放失败 · " + error.message;
    }
  } finally {
    if (request === pending) {
      request = null;
      play.disabled = false;
    }
  }
});

seek.addEventListener("input", () => {
  scrubbing = true;
  paint();
});
function seekToSlider() {
  if (!scrubbing) return;
  scrubbing = false;
  offset = Number(seek.value);
  const playing = sources.length > 0;
  stopSources();
  if (playing) startSources();
  paint();
}
seek.addEventListener("change", seekToSlider);
seek.addEventListener("blur", seekToSlider);
master.addEventListener("input", applyVolumes);
find("[data-reset]").addEventListener("click", () => {
  master.value = 100;
  for (const track of tracks) {
    track.slider.value = 100;
    track.solo = false;
  }
  applyVolumes();
});
find("[data-enable]").addEventListener("click", () => {
  for (const track of tracks) {
    if (Number(track.slider.value) === 0) track.slider.value = 100;
    track.solo = false;
  }
  applyVolumes();
});
find("[data-mute]").addEventListener("click", () => {
  for (const track of tracks) track.slider.value = 0;
  applyVolumes();
});

watch("value", loadMix);
loadMix();
