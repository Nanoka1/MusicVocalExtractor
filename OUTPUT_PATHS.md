# 统一输出与本地构建管理

源码模式原本以模块目录为数据根目录，旧冻结模式却优先以 EXE 所在目录为 DATA_DIR，导致各版本分别写入 dist 下的 outputs。这是路径不一致的原因，与音频模型和 GPU 模式无关。

现在源码使用真实模块目录；当前项目 dist 中的 EXE 沿实际可执行文件路径查找 `mve-project.json`，同时核对应用标识、源码锚点及 dist 归属，找到项目后共用根目录 `outputs/` 和 `models/`。不依赖 CWD、固定父目录层数或 PyInstaller `_MEIPASS`。显式 `MVE_DATA_DIR` / `AUDIO_SEPARATOR_MODEL_DIR` 优先，已有 `runtime-config.json` 自定义路径继续有效。

独立复制到项目外的 EXE 不猜测开发者源码位置，默认使用 `%LOCALAPPDATA%/MusicVocalExtractor/`；可显式配置数据目录。目标不可写时明确报出完整路径并停止，不静默改存其他地方。Gradio 的“当前输出目录”及完成后的歌曲、文件名、保存位置来自实际运行路径，完整路径可复制；不提供可被公共 API 滥用的任意目录打开接口。

## 数据保护与迁移

历史 dist 输出已复制迁移到根 outputs：**11 个含文件的任务目录，共 47 个文件**，包含历史分离、测试和恢复任务，并不等于 11 首不同歌曲。逐文件大小和 SHA-256 一致，复制期间核对源文件没有变化；同名目录使用原子创建及编号，不覆盖已有输出。空的历史工作结构不计入歌曲数量。

未对旧结果进行格式转换或删除其恢复 WAV。原始上传缓存、用户配置和特殊资源另复制校验到 `.reference/old-build-data/`；旧模型与根 models 逐文件核对，不能确认唯一副本时保留副本，不重复下载大型模型。实际含私人文件名的清单只在本地忽略目录保存，不提交 Git。

迁移预览：`python migrate_outputs.py`；已明确授权时才使用 `--apply`。保护清单发生变化、发现未迁移的新文件或链接时停止清理。清理预览：`python audit_builds.py`，该命令没有删除功能。

## 构建与验收

默认 CPU 构建使用固定候选目录 `dist/candidate-cpu/MusicVocalExtractor/` 和 `build/cpu/`；已有候选不覆盖，失败保留旧正式版。候选通过真实冻结 CLI、三个模型 CPU 推理、MP3/WAV、中文空格文件名、Gradio 实际路径及试听下载验收，生成文件 SHA-256 清单后才允许发布。发布前再次核对文件未改变，并检查目标/候选未运行。

正式目录为 `dist/MusicVocalExtractor/`。原正式版及全部数据完整保留至固定 `.reference/formal-exe-rollback/`；该回退目录已经存在时停止，不无限累积回退目录，也不自动删除旧版本。新包不复制模型，配置只记录应用身份，独立分发时不携带开发者绝对目录。

```powershell
.\build_exe.ps1 -Cpu
.\.venv\Scripts\python.exe verify_release.py --cpu --package dist/candidate-cpu/MusicVocalExtractor
.\.venv\Scripts\python.exe publish_release.py --cpu
.\.venv\Scripts\python.exe publish_release.py --cpu --publish
```

独立分发 EXE 已通过实际路径检查；测试使用同卷硬链接复用程序文件，不复制模型或重复占用大型程序文件的数据空间。源码、不同 dist 深度、显式配置、不可写目录、迁移同名保护和完整性已有自动化测试；真实 start.bat 从其他工作目录启动也显示根 outputs。此前 GPU 优化完整保留，当前所有真实推理验收均为 CPU，GPU 后续验收暂停，不要求独显直连。
