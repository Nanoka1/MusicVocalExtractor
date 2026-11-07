"""在纯人声 WAV 上运行 UVR 团队的 BVE v1。"""
from separate import named_stems, prepare_model
from gpu_runtime import validate_loaded_device

BVE_MODEL = "UVR-BVE-4B_SN-44100-1.pth"
VOCAL_LABELS = ("LeadVocals", "BackingVocals")


def split_vocals(Separator, audio, work_dir, model_dir, device, stage):
    import torch

    work_dir.mkdir()
    separator = Separator(model_file_dir=str(model_dir), output_dir=str(work_dir),
                          output_format="WAV", use_autocast=False,
                          vr_params={"batch_size": 1, "window_size": 512})
    if device == "cpu":
        separator.torch_device = torch.device("cpu")
        separator.onnx_execution_provider = ["CPUExecutionProvider"]
    stage(f"正在准备主唱与和声模型：{BVE_MODEL}（{device.upper()}）")
    prepare_model(separator, BVE_MODEL, stage, arch="VR")
    model = separator.model_instance
    if not model.is_bv_model or model.primary_stem_name != "Vocals" or model.secondary_stem_name != "Instrumental":
        raise RuntimeError("BVE 模型元数据与已核实的轨道定义不一致。")

    # UVR 的 BVE 主掩膜预测背景人声，互补掩膜保留主唱。引擎沿用通用标签。
    names = {"Vocals": "BackingVocals", "Instrumental": "LeadVocals"}
    stage(f"正在从人声音轨提取主唱与背景和声（{device.upper()}）")
    with torch.inference_mode():
        returned = separator.separate(str(audio), custom_output_names=names)
    # VR 后端在首次推理时才载入权重，实际设备须在此处核对。
    validate_loaded_device(separator, "VR", device)
    return named_stems(returned, work_dir, VOCAL_LABELS)
