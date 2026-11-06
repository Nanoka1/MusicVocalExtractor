# RTX 5060 GPU 加速与验收

**最新恢复验证见 [GPU_VALIDATION.md](GPU_VALIDATION.md)。** RTX 5060 已恢复，沿用原环境继续 CUDA 和 GPU EXE 验收，不更改显卡/驱动/电源配置。CUDA 可以在正常混合显卡模式下工作，并不要求独显直连。以下保留先前暂停阶段的历史记录；路径与数据保护见 [OUTPUT_PATHS.md](OUTPUT_PATHS.md)。

本轮基线：2026-11-05，Windows 11、Python 3.12.10，RTX 5060 Laptop 8151 MiB，驱动 591.86（nvidia-smi 报告驱动支持 CUDA 13.1）。旧 `.venv` 是 torch 2.8.0+cpu / ONNX Runtime 1.31.1 CPU，保留不变。

隔离 GPU 环境选用官方稳定发布的 **torch 2.8.0+cu128 / torchvision 0.23.0+cu128**，与原引擎 audio-separator 0.48.0 配套。CUDA 12.8 wheel 包含 `sm_120`；本机真实 2048×2048 CUDA 矩阵乘法通过，设备为 `cuda:0`，Compute Capability (12, 0)。驱动支持版本与 PyTorch runtime 版本不是同一概念。

