# 2026-11-05 升级验证记录

使用项目已有 Windows 11 / Python 3.12.10 虚拟环境：audio-separator 0.48.0、torch 2.8.0+cpu、Gradio 6.31.0、系统 FFmpeg/FFprobe。没有重装或升级健康环境。`pip check` 通过。原始歌曲、历史输出、旧模型缓存和历史构建均保留。

## 自动化与真实执行

最终完整回归：**20 项全部通过，无跳过**（同时设置 RUN_MODEL_TESTS=1、RUN_UI_TESTS=1）。第一次新模型及 HTTP 元信息测试中的失败已修复并重跑通过；不是将失败用例跳过。

| 场景 | 验证方式与结果 |
|---|---|
| MP3/WAV/FLAC/M4A 输入 | 原有真实 MDX 模型测试四种输入通过；另有真实 FFmpeg 矩阵覆盖四种输入 × MP3/WAV 两种输出，使用确定性推理替身隔离导出行为 |
| MP3 320 kbps | 使用真实 libmp3lame；FFprobe 核对 mp3、320000 bit/s、44100 Hz、双声道；FFmpeg 完整解码通过 |
| WAV 模式 | 只发布两条 PCM WAV；不生成额外 MP3，成功后临时副本删除 |
| 成功目录无 WAV/临时文件 | 测试以目录文件集合等于返回的两个结果文件断言，而非只检查两个 MP3 是否存在 |
| 编码失败保护 | 强制第二轨编码失败，断言没有成功消息、两个源 WAV 和第一条已编码 MP3 均保留，空结果目录撤销 |
| 中文/英文/空格/特殊字符 | 实际 FFmpeg 使用中文、空格、& 路径；标题测试含英文、非法字符、设备保留名、路径穿越、超长 emoji UTF-16 路径 |
| 重复名称与并发 | 同名原子 mkdir 并发分配 16 个独立目录；真实多次分离也获得不同目录，历史文件不覆盖 |
| 上传原名 | `gr.File` 子类在 NamedString 转换前保存 `FileData.orig_name`。单测用随机缓存名 + 中文原名；真实 HTTP/SSE 直接提交浏览器等效元信息，生成 `周杰伦 - 晴天/` 及两个同名 MP3 |
| 试听/下载 | 真正通过 HTTP 获取两条 MP3 下载及试听资源，内容逐字节一致、可解码，下载 orig_name 与最终结果名一致；保留原有 Python 客户端 WAV 测试 |
| 指定旧模型删除 | 配置、默认值、CLI choices、构建缓存清单均去除 Karaoke 2 / htdemucs；模型校验测试确认两个 MDX 仍在白名单 |
| MDX 实际调用 | Voc FT 的 WAV、MP3 与 Inst HQ 3 的 WAV 均完成真实 CPU 推理，格式/时长/有限值/不同音轨检查通过 |
| RoFormer 下载/校验 | 实际首次下载 913,106,900 字节权重及 YAML，两者通过上游 SHA-256；作者原始权重 LFS SHA 与镜像一致 |
| RoFormer 加载/推理 | Windows CPU，3 秒合成信号的真实加载、推理、双轨 MP3 导出通过；真实 HTTP 另用 1 秒合成信号通过 |
| 缓存复用 | 阻止 `requests.sessions.Session.request` 后仍能完成 RoFormer 真实推理；自动化替身另覆盖首次下载与重复加载不写入已有文件 |
| 下载/加载失败 | 单测覆盖模拟网络中断、缺失校验值、损坏 YAML 保留、加载 SystemExit 转为可见错误；未人为破坏真实模型缓存 |
| CPU/GPU | CPU 真实执行通过；检测到 RTX 5060 Laptop 8151 MiB，但现有 torch 为 CPU 版，未验证 CUDA 推理、速度或显存峰值 |
| CLI/启动 | CLI 真实分离通过；`start.bat` / `start_windows.py` 保持现有双击启动逻辑；不修改系统配置 |
| Windows EXE | 最终构建成功；真实 EXE 的 CLI MDX 分离、Gradio 启动、RoFormer CPU 推理、MP3 下载/试听一致性与双文件结果检查全部通过 |

首轮普通测试受沙箱临时目录权限及本地 socketpair 阻塞影响，切换到项目 `.tools/tmp` 和获准的本机执行后通过；没有修改 Windows 权限。首次新模型测试发现 vocals/other 标签差异，已修复并真实重测。Python Gradio 客户端会按本地文件名重写 orig_name，因此原名与缓存名不同的测试改为浏览器等效的真实上传 + HTTP/SSE 调用，保留服务端安全检查。

## 可复现检查

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:RUN_MODEL_TESTS = '1'
$env:RUN_UI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_MODEL_TESTS
Remove-Item Env:RUN_UI_TESTS
.\.venv\Scripts\python.exe verify_models.py
.\.venv\Scripts\python.exe -m pip check
.\build_exe.ps1
```

完整测试和模型检查会创建自己的合成音频，不使用个人歌曲。音频、机器可读报告、缓存、日志和构建产物位于已忽略目录，不随 Git 提交。主要本地记录：`.tools/upgrade-final-tests.log`、`.tools/upgrade-all-models.log`、`.tools/upgrade-roformer-test-fixed.log`、`.tools/upgrade-ui-roformer-fixed.log`、`test_artifacts/中文 测试 & 音频/model-test-report.json`。

最终已验证的本机 EXE：`dist/build-20261105-221431/MusicVocalExtractor/MusicVocalExtractor.exe`。构建日志 `.tools/upgrade-build-final.log`；实机日志 `.tools/upgrade-exe-test.log`，机器可读报告 `test_artifacts/exe-upgrade-20261105-221944/report.json`。验证显式复用项目 `models/`，将数据根目录隔离到该测试目录，结束时仅关闭验证程序创建的 EXE；没有更换用户旧 EXE，也没有删除旧构建。默认打包仍不含权重。其他电脑上的运行与完整二进制再分发许可不在这次实机验证范围内。

## 范围限制

没有用户授权的真实歌曲与参考 stems，本机未进行完整歌曲 AB 试听、SDR/SI-SDR 质量测评；合成信号只验证功能链路。质量参考是上游公开逐曲数据，来源、共同样本计算及局限见 [MODEL_RESEARCH.md](MODEL_RESEARCH.md)。默认仍保留 Voc FT，不把新模型的功能通过宣称为真实歌曲音质认证。

没有验证其他 Windows 电脑、所有输入采样率组合、超长完整歌曲峰值资源、低磁盘/断电恢复、GPU 实际显存占用，以及外部分发的二进制许可证材料。推理保留引擎官方采样率和参数，不更改用户输入。失败工作目录可由用户按错误提示手动恢复或清理，程序不会批量清理旧失败任务和历史输出。
