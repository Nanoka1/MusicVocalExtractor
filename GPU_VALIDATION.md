# RTX 5060 恢复后的验收（2026-11-06）

沿用既有 `.venv-gpu`：torch 2.8.0+cu128、torchvision 0.23.0+cu128、ONNX Runtime GPU 1.22.0、audio-separator 0.48.0。未重建环境、升级 CUDA 构建或重复下载模型。矩阵运算、sm_120 和 ORT CUDA Provider 复验通过。驱动显示的 CUDA 13.1 是驱动能力，推理 wheel runtime 仍为 12.8。

## 实际模型证据

两个保留 MDX 各执行 356 个 CUDA 节点（包括 Conv、ConvTranspose、MatMul）；Kim RoFormer 前向钩子确认参数、输入及输出均为 CUDA。三模型结果均可解码、双声道 44100 Hz、非静音且有限，无额外中间文件。此检查使用合成音频，不表示已完成真实歌曲 AB 音质认证。

## 同音频测速

继续使用昨日已存在的 16 秒合成 WAV，SHA-256 `4ba73bff628329a1113de13ba36a5f1308f2ace8cbb796c3e21fdaf10d9fab08`，同一 Kim 权重、CPU 4 线程。昨日导出为 WAV，因此本轮所有配置统一重测 MP3 320 kbps，不用旧总耗时计算不一致的倍数。加载结束和推理结束均同步 CUDA。

| 配置 | 加载秒 | AI 分离秒 | MP3 导出/验证秒 | 总秒 | PyTorch 峰值分配 GiB | AI 阶段相对 CPU |
|---|---:|---:|---:|---:|---:|---:|
| CPU FP32 | 3.07 | 59.41 | 1.06 | 69.62 | — | 1× |
| GPU 原 FP32、overlap=1 | 2.51 | 3.60 | 0.88 | 10.41 | 1.71 | 16.52× |
| GPU 高质量 | 3.44 | 8.98 | 0.89 | 17.94 | 1.71 | 6.62× |
| GPU 平衡（默认） | 2.58 | 2.54 | 0.87 | 8.65 | 1.95 | 23.40× |
| GPU 快速 | 2.33 | 1.71 | 0.85 | 7.62 | 1.95 | 34.81× |
| 原生 FP16 实验 | 2.30 | 1.70 | 0.90 | 7.40 | 1.72 | 35.05× |

“AI 分离”包含输入解码及引擎 WAV 写出，导出包含两轨编码/完整解码校验；总时间另含环境、模型校验和加载准备，不能只将三列相加。“峰值”是 PyTorch 分配值，不是整个系统/ORT 的全部显存。短音频、当前负载及 CPU 线程数影响结果，不能外推整首歌或其他机器。

快速模式相对 GPU FP32 基线的 AI 阶段约 2.11×；原生 FP16 相比快速 autocast 仅约 0.7% 推理收益，本轮不将其设为日常默认，也未启用 torch.compile。高质量使用 FP32/overlap=4，平衡使用 autocast/2，快速使用 autocast/1，RoFormer batch_size 在当前引擎路径中不参与计算，保持 1。MDX 沿用独立 ONNX 参数。

所有配置结果非静音、可解码且无 NaN/Inf。相对 GPU FP32 快速基线，伴奏解码波形相对 L2 差约 0.008%–0.011%；这只是合成信号的数值检查，不是人声质量或可感失真指标。本轮没有真实歌曲参考 stems 或完整歌曲试听结论。

首次并行 CPU 回归与测速发生模型锁争用，停止了未完成的测速。回归结束后用 `--resume` 核对同音频哈希和 MP3 口径，仅恢复剩余配置；未隐藏失败或重复计算已成功 CPU 基准。机器可读证据与实际音频均留在忽略的 test_artifacts，详细日志留在 .tools，不提交权重、个人数据或构建产物。

## 复现

```powershell
.\.venv-gpu\Scripts\python.exe verify_gpu.py
.\.venv-gpu\Scripts\python.exe verify_gpu_models.py
# 不要与其他模型加载测试并行：
.\.venv-gpu\Scripts\python.exe benchmark_gpu.py
.\build_exe.ps1 -Gpu
.\.venv-gpu\Scripts\python.exe verify_release.py --package dist/candidate-gpu/MusicVocalExtractor
.\.venv-gpu\Scripts\python.exe publish_release.py --publish
```

GPU 候选必须通过冻结程序自身的 CUDA 运算、三模型前向/ORT profiling、CPU 回退及三模式网页下载试听验收后，才更新统一正式目录 `dist/MusicVocalExtractor/`。当前正式 CPU 版完整保留至固定 `.reference/formal-before-gpu-rollback/`；已有更早回退不覆盖，歌曲与模型仍共用项目根 outputs/models。
