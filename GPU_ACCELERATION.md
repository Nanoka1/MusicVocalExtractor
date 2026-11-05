# RTX 5060 GPU 加速与验收

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
