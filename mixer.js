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
let context, masterGain, outputGain, mix, playback;
let tracks = [];
let offset = 0;
let syncTimer = 0;
let gainFrame = 0;
let scrubbing = false;
const gainEnvelopes = new WeakMap();
const RAMP_SECONDS = 0.040;
const SYNC_INTERVAL_MS = 40;
const SYNC_TOLERANCE = 0.015;
const RESYNC_THRESHOLD = 0.100;
const BUFFER_TIMEOUT_MS = 30000;

function position() {
  return playback?.audible ? Math.min(mix.duration, tracks[0].media.currentTime) : offset;
}

function clock(seconds) {
  const whole = Math.floor(seconds);
  return Math.floor(whole / 60) + ":" + String(whole % 60).padStart(2, "0");
}

function paint() {
  if (!mix) return;
  if (!scrubbing) seek.value = position();
  time.textContent = clock(Number(seek.value)) + " / " + clock(mix.duration);
  play.textContent = playback ? "暂停" : "播放";
}

function silenceOutput() {
  if (!outputGain) return;
  outputGain.gain.cancelScheduledValues(context.currentTime);
  outputGain.gain.setValueAtTime(0, context.currentTime);
}

function pauseTracks() {
  silenceOutput();
  for (const { media } of tracks) {
    if (media) {
      media.pause();
      media.playbackRate = 1;
    }
  }
}

function stopPlayback() {
  playback = null;
  clearInterval(syncTimer);
  pauseTracks();
}

function releaseTracks() {
  for (const track of tracks) {
    if (!track.media) continue;
    const media = track.media;
    track.media = null;
    media.removeAttribute("src");
    media.load();
    track.source?.disconnect();
    track.gain?.disconnect();
    track.source = track.gain = null;
  }
}

function playbackError(error) {
  offset = position();
  stopPlayback();
  releaseTracks();
  message.textContent = "播放失败 · " + error.message;
  paint();
}

function ready(media) {
  return !media.seeking && media.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA;
}

function seekTracks() {
  for (const { media } of tracks) {
    if (Math.abs(media.currentTime - offset) > 0.001) media.currentTime = offset;
  }
}

function bufferAt(target) {
  offset = target;
  if (playback.audible) playback.deadline = performance.now() + BUFFER_TIMEOUT_MS;
  playback.audible = false;
  playback.buffering = true;
  pauseTracks();
  seekTracks();
  message.textContent = "正在同步缓冲音轨…";
  paint();
}

async function playTracks(run, resume) {
  run.buffering = false;
  run.starting = true;
  try {
    // 同一轮用户操作里发出所有 play()，等每条轨道可播后再打开输出。
    await Promise.all([resume, ...tracks.map(async ({ media, label }) => {
      try {
        await media.play();
      } catch (error) {
        throw new Error(label + " · " + error.message);
      }
    })]);
    if (playback === run) {
      run.starting = false;
      syncPlayback();
    }
  } catch (error) {
    if (playback === run) playbackError(error);
  }
}

function syncPlayback() {
  const run = playback;
  if (!run) return;
  if (!run.audible && performance.now() >= run.deadline) {
    playbackError(new Error("等待音轨缓冲超时"));
    return;
  }
  if (run.starting) return;
  if (run.buffering) {
    if (tracks.every(({ media }) => ready(media))) playTracks(run);
    return;
  }

  const reference = tracks[0].media.currentTime;
  if (reference >= mix.duration || tracks.some(({ media }) => media.ended)) {
    offset = mix.duration;
    stopPlayback();
    paint();
    return;
  }
  if (mix.duration - reference > RESYNC_THRESHOLD && tracks.some(({ media }) => !ready(media))) {
    bufferAt(offset);
    return;
  }
  let aligned = true;
  // 所有音轨持续解码，静音和 Solo 只改增益。小偏差逐渐收敛，避免频繁跳采样。
  for (const { media } of tracks.slice(1)) {
    const delta = reference - media.currentTime;
    if (Math.abs(delta) > RESYNC_THRESHOLD) {
      bufferAt(reference);
      return;
    }
    if (Math.abs(delta) > 2 * SYNC_TOLERANCE) aligned = false;
    media.playbackRate = Math.abs(delta) < SYNC_TOLERANCE ? 1 : 1 + Math.max(-0.03, Math.min(0.03, delta / 2));
  }
  offset = reference;
  if (!run.audible && aligned) {
    const now = context.currentTime;
    const end = now + mix.duration - reference;
    const fade = Math.min(mix.fadeSeconds, (end - now) / 2);
    outputGain.gain.setValueAtTime(0, now);
    outputGain.gain.linearRampToValueAtTime(1, now + fade);
    outputGain.gain.setValueAtTime(1, end - fade);
    outputGain.gain.linearRampToValueAtTime(0, end);
    run.audible = true;
    message.textContent = mixTitle();
  }
  paint();
}

function prepareTracks() {
  if (!context) {
    context = new AudioContext();
    masterGain = context.createGain();
    outputGain = context.createGain();
    outputGain.gain.value = 0;
    masterGain.connect(outputGain).connect(context.destination);
  }
  for (const track of tracks) {
    if (track.media) continue;
    const media = new Audio();
    track.media = media;
    media.preload = "auto";
    media.addEventListener("error", () => {
      if (playback && track.media === media) playbackError(new Error("无法播放 " + track.label));
    });
    media.addEventListener("waiting", () => {
      if (playback?.audible && track.media === media && !ready(media) && mix.duration - offset > RESYNC_THRESHOLD) {
        bufferAt(offset);
      }
    });
    track.source = context.createMediaElementSource(media);
    track.gain = context.createGain();
    track.source.connect(track.gain).connect(masterGain);
    media.src = track.url;
  }
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
  if (!playback) applyGains(true);
  else if (!gainFrame) gainFrame = requestAnimationFrame(() => applyGains(!playback));
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
  stopPlayback();
  releaseTracks();
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

play.addEventListener("click", () => {
  if (!mix) return;
  if (playback) {
    offset = position();
    stopPlayback();
    message.textContent = mixTitle();
    paint();
    return;
  }
  try {
    prepareTracks();
    if (offset >= mix.duration) offset = 0;
    seekTracks();
    applyGains(true);
    playback = { deadline: performance.now() + BUFFER_TIMEOUT_MS };
    message.textContent = "正在缓冲音轨…";
    playTracks(playback, context.resume());
    syncTimer = setInterval(syncPlayback, SYNC_INTERVAL_MS);
    paint();
  } catch (error) {
    playbackError(error);
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
  if (playback && offset >= mix.duration) {
    stopPlayback();
    message.textContent = mixTitle();
  } else if (playback) {
    // 让已取消的 play() Promise 无法恢复刚被拖动的时间轴。
    playback = { deadline: performance.now() + BUFFER_TIMEOUT_MS };
    bufferAt(offset);
  }
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
