# MusicVocalExtractor

MusicVocalExtractor 是一款在自己电脑上运行的 **AI 音轨分离与混音工具**。放入一首完整的歌，就能把人声和伴奏拆开，也可以进一步分出主唱和背景和声。分离完成后，你可以让某一轨更响、把它静音，或只听这一轨，再把调好的整首歌导出成 MP3。

这个项目是为了让练唱、扒歌和学习编曲更方便。比如，你可以保存一份伴奏练唱，或者把伴奏调低，听清背景和声是怎么唱的。浏览器是操作界面，音频处理在你的电脑上完成。首次安装依赖和下载模型时需要联网。

## 从一首歌开始

1. **打开软件。** 已有完整 Windows 程序包时，双击包里的 `MusicVocalExtractor.exe`，并把同目录的 `_internal` 文件夹和 EXE 一起保留。项目内自行打包并发布到本机的入口在 `dist/MusicVocalExtractor/`。只有源码时，请先按下文准备环境，再双击 `start.bat`。
2. **选一首歌和一种分离模式。** 导入 MP3、WAV、FLAC 或 M4A。选「人声与伴奏」会得到两轨，选「主唱与和声」会得到主唱、背景和声、伴奏三轨。
3. **点击「开始分离」。** 页面会提示正在检查文件、准备模型、分离还是导出。第一次用到某个模型时，程序会先下载它。分离完成后，可以单独下载每条音轨。
4. **试听和调音量。** 混音器里的各轨会同步播放、暂停和跳转。每轨都有音量、静音和 Solo，Solo 就是只听选中的轨道。静音会记住滑块的位置，取消静音就能恢复。也可以调整总音量、恢复默认、开启全部或静音全部。
5. **点击「导出混音」。** 软件会按点击时的音量、静音、Solo 和总音量设置，从头导出整首歌曲。可以继续调整并再导出一份。下次打开软件时，也可以从「已保存的混音」选择歌曲，点击「载入混音」继续试听。

## 音频格式与保存位置

| 项目 | 说明 |
| --- | --- |
| 导入 | MP3、WAV、FLAC、M4A |
| 新分离音轨和混音 | 320 kbps MP3，可单独下载各轨或导出整首混音 |
| 分离结果 | 默认在 `outputs/歌曲名/`，同名任务会另建带编号的目录 |
| 混音结果 | 在当前歌曲目录的 `mix-exports/` 中，每次导出保存为新文件 |
| 历史结果 | 符合当前两种分离模式的历史混音可以重新载入，支持旧版保存的 WAV 试听文件 |

