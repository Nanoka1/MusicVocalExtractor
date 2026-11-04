"""简单的本地 Gradio 界面，调用已有的人声分离功能。"""

import logging
import gradio as gr

from separate import PROJECT_DIR, separate_audio


OUTPUT_DIR = PROJECT_DIR / "outputs"


def extract_vocals(audio_path):
    """先清空旧结果并显示进度，完成后显示本次文件。"""
    if not audio_path:
        yield None, None, "请先选择一个音乐文件。"
        return

    yield None, None, "正在分离，请稍候。首次使用需要下载模型，CPU 处理可能较慢。"
    try:
        vocals, instrumental = separate_audio(audio_path, OUTPUT_DIR)
    except Exception as error:
        logging.exception("音频分离失败")
        yield None, None, f"分离失败：{error}"
        return

    yield str(vocals), str(instrumental), f"分离完成！文件已保存到：{vocals.parent}"


def create_app():
    with gr.Blocks(title="MusicVocalExtractor", analytics_enabled=False) as demo:
        gr.Markdown("# MusicVocalExtractor\n选择音乐，一键提取人声和伴奏。")
        audio = gr.File(
            label="选择音乐文件（MP3、WAV、FLAC、M4A）",
            file_types=[".mp3", ".wav", ".flac", ".m4a"],
            type="filepath",
        )
        start = gr.Button("开始分离", variant="primary")
        status = gr.Textbox(label="处理状态", value="请选择音乐文件，然后点击“开始分离”。", interactive=False)
        with gr.Row():
            vocals = gr.File(label="人声 Vocals · 点击下载", interactive=False)
            instrumental = gr.File(label="伴奏 Instrumental · 点击下载", interactive=False)
        gr.Markdown("结果自动保存到程序目录的 **outputs** 文件夹。处理期间请保持启动窗口打开。")
        start.click(
            extract_vocals,
            inputs=audio,
            outputs=[vocals, instrumental, status],
            concurrency_limit=1,
            api_name="separate",
        )
    return demo


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    create_app().queue(max_size=8).launch(
        server_name="127.0.0.1",
        inbrowser=True,
        share=False,
        allowed_paths=[str(OUTPUT_DIR)],
    )
