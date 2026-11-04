"""Verified against audio-separator v0.48.0 and the UVR public model list."""
DEFAULT_MODEL = "UVR_MDXNET_KARA_2.onnx"
MODELS = {
    DEFAULT_MODEL: ("默认 · Karaoke 2（保留原效果）", "MDX"),
    "UVR-MDX-NET-Voc_FT.onnx": ("Voc FT · MDX-Net（通用人声，对比效果）", "MDX"),
    "UVR-MDX-NET-Inst_HQ_3.onnx": ("Inst HQ 3 · MDX-Net（侧重伴奏，对比效果）", "MDX"),
    "htdemucs.yaml": ("htdemucs · Demucs v4（四轨分离，合成伴奏；较慢）", "Demucs"),
}
MODEL_CHOICES = [(f"{label} — {filename}", filename) for filename, (label, _) in MODELS.items()]


def check_model(model):
    if model not in MODELS:
        raise ValueError("请选择列表中已核实的 AI 模型。")
    return MODELS[model][1]