源码、`start.bat` 和位于项目 `dist` 内的 EXE 默认共用项目根目录的 `outputs/` 和 `models/`。独立放在项目外的 EXE 默认使用 `%LOCALAPPDATA%\MusicVocalExtractor\`。实际结果目录以界面显示的路径为准。自定义数据目录和模型目录分别使用 `MVE_DATA_DIR` 和 `AUDIO_SEPARATOR_MODEL_DIR`，EXE 也支持 `runtime-config.json`。参见 [目录与历史迁移说明](OUTPUT_PATHS.md)。

分离前的「人声增益」和「伴奏增益」会改变分离时保存的音轨，范围为 0～+12 dB，调高时会限制过高的声音峰值。主唱和背景和声共用人声增益。dB 是表示音量变化的单位。分离后的混音器滑块用于即时试听，点击「导出混音」才会把这些调整写入新文件。参见 [音轨增益说明](AUDIO_GAIN.md)与[混音和 MP3 验收记录](EXE_MP3_VALIDATION.md)。

## 软件用到了哪些 AI 模型？

模型可以理解为已经学过如何识别不同声音的程序组件。首次使用时由 Audio Separator 下载并校验模型文件，之后复用 `models/` 中的缓存。

| 模型 | 用途 |
| --- | --- |
| Kim MelBand RoFormer（`vocals_mel_band_roformer.ckpt`） | 两种模式的第一步，从整首歌分出人声和伴奏。首次下载约 913 MB。 |
| UVR-BVE-4B v1（`UVR-BVE-4B_SN-44100-1.pth`） | 只在「主唱与和声」模式下使用，把已经分出的人声进一步拆成主唱和背景和声。首次下载约 224 MB。 |

分离效果会随录音和编曲变化。人声、和声或乐器可能残留在另一轨里，建议先用短片段试听。旧模型停用、缓存规则、模型选择和整曲测试都有单独记录。[模型说明](MODEL_VERIFICATION.md) · [多轨模型记录](MULTITRACK_MODELS.md)

## CPU 与 GPU 加速

- **CPU** 是电脑的处理器。没有 NVIDIA 显卡也可以使用，处理时间通常更长。
- **CUDA** 是让程序使用兼容 NVIDIA 显卡做运算的方式。「自动检测」会优先尝试 CUDA，初始化不可用时提示并使用 CPU。明确选择「CUDA GPU」时，设备不可用会报错。
- **性能模式** 提供高质量、平衡和快速三个选项，默认使用平衡。速度取决于硬件、歌曲长度和所选模式。运行后可以在「处理状态」中查看实际使用的设备。

安装和排查步骤、RTX 5060 实测条件以及早期模型与 EXE 测试见相关记录。[GPU 配置说明](GPU_ACCELERATION.md) · [GPU 验收记录](GPU_VALIDATION.md) · [升级验证记录](UPGRADE_VERIFICATION.md)

## 在 Windows 上安装和运行

GitHub 仓库提供源码。已有完整 EXE 包时，可以直接按上面的步骤启动。EXE 自带 Python 运行环境，仍需能找到 FFmpeg 和 FFprobe。可以使用系统已安装的版本，或把这两个程序放进 EXE 旁的 `ffmpeg/` 文件夹。

### 源码双击启动

1. 下载源码 ZIP，解压到可写的文件夹。建议使用 Windows 11 和 [64 位 Python 3.12](https://www.python.org/downloads/windows/)。
2. 在 PowerShell 安装 FFmpeg。它负责读取和保存音频，FFprobe 用于检查音频信息。

   ```powershell
   winget install --id Gyan.FFmpeg --exact
   ```

   重新打开 PowerShell，用 `ffmpeg -version` 和 `ffprobe -version` 检查安装。如果没有 winget，可从 [FFmpeg 下载页](https://ffmpeg.org/download.html) 选择 Windows 版本，并把包含这两个程序的 `bin` 目录加入 PATH。
3. 双击 `start.bat`。首次会创建项目专用的 Python 环境并安装依赖，默认使用 CPU。已配置好的 `.venv-gpu` 会优先使用，除非设置 `MVE_DEVICE=cpu`。使用期间请保留启动窗口。

可以先运行 `py -3.12 check_environment.py` 查看 Python、FFmpeg 和显卡情况。这个脚本只读取环境信息。虚拟环境请在对应操作系统上创建，本机环境若依赖 `.tools/python312`，请保留该 Python 运行时。

<details>
<summary>手动安装 CPU 或 NVIDIA GPU 依赖</summary>

在项目根目录打开 PowerShell。CPU 和 GPU 使用各自的虚拟环境，避免混装两套 ONNX Runtime。

**CPU 环境**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ui.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe app.py
```

**NVIDIA GPU 环境**

先用 `nvidia-smi` 检查显卡和驱动。此项目使用 CUDA 12.8 版 PyTorch 和 ONNX Runtime GPU 1.22.0，需要兼容的驱动。环境装好后，双击 `start.bat`，或直接运行 GPU 环境的 `app.py`。

```powershell
py -3.12 -m venv .venv-gpu
.\.venv-gpu\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv-gpu\Scripts\python.exe -m pip install -r requirements-gpu.txt -r requirements-ui.txt
.\.venv-gpu\Scripts\python.exe -m pip check
.\.venv-gpu\Scripts\python.exe verify_gpu.py
.\.venv-gpu\Scripts\python.exe app.py
```

环境检查通过后，可以实际分离一次并查看「处理状态」确认运行设备。显卡可以在混合显卡模式下工作。详细步骤见 [GPU 配置说明](GPU_ACCELERATION.md)。

</details>

## 常见问题

- **浏览器没打开怎么办？** 在启动窗口找到本地地址，复制到浏览器。端口可能随本次启动而变化。
- **一直在准备模型怎么办？** 首次下载需要网络和足够的磁盘空间。可以在启动窗口查看下载进度。下载或校验失败时，先查看窗口里的具体报错。
- **分离失败后去哪找文件？** 界面会显示错误及可用的恢复路径。失败时中间文件可能留在 `cache/separation/work_*/`，处理成功后会清理临时文件。
- **导出的音量为什么和滑块数值看起来不一样？** 试听和导出使用同一套音量比例，并预留余量，避免几条轨叠在一起时声音过响失真。
- **能分出单独的鼓或贝斯吗？** 当前的两种模式都将乐器保存在伴奏轨中。

