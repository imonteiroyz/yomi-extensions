#!/usr/bin/env python3
"""Acceptance check for one extension on a running Suwayomi, through its GraphQL API.

Checks only what a reader sees: the extension comes from the expected store and is
installed, the source lists, searches, opens details and chapters, lists pages, and
the first page image downloads.

    python scripts/acceptance.py eu.kanade.tachiyomi.extension.pt.lycantoonsmy "<known title>"

With --library <manga url>, each work already in the library is also opened by its stored URL:
details, then pages and the first image of its newest stored chapter that the site still has
(up to five are tried). Its chapter list is not
refreshed, because a refresh deletes the stored chapters the site no longer lists.

Exits 0 when every step passes, 1 on the first failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LIBRARY_CHAPTER_TRIES = 5
EXTENSION_FIELDS = "pkgName name versionName isInstalled hasUpdate storeIndexUrl source { nodes { id name } }"


class StepFailed(Exception):
    pass


class Suwayomi:
    def __init__(self, server: str):
        self.server = server.rstrip("/")

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        request = Request(
            f"{self.server}/api/graphql",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=180) as response:
                payload = json.load(response)
        except (URLError, TimeoutError) as error:
            raise StepFailed(f"Suwayomi at {self.server} did not answer: {error}") from error
        if payload.get("errors") or not payload.get("data"):
            raise StepFailed("; ".join(e.get("message", str(e)) for e in payload.get("errors") or [payload]))
        return payload["data"]

    def get(self, url: str) -> tuple[int, str, int]:
        if url.startswith("/"):
            url = self.server + url
        try:
            with urlopen(Request(url), timeout=180) as response:
                return response.status, response.headers.get("Content-Type", ""), len(response.read())
        except HTTPError as error:
            return error.code, error.headers.get("Content-Type", ""), 0
        except (URLError, TimeoutError) as error:
            raise StepFailed(f"could not download {url}: {error}") from error


def check(condition: bool, message: str) -> None:
    if not condition:
        raise StepFailed(message)


def all_extensions(api: Suwayomi) -> list[dict]:
    return api.graphql(
        f"mutation {{ fetchExtensions(input: {{}}) {{ extensions {{ {EXTENSION_FIELDS} }} }} }}"
    )["fetchExtensions"]["extensions"]


def find_extension(api: Suwayomi, pkg: str) -> dict | None:
    return next((e for e in all_extensions(api) if e["pkgName"] == pkg), None)


def step_catalog(api: Suwayomi, pkg: str, store: str) -> str:
    extension = find_extension(api, pkg)
    check(extension is not None, f"{pkg} is not in the catalog; is the {store} repo added?")
    check(
        store in (extension["storeIndexUrl"] or ""),
        f"{pkg} comes from {extension['storeIndexUrl']}, expected a URL containing {store!r}",
    )
    if not extension["isInstalled"] or extension["hasUpdate"]:
        action = "update" if extension["isInstalled"] else "install"
        api.graphql(
            "mutation($id: String!, $patch: UpdateExtensionPatchInput!) {"
            " updateExtension(input: {id: $id, patch: $patch}) { extension { pkgName } } }",
            {"id": pkg, "patch": {action: True}},
        )
        extension = find_extension(api, pkg)
        check(extension and extension["isInstalled"], f"{pkg} did not {action}")
    sources = extension["source"]["nodes"]
    check(len(sources) >= 1, f"{pkg} is installed but exposes no source")
    # The (MY) keeps the original's source ID, so with both installed either one may answer.
    clashing = [
        e["pkgName"]
        for e in all_extensions(api)
        if e["isInstalled"] and e["pkgName"] != pkg and any(s["id"] == sources[0]["id"] for s in e["source"]["nodes"])
    ]
    check(not clashing, f"uninstall {', '.join(clashing)} first: it has the same source ID as {pkg}")
    print(f"  {extension['name']} {extension['versionName']}, source {sources[0]['id']}")
    return sources[0]["id"]


def browse(api: Suwayomi, source: str, kind: str, query: str | None = None) -> list[dict]:
    return api.graphql(
        "mutation($source: LongString!, $type: FetchSourceMangaType!, $query: String) {"
        " fetchSourceManga(input: {source: $source, type: $type, page: 1, query: $query})"
        " { mangas { id title } } }",
        {"source": source, "type": kind, "query": query},
    )["fetchSourceManga"]["mangas"]


def step_list(api: Suwayomi, source: str, kind: str) -> None:
    mangas = browse(api, source, kind)
    check(len(mangas) >= 1, f"{kind} returned no manga")
    print(f"  {len(mangas)} manga, first: {mangas[0]['title']}")


def step_search(api: Suwayomi, source: str, title: str) -> int:
    mangas = browse(api, source, "SEARCH", title)
    match = next((m for m in mangas if title.lower() in m["title"].lower()), None)
    check(match is not None, f"search for {title!r} did not find it (got {[m['title'] for m in mangas[:5]]})")
    print(f"  found {match['title']} (manga {match['id']})")
    return match["id"]


def newest_chapter(chapters: list[dict]) -> dict:
    # sourceOrder 1 is the oldest chapter, the one a site is likeliest to have taken down
    return max(chapters, key=lambda c: c["sourceOrder"])


def step_details_and_chapters(api: Suwayomi, manga_id: int) -> int:
    data = api.graphql(
        "mutation($id: Int!) { fetchMangaAndChapters(input: {id: $id, fetchManga: true, fetchChapters: true})"
        " { manga { title description thumbnailUrl } chapters { id name sourceOrder } } }",
        {"id": manga_id},
    )["fetchMangaAndChapters"]
    manga, chapters = data["manga"], data["chapters"]
    check(bool(manga["title"]), "details came back without a title")
    check(bool(manga["description"]), "details came back without a description")
    check(bool(manga["thumbnailUrl"]), "details came back without a cover")
    check(len(chapters) >= 1, "no chapters")
    newest = newest_chapter(chapters)
    print(f"  {manga['title']}: {len(chapters)} chapters, reading {newest['name']}")
    return newest["id"]


def step_library_manga(api: Suwayomi, source: str, url: str) -> list[dict]:
    mangas = api.graphql(
        "query($source: LongString!, $url: String!) {"
        " mangas(condition: {sourceId: $source, url: $url, inLibrary: true})"
        " { nodes { id chapters { nodes { id name sourceOrder } } } } }",
        {"source": source, "url": url},
    )["mangas"]["nodes"]
    check(len(mangas) == 1, f"{url} is not in the library for source {source}")
    manga_id, chapters = mangas[0]["id"], mangas[0]["chapters"]["nodes"]
    manga = api.graphql(
        "mutation($id: Int!) { fetchManga(input: {id: $id}) { manga { title description thumbnailUrl } } }",
        {"id": manga_id},
    )["fetchManga"]["manga"]
    check(bool(manga["title"]), "details came back without a title")
    check(bool(manga["description"]), "details came back without a description")
    check(bool(manga["thumbnailUrl"]), "details came back without a cover")
    check(len(chapters) >= 1, "no chapters stored")
    print(f"  {manga['title']}: {len(chapters)} stored chapters")
    return chapters


def step_library_pages(api: Suwayomi, chapters: list[dict]) -> str:
    # A stored chapter the site has since taken down answers 404; the next newest one must open.
    tries = sorted(chapters, key=lambda c: c["sourceOrder"], reverse=True)[:LIBRARY_CHAPTER_TRIES]
    for chapter in tries:
        try:
            print(f"  reading {chapter['name']}")
            return step_pages(api, chapter["id"])
        except StepFailed as failure:
            print(f"  {chapter['name']} did not open: {str(failure).splitlines()[0]}")
    raise StepFailed(f"none of the {len(tries)} newest stored chapters opened")


def step_pages(api: Suwayomi, chapter_id: int) -> str:
    pages = api.graphql(
        "mutation($id: Int!) { fetchChapterPages(input: {chapterId: $id}) { pages } }",
        {"id": chapter_id},
    )["fetchChapterPages"]["pages"]
    check(len(pages) >= 1, "chapter has no pages")
    print(f"  {len(pages)} pages")
    return pages[0]


def step_image(api: Suwayomi, url: str) -> None:
    status, content_type, size = api.get(url)
    check(status == 200, f"first page answered {status}")
    check(content_type.startswith("image/"), f"first page content-type is {content_type!r}")
    print(f"  {status} {content_type}, {size} bytes")


def run(api: Suwayomi, pkg: str, title: str, store: str, library: list[str]) -> None:
    state: dict = {}
    steps = [
        ("catalog and install", lambda: state.update(source=step_catalog(api, pkg, store))),
        ("popular", lambda: step_list(api, state["source"], "POPULAR")),
        ("latest", lambda: step_list(api, state["source"], "LATEST")),
        ("search", lambda: state.update(manga=step_search(api, state["source"], title))),
        ("details and chapters", lambda: state.update(chapter=step_details_and_chapters(api, state["manga"]))),
        ("pages", lambda: state.update(page=step_pages(api, state["chapter"]))),
        ("first image", lambda: step_image(api, state["page"])),
    ]
    for url in library:
        steps += [
            (f"library {url}", lambda url=url: state.update(chapters=step_library_manga(api, state["source"], url))),
            (f"library {url} pages", lambda: state.update(page=step_library_pages(api, state["chapters"]))),
            (f"library {url} first image", lambda: step_image(api, state["page"])),
        ]
    for name, step in steps:
        print(f"[{name}]")
        step()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pkg", help="extension package, e.g. eu.kanade.tachiyomi.extension.pt.lycantoonsmy")
    parser.add_argument("title", help="a title the search must find")
    parser.add_argument("--store", default="yomi-extensions", help="text the extension's store URL must contain")
    parser.add_argument("--server", default="http://localhost:4567")
    parser.add_argument(
        "--library", action="append", default=[], metavar="URL",
        help="stored URL of a work already in the library, e.g. /obra/11132; repeatable",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        run(Suwayomi(args.server), args.pkg, args.title, args.store, args.library)
    except StepFailed as failure:
        print(f"FAIL: {failure}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
