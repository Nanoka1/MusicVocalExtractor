"""Preview by default; publish a verified GPU candidate without deleting history."""
import argparse
import json
from pathlib import Path

from verify_release import package_manifest


def validate_candidate(package):
    report = json.loads((package / "release-validation.json").read_text(encoding="utf-8"))
    if not (report.get("passed") and report.get("gpu") and report.get("http_preview_download") and report.get("models_shared")):
        raise RuntimeError("候选没有通过完整 GPU/网页/缓存验收。")
    if package_manifest(package) != report.get("manifest"):
        raise RuntimeError("候选文件与实测清单不同，请重新验证。")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    dist = (root / "dist").resolve()
    candidate = (dist / "candidate-gpu" / "MusicVocalExtractor").resolve(strict=True)
    target = (dist / "MusicVocalExtractor-GPU").resolve()
    if not candidate.is_relative_to(dist) or not target.is_relative_to(dist):
        raise RuntimeError("发布路径超出项目 dist。")
    validate_candidate(candidate)
    if target.exists():
        raise RuntimeError("GPU 正式版已经存在，保留当前版本和候选。请先审查回退及数据保留方案；不自动覆盖或删除。")
    print(f"已验证候选：{candidate}\n新 GPU 正式目录：{target}\n旧目录全部保留。")
    if args.publish:
        candidate.rename(target)
        print(f"发布完成：{target / 'MusicVocalExtractor.exe'}")
    else:
        print("仅预览；使用 --publish 执行已验证候选的移动。")


if __name__ == "__main__":
    main()
