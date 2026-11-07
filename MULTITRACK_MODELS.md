# 多轨模型选型

GitHub Star 为 2026-11-07 通过 GitHub REST API 查询的仓库 Star。表中分别比较 checkpoint 的训练目标、公开质量依据、许可与运行方式。

## 模型 A · 主唱与背景和声

| 项目 / checkpoint | Star | 主唱和和声能力与质量依据 | GPU / Windows 11 | 代码与权重许可 |
|---|---:|---|---|---|
| [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) / UVR-BVE-4B v1 | 26,999 | 输入已分离的人声。官方模型参数标记 `is_bv_model=true`；UVR 把主输出标为和声，互补输出标为主唱。未找到可直接横向比较的官方整曲指标 | PyTorch CUDA / CPU；UVR 支持 Windows，使用现有 Audio Separator VR 后端 | UVR 代码 MIT。UVR 开发者在 README 明确允许第三方在遵守 MIT 并署名的条件下使用团队模型；v1 由核心开发者 TRvlvr 在 UVR 公共模型仓库发布 |
| [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) / UVR-MDX-NET Karaoke 2 | 26,999 | [官方 MDX 元数据](https://github.com/Anjok07/ultimatevocalremovergui/blob/master/models/MDX_Net_Models/model_data/model_data.json)标记为 Karaoke。对纯人声输入可作为候选；没有本次同曲结果可与 BVE 比较 | ONNX Runtime CPU / CUDA，需验证会话首选 Provider；引擎支持 Windows | UVR 团队发布，沿用官方许可及署名 |
| [Audio Separator](https://github.com/nomadkaraoke/python-audio-separator/tree/v0.48.0) / UVR-BVE-4B v2 | 1,474 | 引擎内置参数同样标记为 BVE，采用不同频带参数；不能从版本号推断整曲质量 | PyTorch CUDA / CPU；同一 VR 后端 | 引擎 MIT；镜像发布权重和 SHA-256，未查到该版本的 UVR 原发布及许可说明 |
| [Music Source Separation Training](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21) / Mega 53 Stems | 1,625 | 有 `lead-vocal`、`back-vocal`，也有聚合人声。作者说明单项效果可能低于专用模型，重叠轨道会重复计入混音 | PyTorch CUDA；作者建议至少 16 GB 显存；本机 Windows / 8 GB 未验 | 框架 MIT；该发布未单列 checkpoint 许可 |

**选用 UVR-BVE-4B v1**。它有专用 BVE 标签、可核对的团队发布和现有引擎支持。发布权重为 223,650,277 字节，Audio Separator 0.48.0 提供 SHA-256 `56165bdfa0dd5df7930ff76652200dc287e1bfef622bba5c812c736dc22067fe`。VR 后端把两个输出命名为 `Vocals` 和 `Instrumental`，项目按官方 BVE 语义分别映射为背景和声、主唱。第二轨来自互补掩膜，分离可能有串音。感谢 Anjok07、TRvlvr 和 Ultimate Vocal Remover 团队。[UVR 官方权重](https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models) · [UVR 模型参数](https://github.com/Anjok07/ultimatevocalremovergui/blob/master/models/VR_Models/model_data/model_data.json) · [UVR 轨道映射](https://github.com/Anjok07/ultimatevocalremovergui/blob/master/UVR.py) · [UVR 许可](https://github.com/Anjok07/ultimatevocalremovergui#license)

## 接入方案

- `vocal_split.py` 复用 Audio Separator 0.48.0 的 VR 推理、官方列表、权重 SHA-256 和下载锁。第一次需要联网，之后复用现有 `models` 缓存。BVE 接收第一阶段的原始人声 WAV。
- `separate.py` 与 `app.py` 接入一键流程。Kim MelBand RoFormer 完成后释放第一阶段显存，再运行 BVE。自动模式优先 CUDA，CUDA 初始化不可用时可提示并回退 CPU；显式 CUDA 保持报错。
- `mix_tracks.py` 保存与原曲解码后采样数、采样率、声道数一致的 WAV 和时间轴。`mixer.html`、`mixer.css`、`mixer.js` 通过一个 Web Audio 时钟调度并使用独立的 GainNode。零音量直接静音，调整音量无需再次调用后端。
- 沿用 Windows 11 上的 Python 3.12.10、PyTorch 2.8.0+cu128、cuDNN 9.10.2、ONNX Runtime GPU 1.22.0、Gradio 6.31.0 与 FFmpeg。两阶段均走 PyTorch，无新增 Python 或浏览器依赖。

## 本机验收

2026-11-07 在 Windows 11、RTX 5060 Laptop GPU、Edge 上运行。使用 Liz Nelson & Jennifer Davies 的完整歌曲《Rainfall》，由 Rachel Bittner 等人收录于 MedleyDB 样本。按数据集 CC BY-NC-SA 4.0 条件用于本地非商业验证，测试音频和输出均在 Git 忽略目录中临时使用。[MedleyDB 许可与样本](https://medleydb.weebly.com/downloads.html)

| 项目 | 结果 |
|---|---|
| 原有两轨流程 | 真实上传、RoFormer CUDA 推理、MP3 320 kbps 下载、原 `/separate` 接口和试听字节校验通过。另用 48 kHz 单声道短文件在 Edge 验证两轨混音。 |
| 自动化回归 | 51 项全部通过，含两项真实 Gradio HTTP 测试和 MP3、WAV、FLAC、M4A 四格式真实推理测试。 |
| 一次上传和一次分离 | 《Rainfall》点击一次生成主唱、背景和声、伴奏。总用时 83.88 秒，其中 BVE 阶段 32.64 秒。 |
| 实际 CUDA | Kim RoFormer 的前向张量设备通过既有校验。BVE 的 69 批掩膜预测中，模型参数、输入和输出均为 CUDA。该任务 PyTorch 峰值分配约 1.95 GiB。 |
| CPU 自动回退及缓存 | 在独立进程中隐藏 CUDA，自动模式在《Rainfall》4 秒片段上完成两阶段 CPU 推理，实际张量设备已核对。测试禁止 HTTP 请求，确认两模型可离线复用缓存。 |
| 保存与时间轴 | 原曲与三条试听 WAV、三条 WAV 下载均为 12,564,480 帧、44.1 kHz、立体声，时长约 4 分 45 秒。对主唱与和声参考轨检查的最强相关位置在零采样偏移。 |
| 浏览器同步和控制 | Edge 实测所有轨道共享 AudioContext，每次开始、继续和跳转的开始时刻与偏移一致。验证了暂停、同一终点、独立 GainNode 0% 静音与 50% 恢复、总音量、Solo、恢复默认、开启及静音全部。刷新页面后载入混音并播放，无额外分离请求。 |
| 首次自动下载与 EXE | BVE 已从 UVR 官方发布下载并通过 SHA-256，验收使用该缓存；未再次清空缓存测试首次自动下载。此次实测的是 Python 版，未重新构建或验收 EXE。 |

单曲质量观察采用 MedleyDB 的第 1 轨作为主唱参考、第 2 和第 3 轨之和作为背景和声参考。对单声道下采样信号计算 SI-SDR，主唱约 **14.85 dB**，背景和声约 **4.60 dB**。两条输出的能量和参考轨相关性有明显区别，和声轨仍有较多误差。该结果来自一首歌的客观比较，未做主观 AB 试听。

## 两种分离模式与混音导出

| 文件 | 整改内容 |
|---|---|
| `app.py`、`separate.py`、`models.py` | 双轨与三轨入口，继续使用 Kim 与 BVE。移除额外乐器的界面选项与分离分支。 |
| `mix_tracks.py` | 校验两类历史时间轴和试听规格。只有匹配这两类的历史结果显示在播放器中。 |
| `mixer.html`、`mixer.css`、`mixer.js` | 共享播放时钟、独立静音、Solo、试听电平和混音导出界面。 |
| `mix_export.py` | 从原时间轴分块叠加音频，导出 WAV 或 MP3，核验格式、长度及峰值。 |
| `tests/test_mix_tracks.py`、`tests/test_mix_export.py` | 历史模式筛选、WAV 音量核对、MP3 时长、防削波和重复导出测试。 |
| `instrument_split.py`、`tests/test_instrument_split.py` | 删除仅服务于额外乐器分离的实现与测试。 |
| `README.md`、`THIRD_PARTY_NOTICES.md`、`MULTITRACK_MODELS.md` | 更新当前使用说明、模型许可与验收记录。 |

实时试听和混音导出共用各轨音量、静音、Solo、总音量和固定防削波系数。系数由各轨峰值之和计算，保留至少 2 dB 的样本峰值余量，调整单轨时系数固定。试听与导出均有 5 ms 首尾淡入淡出，拖动滑块时用短增益过渡。WAV 为 24 位 PCM，MP3 有编码损失。混音导出按点击时的设置从歌曲开头渲染，文件保存在该歌曲的 `mix-exports/`。

### 整改后复验

- Windows 11 上通过真实 Gradio 和 Edge 上传《Rainfall》8 秒片段进行双轨分离，上传 284.909 秒整曲进行三轨分离。Kim 和 BVE 的实际设备均为 RTX 5060 Laptop CUDA。三条整曲音轨的文件哈希各不相同，保持 12,564,480 帧、44.1 kHz、立体声。与参考轨比较，主唱和和声 SI-SDR 为 14.85 dB 和 4.60 dB，两条参考相关峰均位于零采样偏移。
- 两种模式各只提交一次分离。验证共用 AudioContext、暂停继续、同步跳转和终点、滑块实时调节、独立静音恢复、Solo 及历史重载。两种模式均从网页下载 WAV 和 MP3，并重复导出 WAV。
- 浏览器导出的 WAV 与相同电平计算值逐样本比较，最大误差小于 0.00000012，属于 24 位 PCM 量化量级。用主唱 100%、背景和声 0%、伴奏 50% 的整曲作为三轨 WAV 检查。MP3 用伴奏 Solo 和总音量 70% 验证，实际编码为 320 kbps，解码后保持原帧数、声道和采样率。重复导出同设置的 WAV 字节一致，下载名称各不相同。
- 53 项回归测试均获得通过结果。并发整曲验收期间有一项旧接口测试占用同一模型缓存锁，单独复跑旧 Gradio 测试组后，五项均通过。四种支持的输入格式均经过真实推理。本轮验收使用 Python 版。
