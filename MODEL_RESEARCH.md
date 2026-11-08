# 模型升级调研与选择

查询日期：**2026-11-05（Asia/Shanghai）**。Star 来自当次 GitHub REST `GET /repos/{owner}/{repo}` 的 `stargazers_count`，不是搜索引擎的四舍五入数字。下表按仓库 Star 排序；软件、推理框架、架构实现和具体 checkpoint 分开评估。Star 不代表音质。

| 项目与类型 | Star | 架构、歌曲人声适用性与质量依据 | 预训练权重 / 工程兼容性 | 代码与权重许可 |
|---|---:|---|---|---|
| [Anjok07/ultimatevocalremovergui](https://github.com/Anjok07/ultimatevocalremovergui)，完整桌面软件 | 26,971 | 支持 MDX-Net、VR、Demucs、RoFormer 等；适合歌曲人声，但软件没有单一的音质分数 | 有公开模型清单；现有两个 MDX 即来自该生态，无需嵌入整个 GUI | GUI 代码 MIT；各权重单独核对；VIP 权重不作为本次候选 |
| [facebookresearch/demucs](https://github.com/facebookresearch/demucs)，模型与推理项目 | 10,406 | Hybrid Transformer Demucs；适合多轨，包括人声；README 报告 MUSDB HQ 全源 SDR 9.0，不能当作人声 SDR 与下表直接比较 | 公开 htdemucs 权重；已有引擎支持，但用户要求移除该具体模型，不再集成 | 代码 MIT；参照官方权重发布条件；仓库已归档、维护受限 |
| [ZFTurbo/Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)，训练/评估框架 | 1,624 | 支持 BS/MelBand RoFormer、MDX23C、SCNet、BSMamba2 等；是否适合人声取决于 checkpoint 的 target/stems | 有各架构权重和配置；只复用 audio-separator 已支持的公开模型，不额外安装第二套训练框架 | 框架 MIT；外部 checkpoint 许可各异，不能用框架 MIT 替代 |
| [nomadkaraoke/python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)，统一推理/下载引擎 | 1,471 | 多架构；质量取决于实际模型；提供逐曲和汇总评分 | 当前固定 0.48.0 已支持 Kim MelBand，模型、配置、SHA-256 均齐全，兼容性最高 | 引擎 MIT；权重仍按作者许可 |
| [lucidrains/BS-RoFormer](https://github.com/lucidrains/BS-RoFormer)，BS/MelBand 架构实现 | 1,013 | 频率/时间 Transformer + RoPE；论文支持其音乐分离能力，不表示任何同名权重都具有论文指标 | 链接 ZFTurbo 和 Kim 已训练权重；现有引擎已有实现，无需直接增加依赖 | 实现 MIT；Viperx 等权重需另行核实，未将实现许可证套用于它们 |
| [KimberleyJensen/Mel-Band-Roformer-Vocal-Model](https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model)，具体人声模型 | 434 | MelBand RoFormer；训练目标明确为 vocals，输出 vocals + 完整 other；本次选择，质量参考见下文 | 作者发布真实权重；0.48.0 将其命名为 `vocals_mel_band_roformer.ckpt`，可直接调用现有 MDXC 适配器 | GitHub 仓库 API 未识别独立 LICENSE；本项目不复制其仓库源码。实际调用 MIT 引擎，作者 [Hugging Face 权重卡](https://huggingface.co/KimberleyJSN/melbandroformer/blob/main/README.md)明确标注 MIT |

## Windows、硬件与资源

以下“支持”指上游推理路径及工程可用性，不等于本机 GPU 实测通过。所有候选均有 PyTorch/ONNX CPU 与 NVIDIA 路径，Windows 可使用其 Python 实现或现有 audio-separator 适配器；ZFTurbo/新架构的全部训练依赖并不因此成为本项目依赖。

| 具体候选 | 下载体积 | Windows / CPU / NVIDIA | 内存与显存 / 速度 / 当前项目接入 |
|---|---|---|---|
| UVR Voc FT / Inst HQ 3 | 66,762,490 / 66,759,214 字节 | 两个模型均 Windows CPU 真实推理通过；NVIDIA 需要 ONNX Runtime CUDA | 相比 RoFormer 小且 CPU 较快；显存随 segment、batch 改变，未测最低值；保留原 MDX 路径 |
| htdemucs | 本地权重 84,141,911 字节，另有 YAML；FT ensemble 会更大 | 上游支持 Windows CPU/CUDA | 多轨额外计算及合成；官方有分段控制显存方案，不能承诺所有机器固定用量；按用户要求移除 |
| Viperx BS-RoFormer 1297 | 639,331,213 字节，另有 YAML | audio-separator 原生 MDXC / Windows CPU/CUDA 路径 | 较重，依赖 chunk、overlap、精度；未进行本机推理/显存测量；有可下载权重，但其具体授权未充分核实，未添加 |
| Kim MelBand RoFormer | **913,106,900 字节**，另有 944 字节 YAML | **Windows CPU 真实推理通过**；NVIDIA 使用 PyTorch CUDA，不要求此模型由 ORT 执行 | 权重体积不等于 RAM/VRAM；CPU 慢于 MDX。保留官方 chunk=352800、num_overlap=1、float32，不承诺固定最低显存；本机为 CPU 版 torch，无 GPU 推理实测 |
| MSST 的其他新架构（SCNet、BSMamba2 等） | 随 checkpoint 不同，未下载，不填写虚构统一大小 | 上游提供 CPU/CUDA 路径；逐一 Windows 集成仍需验证 | 当前白名单/引擎并不自动兼容所有架构；本轮不引入新引擎和额外模型 |

本机检测到 RTX 5060 Laptop 8151 MiB，但健康项目环境为 torch 2.8.0+cpu；未为本任务重装 CUDA 依赖。没有实际 GPU 峰值，亦没有将作者 README 中训练所需的 40 GB 显存误写为推理需求。资源不足应选保留的 MDX 或更短音频；用户可在独立 GPU 环境按 README 配置后实测。

## 质量依据与取舍

原始依据：[Audio Separator 0.48.0 逐曲评分](https://github.com/nomadkaraoke/python-audio-separator/blob/v0.48.0/audio_separator/models-scores.json)、[BS-RoFormer 论文](https://arxiv.org/abs/2309.02612)、[MelBand RoFormer 论文](https://arxiv.org/abs/2310.01809)。论文模型、社区 checkpoint 及测试集不同，不能混为同一次测评。

本次没有具有授权的歌曲及其干净参考 stems，不能自行报告歌曲 SDR。为避免直接比较 Kim 的 11 首与其他模型的 40/41 首汇总值，仅对上游文件中四个候选**共同的 11 首**逐曲人声指标重新取中位数：

| checkpoint | 人声 SDR ↑ | SIR ↑（干扰抑制） | SAR ↑（伪影） |
|---|---:|---:|---:|
| Kim MelBand | 12.5967 | 25.5790 | 13.4438 |
| Viperx BS 1297 | 12.8670 | 25.2781 | 13.8535 |
| Voc FT | 10.6445 | 21.2362 | 11.0698 |
| Inst HQ 3 | 10.2541 | 20.3640 | 10.8039 |

这是对上游公开数据的重算，**不是本机音质复测**。Kim 在这组数据的人声分离和干扰抑制表现强于两个 MDX；Viperx 的部分指标更高，不能称 Kim 全面最好。Kim 的 `other` 不能与四轨模型的 Other 指标混用，亦不使用其伴奏负分做结论。人声清晰度、人声残留、伴奏漏人声、音乐细节和高频失真仍需真实歌曲 AB 试听；这些指标不能穷尽主观音质。

选择 Kim 的原因是：人声目标明确、公开人声评分良好、权重卡 MIT 明确、现有固定引擎直接兼容、真实下载/校验/加载/推理已通过。只新增这一款，保留轻量 MDX。**默认仍为 Voc FT**：本轮合成信号验证功能，未完成真实歌曲音质验证，不据此把新模型设为默认。

## 权重来源与身份

- [作者 GitHub README](https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model) 指向 [原始 MelBandRoformer.ckpt](https://huggingface.co/KimberleyJSN/melbandroformer/blob/main/MelBandRoformer.ckpt)。
- 引擎使用 [官方 release 镜像](https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs/vocals_mel_band_roformer.ckpt) 和 [参数 YAML](https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs/vocals_mel_band_roformer.yaml)。原始 Hugging Face LFS SHA-256 与下载镜像、引擎校验清单一致，确认是同一权重而非仅凭文件名判断。
- 权重 SHA-256：`87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e`。
- YAML SHA-256：`b958b29c8f7195f0d86bee6759a33980db675c4ecaf2fcaa80fa125828e6cd38`。
- 由引擎官方机制下载 `.partial`、校验后原子改名；本项目在下载前检查所有权重/配置文件及校验值是否存在，损坏旧文件保留并报错。有效缓存实测在禁止 requests 网络的情况下仍能完成新模型推理。
- 权重、模型缓存、测试音频、输出和 EXE 均不提交 Git；不复制 Kim GitHub 仓库的未明确许可代码。
