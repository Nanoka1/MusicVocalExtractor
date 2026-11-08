# FFmpeg / FFprobe

默认构建不捆绑 FFmpeg，运行时使用本机现有安装，或程序旁 `ffmpeg/ffmpeg.exe` 和 `ffmpeg/ffprobe.exe`。

本次检查到的本机版本为 Gyan FFmpeg 9.0.2 full build，配置带 `--enable-gpl --enable-version3`，不能当作 LGPL 构建分发。
仅供本机使用时，可通过 `build_exe.ps1 -FFmpegDir <包含两个EXE的目录>` 捆绑。
若要再分发捆绑版，必须核对所用二进制及启用库的许可证，附带适用 GPL 许可证、版权声明及对应源代码/合法有效的源代码提供方式。
本项目没有自动下载或再分发该二进制，也没有宣称完成对外发行所需的许可证材料。

官方许可说明：https://ffmpeg.org/legal.html
本机二进制来源：https://www.gyan.dev/ffmpeg/builds/
