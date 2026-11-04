# MusicVocalExtractor
A simple AI music vocal separation application

使用 Python、Audio Separator 和预训练模型，在 Windows 11 上将音乐分离为人声和伴奏，使用 Gradio 提供简单的操作界面，优先使用已配置好的 NVIDIA GPU。

## Windows 双击启动

1. 下载当前分支的 ZIP 并全部解压到可写文件夹，例如 `D:\MusicVocalExtractor`，不要直接在压缩包内运行。
2. 首次使用，安装 **Python 3.12（64 位）** 和 **FFmpeg**，具体方法见下文。两者是本机前提，云端环境不会自动安装到你的电脑。
3. 双击 **`start.bat`**。第一次会创建虚拟环境并联网安装依赖，下载可能需要几分钟。
4. 浏览器自动打开界面后，选择 MP3、WAV、FLAC 或 M4A，点击“开始分离”。
5. 完成后点击人声、伴奏文件下载，或直接查看程序目录下的 `outputs` 文件夹。

使用时保留启动窗口，关闭它将停止软件。浏览器没有自动打开时，可使用启动窗口显示的本地地址。启动出错时窗口会保留报错；可将报错发来排查。

默认首次安装 CPU 版，速度较慢；已经按下文配置好的 GPU 环境会保留。已有 `.venv` 必须是 Windows 创建的 Python 3.12 环境。启动助手不会覆盖 Linux 虚拟环境，也不会自动修复损坏的 GPU 环境。

这是本机运行的浏览器界面版，尚未打包为免 Python 安装的 EXE。界面不建立公开分享链接，音乐处理在运行软件的这台电脑上完成。模型及依赖的首次下载需要联网。

已经安装命令行版的用户，也可以手动运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe app.py
```

## 项目结构

```text
MusicVocalExtractor/
├── start.bat             # Windows 双击入口
├── start_windows.py      # 首次安装与启动助手
├── app.py                # 简单的 Gradio 界面
├── check_environment.py   # 检查电脑配置，不需要额外依赖
├── separate.py            # 基础音频分离程序
├── requirements.txt       # CPU 依赖
├── requirements-gpu.txt   # NVIDIA GPU 依赖，二选一
├── requirements-ui.txt    # Gradio 界面依赖
├── tests/test_separate.py # 输入检查和可选的真实模型测试
├── .venv/                # 本机虚拟环境，创建后生成
├── models/               # 首次运行下载的预训练模型
└── outputs/              # 默认结果文件夹
```

后三个目录不会提交到 Git。原始音频可以放在任何文件夹。

## 第一步：检查 Windows 电脑

在项目文件夹打开 PowerShell，先查看已安装的 Python：

```powershell
py --list
py check_environment.py
```

如果没有 `py` 命令，但已安装 Python，可以尝试：

```powershell
python --version
python check_environment.py
```

脚本仅使用 Python 标准库，不需要提前安装依赖。它显示系统、Python 版本与路径、位数、CPU、内存、磁盘可用空间、虚拟环境状态、pip、FFmpeg、NVIDIA 显卡及相关 Python 包版本；不会安装软件或修改系统。

建议使用 **Windows 11 x64、Python 3.12（64 位）**。如果没有 Python，请从 <https://www.python.org/downloads/windows/> 安装 3.12 的 64 位版本。分享检查结果前可以遮住路径中的个人用户名。

注意：云端检查不能代表你的 Windows 电脑。`nvidia-smi` 不存在可能是未安装驱动或命令未加入 PATH；检测到显卡也不代表 AI 引擎已经能使用 GPU。GPU 推理会在安装依赖后另行验证。

## 第二、三步：准备结构和虚拟环境

上面的结构已经创建。在 Windows 的项目文件夹中运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

后续直接使用虚拟环境的 Python，无需执行激活脚本，也无需修改 PowerShell 执行策略。不要将云端的 Linux `.venv` 复制到 Windows；两边需要各自创建。

## 第四步：安装依赖

先安装 FFmpeg（包含 ffprobe），它用于读取 MP3、WAV、FLAC、M4A。Windows 可以运行：

```powershell
winget install --id Gyan.FFmpeg --exact
```

安装后重新打开 PowerShell，回到项目文件夹，检查：

```powershell
ffmpeg -version
ffprobe -version
```

如果没有 winget，可从 <https://ffmpeg.org/download.html> 提供的 Windows 下载入口安装，并把包含这两个程序的 `bin` 文件夹加入 PATH。

**选择一种依赖方案，不要混装 CPU 和 GPU 版 ONNX Runtime。**

### 方案 A：CPU 基础版

不需要独立显卡，速度较慢。云端使用这一方案。

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

### 方案 B：NVIDIA GPU 版

需要 NVIDIA 显卡及支持 CUDA 12.8 的驱动。在 Windows PowerShell 中先运行 `nvidia-smi` 检查显卡与驱动。这里选用配套的 PyTorch 2.8.0 / torchvision 0.23.0 CUDA 12.8 包及 ONNX Runtime GPU 1.22.0（CUDA 12、cuDNN 9）。不同显卡和驱动的兼容性需要本机验证；并非所有 NVIDIA 显卡都适用。

在一个没有安装 CPU 版依赖的虚拟环境中运行：

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import torch; import onnxruntime as ort; ort.preload_dlls(); print('CUDA:', torch.cuda.is_available()); print('Providers:', ort.get_available_providers())"
```

