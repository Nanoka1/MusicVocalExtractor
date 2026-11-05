"""Copy historical dist outputs to the shared root without deleting or overwriting."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from separate import reserve_result_dir, song_title


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_manifest(folder):
    entries = {}
    for item in sorted(folder.rglob("*")):
        if item.is_symlink() or item.is_junction():
            raise RuntimeError(f"不能自动迁移链接目录或文件：{item}")
        if item.is_file():
            entries[item.relative_to(folder).as_posix()] = {"bytes": item.stat().st_size, "sha256": digest(item)}
    return entries


def copy_verified_tree(source, target):
    """target is an empty exclusively reserved directory; source is never altered."""
    before = tree_manifest(source)
    for relative, info in before.items():
        origin = source / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with origin.open("rb") as src, destination.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        shutil.copystat(origin, destination)
        if destination.stat().st_size != info["bytes"] or digest(destination) != info["sha256"]:
            raise RuntimeError(f"迁移副本校验失败：{destination}；源文件已保留。")
    if tree_manifest(source) != before or tree_manifest(target) != before:
        raise RuntimeError("迁移期间文件发生变化；源目录保留，停止后续清理。")
    return before


def migrate(root, apply=False):
    root = root.resolve()
    output = root / "outputs"
    output.mkdir(exist_ok=True)
    report_path = root / "test_artifacts/path-migration/migration.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"tasks": []}
    previous = {row["source"]: row for row in report["tasks"]}
    sources = []
    for folder in (root / "dist").rglob("outputs"):
        if not folder.is_dir() or "_internal" in folder.relative_to(root / "dist").parts:
            continue
        if folder.is_junction() or folder.is_symlink():
            raise RuntimeError(f"拒绝跟随输出链接：{folder}")
        for task in folder.iterdir():
            if task.is_dir() and any(task.iterdir()):
                sources.append(task)
            elif task.is_file():
                raise RuntimeError(f"输出根目录存在散文件，需要单独保护：{task}")
    for source in sources:
        key = str(source.relative_to(root))
        if key in previous:
            row = previous[key]
            destination = root / row["destination"]
            if tree_manifest(source) != row["files"] or tree_manifest(destination) != row["files"]:
                raise RuntimeError(f"上次迁移内容已变化，需要人工核对：{source}")
            continue
        if not apply:
            print(f"待复制：{source}")
            continue
        destination = reserve_result_dir(output, song_title(source.name + ".wav"))
        manifest = copy_verified_tree(source, destination)
        row = {"source": key, "destination": str(destination.relative_to(root)), "files": manifest, "verified": True}
        report["tasks"].append(row)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已复制并校验：{source.name} -> {destination.name}（{len(manifest)} 文件）")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrate(Path(__file__).resolve().parent, args.apply)
