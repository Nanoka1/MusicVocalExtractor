# 第三方来源与分发边界

根目录 MIT 许可证仅适用于本项目拥有版权的代码，不替代依赖、模型、音频的许可证。

| 组件 | 许可 / 官方来源 |
| --- | --- |
| Audio Separator | MIT；https://github.com/nomadkaraoke/python-audio-separator |
| Kim MelBand RoFormer 权重 | 作者权重卡标注 MIT；https://huggingface.co/KimberleyJSN/melbandroformer 。通过 MIT 的 Audio Separator 推理，不复制作者 GitHub 仓库源码；原始权重与镜像 SHA-256 一致。详见 [MODEL_RESEARCH.md](MODEL_RESEARCH.md) |
| Ultimate Vocal Remover (UVR) | MIT 代码；感谢 Anjok07、UVR 开发者以及 MDX-Net 作者 Kuielab、Woosung Choi；https://github.com/Anjok07/ultimatevocalremovergui |
| Demucs | MIT 代码；Copyright Meta Platforms, Inc. and affiliates；https://github.com/facebookresearch/demucs |
| PyTorch / torchvision | BSD 类许可证；https://github.com/pytorch/pytorch 、https://github.com/pytorch/vision |
| librosa | ISC；https://github.com/librosa/librosa |
| ONNX Runtime | MIT；https://github.com/microsoft/onnxruntime |
| Gradio | Apache-2.0；https://github.com/gradio-app/gradio |
| PyInstaller | GPL 并附带引导程序分发例外；https://pyinstaller.org/en/stable/license.html |
| FFmpeg / FFprobe | 取决于构建选项；见 [FFMPEG_NOTICE.md](FFMPEG_NOTICE.md) 和 https://ffmpeg.org/legal.html |

本表用于说明来源，不是完整二进制发行许可包。发布 EXE 前还需收集实际打包的所有直接和传递依赖的许可证、版权及适用 NOTICE，满足相应源码提供要求；仅复制本文件不足以完成再分发合规。

源码仓库不包含模型权重、歌曲、FFmpeg 或 EXE。模型选择和校验成功不等于获得再分发或商业使用授权；必须按具体权重发布页面确认条件，不能将代码的 MIT 许可证自动套用于全部模型。构建默认不复制模型；仅个人自用需要复用缓存时显式使用 `-IncludeCachedModels`，不删除原缓存。自动下载与模型选择继续可用。

用户应只处理有权使用的音频，分离结果不改变原作品的版权。
