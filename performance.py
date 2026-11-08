"""Model-specific, bounded inference settings for audio-separator 0.48.0."""
from models import ROFORMER_MODEL

MODES = {"quality": "高质量模式", "balanced": "平衡模式", "fast": "快速模式"}
MODE_CHOICES = [(label, key) for key, label in MODES.items()]


def inference_options(model, mode, device, free_bytes=None):
    if mode not in MODES:
        raise ValueError("请选择高质量、平衡或快速模式。")
    if model != ROFORMER_MODEL:
        # MDX uses ONNX, not RoFormer chunking or PyTorch autocast.
        return {"mdx_params": {"hop_length": 1024, "segment_size": 256, "batch_size": 1,
                               "overlap": {"quality": 0.5, "balanced": 0.25, "fast": 0.1}[mode],
                               "enable_denoise": False}}
    # stft_hop_length=441; 801 frames => model author's recommended 8s chunks.
    segment = 801
    if device == "cuda" and free_bytes is not None:
        if free_bytes < 3 * 1024**3:
            segment = 301
        elif free_bytes < 5 * 1024**3:
            segment = 501
    return {"use_autocast": device == "cuda" and mode != "quality",
            "use_native_fp16": False, "use_torch_compile": False,
            "mdxc_params": {"segment_size": segment, "override_model_segment_size": True,
                            "batch_size": 1, "overlap": {"quality": 4, "balanced": 2, "fast": 1}[mode],
                            "pitch_shift": 0}}


def observe_forward(separator, device, metrics):
    """Check actual forward device/finite values without trusting log labels."""
    import torch
    model = separator.model_instance.model_run

    def before(module, args):
        if next(module.parameters()).device.type != device or args[0].device.type != device:
            raise RuntimeError("模型前向张量设备与请求设备不一致。")
        metrics["autocast_active"] = torch.is_autocast_enabled("cuda") if device == "cuda" else False

    def after(module, args, output):
        if not torch.isfinite(output).all().item():
            raise FloatingPointError("模型产生 NaN/Inf；结果未发布。请使用高质量 FP32 模式重试。")
        metrics["forward_calls"] = metrics.get("forward_calls", 0) + 1
        metrics["forward_device"] = output.device.type

    return [model.register_forward_pre_hook(before), model.register_forward_hook(after)]


def infer_with_retry(separator, audio, names, work_dir, model_name, device, metrics, stage):
    import gc
    import torch
    from models import ROFORMER_MODEL
    from gpu_runtime import validate_loaded_device
    active_dir = work_dir
    started_segment = getattr(getattr(separator, "model_instance", None), "segment_size", 0)
    for attempt in range(2):
        handles = observe_forward(separator, device, metrics) if model_name == ROFORMER_MODEL else []
        retry = False
        try:
            with torch.inference_mode():
                returned = separator.separate(str(audio), custom_output_names=names)
            return returned, active_dir
        except RuntimeError as error:
            message = str(error).lower()
            oom = isinstance(error, torch.cuda.OutOfMemoryError) or ("cuda" in message and "out of memory" in message)
            if not oom:
                raise
            if device != "cuda" or model_name != ROFORMER_MODEL or attempt or started_segment <= 256:
                raise RuntimeError("CUDA 显存不足；已停止，未发布不完整结果。请关闭其他 GPU 程序或主动选择 CPU。") from error
            retry = True
        finally:
            for handle in handles:
                handle.remove()
        if retry:
            # The exception traceback is now released before clearing cached allocations.
            gc.collect()
            torch.cuda.empty_cache()
            active_dir = work_dir / "oom_retry"
            active_dir.mkdir()
            separator.output_dir = str(active_dir)
            separator.model_instance.output_dir = str(active_dir)
            segment = max(256, started_segment // 2)
            separator.model_instance.segment_size = segment
            separator.model_instance.override_model_segment_size = True
            validate_loaded_device(separator, "MDXC", device)
            metrics.update(oom_retries=1, effective_segment_size=segment)
            stage(f"CUDA 显存不足：batch_size 已为 1；将 segment_size 降为 {segment}，仅重试一次，继续使用 GPU。")
    raise RuntimeError("推理重试未完成。")


def format_metrics(metrics):
    return (f"推理设备：{metrics['name']}（{metrics['device'].upper()}）\n"
            f"性能模式：{MODES[metrics['mode']]}\n"
            f"模型检查/下载/加载：{metrics['prepare_seconds']:.2f} 秒（其中加载 {metrics.get('load_seconds', 0):.2f} 秒）\n"
            f"AI 分离（含解码及 WAV 写出）：{metrics['inference_seconds']:.2f} 秒\n"
            f"音频导出及验证：{metrics['export_seconds']:.2f} 秒\n总耗时：{metrics['total_seconds']:.2f} 秒"
            + (f"\nPyTorch 峰值分配显存：{metrics['peak_bytes'] / 1024**3:.2f} GiB" if metrics['device'] == 'cuda' else ''))
