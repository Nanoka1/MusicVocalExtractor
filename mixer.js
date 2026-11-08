const find = (selector) => element.querySelector(selector);
const message = find("[data-message]");
const controls = find("[data-controls]");
const play = find("[data-play]");
const seek = find("[data-seek]");
const time = find("[data-time]");
const rows = find("[data-tracks]");
const master = find("[data-master]");
const masterValue = find("[data-master-value]");
const exportButton = find("[data-export]");
const exportLink = find("[data-export-link]");
const exportStatus = find("[data-export-status]");
let context, masterGain, mix, request;
let tracks = [];
let sources = [];
let offset = 0;
let startedAt = 0;
let animation = 0;
let gainFrame = 0;
let scrubbing = false;
const gainEnvelopes = new WeakMap();
const RAMP_SECONDS = 0.040;

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
  applyGains(true);
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

function effectiveVolumes() {
  const solo = tracks.some((track) => track.solo);
  return Object.fromEntries(tracks.map((track) => [
    track.id, track.muted || (solo && !track.solo) ? 0 : Number(track.slider.value)
  ]));
}

function setGain(node, target, instant) {
  if (!node) return;
  const parameter = node.gain;
  const now = context.currentTime;
  const previous = gainEnvelopes.get(node);
  if (previous?.target === target && (!instant || now >= previous.end)) return;
  const end = now + (instant ? 0 : RAMP_SECONDS);
  let start = target;
  if (!instant) {
    // 新滑块事件从上一段包络的当前位置接续，快速拖动也不会从旧目标跳变。
    const fraction = previous && now < previous.end
      ? Math.max(0, (now - previous.time) / (previous.end - previous.time)) : 1;
    start = previous ? previous.start + (previous.target - previous.start) * fraction : parameter.value;
  }
  // 显式锁住当前增益，避免部分浏览器取消旧斜坡时重用过时的自动化事件。
  parameter.cancelScheduledValues(now);
  parameter.setValueAtTime(start, now);
  if (!instant) parameter.linearRampToValueAtTime(target, end);
  gainEnvelopes.set(node, { start, target, time: now, end });
}

function applyGains(instant) {
  cancelAnimationFrame(gainFrame);
  gainFrame = 0;
  if (!mix) return;
  const levels = effectiveVolumes();
  for (const track of tracks) setGain(track.gain, levels[track.id] / 100, instant);
  setGain(masterGain, Number(master.value) / 100 * mix.headroom, instant);
}

function applyVolumes() {
  const levels = effectiveVolumes();
  for (const track of tracks) {
    track.row.classList.toggle("mve-quiet", levels[track.id] === 0);
    track.value.textContent = track.slider.value + "%";
    track.muteButton.textContent = track.muted ? "恢复" : "静音";
    track.muteButton.setAttribute("aria-pressed", String(track.muted));
    track.soloButton.setAttribute("aria-pressed", String(track.solo));
  }
  masterValue.textContent = master.value + "%";
  if (!sources.length) applyGains(true);
  else if (!gainFrame) gainFrame = requestAnimationFrame(() => applyGains(!sources.length));
}

function fadeBufferEdges(buffer, seconds) {
  const fade = Math.min(Math.floor(buffer.sampleRate * seconds), Math.floor(buffer.length / 2));
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const samples = buffer.getChannelData(channel);
    for (let i = 0; i < fade; i++) {
      const gain = i / fade;
      samples[i] *= gain;
      samples[samples.length - 1 - i] *= gain;
    }
  }
}

function createTrack(track) {
  const row = document.createElement("div");
  row.className = "mve-track";
  const label = document.createElement("label");
  const icons = { Vocals: "🎤", LeadVocals: "🎤", BackingVocals: "🎙" };
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
  const muteButton = document.createElement("button");
  muteButton.type = "button";
  muteButton.setAttribute("data-mute-track", "");
  muteButton.setAttribute("aria-label", track.label + " 静音");
  const soloButton = document.createElement("button");
  soloButton.type = "button";
  soloButton.textContent = "Solo";
  soloButton.setAttribute("aria-label", track.label + " Solo");
  const state = { ...track, slider, row, value, muteButton, soloButton, muted: false, solo: false };
  muteButton.addEventListener("click", () => {
    state.muted = !state.muted;
    applyVolumes();
  });
  soloButton.addEventListener("click", () => {
    state.solo = !state.solo;
    applyVolumes();
  });
  const buttons = document.createElement("div");
  buttons.className = "mve-track-buttons";
  buttons.append(muteButton, soloButton);
  row.append(label, slider, value, buttons);
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
  exportButton.disabled = false;
  exportLink.hidden = true;
  exportStatus.textContent = "";
  master.value = 100;
  seek.max = mix ? mix.duration : 1;
  message.textContent = mix ? mixTitle() : "分离完成后，音轨会显示在这里。";
  applyVolumes();
  paint();
}

function mixTitle() {
  const db = 20 * Math.log10(mix.headroom);
  return mix.title + (db < 0 ? " · 防削波余量 " + (-db).toFixed(1) + " dB" : "");
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
      fadeBufferEdges(buffer, mix.fadeSeconds);
      track.buffer = buffer;
      track.gain = context.createGain();
      track.gain.connect(masterGain);
    }
    if (pending.signal.aborted) return;
    if (offset >= mix.duration) offset = 0;
    applyVolumes();
    startSources();
    message.textContent = mixTitle();
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

exportButton.addEventListener("click", async () => {
  if (!mix) return;
  const currentMix = mix;
  exportButton.disabled = true;
  exportLink.hidden = true;
  exportStatus.textContent = "正在导出整首歌曲…";
  try {
    // 在点击时快照化设置，导出不受试听过渡、进度和后续拖动影响。
    const result = await server.export_mix({
      name: currentMix.title, format: "MP3", levels: effectiveVolumes(), master: Number(master.value)
    });
    if (mix !== currentMix) return;
    if (!result?.url) throw new Error(result?.error || "无法连接本机混音服务。");
    exportLink.href = result.url;
    exportLink.download = result.name;
    exportLink.textContent = "下载 MP3";
    exportLink.hidden = false;
    exportStatus.textContent = "已保存到歌曲目录的 mix-exports";
  } catch (error) {
    if (mix === currentMix) exportStatus.textContent = "导出失败 · " + (error.message || String(error));
  } finally {
    if (mix === currentMix) exportButton.disabled = false;
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
    track.muted = false;
    track.solo = false;
  }
  applyVolumes();
});
find("[data-enable]").addEventListener("click", () => {
  for (const track of tracks) {
    if (Number(track.slider.value) === 0) track.slider.value = 100;
    track.muted = false;
    track.solo = false;
  }
  applyVolumes();
});
find("[data-mute]").addEventListener("click", () => {
  for (const track of tracks) track.muted = true;
  applyVolumes();
});

watch("value", loadMix);
loadMix();
