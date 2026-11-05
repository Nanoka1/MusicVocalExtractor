# MusicVocalExtractor

项目内 Python、start.bat 和新版 EXE 默认共用根目录 `outputs/`、`models/`，路径解析与历史迁移见 [OUTPUT_PATHS.md](OUTPUT_PATHS.md)。此前 GPU 优化与 CUDA 证据完整保留；本轮按用户要求只做 CPU 验证，不要求独显直连，也不改系统设置。GPU 状态见 [GPU_ACCELERATION.md](GPU_ACCELERATION.md)。

一个在自己电脑上使用的 **AI 人声与伴奏分离工具**。

放入一首歌，点击“开始分离”，就能得到两份音频：一份是**人声**，另一份是**伴奏**。可以直接试听，也可以保存下来，用来练唱、练耳或学习歌曲。

## 能做什么？

- **分开人声和伴奏**：支持导入 MP3、WAV、FLAC、M4A。
- **选择保存格式**：默认导出 MP3（320 kbps），也可以选择 WAV。
- **切换不同模型**：可以比较哪种更适合这首歌；首次使用某个模型时自动下载，之后复用。
- **查看处理状态**：告诉你当前正在检查文件、下载模型、分离还是导出。
- **试听和下载**：处理完成后，两条音轨都能单独试听、下载；每次结果分开保存，原歌曲保持不变。

## 怎么使用？

