"""Preview by default; publish a verified GPU candidate without deleting history."""
import argparse
import json
import subprocess
from pathlib import Path

from verify_release import package_manifest


def validate_candidate(package, require_gpu=True):
    report = json.loads((package / "release-validation.json").read_text(encoding="utf-8"))
    if not (report.get("passed") and report.get("gpu" if require_gpu else "cpu") and report.get("http_preview_download") and report.get("models_shared")):
        raise RuntimeError("候选没有通过完整设备/网页/缓存验收。")
    if package_manifest(package) != report.get("manifest"):
        raise RuntimeError("候选文件与实测清单不同，请重新验证。")
    return report


def assert_not_running(folders):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                             "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter \"Name='MusicVocalExtractor.exe'\" | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    rows = rows if isinstance(rows, list) else [rows]
    for row in rows:
        if not row.get("ExecutablePath") or any(Path(row["ExecutablePath"]).resolve().is_relative_to(folder.resolve()) for folder in folders):
            raise RuntimeError(f"待发布目录可能正在运行（PID {row['ProcessId']}），请先关闭该程序。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    dist = (root / "dist").resolve()
    candidate = (dist / ("candidate-cpu" if args.cpu else "candidate-gpu") / "MusicVocalExtractor").resolve(strict=True)
    target = (dist / ("MusicVocalExtractor" if args.cpu else "MusicVocalExtractor-GPU")).resolve()
    if not candidate.is_relative_to(dist) or not target.is_relative_to(dist):
        raise RuntimeError("发布路径超出项目 dist。")
    validate_candidate(candidate, require_gpu=not args.cpu)
    if target.exists() and not args.cpu:
        raise RuntimeError("GPU 正式版已经存在，保留当前版本和候选。请先审查回退及数据保留方案；不自动覆盖或删除。")
    backup = (root / ".reference" / "formal-exe-rollback").resolve()
    if args.cpu and target.exists() and backup.exists():
        raise RuntimeError("固定回退目录已存在，保留正式版和候选；请先审查回退保留方案。")
    print(f"已验证候选：{candidate}\n正式目录：{target}\n旧正式版及数据完整保留到：{backup}")
    if args.publish:
        assert_not_running([candidate, target])
        if not backup.is_relative_to(root.resolve()) or not dist.is_relative_to(root.resolve()):
            raise RuntimeError("解析后的发布/回退路径超出本项目。")
        retained = False
        if target.exists():
            backup.parent.mkdir(exist_ok=True)
            target.rename(backup)
            retained = True
        try:
            candidate.rename(target)
        except Exception:
            if retained and not target.exists():
                backup.rename(target)
            raise
        print(f"发布完成：{target / 'MusicVocalExtractor.exe'}")
    else:
        print("仅预览；使用 --publish 执行已验证候选的移动。")


if __name__ == "__main__":
    main()
