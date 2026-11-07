"""SCNet 的四轨 ONNX 推理，沿用项目现有的 Torch 和 ONNX Runtime。"""
import hashlib
import logging
import tempfile
import time
from pathlib import Path

from gpu_runtime import preload_onnx_cuda
from separate import run_tool

SCNET_MODEL = "scnet.int8.onnx"
SCNET_LABELS = ("Drums", "Bass", "Other", "Vocals")
SCNET_SHA256 = "98228931494151762a1c4ab1ec7899a894b1f81fd4a509921a9d2f9bacc50845"
SCNET_BYTES = 12900277
SCNET_URL = ("https://huggingface.co/audiojs/scnet/resolve/"
             "e71bcdb42bce1d62b7fae25ba90fcbcf90f73f46/scnet.int8.onnx")
SAMPLE_RATE = 44100
CHUNK = 11 * SAMPLE_RATE
HOP = 1024
FFT = 4096
FRAMES = 476


def verify_weights(path):
    with path.open("rb") as weights:
        if path.stat().st_size != SCNET_BYTES or hashlib.file_digest(weights, "sha256").hexdigest() != SCNET_SHA256:
            raise RuntimeError("SCNet 权重校验失败。请检查模型缓存，原文件已保留。")


def cached_weights(model_dir, stage):
    import requests
    from filelock import FileLock

    model_dir.mkdir(parents=True, exist_ok=True)
    target = model_dir / SCNET_MODEL
    with FileLock(str(model_dir / ".download.lock"), timeout=1):
        if target.exists():
            verify_weights(target)
            return target
        stage("首次使用 SCNet：正在下载并校验权重")
        # 下载完整且通过校验后才发布，重试只清理本次的临时文件。
        pending = None
        try:
            with tempfile.NamedTemporaryFile(prefix="scnet-", suffix=".partial", dir=model_dir,
                                             delete=False) as output:
                pending = Path(output.name)
                with requests.get(SCNET_URL, stream=True, timeout=(10, 60)) as response:
                    response.raise_for_status()
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        output.write(block)
                        if output.tell() > SCNET_BYTES:
                            raise RuntimeError("SCNet 下载大小超出发布清单。")
            verify_weights(pending)
            pending.rename(target)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
    return target


def open_session(weights, device, options=None):
    import onnxruntime as ort

    options = options or ort.SessionOptions()
    options.intra_op_num_threads = 4
    if device == "cuda":
        preload_onnx_cuda()
        # 该图已在 CUDA Provider 上验证。会话缺少可用算子时显式报错。
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        expected = "CUDAExecutionProvider"
        providers = [(expected, {"cudnn_conv_algo_search": "HEURISTIC"})]
    else:
        expected = "CPUExecutionProvider"
        providers = [expected]
    session = ort.InferenceSession(str(weights), sess_options=options, providers=providers)
    session.disable_fallback()
    if session.get_providers()[0] != expected:
        raise RuntimeError(f"SCNet 实际会话未使用 {expected}。")
    return session