1. 第一次使用，按下方的[启动说明](#windows-双击启动)准备 Python 3.12 和 FFmpeg。
2. 双击项目里的 `start.bat`，浏览器会自动打开操作页面。
3. 选择歌曲、分离模型和输出格式，点击 **“开始分离”**。
4. 完成后试听或下载，也可以在 `outputs` 文件夹里找到结果。

浏览器只是操作界面，歌曲在你的电脑上处理，不上传到云端。第一次安装依赖、下载模型需要联网。没有 NVIDIA 显卡也可以使用 CPU 处理，但可能需要多等一会儿。

分离效果会因歌曲而异，可能仍有少量人声或乐器残留，可以换一个模型比较效果。

> GitHub 提供的是源码，不包含 Python 环境、模型、个人音频或现成 EXE。想自己打包 EXE，可以查看下面的技术说明。

<details>
<summary>查看模型、文件保存和 EXE 打包的技术说明</summary>

### 已实现的功能

保留 `start.bat`，支持模型下拉选择、MP3 320 kbps / WAV PCM 输出、真实阶段进度、音频试听，以及专用 PyInstaller onedir 构建脚本。

**已配置好环境后，双击 `start.bat` 即可使用网页版本。** 首次下载源码请按下方说明准备本机 Python 3.12、FFmpeg 和项目虚拟环境。虚拟环境、模型、音频、EXE 和本地诊断资料不随 GitHub 源码分发。本机已有环境若依赖 `.tools/python312`，请保留该基础运行时。

使用步骤：上传音乐 → 在「选择 AI 分离模型」选择模型 → 在「输出音频格式」选择 MP3（默认）或 WAV → 点击「开始分离」→ 试听及下载两条音轨。首次使用模型由 Audio Separator 官方机制下载并校验 SHA-256，之后复用缓存。

保留 `UVR-MDX-NET-Voc_FT.onnx`（默认）、`UVR-MDX-NET-Inst_HQ_3.onnx`，新增 **MelBand RoFormer · Kim**（`vocals_mel_band_roformer.ckpt`）。新模型权重约 913 MB，首次自动下载，CPU 较慢；Windows CPU 加载与推理已验证，GPU 未实测。默认仍用 Voc FT，因为尚未完成真实歌曲音质 AB 验证。移除 Karaoke 2 和 htdemucs 选项及四轨合成专用逻辑，已有模型缓存不会删除。参数见 [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)，六个候选的实时 Star、质量与许可比较见 [MODEL_RESEARCH.md](MODEL_RESEARCH.md)，本轮实测范围见 [UPGRADE_VERIFICATION.md](UPGRADE_VERIFICATION.md)。

MP3 通过 FFmpeg `libmp3lame -b:a 320k` 真正编码，检查编码、比特率、采样率和声道，并完整解码两轨。只有两轨均成功才发布，随后删除本任务临时工作目录；WAV 模式只发布两条 PCM WAV。试听及下载使用同一结果文件。失败时不显示成功，恢复 WAV 和已编码音轨保留在错误消息指出的 `cache/separation/work_*/`，不会清理历史输出。

Python 版模型和输出位于项目 `models/`、`outputs/歌曲名/`。Gradio 在预处理上传元信息时保留 `FileData.orig_name`，不将缓存路径名误当歌曲名；CLI 使用输入路径文件名。名称清理 Windows 非法字符及保留设备名，按 UTF-16 路径预算截短；通过原子 mkdir 分配同名的 `歌曲名 (2)`、`歌曲名 (3)`，支持并发，不覆盖历史。EXE 版默认位于 EXE 旁的相应目录；目录不可写时使用 `%LOCALAPPDATA%/MusicVocalExtractor/`。可通过 `MVE_DATA_DIR` 指定数据根目录；原有 `AUDIO_SEPARATOR_MODEL_DIR` 模型路径配置继续有效。

进度为真实阶段及不确定进度条，不会显示伪造的整体百分比；推理阶段包含引擎内部的 WAV 写出。首次下载的字节进度仍可在启动窗口查看。

### 构建 Windows EXE

在项目 PowerShell 执行：

```powershell
# 构建不自动安装依赖；当前电脑已有 PyInstaller
.\build_exe.ps1 -Cpu
# 以后 GPU 恢复并准备验收时，才显式使用 -Gpu
```

新构建使用固定的 `dist/candidate-cpu/MusicVocalExtractor/`（显式 `-Gpu` 时为 candidate-gpu）。候选存在时停止，不自动覆盖或生成更多时间戳目录。CPU 候选通过 `verify_release.py --cpu` 的三个模型、网页及试听下载验收后，使用 `publish_release.py --cpu --publish` 发布到 `dist/MusicVocalExtractor/`；旧正式版及全部数据先保留至固定 `.reference/formal-exe-rollback/`，已有回退时停止而不覆盖。GPU 候选仍需真实 CUDA 验收，当前暂停。必须保留完整程序目录及 `_internal`。

通过项目根标识 `mve-project.json` 及源码锚点定位当前项目的 dist EXE，不依赖父目录层数或工作目录；独立分发版无法确认项目位置时使用用户数据目录。`MVE_DATA_DIR`、`AUDIO_SEPARATOR_MODEL_DIR` 及显式 `runtime-config.json` 路径覆盖继续有效。不复制权重，原 `-IncludeCachedModels` 已停止支持。历史清理预览使用 `audit_builds.py`；它本身不会删除任何目录。

默认使用系统已有 FFmpeg/FFprobe，不需要另外安装 Python。若需要个人自用的 FFmpeg 捆绑构建，可执行 `.\build_exe.ps1 -FFmpegDir '包含ffmpeg.exe与ffprobe.exe的目录'`。也可把两个工具放在 EXE 旁的 `ffmpeg/` 文件夹；不会修改系统 PATH。许可说明见 [FFMPEG_NOTICE.md](FFMPEG_NOTICE.md)。

可复现检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe verify_models.py
# 对已启动的网页或 EXE 执行 HTTP 上传、试听文件及下载验证
.\.venv\Scripts\python.exe verify_web.py --url http://127.0.0.1:7860
```

真实模型检查使用生成的短音频，不访问个人歌曲；其通过只能证明功能与编码流程正常，歌曲分离质量仍需试听。当前环境为 CPU 版，GPU 推理没有验证。下方原有安装和 GPU 配置说明继续保留。

</details>

## Windows 双击启动

1. 下载当前分支的 ZIP 并全部解压到可写文件夹，例如 `D:\MusicVocalExtractor`，不要直接在压缩包内运行。
2. 首次使用，安装 **Python 3.12（64 位）** 和 **FFmpeg**，具体方法见下文。两者是本机前提，云端环境不会自动安装到你的电脑。
3. 双击 **`start.bat`**。第一次会创建虚拟环境并联网安装依赖，下载可能需要几分钟。
4. 浏览器自动打开界面后，选择 MP3、WAV、FLAC 或 M4A，点击“开始分离”。
5. 完成后点击人声、伴奏文件下载，或直接查看程序目录下的 `outputs` 文件夹。

使用时保留启动窗口，关闭它将停止软件。浏览器没有自动打开时，可使用启动窗口显示的本地地址。启动出错时窗口会保留报错；可将报错发来排查。

默认首次安装 CPU 版，速度较慢；已经按下文配置好的 GPU 环境会保留。已有 `.venv` 必须是 Windows 创建的 Python 3.12 环境。启动助手不会覆盖 Linux 虚拟环境，也不会自动修复损坏的 GPU 环境。

这是本机运行的浏览器界面，EXE 构建方式与本次验证结果见上方升级说明。界面不建立公开分享链接，音乐处理在运行软件的这台电脑上完成。模型及依赖的首次下载需要联网。

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

程序默认使用 `UVR-MDX-NET-Voc_FT.onnx` 预训练二轨模型，无需自行训练。可以通过 `--model` 选择其他模型。首次运行联网下载模型及配置到 `models/`，保持引擎自带的 SHA-256 校验。所需下载地址包括 `github.com`、`release-assets.githubusercontent.com`、`raw.githubusercontent.com`。下载失败时程序会报告错误。

使用新模型（CPU 示例；下载约 913 MB，只需首次联网）：

```powershell
.\.venv\Scripts\python.exe separate.py "D:\Music\周杰伦 - 晴天.mp3" --model vocals_mel_band_roformer.ckpt --format MP3 --cpu
```

成功后会打印实际保存位置，例如：

```text
outputs/周杰伦 - 晴天/
├── 周杰伦 - 晴天_Vocals.mp3
└── 周杰伦 - 晴天_Instrumental.mp3
```

每次运行使用新文件夹，不覆盖之前的结果，原始音频保持不变。失败时可能留下空文件夹或不完整结果，只有显示“分离完成”才代表本次成功。默认输出 MP3 320 kbps，使用 `--format WAV` 可输出 PCM WAV；较长音频会占用较多内存和磁盘，建议先用短音频试用。分离可能有残留或音质损失，需要根据歌曲试听比较模型。

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

当前 Windows 11 CPU 验证与 EXE 状态见 [UPGRADE_VERIFICATION.md](UPGRADE_VERIFICATION.md)；NVIDIA GPU 尚未验证。批量处理不在本次范围内。

Linux 上 Audio Separator 的 `diffq` 依赖需要编译器；以上命令使用系统已有的 GCC/G++，并要求安装 Python 开发头文件。Windows 的相应依赖为 `diffq-fixed`，Python 3.12 x64 有预编译包。

云端验证记录（2026-11-03）：Python 3.12.14、PyTorch 2.8.0+cpu、torchvision 0.23.0+cpu、Audio Separator 0.48.0、librosa 0.11.0、ONNX Runtime 1.31.1、FFmpeg 7.1.5。依赖完整性检查通过；4 项输入检查及 1 项包含四种格式的真实模型测试全部通过，无跳过。模型约 53 MB，已单独核对上游发布的 SHA-256。GPU 依赖清单是 Windows 安装方案，未在 NVIDIA 硬件上验证。

## 界面测试

原始云端 Gradio 6.31.0 的 3 项界面测试已通过：未选文件、错误输入清空界面结果，以及通过本地 HTTP 服务上传 MP3、真实分离并下载两份有效 WAV。本次 Windows 网页及 EXE 的上传、分离、试听文件和下载端到端检查也已通过。

安装 `requirements-ui.txt` 后，可运行基础测试。额外启用真实界面测试时，会启动临时本地服务，上传合成 MP3，运行真实模型，再下载并检查两份 WAV：

```powershell
$env:RUN_UI_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_app.py -v
Remove-Item Env:RUN_UI_TESTS
```

## 安全与许可证

本项目自有代码采用 [MIT](LICENSE)。第三方依赖和模型遵循各自条款，来源与分发边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。仅限本机处理可信文件，不要公开运行服务；已知依赖风险和使用限制见 [SECURITY.md](SECURITY.md)。当前安全加固不代表已完成依赖漏洞修复或 EXE 再分发合规。
