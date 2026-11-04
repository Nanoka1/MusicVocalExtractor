# 模型和接口核实记录

核实日期：2026-11-04。项目及本机安装均使用 **audio-separator 0.48.0**；没有升级分离引擎。

来源：

- [Audio Separator v0.48.0 源码](https://github.com/nomadkaraoke/python-audio-separator/tree/v0.48.0)，检查版本提交 `4dd3477c0a8f5bfb0fb053c6ed444bb935cb150e`。
- [UVR 官方模型清单](https://github.com/TRvlvr/application_data/blob/main/filelists/download_checks.json)。
- [UVR MDX 参数](https://github.com/TRvlvr/application_data/blob/main/mdx_model_data/model_data_new.json)。
- [官方 SHA-256 清单](https://github.com/nomadkaraoke/python-audio-separator/blob/v0.48.0/audio_separator/model-checksums.json)。

| 模型准确文件名 | 架构 | 原生主轨/输出 | 模型参数 |
|---|---|---|---|
| `UVR_MDXNET_KARA_2.onnx`（原默认） | MDX-Net / ONNX | 主轨 Instrumental，互补 Vocals | dim_f=2048, dim_t=8, n_fft=5120, compensate=1.065, is_karaoke=true |
| `UVR-MDX-NET-Voc_FT.onnx` | MDX-Net / ONNX | 主轨 Vocals，互补 Instrumental | dim_f=3072, dim_t=8, n_fft=7680, compensate=1.021 |
| `UVR-MDX-NET-Inst_HQ_3.onnx` | MDX-Net / ONNX | 主轨 Instrumental，互补 Vocals | dim_f=3072, dim_t=8, n_fft=6144, compensate=1.022 |
| `htdemucs.yaml` | Demucs v4 / Hybrid Transformer | Vocals, Drums, Bass, Other | YAML: `models: ['955717e8']`；权重 `955717e8-8726e21a.th` |

不手工硬编码 MDX 模型内部参数；由引擎用模型哈希读取官方参数。保留引擎运行默认值：MDX hop_length=1024、segment_size=256、overlap=0.25、batch_size=1、enable_denoise=false；Demucs segment_size=Default、shifts=2、overlap=0.25、segments_enabled=true；输出采样率沿用原来的 44100 Hz。

`Separator.list_supported_model_files()` 在运行时确认架构和准确文件名；`download_model_and_data()` 下载并准备参数；`load_model()` 加载。下载由官方引擎先尝试其 GitHub release 镜像，再回退 UVR release 或 Meta CDN。已有文件通过 SHA-256 后复用，新文件经 `.partial` 完整性校验后原子改名。不替换第三方下载代码；本项目额外在下载前检查损坏缓存并报错保留，避免引擎自行删除旧的损坏文件。

`custom_output_names` 以语义标签指定路径，随后从返回路径的名称映射，完全不依赖返回顺序。Demucs 伴奏为 Drums + Bass + Other，通过 FFmpeg `amix=inputs=3:normalize=0` 相加并写 PCM 24-bit WAV，再按用户选择导出；不把 Other 当作伴奏。

核实 `Separator.separate()` 没有统一进度回调或任务状态 API。MDX/Demucs 内部有局部 tqdm 循环，下载也有字节进度，但不能据此得出统一的任务总百分比。本项目使用真实阶段回调和 Gradio 不确定进度条 `Progress(None)`；没有计时百分比，没有修改第三方库源码。推理阶段同时包含引擎原生 WAV 写出，后续才进入本项目的合成伴奏/格式导出及 FFprobe 检查。

Audio Separator 支持 `output_bitrate`，但通用导出接口未显式固定 `libmp3lame`。因此继续使用原 WAV 导出，再由 FFmpeg 参数列表 `-c:a libmp3lame -b:a 320k` 编码一次。没有 shell 命令字符串拼接。试听使用与下载一致的结果文件。

真实测试日志：`.tools/model-tests.log`；机器可读报告：`test_artifacts/中文 测试 & 音频/model-test-report.json`。三秒合成信号用于验证加载、执行、映射、时长、编码和可解码性，不能代替真实歌曲音质的人工试听。
