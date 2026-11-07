# MusicVocalExtractor

项目内 Python、start.bat 和新版 EXE 默认共用根目录 `outputs/`、`models/`，路径解析与历史迁移见 [OUTPUT_PATHS.md](OUTPUT_PATHS.md)。RTX 5060 恢复后的 CUDA、三模型、性能模式与 GPU EXE 验收见 [GPU_VALIDATION.md](GPU_VALIDATION.md)。CUDA 不要求独显直连，不需要修改驱动或系统设置。

一个在自己电脑上使用的 **AI 音乐分离和混音工具**。

上传一首歌，选择「人声与伴奏」或「主唱与和声」，点击「开始分离」。生成的音轨可以一起试听，也可以单独下载。

## 能做什么？

- **分开人声和伴奏**：支持导入 MP3、WAV、FLAC、M4A。
- **选择保存格式**：默认导出 MP3（320 kbps），也可以选择 WAV。
- **提取主唱与背景和声**：Kim MelBand RoFormer 先分离人声，UVR-BVE-4B v1 再从人声中提取主唱与背景和声。模型首次使用时自动下载并校验，之后复用缓存。
- **查看处理状态**：告诉你当前正在检查文件、下载模型、分离还是导出。
- **多轨混音**：一起播放、暂停或跳转。每条音轨可独立调音量，拉到 0% 即静音，再向右拖动即可恢复。支持总音量、Solo、恢复默认、开启全部和静音全部。
- **下载和重新载入**：本次音轨可单独下载。以后可以从「已保存的混音」载入结果，直接试听。

## 怎么使用？