官方依据：[PyTorch 安装版本配对](https://pytorch.org/get-started/previous-versions/)、[ONNX Runtime CUDA/cuDNN 兼容及 DLL 预加载](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。CPU 环境不安装 GPU 包；GPU 环境只安装 onnxruntime-gpu，不混装 onnxruntime。

## 复现隔离安装

仅在目标目录尚不存在时创建；不要重建已有健康环境：

```powershell
.\.venv\Scripts\python.exe -m venv .venv-gpu
.\.venv-gpu\Scripts\python.exe -m pip install -r requirements-gpu.txt -r requirements-ui.txt
.\.venv-gpu\Scripts\python.exe -m pip check
.\.venv-gpu\Scripts\python.exe verify_gpu.py
.\.venv-gpu\Scripts\python.exe verify_gpu_models.py
```

`requirements-gpu.txt` 明确固定 `+cu128`，避免普通 `torch==2.8.0` 被 CPU 发行包满足。驱动由本机现有 NVIDIA 安装提供；不安装系统 CUDA Toolkit，不下载第三方 DLL，不修改系统 PATH。

`--device cuda` 需要真实初始化和 GPU 运算成功；失败时报错，不静默回退。`--device cpu` / 原有 `--cpu` 显式使用 CPU；`auto` 在无 GPU 环境使用 CPU并明确显示，检测到 NVIDIA 但 CUDA 构建初始化失败则要求用户检查或主动选择 CPU。

ORT 预加载项目 GPU torch/lib 中的 CUDA/cuDNN DLL；模型加载后检查实际会话首选 Provider 并关闭运行时 EP 回退。RoFormer 检查加载后的真实参数设备。`verify_gpu_models.py` 额外通过前向钩子确认参数、输入和输出均为 CUDA，并检查有限值；两个 MDX 则记录 ORT 节点 profiling，要求真实 CUDA 节点执行，不以 Provider 名单代替实际推理。

原名命名、MP3 320 kbps、成功目录只含两个最终文件及失败保留恢复材料的规则继续有效。权重、环境、音频、日志、性能报告及构建产物均不提交 Git。

P0 实测通过：ORT GPU 1.22.0、cuDNN 9.10.2、`pip check` 正常；两个 MDX 的实际 CUDA 节点执行和 Kim RoFormer 的 CUDA 参数/输入/输出均已确认。3 秒合成音频的 RoFormer 测试发生 2 次 CUDA 前向，PyTorch 峰值分配 1,839,783,424 字节。只证明功能，不表示真实歌曲质量认证或整曲峰值显存。原始证据在已忽略的 `test_artifacts/gpu-preflight.json`、`test_artifacts/gpu-model-proof/report.json` 及 ORT profiling，控制台日志 `.tools/gpu-p0-model-proof.log`。

## 性能模式与计时

界面及 CLI `--performance quality|balanced|fast`（默认 balanced）使用真正不同的参数：

| 模型 | 高质量 | 平衡 | 快速 |
|---|---|---|---|
| Kim RoFormer | FP32、overlap=4 | CUDA autocast、overlap=2 | CUDA autocast、overlap=1 |
| 两个 MDX | ONNX、overlap=.5 | ONNX、overlap=.25 | ONNX、overlap=.1 |

RoFormer 分段按作者 8 秒推荐值设置 segment_size=801（441 hop），显存空闲不足 5/3 GiB 时分别降低到 501/301；CPU 使用 FP32。batch_size 固定 1：0.48.0 的 RoFormer 路径实际上忽略批量参数，因此不宣称调大它有加速效果。保留原生 FP16 和 torch.compile 为关闭状态，混合精度须以实测结果决定是否验收。

前向钩子检查实际参数/输入设备和输出 NaN/Inf。CUDA OOM 最多降低一次 segment_size，并使用独立重试目录，仍失败则明确报错，不静默回退 CPU，不发布半成品；可主动选择 CPU 或高质量 FP32。计时明确区分模型准备（含校验/下载）、引擎加载、AI 分离（含解码/WAV 写出）、最终导出及完整校验、总时间；不能把 WAV 写出误称为纯 GPU kernel 耗时。

`benchmark_gpu.py` 默认使用同一段 16 秒合成音频，CPU 4 线程。CPU FP32 基准实测：加载 2.85 秒、准备 7.14 秒、AI 分离 62.85 秒、导出验证 0.99 秒、总计 73.20 秒。随后独显从系统在线列表消失，NVIDIA PnP 状态 Unknown、核显 OK，nvidia-smi 报权限不足；新进程 CUDA 也不可用。**GPU 三种模式与原生 FP16 的后续基准尚未完成，不能填写加速倍数、音质结论或宣称新模式完成 GPU 验收。** 已暂停这些改动的发布，保留 P0 成功时的原始证据。CPU 环境完整 26 项回归通过、无跳过。

## 构建及共享缓存

当前构建默认使用 CPU，只有显式 `-Gpu` 才使用 `.venv-gpu` 并要求真实 CUDA 预检；不会为普通 CPU 构建探测异常 GPU。不重装依赖，不清空 dist。GPU 使用固定 `dist/candidate-gpu/MusicVocalExtractor/` 和 `build/gpu/`，已有候选则停止而不叠加时间戳目录。

候选的本地 `runtime-config.json` 指向项目现有数据/模型目录，跨版本复用校验过的缓存，不复制或移动权重；不再使用 `-IncludeCachedModels`。分发到其他位置/电脑前应调整该本地路径配置，不能随意删除原缓存。现有旧 EXE 的目录与数据不受影响。

GPU 恢复后运行：

```powershell
.\.venv-gpu\Scripts\python.exe verify_gpu.py
.\.venv-gpu\Scripts\python.exe benchmark_gpu.py
.\build_exe.ps1 -Gpu
.\.venv-gpu\Scripts\python.exe verify_release.py --package dist/candidate-gpu/MusicVocalExtractor
.\.venv-gpu\Scripts\python.exe publish_release.py
# 上一条预览通过后才执行：
.\.venv-gpu\Scripts\python.exe publish_release.py --publish
```

冻结程序提供 `--gpu-check` 和 `--verify-gpu-models`，分别实测 CUDA 矩阵运算和三个模型的 GPU 证据。发布验证还启动真实 EXE 网页、使用 CUDA 平衡模式分离并检查下载/试听一致性，生成文件 SHA-256 清单。发布仅将通过验收且未被修改的候选移动到新的 `dist/MusicVocalExtractor-GPU/`，不覆盖旧正式目录；已有 GPU 正式版时停止，需先审查回退方案，不自动删除任何历史。

**新的 GPU EXE 仍未验收，不宣称 GPU 性能测试完成。** 用户后续已调整优先级，明确授权在数据完整迁移、进程检查及保留可用 CPU 正式版的条件下清理三个指定旧构建；这项授权不扩展到其他构建或数据目录。当前处理记录见 [OUTPUT_PATHS.md](OUTPUT_PATHS.md)。
