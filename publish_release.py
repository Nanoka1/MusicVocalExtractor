"""Preview by default; publish a verified GPU candidate without deleting history."""
import argparse
import json
import re
import subprocess
from pathlib import Path

from verify_release import package_manifest


def validate_candidate(package, require_gpu=True):
    from runtime_paths import web_revision

    report = json.loads((package / "release-validation.json").read_text(encoding="utf-8"))
    if not (report.get("passed") and report.get("gpu" if require_gpu else "cpu") and report.get("http_preview_download") and report.get("models_shared")):
        raise RuntimeError("候选没有通过完整设备/网页/缓存验收。")
    if report.get("web_revision") != web_revision() or not report.get("mp3_mix"):
        raise RuntimeError("候选没有通过当前网页版本及 MP3 混音验收。")
    if package_manifest(package) != report.get("manifest"):
        raise RuntimeError("候选文件与实测清单不同，请重新验证。")
    return report


def assert_not_running(folders):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                             "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter \"Name='MusicVocalExtractor.exe' OR Name='MusicVocalExtractor-GUI.exe'\" | Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"],
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
    parser.add_argument("--build-id", help="发布对应构建编号的候选包")
    parser.add_argument("--backup-name", help="为本次升级指定 .reference 下的新回退目录名；不覆盖已有回退")
    args = parser.parse_args()
    if args.backup_name and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.backup_name):
        parser.error("回退目录名只能包含英文字母、数字、下划线和连字符，最多 64 字符。")
    if args.build_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", args.build_id):
        parser.error("构建编号无效。")
    root = Path(__file__).resolve().parent
    dist = (root / "dist").resolve()
    flavor = "cpu" if args.cpu else "gpu"
    staging = (root / "build" / "packaging" / "staging").resolve()
    candidate = (staging / flavor / "MusicVocalExtractor").resolve(strict=True)
    target = (dist / "MusicVocalExtractor").resolve()
    if not staging.is_relative_to(root.resolve()) or not candidate.is_relative_to(staging) or not target.is_relative_to(dist):
        raise RuntimeError("发布路径超出项目打包暂存目录或 dist。")
    validate_candidate(candidate, require_gpu=not args.cpu)
    backup_name = args.backup_name or (f"formal-before-{args.build_id}" if args.build_id else
                                       ("formal-exe-rollback" if args.cpu else "formal-before-gpu-rollback"))
    backup = (root / ".reference" / backup_name).resolve()
    if target.exists() and backup.exists():
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
        print(f"发布完成：{target / 'MusicVocalExtractor-GUI.exe'}")
    else:
        print("仅预览；使用 --publish 执行已验证候选的移动。")


if __name__ == "__main__":
    main()