期望看到 `CUDA: True` 和 `CUDAExecutionProvider`。这只是基础检测，仍需实际运行一次分离并检查引擎日志，确认没有回退到 CPU。程序会尝试预加载 PyTorch 提供的 CUDA/cuDNN 库。

如已安装 CPU 版，可以保留 `.venv`，另建 `.venv-gpu`，并将本节命令中的 `.venv` 替换为 `.venv-gpu`。显卡、DLL 或驱动出错时，先使用 CPU 版；不要反复混装两个 ONNX Runtime 包。

参考：<https://pytorch.org/get-started/previous-versions/>、<https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html>。

## 第五步：运行基础分离

在项目文件夹中运行，输入路径带空格时请保留双引号：

```powershell
.\.venv\Scripts\python.exe separate.py "D:\Music\歌曲.mp3"
```

也支持 `.wav`、`.flac`、`.m4a`。指定结果保存位置：

```powershell
.\.venv\Scripts\python.exe separate.py "D:\Music\歌曲.flac" --output-dir "D:\Music\分离结果"
```

需要强制使用 CPU 时：

```powershell
.\.venv\Scripts\python.exe separate.py "D:\Music\歌曲.m4a" --cpu
```

程序使用 Audio Separator 的 `UVR_MDXNET_KARA_2.onnx` 预训练二轨模型，无需自行训练。首次运行联网下载模型及配置到 `models/`，下载过程中保持引擎自带的 SHA-256 校验。所需下载地址包括 `github.com`、`release-assets.githubusercontent.com`、`raw.githubusercontent.com`；上游可能还有备用来源。下载失败时程序会报告错误。

成功后会打印实际保存位置，例如：

```text
outputs/separation_随机字符/
├── Vocals.wav         # 人声
└── Instrumental.wav   # 伴奏
```

每次运行使用新文件夹，不覆盖之前的结果，原始音频保持不变。失败时可能留下空文件夹或不完整结果，只有显示“分离完成”才代表本次成功。输出固定为 WAV；较长音频会占用较多内存和磁盘，建议先用短音频试用。分离可能有残留或音质损失，这个基础版本不保证人声或伴奏完全纯净。

查看命令帮助：

```powershell
.\.venv\Scripts\python.exe separate.py --help
```

## 验证与测试

运行不需要下载模型的输入检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实模型测试会生成两秒合成信号，转换成四种输入格式，再实际分离并检查两个 WAV 的采样率、时长、声道和非静音数据；需要 FFmpeg、依赖和模型下载网络。它验证处理流程，不评价真实歌曲的分离质量。

```powershell
$env:RUN_MODEL_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_MODEL_TESTS
```

云端 Linux 的对应命令：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
CC=gcc CXX=g++ .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python separate.py /path/to/music.wav --cpu
RUN_MODEL_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
```

Windows 11 与 NVIDIA GPU 的运行结果需要在对应电脑验证；云端 CPU 测试不能代替这些验证。批量处理和打包为免 Python 安装的 EXE 留待后续阶段。

Linux 上 Audio Separator 的 `diffq` 依赖需要编译器；以上命令使用系统已有的 GCC/G++，并要求安装 Python 开发头文件。Windows 的相应依赖为 `diffq-fixed`，Python 3.12 x64 有预编译包。

云端验证记录（2026-11-03）：Python 3.12.14、PyTorch 2.8.0+cpu、torchvision 0.23.0+cpu、Audio Separator 0.48.0、librosa 0.11.0、ONNX Runtime 1.31.1、FFmpeg 7.1.5。依赖完整性检查通过；4 项输入检查及 1 项包含四种格式的真实模型测试全部通过，无跳过。模型约 53 MB，已单独核对上游发布的 SHA-256。GPU 依赖清单是 Windows 安装方案，未在 NVIDIA 硬件上验证。

## 界面测试

云端 Gradio 6.31.0 的 3 项界面测试已通过：未选文件、错误输入清空旧结果，以及通过本地 HTTP 服务上传 MP3、真实分离并下载两份有效 WAV。Windows 双击入口尚未在 Windows 系统实测。

安装 `requirements-ui.txt` 后，可运行基础测试。额外启用真实界面测试时，会启动临时本地服务，上传合成 MP3，运行真实模型，再下载并检查两份 WAV：

```powershell
$env:RUN_UI_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_app.py -v
Remove-Item Env:RUN_UI_TESTS
```
