"""Local Gradio UI: real stages, model selection, preview and downloads."""
import logging
import os
import queue
import threading

from runtime_paths import DATA_DIR, OUTPUT_DIR, SOURCE_DIR

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("GRADIO_TEMP_DIR", str(DATA_DIR / "cache" / "gradio"))

import gradio as gr

from models import DEFAULT_MODEL, MODEL_CHOICES, TRACK_LABELS
from separate import separate_audio
from gpu_runtime import hardware_status
from performance import MODE_CHOICES, MODES, format_metrics
from audio_gain import format_gain_report
from mix_tracks import mix_manifest, saved_mixes
from vocal_split import BVE_MODEL


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
    # 保留原有 /separate 接口的两条下载和两条试听输出。
    for paths, status in separation_updates(audio_path, model_name, output_format, performance_mode,
                                            device, vocal_gain_db, instrumental_gain_db, progress):
        vocals, instrumental = map(str, paths) if paths else (None, None)
        yield vocals, instrumental, status, vocals, instrumental


def separation_updates(audio_path, model_name, output_format, performance_mode, device,
                       vocal_gain_db, instrumental_gain_db, progress, prepare_mix=False, split_backing=False):
    if not audio_path:
        yield None, "请先选择一个音乐文件。"
        return
    events = queue.Queue()
    active_models = f"{model_name} → {BVE_MODEL}" if split_backing else model_name

    def worker():
        try:
            stats = {}
            result = separate_audio(audio_path, OUTPUT_DIR, model_name=model_name, output_format=output_format,
                                    original_name=getattr(audio_path, "original_name", None),
                                    performance_mode=performance_mode, device=device, vocal_gain_db=vocal_gain_db,
                                    instrumental_gain_db=instrumental_gain_db, prepare_mix=prepare_mix,
                                    split_backing=split_backing,
                                    metrics_callback=stats.update,
                                    progress_callback=lambda message: events.put(("stage", message)))
            events.put(("done", (result, stats)))
        except Exception as error:
            logging.exception("音频分离失败")
            events.put(("error", str(error)))

    yield None, f"模型：{active_models}\n正在检查音频文件"
    threading.Thread(target=worker, daemon=True, name="audio-separation").start()
    while True:
        kind, payload = events.get()
        if kind == "stage":
            progress(None, desc=payload)
            yield None, f"模型：{active_models}\n{payload}"
        elif kind == "error":
            yield None, f"模型：{active_models}\n分离失败：{payload}"
            return
        else:
            paths, stats = payload
            gains = stats["stem_gains"]
            files = "\n".join(f"{TRACK_LABELS[label]}：{path.name}" for label, path in zip(gains, paths))
            reports = "\n".join(format_gain_report(report, TRACK_LABELS[label]) for label, report in gains.items())
            used_models = f"{stats['model']} → {stats['vocal_model']}" if split_backing else stats["model"]
            status = (f"分离完成！\n歌曲：{paths[0].parent.name}\n{files}\n"
                      f"保存位置：{paths[0].parent}\n模型：{used_models}\n{reports}\n{format_metrics(stats)}")
            if split_backing:
                status += f"\n和声推理设备：{stats['vocal_device'].upper()}，模型阶段 {stats['vocal_seconds']:.2f} 秒"
            yield paths, status
            return


def extract_for_mixer(audio_path, model_name, output_format, performance_mode, device,
                      vocal_gain_db, instrumental_gain_db, mode="two", progress=gr.Progress()):
    for paths, status in separation_updates(audio_path, model_name, output_format, performance_mode,
                                            device, vocal_gain_db, instrumental_gain_db, progress,
                                            prepare_mix=True, split_backing=mode == "vocals"):
        if not paths:
            yield None, status, None, gr.skip()
            continue
        name = paths[0].parent.name
        yield list(map(str, paths)), status, mix_manifest(OUTPUT_DIR, name), gr.update(
            choices=saved_mixes(OUTPUT_DIR), value=name)


def load_mix(name):
    try:
        return mix_manifest(OUTPUT_DIR, name)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise gr.Error(f"无法载入混音：{error}") from error


def refresh_history():
    return gr.update(choices=saved_mixes(OUTPUT_DIR), value=None)


def create_app():
    with gr.Blocks(title="MusicVocalExtractor", analytics_enabled=False) as demo:
        gr.Markdown("# MusicVocalExtractor\n分离音乐并同步试听各音轨。所有音频处理均在本机完成。")
        gr.Textbox(label="当前输出目录", value=str(OUTPUT_DIR), interactive=False)
        audio = UploadedAudio(label="选择音乐文件（MP3、WAV、FLAC、M4A）",
                        file_types=[".mp3", ".wav", ".flac", ".m4a"], type="filepath")
        model = gr.Dropdown(label="选择 AI 分离模型", choices=MODEL_CHOICES, value=DEFAULT_MODEL)
        mode = gr.Radio(label="分离模式", choices=[("人声与伴奏", "two"), ("主唱与和声", "vocals")], value="two",
                        info=f"主唱与和声模式先分离人声，再由 {BVE_MODEL} 处理，伴奏保留为一轨。")
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
        gr.Markdown("导出增益在分离前设置，正增益启用峰值保护。主唱与和声沿用人声导出增益。下方混音器可独立调整各轨试听音量。")
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
        downloads = gr.File(label="本次分离结果 · 点击下载", file_count="multiple", interactive=False)
        gr.Markdown(f"结果保存到 **{OUTPUT_DIR}**，每次任务使用独立目录。首次使用模型需要联网下载。处理期间请保持启动窗口打开。")
        with gr.Row():
            history = gr.Dropdown(label="已保存的混音", choices=saved_mixes(OUTPUT_DIR), scale=4)
            load = gr.Button("载入混音")
            refresh = gr.Button("刷新列表")
        mixer = gr.HTML(
            html_template=(SOURCE_DIR / "mixer.html").read_text(encoding="utf-8"),
            css_template=(SOURCE_DIR / "mixer.css").read_text(encoding="utf-8"),
            js_on_load=(SOURCE_DIR / "mixer.js").read_text(encoding="utf-8"),
        )
        load.click(load_mix, inputs=history, outputs=mixer, queue=False, api_visibility="private")
        refresh.click(refresh_history, outputs=history, queue=False, api_visibility="private")
        demo.load(refresh_history, outputs=history, queue=False, api_visibility="private")
        inputs = [audio, model, output_format, performance, device, gain, instrumental_gain]
        start.click(extract_for_mixer, inputs=[*inputs, mode], outputs=[downloads, status, mixer, history],
                    concurrency_limit=1, concurrency_id="separation", api_name="mix")
        # 单独保留已有 HTTP 接口，界面试听统一交给多轨播放器。
        with gr.Column(visible=False):
            legacy = gr.Button("两轨 API")
            vocals, instrumental = gr.File(), gr.File()
            legacy_status = gr.Textbox()
            vocals_player, instrumental_player = gr.Audio(format=None), gr.Audio(format=None)
        legacy.click(extract_vocals, inputs=inputs,
                     outputs=[vocals, instrumental, legacy_status, vocals_player, instrumental_player],
                     concurrency_limit=1, concurrency_id="separation", api_name="separate")
    return demo


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    create_app().queue(max_size=8).launch(server_name="127.0.0.1", inbrowser=os.environ.get("MVE_NO_BROWSER") != "1", share=False,
                                        allowed_paths=[str(OUTPUT_DIR)])


if __name__ == "__main__":
    main()
