# 长音频分离与恢复

主唱与和声模式先保存基础模型的人声、伴奏 WAV，再运行 UVR-BVE-4B。BVE 采用 60 秒有效块，每侧保留 3 秒上下文及最多 1 秒淡化区域。每个块独立完成频谱、推理、逆 STFT 和落盘，避免为整段长音频构造巨大复数频谱。权重和 CUDA 推理方式不变。

相邻块在同一采样位置进行互补余弦淡化。输入窗口按 BVE 的 480 采样频谱网格对齐；尾部额外上下文使用零填充，输出有效区必须有完整的实际样本，不以补零掩盖模型输出缺失。合并时每次只读取 65536 个采样，完整音轨共用一次峰值保护，不逐块改变音量。

## 自动恢复

任务失败后，重新选择相同音频和相同设置，点击开始分离。程序按音频内容 SHA-256、模型及参数文件 SHA-256、运行库版本、设备、性能与增益等设置匹配未完成任务。上传缓存路径变化不影响同内容匹配。显式恢复也可使用：

```powershell
.venv-gpu/Scripts/python.exe separate.py "原曲.mp3" --device cuda --split-backing --resume-work "cache/separation/work_任务编号"
```

`task.json` 保存第一阶段成功状态；`bve/chunks.json` 保存每个完整块的范围、采样格式、文件大小和 SHA-256。检查点采用写临时文件、刷新落盘、原子替换。恢复时逐文件验证 WAV 声明长度、全部采样、有限值、时间轴及哈希。文件仅存在、进度到 100% 或一次推理返回，均不构成成功依据。

不完整块不计入检查点；损坏块保留在原处，在新目录重新计算。输入或模型参数变化时，显式恢复拒绝复用。两个进程不能同时修改同一任务。

失败时保留恢复材料。MP3 编码后还要检查编码、解码采样时间轴和完整 FFmpeg 解码，全部结果复制及混音清单准备成功后，才清理本次任务目录。导出失败后可复用已有模型输出重新导出；暂不单独恢复某条已完成的 MP3。原曲、模型、历史结果以及导入的旧缓存原件不会因此清理。

## 旧版缓存

旧版没有检查点，无法恢复未落盘的 BVE 计算。对实际存在的完整第一阶段 WAV，可显式提供原曲、旧任务路径及来源日志：

```powershell
.venv-gpu/Scripts/python.exe separate.py "原曲.mp3" --device cuda --split-backing --legacy-work "cache/separation/work_旧任务编号" --legacy-log "cache/logs/旧任务.log"
```

程序要求日志关联原曲、基础模型名称和该任务的人声 WAV，并全量验证两条 WAV 及原曲时间轴，再复制到新的恢复任务。旧版没有保存的精确参数及权重快照不能追溯证明；导入记录会明确保留这个限制，不将导入表述为恢复旧推理状态。无法关联来源的旧缓存不会自动采用。

## 进度和内存原因

网页和终端通过同一阶段回调显示：第一阶段推理及 WAV 写出、已完成 BVE 块数、当前块频谱后处理/逆 STFT、交叉淡化合并、MP3 编码及验证、失败及恢复。耗时阶段每 10 秒报告一次实际阶段及耗时，不制造整体百分比。内部 tqdm 的 100% 仅表示对应内部循环结束。

Audio Separator VR 的 `inference_vr.postprocess` 对整段音频执行 `mask * X_mag * exp(1j * X_phase)` 及互补掩膜。形状 `(2, 673, 432958)` 的 complex64 单个数组即约 4.34 GiB，多个输入、掩膜和输出同时存在会进一步提高峰值。其频谱转波形实现还会构建 complex128 分频段数组，随后在 librosa 逆 STFT 产生 float64 临时数组。减少 batch_size 不能限制这些整曲后处理数组。

参考：[上游 VR 实现](https://github.com/nomadkaraoke/python-audio-separator/blob/main/audio_separator/separator/architectures/vr_separator.py)、[上游频谱转换实现](https://github.com/nomadkaraoke/python-audio-separator/blob/main/audio_separator/separator/uvr_lib_v5/spec_utils.py)。本项目使用实例局部适配器报告阶段并写浮点中间音频，不修改虚拟环境中的依赖文件。

第一阶段 RoFormer 本身仍使用现有实现；此次限制的是新增 BVE 阶段的内存。恢复过程会增加磁盘占用和校验时间。未经过实际长音频、GPU、导出和恢复验证的构建不能仅凭编译成功认定为通过。
