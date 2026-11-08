# 人声与伴奏独立增益

人声与伴奏的增益范围各为 0～+12 dB，默认 0，支持 0.1 dB 的界面步长及 API 浮点参数。设置会在分离模型完成、两轨语义映射之后，最终 MP3/WAV 导出之前应用，不改变模型、输入混音或其他音轨。两轨同时增加增益也不会在本程序中混合；若之后重新混音，仍需管理相加后的电平。

`audio_gain.py` 使用 `10 ** (dB / 20)` 计算线性振幅系数。+3、+6、+12 dB 分别约为 1.4125、1.9953、3.9811 倍。只有峰值留有足够余量、保护未介入时才会保持这一全程振幅比例；不能在保留满幅上限的同时保证所有高峰也增加 12 dB。

0 dB 完全绕过新处理，不扫描/限幅/重新编码额外 WAV；WAV 使用原文件字节复制，MP3 沿用原 libmp3lame 320 kbps 命令。只调整一轨时，另一轨的导出路径不变。

正增益使用 FFmpeg 双精度音量乘法、4 倍过采样、联动各声道的前瞻 `alimiter`、再回到原采样率；关闭自动补偿增益，前瞻 5 ms、释放 50 ms、上限 -1 dBFS，启用延迟补偿以保留长度和对齐。不使用逐样本硬裁剪或整首归一化。限幅只在峰值附近改变增益包络；极大增益/持续高电平可能减少动态或产生可听变化，不能保证所有歌曲的主观音质无差异。[FFmpeg 官方滤镜说明](https://github.com/FFmpeg/FFmpeg/blob/master/doc/filters.texi)给出了前瞻、延迟补偿、关闭自动电平及过采样的参数依据。

浮点 WAV 仅保留在任务工作目录，避免增益过程先发生整数削波；还会在编码前检查浮点重采样结果，达到满幅就停止，防止整数编码裁剪后掩盖过冲。最终正增益 WAV 为 24-bit PCM；MP3 仍为 libmp3lame 320 kbps。采样率、声道、增益处理前后帧数均核对，MP3 编码后还完整解码验证。解码后峰值达到满幅或出现 NaN/Inf 时停止发布并保留恢复材料，不把编码过冲当成成功；-1 dB 余量和过采样可减少过冲风险，但不是经过认证的 true-peak 响度标准实现。

界面及 CLI 分别报告两轨的用户设置值/线性系数、实际导出采样峰值（dBFS）、限幅器上限，以及峰值相对未限幅理论值降低的 dB 数。最后一项包含限幅及编码影响，**不是**全程实际增益、最大瞬时衰减量或综合响度 LUFS，避免把设置的 +12 dB 与有限峰值电平混为一谈。静音显示“静音”，不出现无效对数。

参数：`--vocal-gain-db` 和 `--instrumental-gain-db`；Python `separate_audio(..., vocal_gain_db=6, instrumental_gain_db=3)`；Gradio `/separate` 同名参数默认 0，原有其他参数顺序保留。拒绝负数、超过 12、NaN/Inf。滑块在分离前设置，当前架构不保存长期原始 stems，因此本轮没有增加分离后的无模型重调功能。

成功后仍仅发布两条最终音轨，并清理本任务全部中间 WAV；失败保留原始未加增益 stems 及已生成的处理文件。歌曲命名、同名冲突、根 outputs/models、CUDA 三模式及缓存机制保持原有行为。

## 验证

`tests/test_audio_gain.py` 使用合成信号及真实 FFmpeg 检查：0 dB 文件不变、3/6/12 dB 低电平振幅比例、独立调整时另一轨字节不变、双轨同时增益、满电平高增益的非硬裁剪限幅、声道比例、44.1/48 kHz、单/双声道、PCM/MP3、静音及非法数值、NaN、解码过冲拒绝、失败恢复和成功清理。`tests/test_app.py` 检查两个滑块范围/默认值，并通过真实 RoFormer HTTP 分离验证人声 +6、伴奏 +12 dB 时的状态、文件名、试听及下载内容一致。完整歌曲的主观听感不在合成测试结论内。

2026-11-06：现有 `.venv` 启用 `RUN_MODEL_TESTS=1`、`RUN_UI_TESTS=1`，完整 CPU 回归 **42 项全部通过，无跳过**；随后新增安全发布的命名回退/路径约束测试，`test_release.py` **7 项通过**（与前述完整回归有重叠，不能相加成一次全量测试）。首轮零增益的跨任务文件字节测试因 FLOAT WAV 创建时间戳不同失败，改为使用完全相同的输入文件后通过，没有放宽音频一致性要求。日志保存在忽略的 `.tools/gain-*.log`。

最终安全复核额外加入编码前的浮点过冲检查，增益专项 **6 项全部通过**。包含注入大于满幅的滤镜结果，验证整数编码不会执行、原始音轨保留；另按样本比较低电平增益波形，验证延迟补偿后的两轨对齐。新增故障注入测试首轮误拦正常 ffprobe，修正为只注入滤镜结果后通过。

双击使用的 EXE 需要以更新源码重新打包；`verify_release.py` 的验收包括两个滑块、三模式中的 0/6/12 dB 组合、真实 CUDA 三模型、CPU 回退的正增益 PCM、MP3 下载/试听及根输出目录。发布脚本支持 `--backup-name formal-before-audio-gain`，目录名限制为安全单段名称；仅移动至新的 `.reference` 回退目录，已有目录时停止，从不覆盖或删除旧回退。

## 最终 GPU EXE 交付

2026-11-06 最终 EXE 使用干净源码 `2defbe82a5eb33f944728a0bbdbd1cf413f7fb03`，嵌入模块检查确认包含编码前过冲保护。沿用原 `.venv-gpu`，PyTorch 2.8.0+cu128 / ORT GPU 1.22.0，没有安装或重建环境，也没有重复下载大型权重。

冻结程序的 RTX 5060 矩阵运算、MelBand RoFormer 实际 CUDA 前向、两个 MDX 模型实际 CUDA 节点，以及 CPU 回退的人声 +6/伴奏 +12 dB PCM 导出全部通过。真实网页以 16 秒合成音频验证高质量 0/0、平衡 6/12、快速 12/6 dB：双轨 MP3 320 kbps 可解码、峰值低于满幅，下载和试听字节一致；每个最终歌曲目录恰好两条 MP3，没有 WAV。

验收后正式更新 `dist/MusicVocalExtractor/MusicVocalExtractor.exe`，原 GPU 正式版完整保留在 `.reference/formal-before-audio-gain/`，更早 CPU 回退不变。正式 EXE 从其他工作目录启动仍指向根 `outputs/` 与 `models/`；升级前记录的 **97 个现有音频/模型文件**逐项 SHA-256 一致，没有覆盖或删除。首轮候选同样保留，未冒充包含最终额外保护的版本发布。

本地证据仅保留在忽略目录，不提交二进制、权重、音频或系统诊断：`.tools/gain-full-cpu-tests.log`、`.tools/gain-final-guard-tests.log`、`.tools/gain-release-tests.log`、`.tools/gain-gpu-final-build.log`、`.tools/gain-gpu-final-validation.log`、`.tools/gain-delivery.log`、`test_artifacts/gain-update/delivery-report.json` 以及正式包内 `release-validation.json`。本轮未做完整歌曲的主观 AB 听感验收。
