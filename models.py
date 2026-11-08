"""Verified against audio-separator v0.48.0 and the UVR public model list."""
ROFORMER_MODEL = "vocals_mel_band_roformer.ckpt"
DEFAULT_MODEL = ROFORMER_MODEL
REMOVED_MODELS = frozenset({"UVR-MDX-NET-Voc_FT.onnx", "UVR-MDX-NET-Inst_HQ_3.onnx"})
MODELS = {
    ROFORMER_MODEL: ("默认 · MelBand RoFormer · Kim（高质量人声，CPU 较慢）", "MDXC"),
}
MODEL_CHOICES = [(f"{label} — {filename}", filename) for filename, (label, _) in MODELS.items()]


def check_model(model):
    if model in REMOVED_MODELS:
        raise ValueError(f"模型 {model} 已停用，请选择 {DEFAULT_MODEL}；不会重新下载已停用模型。")
    if model not in MODELS:
        raise ValueError("请选择列表中已核实的 AI 模型。")
    return MODELS[model][1]