1. 第一次使用，按下方的[启动说明](#windows-双击启动)准备 Python 3.12 和 FFmpeg。
2. 双击项目里的 `start.bat`，浏览器会自动打开操作页面。
3. 选择歌曲、分离模式和输出格式，点击 **“开始分离”**。
4. 完成后试听或下载，也可以在 `outputs` 文件夹里找到结果。

浏览器只是操作界面，歌曲在你的电脑上处理，不上传到云端。第一次安装依赖、下载模型需要联网。没有 NVIDIA 显卡也可以使用 CPU 处理，但可能需要多等一会儿。

分离效果会随歌曲变化，主唱与和声可能有串音。模型选型、吉他角色候选及本机整曲测试见 [MULTITRACK_MODELS.md](MULTITRACK_MODELS.md)。

> GitHub 提供的是源码，不包含 Python 环境、模型、个人音频或现成 EXE。想自己打包 EXE，可以查看下面的技术说明。

<details>
<summary>查看模型、文件保存和 EXE 打包的技术说明</summary>

### 已实现的功能

保留 `start.bat`，支持模型下拉选择、MP3 320 kbps / WAV PCM 输出、真实阶段进度、音频试听，以及专用 PyInstaller onedir 构建脚本。

**已配置好环境后，双击 `start.bat` 即可使用网页版本。** 首次下载源码请按下方说明准备本机 Python 3.12、FFmpeg 和项目虚拟环境。虚拟环境、模型、音频、EXE 和本地诊断资料不随 GitHub 源码分发。本机已有环境若依赖 `.tools/python312`，请保留该基础运行时。

首次使用模型由 Audio Separator 官方机制下载并校验 SHA-256，之后复用缓存。自动设备模式优先用 CUDA，初始化不可用时会在分离状态中提示并使用 CPU。显式选择 CUDA 时，设备不可用会报错。

分离前设置的**导出增益**为 0～+12 dB。主唱和背景和声沿用人声设置，正增益启用峰值保护。混音器的 0～100% 滑块即时调整浏览器试听音量。导出增益处理详见 [AUDIO_GAIN.md](AUDIO_GAIN.md)。

CLI 示例（两个参数均可省略，默认 0 dB）：

```powershell
.\.venv-gpu\Scripts\python.exe separate.py "音乐.mp3" --vocal-gain-db 6 --instrumental-gain-db 3
```

Python API 和 Gradio `/separate` 保留两轨输出及原有导出增益参数。Python 调用可通过 `split_backing=True` 请求主唱、和声与伴奏。网页的「开始分离」使用独立的 `/mix` 入口并保存混音时间轴。

当前可选及默认模型为 **MelBand RoFormer · Kim**（`vocals_mel_band_roformer.ckpt`），复用已下载的约 913 MB 权重；Windows CPU 与 RTX 5060 CUDA 加载/推理已验证。按用户明确选择停用 Voc FT（`UVR-MDX-NET-Voc_FT.onnx`）和 Inst HQ 3（`UVR-MDX-NET-Inst_HQ_3.onnx`），不再提供这两个选项或下载它们。此前移除的 Karaoke 2、htdemucs 不恢复；其他模型权重和通用 MDX/ONNX 推理依赖不受影响。尚未完成真实歌曲音质 AB 验证，不将默认设置等同于音质排名。参数和旧配置处理见 [MODEL_VERIFICATION.md](MODEL_VERIFICATION.md)，候选研究见 [MODEL_RESEARCH.md](MODEL_RESEARCH.md)，此前升级记录见 [UPGRADE_VERIFICATION.md](UPGRADE_VERIFICATION.md)。

MP3 通过 FFmpeg `libmp3lame -b:a 320k` 编码，每轨都会核验格式并完整解码。网页另保存与原曲解码时间轴一致的 `mix/*.wav` 和 `mix/timeline.json`，便于同步播放及重新载入，因此会占用额外磁盘空间。「主唱与和声」模式选择 WAV 时，下载文件也保持原曲的采样率、声道数和样本数。失败时恢复 WAV 和已编码音轨保留在错误提示所列的 `cache/separation/work_*/`。

Python 版模型和输出位于项目 `models/`、`outputs/歌曲名/`。Gradio 在预处理上传元信息时保留 `FileData.orig_name`，不将缓存路径名误当歌曲名；CLI 使用输入路径文件名。名称清理 Windows 非法字符及保留设备名，按 UTF-16 路径预算截短；通过原子 mkdir 分配同名的 `歌曲名 (2)`、`歌曲名 (3)`，支持并发，不覆盖历史。EXE 版默认位于 EXE 旁的相应目录；目录不可写时使用 `%LOCALAPPDATA%/MusicVocalExtractor/`。可通过 `MVE_DATA_DIR` 指定数据根目录；原有 `AUDIO_SEPARATOR_MODEL_DIR` 模型路径配置继续有效。

进度为真实阶段及不确定进度条，不会显示伪造的整体百分比；推理阶段包含引擎内部的 WAV 写出。首次下载的字节进度仍可在启动窗口查看。

### 构建 Windows EXE

在项目 PowerShell 执行：

```powershell
# 构建不自动安装依赖；当前电脑已有 PyInstaller
.\build_exe.ps1 -Gpu
# 需要构建 CPU 候选时显式使用 -Cpu；环境不重装
```

新构建使用固定的 `dist/candidate-cpu/MusicVocalExtractor/`（显式 `-Gpu` 时为 candidate-gpu）。候选存在时停止，不自动覆盖或生成更多时间戳目录。CPU 候选通过 `verify_release.py --cpu` 的三个模型、网页及试听下载验收后，使用 `publish_release.py --cpu --publish` 发布到 `dist/MusicVocalExtractor/`；旧正式版及全部数据先保留至固定 `.reference/formal-exe-rollback/`，已有回退时停止而不覆盖。GPU 候选通过 verify_release.py 后以 publish_release.py --publish 更新同一正式目录，原 CPU 正式版完整保留至 .reference/formal-before-gpu-rollback/。必须保留完整程序目录及 `_internal`。

通过项目根标识 `mve-project.json` 及源码锚点定位当前项目的 dist EXE，不依赖父目录层数或工作目录；独立分发版无法确认项目位置时使用用户数据目录。`MVE_DATA_DIR`、`AUDIO_SEPARATOR_MODEL_DIR` 及显式 `runtime-config.json` 路径覆盖继续有效。不复制权重，原 `-IncludeCachedModels` 已停止支持。历史清理预览使用 `audit_builds.py`；它本身不会删除任何目录。

默认使用系统已有 FFmpeg/FFprobe，不需要另外安装 Python。若需要个人自用的 FFmpeg 捆绑构建，可执行 `.\build_exe.ps1 -FFmpegDir '包含ffmpeg.exe与ffprobe.exe的目录'`。也可把两个工具放在 EXE 旁的 `ffmpeg/` 文件夹；不会修改系统 PATH。许可说明见 [FFMPEG_NOTICE.md](FFMPEG_NOTICE.md)。

可复现检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe verify_models.py
# 对已启动的网页或 EXE 执行 HTTP 上传、试听文件及下载验证
.\.venv\Scripts\python.exe verify_web.py --url http://127.0.0.1:7860
```

真实模型检查使用生成的短音频，不访问个人歌曲；其通过只能证明功能与编码流程正常，歌曲分离质量仍需试听。CPU 与 GPU 隔离环境均保留，最新 GPU 实测见 GPU_VALIDATION.md。下方原有安装和 GPU 配置说明继续保留。

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

程序默认使用 `vocals_mel_band_roformer.ckpt` 预训练二轨模型，无需自行训练。模型缓存保持引擎自带的 SHA-256 校验，已有有效权重复用。界面和 CLI 不接受已停用模型；Python API 收到上述两个旧 ID 时会提示并切换到已存在的本地默认模型，若本地默认权重缺失则停止而不下载。正常主动选择有效模型时仍使用官方下载机制，下载失败会报告错误。

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

当前 Windows 11 CPU/GPU 与 EXE 状态见 [GPU_VALIDATION.md](GPU_VALIDATION.md)，早期记录见 [UPGRADE_VERIFICATION.md](UPGRADE_VERIFICATION.md)。批量处理不在本次范围内。

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