## 主要技术与项目文件

| 文件 | 做什么 |
| --- | --- |
| `app.py`、`start.bat`、`start_windows.py` | 用 Python 和 Gradio 提供本地网页和 Windows 启动入口。 |
| `separate.py`、`models.py`、`vocal_split.py` | 用 Audio Separator 和 PyTorch 执行模型，交给 FFmpeg 处理音频输入和 MP3 编码。 |
| `mixer.html`、`mixer.css`、`mixer.js` | 用浏览器的 Web Audio 功能，让各轨按同一个时钟播放。 |
| `mix_tracks.py`、`mix_export.py` | 保存试听所需的时间轴，按混音器设置生成整首 MP3。 |
| `runtime_paths.py`、`build_exe.ps1`、`MusicVocalExtractor.spec` | 定位数据路径，并用 PyInstaller 把程序和运行环境打成 Windows 文件夹。 |
| `tests/`、`verify_release.py` | 检查分离、编码、混音和发布候选包。 |

<details>
<summary>命令行、测试和 EXE 打包</summary>

**命令行示例**

```powershell
.\.venv\Scripts\python.exe separate.py "D:\Music\歌曲.mp3" --cpu
.\.venv\Scripts\python.exe separate.py "D:\Music\歌曲.flac" --output-dir "D:\Music\分离结果"
.\.venv\Scripts\python.exe separate.py "歌曲.mp3" --vocal-gain-db 6 --instrumental-gain-db 3
.\.venv\Scripts\python.exe separate.py --help
```

Gradio 的 `/separate` 接口返回双轨，网页混音使用 `/mix`。Python API 的 `separate_audio(..., split_backing=True)` 可以返回主唱、背景和声与伴奏。

**测试**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

常规测试使用本地生成的测试信号。设置 `RUN_MODEL_TESTS=1` 可运行四种输入格式的真实分离测试。设置 `RUN_UI_TESTS=1` 可运行真实网页上传和下载测试。两者都需要 FFmpeg 和模型缓存，或允许首次下载模型。对已启动的网页可用 `verify_web.py --url` 检查上传和下载，网址以启动窗口为准。

**Windows EXE 候选包**

先在选定环境中准备 PyInstaller。下面以 GPU 候选包为例，构建 ID 请每次使用新的值。

```powershell
$buildId = 'my-release-01'
.\build_exe.ps1 -Gpu -BuildId $buildId
.\.venv-gpu\Scripts\python.exe verify_release.py --package "dist/candidate-gpu-$buildId/MusicVocalExtractor"
```

构建 CPU 版时使用 `-Cpu`、`.venv` 和对应的 `candidate-cpu` 路径，验收加 `--cpu`。需要在验收通过后更新本机正式目录时，使用同一个构建 ID 发布。CPU 发布也要带 `--cpu`。

```powershell
.\.venv-gpu\Scripts\python.exe publish_release.py --build-id $buildId --publish
```

发布脚本会核对文件清单并完整保留旧包。构建时可以用 `-FFmpegDir` 指向包含 FFmpeg 和 FFprobe 的目录。参见 [构建与回退说明](OUTPUT_PATHS.md)及 [FFmpeg 许可说明](FFMPEG_NOTICE.md)。

**Linux 源码运行**

使用 Python 3.12、FFmpeg 和独立虚拟环境。Audio Separator 的 `diffq` 依赖可能需要 GCC/G++ 和 Python 开发头文件。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
CC=gcc CXX=g++ .venv/bin/python -m pip install -r requirements.txt -r requirements-ui.txt
.venv/bin/python app.py
```

</details>

## 安全与许可证

请在本机处理可信音频，将网页服务保留在本机访问范围内。已知依赖风险和使用边界见 [安全说明](SECURITY.md)。

项目自有代码采用 MIT 许可证，版权为 Copyright (c) 2026 MusicVocalExtractor contributors。依赖、模型及 FFmpeg 遵循各自的许可与署名要求。分发程序前，请查看相关条款。[MIT 许可证](LICENSE) · [第三方许可与署名](THIRD_PARTY_NOTICES.md) · [FFmpeg 许可说明](FFMPEG_NOTICE.md)

## 后续可以评估的方向

可以继续收集不同类型歌曲的人工试听结果，并补充不同显卡和系统环境的兼容性验证。批量处理也是可评估的方向，具体安排以维护者后续决定为准。
