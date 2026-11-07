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

## 模型 B · 主音吉他与节奏吉他

| 项目 / checkpoint | Star | 主音吉他 | 节奏吉他与质量依据 | GPU / Windows 11 | 代码与权重许可 |
|---|---:|---|---|---|---|
| [Sound Razor](https://github.com/pedromtcosta/sound-razor#lead-and-rhythm-guitar) / listra92 Mel-Band RoFormer | 2 | 模型预测，输入为总吉他轨 | 原吉他减去预测主音。参考实现说明有串音，未找到作者整曲基准 | PyTorch 具 CUDA 路径；本机整曲未测 | 参考代码和 RoFormer 实现 MIT；[社区权重仓库](https://huggingface.co/noblebarkrr/mvsepless_resources/tree/283025218e6447db47da1ad18df3c2f67ca8d66d)缺少许可证、模型卡和原作者许可 |
| [Demucs](https://github.com/facebookresearch/demucs) / `htdemucs_6s` | 10,406 | 只提供总吉他 | 同一总吉他轨。作者将六轨版标为实验性，提示钢琴有串音和伪影 | PyTorch CPU / CUDA，官方提供 Windows 使用说明 | 官方公开权重和 MIT 代码；本次未单独核验该 checkpoint 的发布条款 |
| [Music Source Separation Training](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21) / Mega 53 Stems | 1,625 | 只有总吉他、电吉他、木吉他等乐器类别 | 无节奏角色输出；电/木吉他类别不能代替演奏角色 | PyTorch CUDA，作者建议 16 GB 以上；未实测 Windows | 框架 MIT，权重没有单列许可 |
| [MVSep Lead/Rhythm Guitar](https://de.mvsep.com/en/full_api) | — | 服务明确提供主音输出 | 提供节奏输出，服务报告其两阶段 9.21 dB、一阶段 9.02 dB SDR；与 listra92 没有同口径数据 | 远程服务 | 未找到对应可下载且有许可的本地 checkpoint |

**暂缓接入模型 B**。listra92 是已找到最符合任务的本地权重候选。它需要原作者确认权重许可，并在有真实主音和节奏参考轨的完整歌曲上评估泄漏和伪影。架构实现的 [MIT 许可](https://github.com/lucidrains/BS-RoFormer)不授予社区 checkpoint 的使用权。

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
| 主音和节奏吉他、两专用模型并行 | 权重许可待核实，相关功能与并行推理没有验收。鼓、贝斯、钢琴等乐器仍包含在伴奏轨内。 |
| 首次自动下载与 EXE | BVE 已从 UVR 官方发布下载并通过 SHA-256，验收使用该缓存；未再次清空缓存测试首次自动下载。此次实测的是 Python 版，未重新构建或验收 EXE。 |

单曲质量观察采用 MedleyDB 的第 1 轨作为主唱参考、第 2 和第 3 轨之和作为背景和声参考。对单声道下采样信号计算 SI-SDR，主唱约 **14.85 dB**，背景和声约 **4.60 dB**。两条输出的能量和参考轨相关性有明显区别，和声轨仍有较多误差。该结果来自一首歌的客观比较，未做主观 AB 试听。
