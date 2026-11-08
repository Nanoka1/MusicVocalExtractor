"""Local Gradio UI: real stages, model selection, preview and downloads."""
import logging
import os
import queue
import threading

from runtime_paths import DATA_DIR, OUTPUT_DIR

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("GRADIO_TEMP_DIR", str(DATA_DIR / "cache" / "gradio"))

import gradio as gr

from models import DEFAULT_MODEL, MODEL_CHOICES
from separate import separate_audio
from gpu_runtime import hardware_status
from performance import MODE_CHOICES, MODES, format_metrics
from audio_gain import format_gain_report


class UploadedAudio(gr.File):
    """Preserve FileData.orig_name before Gradio converts it to NamedString."""
    is_template = True  # Reuse Gradio's built-in File frontend, including frozen builds.

    def preprocess(self, payload):
        path = super().preprocess(payload)
        if path is not None:
            path.original_name = payload.orig_name or os.path.basename(path)
        return path


def extract_vocals(audio_path, model_name=DEFAULT_MODEL, output_format="MP3", performance_mode="balanced",
                   device="auto", vocal_gain_db=0, instrumental_gain_db=0, progress=gr.Progress()):
    if not audio_path:
        yield None, None, "请先选择一个音乐文件。", None, None
        return
    events = queue.Queue()

    def worker():
        try:
            stats = {}
            result = separate_audio(audio_path, OUTPUT_DIR, model_name=model_name, output_format=output_format,
                                    original_name=getattr(audio_path, "original_name", None),
                                    performance_mode=performance_mode, device=device, vocal_gain_db=vocal_gain_db,
                                    instrumental_gain_db=instrumental_gain_db,
                                    metrics_callback=stats.update,
                                    progress_callback=lambda message: events.put(("stage", message)))
            events.put(("done", (result, stats)))
        except Exception as error:
            logging.exception("音频分离失败")
            events.put(("error", str(error)))

    yield None, None, f"模型：{model_name}\n正在检查音频文件", None, None
    threading.Thread(target=worker, daemon=True, name="audio-separation").start()
    while True:
        kind, payload = events.get()
        if kind == "stage":
            progress(None, desc=payload)
            yield None, None, f"模型：{model_name}\n{payload}", None, None
        elif kind == "error":
            yield None, None, f"模型：{model_name}\n分离失败：{payload}", None, None
            return
        else:
            paths, stats = payload
            vocals, instrumental = map(str, paths)
            yield vocals, instrumental, (f"分离完成！\n歌曲：{paths[0].parent.name}\n"
                                        f"人声：{paths[0].name}\n伴奏：{paths[1].name}\n"
                                        f"保存位置：{paths[0].parent}\n模型：{stats.get('model', model_name)}\n"
                                        f"{format_gain_report(stats.get('stem_gains', {}).get('Vocals', {}), '人声')}\n"
                                        f"{format_gain_report(stats.get('stem_gains', {}).get('Instrumental', {}), '伴奏')}\n"
                                        f"{format_metrics(stats)}"), vocals, instrumental
            return


def create_app():
    with gr.Blocks(title="MusicVocalExtractor", analytics_enabled=False) as demo:
        gr.Markdown("# MusicVocalExtractor\n选择音乐，提取人声和伴奏。所有音频处理均在本机完成。")
        gr.Textbox(label="当前输出目录", value=str(OUTPUT_DIR), interactive=False)
        audio = UploadedAudio(label="选择音乐文件（MP3、WAV、FLAC、M4A）",
                        file_types=[".mp3", ".wav", ".flac", ".m4a"], type="filepath")
        model = gr.Dropdown(label="选择 AI 分离模型", choices=MODEL_CHOICES, value=DEFAULT_MODEL)
        output_format = gr.Dropdown(label="输出音频格式", choices=[("MP3（320 kbps）", "MP3"), ("WAV（无损 PCM）", "WAV")], value="MP3")
        with gr.Row():
            with gr.Column():
                gain_label = gr.Markdown("**人声增益：+0.0 dB**")
                gain = gr.Slider(minimum=0, maximum=12, value=0, step=0.1, label="人声增益（dB）")
            with gr.Column():
                instrumental_gain_label = gr.Markdown("**伴奏增益：+0.0 dB**")
                instrumental_gain = gr.Slider(minimum=0, maximum=12, value=0, step=0.1, label="伴奏增益（dB）")
        gain.change(lambda value: f"**人声增益：+{value:.1f} dB**", inputs=gain, outputs=gain_label,
                    queue=False, api_name=False)
        instrumental_gain.change(lambda value: f"**伴奏增益：+{value:.1f} dB**", inputs=instrumental_gain,
                                 outputs=instrumental_gain_label, queue=False, api_name=False)
        gr.Markdown("两条音轨独立调整，均为 0～+12 dB。0 dB 保持原输出；正增益启用峰值保护，结果显示实际峰值。请在分离前设置，修改后需重新开始分离。")
        performance = gr.Dropdown(label="AI 分离性能模式", choices=MODE_CHOICES, value="balanced")
        device = gr.Dropdown(label="推理设备", choices=[("自动检测", "auto"), ("CUDA GPU（不可用时报错）", "cuda"), ("CPU", "cpu")], value=os.environ.get("MVE_DEVICE", "auto"))
        hardware = gr.Textbox(label="GPU 加速状态", value=hardware_status(), interactive=False)
        gr.Markdown("高质量优先使用 FP32 和更多重叠；平衡/快速在 CUDA 下使用混合精度，快速模式减少重叠，可能产生音质差异。显存不足最多降低分段重试一次。")
        def show_hardware(model_name, mode, requested):
            return f"{hardware_status()}\n模型：{model_name}\n性能模式：{MODES[mode]}\n请求设备：{requested}（本次实际设备见处理状态）"
        for component in (model, performance, device):
            component.change(show_hardware, inputs=[model, performance, device], outputs=hardware, api_name=False)
        start = gr.Button("开始分离", variant="primary")
        status = gr.Textbox(label="处理状态", value="请选择音乐文件，然后点击“开始分离”。", interactive=False)
        with gr.Row():
            vocals_player = gr.Audio(label="人声 Vocals · 试听", type="filepath", interactive=False, format=None)
            instrumental_player = gr.Audio(label="伴奏 Instrumental · 试听", type="filepath", interactive=False, format=None)
        with gr.Row():
            vocals = gr.File(label="人声 Vocals · 点击下载", interactive=False)
            instrumental = gr.File(label="伴奏 Instrumental · 点击下载", interactive=False)
        gr.Markdown(f"结果保存到 **{OUTPUT_DIR}**，每次任务使用独立目录。首次使用模型需要联网下载。处理期间请保持启动窗口打开。")
        start.click(extract_vocals, inputs=[audio, model, output_format, performance, device, gain, instrumental_gain],
                    outputs=[vocals, instrumental, status, vocals_player, instrumental_player],
                    concurrency_limit=1, concurrency_id="separation", api_name="separate")
    return demo


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    create_app().queue(max_size=8).launch(server_name="127.0.0.1", inbrowser=os.environ.get("MVE_NO_BROWSER") != "1", share=False,
                                        allowed_paths=[str(OUTPUT_DIR)])


if __name__ == "__main__":
    main()
