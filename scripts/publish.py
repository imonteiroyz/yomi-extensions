#!/usr/bin/env python3
"""Publish the built extensions: a GitHub Release with each APK and JAR, plus the repo files.

Adapted from keiyoushi's .github/scripts/publish-repo.py. Every run rebuilds every extension
this repo carries, so the index is written from the build output alone, nothing is merged.

    python scripts/publish.py <upstream checkout> <output dir> --tag v3 --fingerprint <sha256> \
        --repo imonteiroyz/yomi-extensions --upstream-sha <commit> [--dry-run]

Writes index.pb, index.json and repo.json to <output dir>; the workflow commits them to the
`repo` branch, which is what the apps read.
"""
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
from pathlib import Path

NAME = "Yomi Extensions"
BADGE = "MY"
ICON_FILE = "res/mipmap-xhdpi/ic_launcher.png"


def load_proto(upstream: Path):
    # The index proto (with keiyoushi's jarUrl field) comes from the pinned upstream commit.
    sys.path.insert(0, str(upstream / ".github" / "scripts"))
    import index_pb2

    return index_pb2


def built_extensions(upstream: Path) -> list[tuple[dict, Path, Path]]:
    built = []
    for info_file in sorted(upstream.glob("src/*/*/build/keiyoushi-source-info.json")):
        info = json.loads(info_file.read_text(encoding="utf-8"))
        apks = list((info_file.parent / "outputs/apk/release").glob("*.apk"))
        jars = list((info_file.parent / "outputs/jar/release").glob("*.jar"))
        if len(apks) != 1 or len(jars) != 1:
            raise SystemExit(f"{info['packageName']}: expected one APK and one JAR, found {apks + jars}")
        built.append((info, apks[0], jars[0]))
    if not built:
        raise SystemExit(f"no built extension under {upstream}/src")
    return built


def icon_url(upstream_sha: str, module: str) -> str:
    return f"https://cdn.jsdelivr.net/gh/keiyoushi/extensions-source@{upstream_sha}/src/{module.replace('.', '/')}/{ICON_FILE}"


def build_index(pb, built, args) -> object:
    release_base = f"https://github.com/{args.repo}/releases/download/{args.tag}"
    extensions = [
        pb.Extension(
            name=info["name"],
            packageName=info["packageName"],
            resources=pb.Resources(
                apkUrl=f"{release_base}/{apk.name}",
                jarUrl=f"{release_base}/{jar.name}",
                iconUrl=icon_url(args.upstream_sha, info["module"]),
            ),
            extensionLib=info["extensionLib"],
            versionCode=info["versionCode"],
            versionName=info["versionName"],
            contentWarning=info["contentWarning"],
            sources=[
                pb.Source(
                    id=int(source["id"]),
                    name=source["name"],
                    language=source["lang"],
                    homeUrl=source["baseUrl"],
                    mirrorUrls=source.get("mirrorUrls", []),
                )
                for source in info["sources"]
            ],
        )
        for info, apk, jar in built
    ]
    extensions.sort(key=lambda ext: ext.packageName)
    return pb.Index(
        name=NAME,
        badgeLabel=BADGE,
        signingKey=args.fingerprint,
        contact=pb.Contact(website=f"https://github.com/{args.repo}"),
        extensionList=pb.ExtensionList(extensions=extensions),
    )


def write_repo_files(index, out: Path, args) -> None:
    from google.protobuf import json_format

    out.mkdir(parents=True, exist_ok=True)
    (out / "index.pb").write_bytes(gzip.compress(index.SerializeToString(deterministic=True), mtime=0))
    (out / "index.json").write_text(
        json_format.MessageToJson(index, preserving_proto_field_name=True) + "\n", encoding="utf-8"
    )
    descriptor = {
        "index_v2": f"https://raw.githubusercontent.com/{args.repo}/repo/index.pb",
        "meta": {
            "name": NAME,
            "website": f"https://github.com/{args.repo}",
            "signingKeyFingerprint": args.fingerprint,
        },
    }
    (out / "repo.json").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")


def create_release(built, args) -> None:
    names = ", ".join(info["name"] for info, _, _ in built)
    files = [str(path) for _, apk, jar in built for path in (apk, jar)]
    subprocess.run(
        [
            "gh", "release", "create", args.tag, *files,
            "--repo", args.repo,
            "--title", f"{args.tag}: {names}",
            "--notes", f"Built from keiyoushi/extensions-source@{args.upstream_sha} with this repo's patches.",
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("upstream", type=Path, help="the patched and built extensions-source checkout")
    parser.add_argument("out", type=Path, help="where index.pb, index.json and repo.json are written")
    parser.add_argument("--tag", required=True, help="release tag, e.g. v3")
    parser.add_argument("--fingerprint", required=True, help="SHA-256 of the signing certificate, lowercase, no colons")
    parser.add_argument("--repo", required=True, help="owner/name of this repo")
    parser.add_argument("--upstream-sha", required=True)
    parser.add_argument("--dry-run", action="store_true", help="write the repo files without creating the release")
    args = parser.parse_args()

    if len(args.fingerprint) != 64 or args.fingerprint != args.fingerprint.lower():
        raise SystemExit(f"fingerprint must be 64 lowercase hex characters, got {args.fingerprint!r}")

    pb = load_proto(args.upstream)
    built = built_extensions(args.upstream)
    index = build_index(pb, built, args)
    if not args.dry_run:
        create_release(built, args)
    write_repo_files(index, args.out, args)
    for info, apk, jar in built:
        print(f"{info['packageName']} {info['versionName']}: {apk.name}, {jar.name}")


if __name__ == "__main__":
    main()
