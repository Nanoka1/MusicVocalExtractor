# 模型和接口核实记录

核实日期：2026-11-05。项目及本机安装均使用 **audio-separator 0.48.0**；没有升级分离引擎。

来源：

- [Audio Separator v0.48.0 源码](https://github.com/nomadkaraoke/python-audio-separator/tree/v0.48.0)，检查版本提交 `4dd3477c0a8f5bfb0fb053c6ed444bb935cb150e`。
- [UVR 官方模型清单](https://github.com/TRvlvr/application_data/blob/main/filelists/download_checks.json)。
- [UVR MDX 参数](https://github.com/TRvlvr/application_data/blob/main/mdx_model_data/model_data_new.json)。
- [官方 SHA-256 清单](https://github.com/nomadkaraoke/python-audio-separator/blob/v0.48.0/audio_separator/model-checksums.json)。

| 模型准确文件名 | 架构 | 原生主轨/输出 | 模型参数 |
|---|---|---|---|
| `UVR-MDX-NET-Voc_FT.onnx` | MDX-Net / ONNX | 主轨 Vocals，互补 Instrumental | dim_f=3072, dim_t=8, n_fft=7680, compensate=1.021 |
| `UVR-MDX-NET-Inst_HQ_3.onnx` | MDX-Net / ONNX | 主轨 Instrumental，互补 Vocals | dim_f=3072, dim_t=8, n_fft=6144, compensate=1.022 |
| `vocals_mel_band_roformer.ckpt` | MelBand RoFormer / MDXC / PyTorch | vocals，完整非人声 other | `vocals_mel_band_roformer.yaml`：dim=384、depth=6、num_bands=60、chunk_size=352800、num_overlap=1、sample_rate=44100 |

不手工硬编码 MDX 模型内部参数；由引擎用模型哈希读取官方参数。保留引擎运行默认值：MDX hop_length=1024、segment_size=256、overlap=0.25、batch_size=1、enable_denoise=false；输出采样率沿用原来的 44100 Hz。

`Separator.list_supported_model_files()` 在运行时确认架构和准确文件名；`download_model_and_data()` 下载并准备参数；`load_model()` 加载。下载由官方引擎先尝试其 GitHub release 镜像，再回退 UVR release 或 Meta CDN。已有文件通过 SHA-256 后复用，新文件经 `.partial` 完整性校验后原子改名。不替换第三方下载代码；本项目额外在下载前检查损坏缓存并报错保留，避免引擎自行删除旧的损坏文件。

`custom_output_names` 以语义标签指定路径，随后从返回路径的名称映射，不依赖返回顺序。移除 Karaoke 2 和 htdemucs 可用选项及专用四轨合成，保留两个 MDX 模型；默认 Voc FT。缓存不删除。

核实 `Separator.separate()` 没有统一进度回调或任务状态 API。引擎 内部有局部 tqdm 循环，下载也有字节进度，但不能据此得出统一的任务总百分比。本项目使用真实阶段回调和 Gradio 不确定进度条 `Progress(None)`；没有计时百分比，没有修改第三方库源码。推理阶段同时包含引擎原生 WAV 写出，后续才进入本项目的格式导出及 FFprobe 检查。

Audio Separator 支持 `output_bitrate`，但通用导出接口未显式固定 `libmp3lame`。因此继续使用原 WAV 导出，再由 FFmpeg 参数列表 `-c:a libmp3lame -b:a 320k` 编码一次。没有 shell 命令字符串拼接。试听使用与下载一致的结果文件。

真实测试日志：`.tools/model-tests.log`；机器可读报告：`test_artifacts/中文 测试 & 音频/model-test-report.json`。三秒合成信号用于验证加载、执行、映射、时长、编码和可解码性，不能代替真实歌曲音质的人工试听。

成功结果目录按上传原名命名，只含两条最终音轨。临时 WAV 位于独立 cache/separation/work_*；两轨通过 FFprobe、声道/采样率和完整解码检查后发布，随后清理工作目录。失败保留恢复材料并返回错误。

Kim 的 YAML 将两轨命名为 vocals/other。仅对准确文件名 `vocals_mel_band_roformer.ckpt` 增加 `other -> Instrumental` 自定义输出名；这是完整伴奏，不是四轨模型的 Other，不进行四轨合成。MDX 保持原语义映射。引擎 MDXC 加载失败可能抛出 SystemExit，本项目转为可见错误，避免 Gradio 工作线程退出后无限等待。

本次不升级依赖：audio-separator 0.48.0 原生支持该模型和配置，CPU/GPU 依赖文件沿用原固定版本；不额外安装 bs-roformer 或另一套训练/推理引擎。新权重首次通过官方镜像实际下载并校验；原作者文件的 SHA-256 已核对一致。许可证与完整来源见 [MODEL_RESEARCH.md](MODEL_RESEARCH.md)，测试范围见 [UPGRADE_VERIFICATION.md](UPGRADE_VERIFICATION.md)。默认 Voc FT 保留，真实歌曲音质未完成本机验证。