def infer_chunk(session, chunk, window):
    import torch
    from torch.nn.functional import pad

    # 先补齐波形，使中心 STFT 产生模型要求的 476 帧。通道顺序为左实、左虚、右实、右虚。
    chunk = torch.as_tensor(chunk, device=window.device)
    samples = pad(chunk, (0, (FRAMES - 1) * HOP - CHUNK))
    spec = torch.stft(samples, FFT, HOP, window=window, normalized=True, return_complex=True)
    packed = torch.view_as_real(spec).permute(0, 3, 1, 2).reshape(1, 4, FFT // 2 + 1, FRAMES)
    estimate, = session.run(["stems_spec"], {"mix_spec": packed.contiguous().cpu().numpy()})
    separated = torch.from_numpy(estimate).to(window.device).reshape(len(SCNET_LABELS) * 2, 2, FFT // 2 + 1, FRAMES)
    separated = torch.view_as_complex(separated.permute(0, 2, 3, 1).contiguous())
    wave = torch.istft(separated, FFT, HOP, window=window, normalized=True, length=samples.shape[-1])
    return wave.reshape(len(SCNET_LABELS), 2, -1)[..., :CHUNK].cpu().numpy()


def demix(session, audio, device, mode, stage):
    import numpy as np
    import torch

    # 11 秒分块。质量、平衡和快速模式分别使用 75%、50% 和 25% 的重叠。
    stride = CHUNK * {"quality": 1, "balanced": 2, "fast": 3}[mode] // 4
    overlap = CHUNK - stride
    deviation = float(audio.std(dtype=np.float64))
    if deviation <= 1e-8:
        return np.zeros((len(SCNET_LABELS), *audio.shape), dtype=np.float32)
    wave = (audio - float(audio.mean(dtype=np.float64))) / deviation
    border = overlap if audio.shape[1] > 2 * overlap else 0
    if border:
        wave = np.pad(wave, ((0, 0), (border, border)), mode="reflect")
    frames = wave.shape[1]
    mixed = np.zeros((len(SCNET_LABELS), *wave.shape), dtype=np.float32)
    weights = np.zeros(frames, dtype=np.float32)
    fade = np.linspace(0, 1, CHUNK // 10, dtype=np.float32)
    window = torch.ones(FFT, device=device)
    blocks = 1 + max(0, frames - CHUNK + stride - 1) // stride
    with torch.inference_mode():
        for index in range(blocks):
            start = index * stride
            end = min(start + CHUNK, frames)
            count = end - start
            part = wave[:, start:end]
            if count < CHUNK:
                part = np.pad(part, ((0, 0), (0, CHUNK - count)),
                              mode="reflect" if count > CHUNK // 2 else "constant")
            if index % 5 == 0 or index == blocks - 1:
                stage(f"SCNet（{device.upper()}）正在分离鼓、贝斯与其他乐器 · 分段 {index + 1}/{blocks}")
            estimate = infer_chunk(session, part, window)
            if not np.isfinite(estimate).all():
                raise RuntimeError("SCNet 输出了无效采样。")
            gain = np.ones(CHUNK, dtype=np.float32)
            if index:
                gain[:len(fade)] = fade
            if end < frames:
                gain[-len(fade):] = fade[::-1]
            mixed[..., start:end] += estimate[..., :count] * gain[:count]
            weights[start:end] += gain[:count]
    mixed /= weights
    mixed *= deviation
    return mixed[..., border:border + audio.shape[1]]


def separate_instruments(audio, work_dir, model_dir, tools, device, mode, stage, metrics, auto_fallback):
    import soundfile as sf

    start = time.perf_counter()
    weights = cached_weights(model_dir, stage)
    stage(f"正在初始化 SCNet · {device.upper()}")
    load_start = time.perf_counter()
    try:
        session = open_session(weights, device)
    except Exception as error:
        if device != "cuda" or not auto_fallback:
            raise
        logging.warning("SCNet CUDA 初始化失败，回退 CPU: %s", error)
        stage("SCNet 无法初始化 ONNX CUDA，正在使用 CPU。")
        device = "cpu"
        session = open_session(weights, device)
    metrics.update(instrument_device=device, load_seconds=time.perf_counter() - load_start,
                   prepare_seconds=time.perf_counter() - start)
    inference_start = time.perf_counter()
    decoded = work_dir / "scnet_input.wav"
    run_tool([tools["ffmpeg"], "-nostdin", "-v", "error", "-xerror", "-n", "-i", str(audio),
              "-map", "0:a:0", "-ac", "2", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_f32le", str(decoded)])
    mix, _ = sf.read(decoded, dtype="float32", always_2d=True)
    tracks = demix(session, mix.T, device, mode, stage)
    stems = {}
    for label, track in zip(SCNET_LABELS, tracks):
        stems[label] = work_dir / f"{label}.wav"
        sf.write(stems[label], track.T, SAMPLE_RATE, subtype="FLOAT")
    metrics["inference_seconds"] = time.perf_counter() - inference_start
    return stems
