"""检查开发环境。只读取配置，不安装软件，也不修改系统。"""

import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def check_command(title, command):
    """运行一个检查命令，失败时显示原因并继续其他检查。"""
    print(f"\n[{title}]", flush=True)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, errors="replace", timeout=20
        )
    except FileNotFoundError:
        print("Command not found. It may not be installed or on PATH.")
        return
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Check unavailable: {error}")
        return

    output = (result.stdout or result.stderr).strip()
    if result.returncode == 0:
        print(output or "OK")
    else:
        print(f"Check failed (exit {result.returncode}): {output}")


def main():
    print("MusicVocalExtractor - Environment Check")
    print("This report describes the machine running this script.")
    print(f"OS: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Python executable: {sys.executable}")
    print(f"Python bits: {64 if sys.maxsize > 2**32 else 32}")
    print(f"Architecture: {platform.machine()}")
    print(f"CPU: {platform.processor() or 'Unknown'}")
    print(f"Logical CPUs: {os.cpu_count()}")
    print(f"Virtual environment: {sys.prefix != sys.base_prefix}")

    project_folder = Path(__file__).resolve().parent
    free_gb = shutil.disk_usage(project_folder).free / 1024**3
    print(f"Free disk space (project drive): {free_gb:.1f} GiB")

    if platform.system() == "Windows":
        check_command("CPU and physical memory", [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance Win32_Processor | Select-Object Name | Format-List; "
            "Get-CimInstance Win32_ComputerSystem | "
            "Select-Object @{Name='RAM_GiB';Expression={"
            "[math]::Round($_.TotalPhysicalMemory / 1GB, 1)}} | Format-List",
        ])
    elif platform.system() == "Linux":
        ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
        print(f"Physical RAM: {ram_gb:.1f} GiB (host; container limits may differ)")

    check_command("pip", [sys.executable, "-m", "pip", "--version"])
    check_command("FFmpeg", ["ffmpeg", "-version"])
    check_command("NVIDIA GPU", [
        "nvidia-smi", "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader",
    ])

    print("\n[Installed Python packages]")
    for package in ("audio-separator", "gradio", "torch", "onnxruntime", "onnxruntime-gpu"):
        try:
            print(f"{package}: {importlib.metadata.version(package)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"{package}: not installed in this Python environment")

    print("\nNVIDIA detection does not prove GPU inference works.")
    print("A missing command does not prove that the computer has no GPU.")
    print("Dependency compatibility and audio separation will be checked in later stages.")


if __name__ == "__main__":
    main()
