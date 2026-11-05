"""Windows 双击启动助手：首次安装到虚拟环境，以后直接启动界面。"""

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def run(command):
    subprocess.run(command, cwd=PROJECT_DIR, check=True)


def main():
    if sys.platform != "win32":
        print("此助手用于 Windows。Linux 请安装 requirements-ui.txt 后运行 .venv/bin/python app.py。")
        return 1
    if sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        print("请安装 Python 3.12（64 位），然后重新双击 start.bat。")
        print("下载地址：https://www.python.org/downloads/windows/")
        return 1
    for program in ("ffmpeg", "ffprobe"):
        if shutil.which(program) is None:
            print("请先安装 FFmpeg。在 PowerShell 中运行：")
            print("winget install --id Gyan.FFmpeg --exact")
            print("安装完成后，重新打开项目文件夹并双击 start.bat。")
            return 1

    gpu_python = PROJECT_DIR / ".venv-gpu" / "Scripts" / "python.exe"
    python = gpu_python if gpu_python.is_file() else PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        if (PROJECT_DIR / ".venv").exists():
            print("现有 .venv 不能用于 Windows。请先将其重命名备份，再重新启动。")
            return 1
        print("正在创建项目虚拟环境……", flush=True)
        run([sys.executable, "-m", "venv", str(PROJECT_DIR / ".venv")])

    python_command = [str(python), "-X", "utf8"]
    # 已配置好的 GPU 环境保持原样；缺少引擎时才安装 CPU 基础版。
    probe = subprocess.run(
        python_command + ["-c", "from audio_separator.separator import Separator"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if probe.returncode:
        gpu_probe = subprocess.run(
            python_command + ["-c", "from importlib.metadata import version; version('onnxruntime-gpu')"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if gpu_probe.returncode == 0:
            print("检测到未能正常导入的 GPU 环境，请按 README 修复依赖后重试，避免混装 CPU/GPU 包。")
            return 1
        print("首次使用，正在安装 AI 依赖，下载可能需要几分钟……", flush=True)
        run(python_command + ["-m", "pip", "install", "torch==2.8.0", "torchvision==0.23.0",
                              "--index-url", "https://download.pytorch.org/whl/cpu"])
        run(python_command + ["-m", "pip", "install", "-r", "requirements.txt"])

    ui_probe = subprocess.run(
        python_command + ["-c", "import gradio; assert gradio.__version__ == '6.31.0'"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if ui_probe.returncode:
        run(python_command + ["-m", "pip", "install", "-r", "requirements-ui.txt"])
    print("正在打开界面。使用期间请保留此窗口，关闭窗口将停止软件。", flush=True)
    run(python_command + ["app.py"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"启动失败：{error}\n请保留窗口中的报错信息，以便排查。")
        sys.exit(1)
