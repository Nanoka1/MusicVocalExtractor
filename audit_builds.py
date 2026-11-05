"""Read-only cleanup preview. Deletion is never performed by this command."""
import argparse
import json
from pathlib import Path

from migrate_outputs import digest
from publish_release import assert_not_running, validate_candidate

AUTHORIZED_OLD_BUILDS = ("build-20261105-220818", "build-20261105-221431", "diagnostic-build-20261104-195206")
MEDIA = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".mp4", ".pcm", ".wma", ".aiff"}
WEIGHTS = {".onnx", ".ckpt", ".th", ".pth", ".pt", ".safetensors"}


def verify_preserved(root, target, records):
    covered = set()
    for row in records:
        source, destination = (root / row["source"]).resolve(), (root / row["destination"]).resolve()
        if not source.is_relative_to(target.resolve()) or not destination.is_relative_to(root.resolve()) or destination.is_relative_to(target.resolve()):
            raise RuntimeError("保护清单路径不在预期范围。")
        if not destination.is_file() or digest(source) != row["sha256"] or digest(destination) != row["sha256"]:
            raise RuntimeError("歌曲、配置或模型保护副本不完整/发生变化。")
        covered.add(source)
    for item in target.rglob("*"):
        if item.is_symlink() or item.is_junction():
            raise RuntimeError("目录包含链接，不能自动清理。")
        if not item.is_file():
            continue
        relative = item.relative_to(target)
        data = "_internal" not in relative.parts or item.suffix.lower() in MEDIA | WEIGHTS
        if item.name == "MusicVocalExtractor.exe":
            data = False
        if item.name in ("LICENSE", "FFMPEG_NOTICE.md", "THIRD_PARTY_NOTICES.md") and (root / item.name).is_file() and digest(item) == digest(root / item.name):
            data = False
        if data and item.resolve() not in covered:
            raise RuntimeError("发现尚未保护的新数据文件，不能删除。")
    return True


def audit(root):
    root = root.resolve()
    dist = (root / "dist").resolve()
    if not dist.is_relative_to(root):
        raise RuntimeError("dist 解析到项目外部，停止检查。")
    formal = dist / "MusicVocalExtractor"
    formal_error = None
    try:
        validate_candidate(formal, require_gpu=False)
    except Exception as error:
        formal_error = str(error)
    protection_file = root / ".reference/old-build-data/preservation.json"
    protection = json.loads(protection_file.read_text(encoding="utf-8")) if protection_file.exists() else []
    rows = []
    for name in AUTHORIZED_OLD_BUILDS:
        target = (dist / name).resolve()
        row = {"name": name, "exists": target.exists(), "eligible": False}
        if not target.exists():
            row["reason"] = "目录已不存在，不重建。"
        else:
            if target.parent != dist:
                raise RuntimeError("旧构建路径超出授权目录。")
            row["bytes"] = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
            try:
                if formal_error:
                    raise RuntimeError("保留的正式 EXE 尚未通过当前验收：" + formal_error)
                assert_not_running([target])
                preserved = next((r for r in protection if r["directory"] == name), None)
                if not preserved or not preserved.get("verified"):
                    raise RuntimeError("尚无歌曲/缓存/配置保护清单。")
                verify_preserved(root, target, preserved["protected_files"])
                row.update(eligible=True, reason="正式版已验收、未运行、数据副本已再次校验；仅限本轮指定删除授权。")
            except Exception as error:
                row["reason"] = str(error)
        rows.append(row)
    return {"formal": str(formal), "formal_verified": formal_error is None, "directories": rows,
            "eligible_bytes": sum(r.get("bytes", 0) for r in rows if r["eligible"]), "deletion_performed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(Path(__file__).resolve().parent)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
