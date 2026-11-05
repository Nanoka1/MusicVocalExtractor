"""Verified against audio-separator v0.48.0 and the UVR public model list."""
DEFAULT_MODEL = "UVR-MDX-NET-Voc_FT.onnx"
MODELS = {
    DEFAULT_MODEL: ("默认 · Voc FT · MDX-Net（通用人声）", "MDX"),
    "UVR-MDX-NET-Inst_HQ_3.onnx": ("Inst HQ 3 · MDX-Net（侧重伴奏，对比效果）", "MDX"),
}
MODEL_CHOICES = [(f"{label} — {filename}", filename) for filename, (label, _) in MODELS.items()]


def check_model(model):
    if model not in MODELS:
        raise ValueError("请选择列表中已核实的 AI 模型。")
    return MODELS[model][1]
