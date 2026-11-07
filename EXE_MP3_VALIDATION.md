# EXE 启动、MP3 和混音器

旧正式包的 `build-info.json` 记录源码提交为 `795d5e5`。包内缺少新版混音器的 HTML、CSS 和 JavaScript，双击时执行的是这个旧包中的源码。新版构建会检查这三项资源并计算网页指纹。Gradio 服务就绪后，EXE 使用本次绑定的端口和指纹打开浏览器。

滑块原来的短音量过渡在快速输入时会被频繁取消和重设，可能在波形中造成跳变。新版每个渲染帧合并拖动事件，只更新目标有变化的 GainNode。从上一次斜坡的当前电平接到新目标，过渡为 40 ms。各轨继续共享播放时钟，静音和 Solo 采用同一套增益控制。混音导出在点击时读取最终设置，并与试听共用固定的防削波余量。

新任务输出 320 kbps MP3。试听复用这些音轨，历史混音仍可读取原来的时间轴和文件。成功后清理中间 WAV。

## 实测

- 正式路径 `dist/MusicVocalExtractor/MusicVocalExtractor.exe` 已更新。通过 Windows 资源管理器的 ShellExecute 无参数启动，在 7860 被占用时实际绑定 7861。Windows UI 自动化确认默认 Edge 打开的地址包含网页指纹 `eb2a0df28cfe58d1`，配置仍指向项目根 `outputs/`。旧正式包整体保留在 `.reference/formal-before-mp3-mixer-r2-20261107/`。
- 源码回归 54 项通过，包含真实的 MP3、WAV、FLAC、M4A 导入及本地 Gradio HTTP 下载。
- 冻结包通过网页资源、CUDA 实际推理、显式 CPU 回退和 MP3 下载检查。双轨模式也用《Rainfall》片段在网页测试了分离、共用时钟播放和混音导出。
- 冻结版从其他工作目录启动。整曲测试进程的 PATH 仅包含 Windows 目录，使用包内 Python、FFmpeg 和 FFprobe。
- RTX 5060 Laptop GPU 用 Kim 与 BVE v1 分离 MedleyDB 的完整歌曲《Rainfall》。三条 MP3 内容各不相同。新的浏览器会话从历史载入，快速拖动三条滑块，测试 0% 与 100% 切换、静音、Solo、暂停、继续和同步跳转。各轨共用同一 AudioContext、开始时刻和偏移，调整音量与导出期间没有再次提交分离。[MedleyDB 样本与许可](https://medleydb.weebly.com/downloads.html)
- Edge 的离线波形测试用恒定测试信号验证过渡连续性，记录到的最大相邻样本变化约为 0.00026，并测得静音归零。整曲导出以主唱 100%、背景和声 15%、伴奏 50%、总音量 80% 验证。独立按电平计算并对照解码结果，信号与差值的能量比约为 49.03 dB，峰值约为 0.354。三条音轨和混音均为 320 kbps、44.1 kHz、立体声，各保留 12,564,480 帧。结果目录无 WAV，分离工作目录已自动清理。
- 音量过渡验收使用浏览器实际播放与数字波形检查。外放或耳机的人工试听尚未执行。

## 修改文件

| 文件 | 修改目的 |
| --- | --- |
| `MusicVocalExtractor.spec` | 检查并收录网页资源，收录和声模型在冻结运行时需要的 samplerate 模块和 DLL。 |
| `build_exe.ps1` | 用独立构建 ID 生成候选，核对包内网页指纹，沿用已有数据路径配置。 |
| `exe_entry.py` | 提供冻结程序的网页指纹检查入口。 |
| `runtime_paths.py` | 计算当前实际加载的网页资源指纹。 |
| `publish_release.py` | 校验候选内容与测试报告，发布时完整保留上一个正式目录。 |
| `app.py` | 等待服务就绪后打开实际地址，显示网页指纹，限制输出为 MP3。 |
| `separate.py` | 将两种分离模式对齐到 MP3 兼容时间轴，统一编码并校验 320 kbps 文件。 |
| `mix_tracks.py` | 保存时间轴，让新任务直接播放 MP3，并继续读取历史混音。 |
| `mix_export.py` | 按点击时的有效电平混音，只发布校验后的 MP3，自动清理临时文件。 |
| `mixer.html`、`mixer.css` | 移除格式选择，明确显示 MP3 混音导出。 |
| `mixer.js` | 平滑调节各轨和总音量，按点击时的设置导出。 |
| `verify_models.py`、`verify_web.py` | 使用 MP3 检查真实推理、试听和下载。 |
| `verify_release.py` | 对比源码、冻结资源和网页指纹，验证双轨、三轨和混音下载。 |
| `tests/test_app.py`、`tests/test_separate.py`、`tests/test_upgrade.py` | 验证界面、分离和导入格式回归。 |
| `tests/test_audio_gain.py`、`tests/test_mix_export.py`、`tests/test_mix_tracks.py`、`tests/test_outputs.py` | 验证导出增益、混音电平、时间轴、历史读取及文件输出。 |
| `tests/test_release.py` | 验证候选校验与回退目录保护。 |
| `README.md`、`AUDIO_GAIN.md`、`GPU_ACCELERATION.md`、`MULTITRACK_MODELS.md`、`OUTPUT_PATHS.md`、`THIRD_PARTY_NOTICES.md` | 更新启动、输出、重建、历史记录和依赖说明。 |
