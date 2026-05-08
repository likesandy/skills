#!/usr/bin/env python3
"""Package a WeChat article HTML or local page copy into a resource folder."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


REMOTE_IMAGE_RE = re.compile(r"https?://mmbiz\.qpic\.cn.*?(?=(?:&quot;|\"|'|\)|\s|<))")
URL_RE = re.compile(rb"https?://[^\x00\s\"'<>\\]+")
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
VIDEO_PLACEHOLDER_RE = re.compile(
    r"<mp-common-videosnap\b[^>]*></mp-common-videosnap>"
    r"|<iframe\b(?=[^>]*(?:video_iframe|action=mpvideo|data-mpvid))[^>]*>"
    r"(?:\s*</iframe>)?",
    re.I,
)
ATTR_RE = re.compile(r'([\w:-]+)=("[^"]*"|\'[^\']*\')')
DIV_TAG_RE = re.compile(r"</?div\b[^>]*>", re.I)
TITLE_PATTERNS = [
    re.compile(r"var\s+msg_title\s*=\s*['\"](.+?)['\"]", re.S),
    re.compile(
        r"<meta\s+property=['\"]og:title['\"]\s+content=['\"](.+?)['\"]", re.I | re.S
    ),
    re.compile(r"<title>(.+?)</title>", re.I | re.S),
]
DEFAULT_WEBVIEW_PATH = Path(
    "/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/Contents/MacOS"
)
DEFAULT_PROFILE_ROOT = (
    Path.home()
    / "Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/web/profiles"
)
ARTICLE_MARKERS = [
    "rich_media_content",
    "js_content",
    "mp-common-videosnap",
    'data-src="https://mmbiz.qpic.cn',
    "data-src='https://mmbiz.qpic.cn",
    "mdnice",
]
HTML_START_RE = re.compile(r"<!doctype|<html|<section", re.I)
WECHAT_ARTIFACT_RE = re.compile(
    r"<p\b[^>]*>\s*<mp-style-type\b[^>]*></mp-style-type>\s*</p>",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", help="Article URL used to locate an existing local page copy"
    )
    parser.add_argument("--html", type=Path, help="Article body/full HTML")
    parser.add_argument(
        "--source-html", type=Path, help="Optional full source HTML for title inference"
    )
    parser.add_argument(
        "--links-json", type=Path, help="Optional extracted image/video metadata JSON"
    )
    parser.add_argument(
        "--webview-path",
        type=Path,
        default=DEFAULT_WEBVIEW_PATH,
        help="Optional local WeChat WebView program path for environment verification",
    )
    parser.add_argument(
        "--profile-root",
        type=Path,
        default=DEFAULT_PROFILE_ROOT,
        help="Local WeChat WebView profile root for URL-based lookup",
    )
    parser.add_argument("--title", help="Article title used for folder and HTML title")
    parser.add_argument(
        "--output-root", type=Path, help="Root directory for title-based output"
    )
    parser.add_argument("--output-dir", type=Path, help="Exact output directory")
    parser.add_argument(
        "--include-maps",
        action="store_true",
        help="Write image mapping txt files",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def article_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path.startswith("s/"):
        return path.rsplit("/", 1)[-1]
    if path == "s" and parsed.query:
        return "mp.weixin.qq.com/s"
    return path.rsplit("/", 1)[-1] or url


def iter_lookup_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if (
            path.name == "Share Data"
            or "Cache_Data" in parts
            or path.suffix in {".html", ".htm"}
        ):
            yield path


def iter_discovery_files(root: Path):
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if (
            path.name == "Share Data"
            or "Cache_Data" in parts
            or "Local Storage" in parts
            or "IndexedDB" in parts
            or path.suffix in {".html", ".htm", ".log", ".ldb"}
        ):
            yield path


def trim_to_html(text: str) -> str:
    match = HTML_START_RE.search(text)
    return text[match.start() :] if match else text


def decode_gzip_html(data: bytes) -> str | None:
    offset = 0
    while True:
        offset = data.find(b"\x1f\x8b", offset)
        if offset < 0:
            return None
        try:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            decoded = decoder.decompress(data[offset:])
        except zlib.error:
            offset += 2
            continue
        text = decoded.decode("utf-8", errors="replace")
        if HTML_START_RE.search(text):
            return trim_to_html(text)
        offset += 2


def decode_possible_html(data: bytes) -> str:
    gzip_html = decode_gzip_html(data)
    if gzip_html:
        return gzip_html
    text = data.decode("utf-8", errors="replace")
    return trim_to_html(text)


def collect_lookup_terms(url: str, profile_root: Path) -> set[str]:
    key = article_key(url)
    terms = {url, key}
    url_re = re.compile(
        r"https://mp\.weixin\.qq\.com/s(?:\?[^\\\x00\s\"'<>]+|/[A-Za-z0-9_-]+)"
    )
    param_re = re.compile(r"(?:__biz|mid|sn)=([^&\x00\s\"'<>]+)")
    for path in iter_discovery_files(profile_root) or []:
        try:
            if path.stat().st_size > 40 * 1024 * 1024:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if key.encode() not in data and url.encode() not in data:
            continue
        raw_text = data.decode("utf-8", errors="replace")
        page_text = decode_possible_html(data)
        text = f"{raw_text}\n{page_text}"
        positions = [match.start() for match in re.finditer(re.escape(key), text)]
        snippets = [text[pos : min(len(text), pos + 1800)] for pos in positions]
        for snippet in snippets:
            for match in param_re.finditer(snippet):
                value = html.unescape(match.group(1))
                if value:
                    terms.add(value)
        for match in url_re.finditer("\n".join(snippets)):
            found_url = html.unescape(match.group(0))
            second_start = found_url.find("https://mp.weixin.qq.com/s", 1)
            if second_start > 0:
                found_url = found_url[:second_start]
            terms.add(found_url)
            parsed = urlparse(found_url)
            query = parse_qs(parsed.query)
            for name in ("__biz", "mid", "sn"):
                for value in query.get(name, []):
                    if value:
                        terms.add(value)
    return {term for term in terms if term}


def score_page_text(text: str, terms: set[str]) -> int:
    score = 0
    has_page_content = False
    for term in terms:
        if term in text:
            score += 4
    for marker in ARTICLE_MARKERS:
        if marker in text:
            has_page_content = True
            score += 5
    if "<html" in text or "<section" in text:
        has_page_content = True
        score += 2
    if not has_page_content:
        return 0
    return score


def locate_local_page_copy(url: str, profile_root: Path) -> tuple[str, Path]:
    terms = collect_lookup_terms(url, profile_root)
    encoded_terms = [term.encode() for term in terms]
    best: tuple[int, Path, str] | None = None
    for path in iter_lookup_files(profile_root) or []:
        try:
            if path.stat().st_size > 40 * 1024 * 1024:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if not any(term in data for term in encoded_terms):
            continue
        text = decode_possible_html(data)
        score = score_page_text(text, terms)
        if score <= 0:
            continue
        if (
            best is None
            or score > best[0]
            or (score == best[0] and len(text) > len(best[2]))
        ):
            best = (score, path, text)
    if best is None:
        raise FileNotFoundError(
            f"未在本地页面副本中找到文章: {url}\n"
            f"请先在微信中打开该文章，或改用 --html 指定已导出的 HTML。"
        )
    return best[2], best[1]


def infer_title(source: str, fallback: str) -> str:
    for pattern in TITLE_PATTERNS:
        match = pattern.search(source)
        if match:
            title = html.unescape(match.group(1)).strip()
            title = re.sub(r"\s+", " ", title)
            if title:
                return title
    return fallback


def extract_article_body(source: str) -> str:
    match = re.search(r"<div\b[^>]*\bid=[\"']js_content[\"'][^>]*>", source, re.I)
    if not match:
        return source
    depth = 0
    for tag in DIV_TAG_RE.finditer(source, match.start()):
        is_close = tag.group(0).startswith("</")
        depth += -1 if is_close else 1
        if depth == 0:
            body = source[match.start() : tag.end()]
            body = re.sub(r"visibility:\s*hidden;?", "", body, flags=re.I, count=1)
            body = re.sub(r"opacity:\s*0;?", "", body, flags=re.I, count=1)
            body = re.sub(r"user-select:\s*none;?", "", body, flags=re.I, count=1)
            body = re.sub(
                r"-webkit-user-select:\s*none;?", "", body, flags=re.I, count=1
            )
            return body
    return source


def remove_wechat_artifacts(html_text: str) -> str:
    return WECHAT_ARTIFACT_RE.sub("", html_text)


def safe_name(title: str) -> str:
    name = html.unescape(title).strip()
    name = re.sub(r"[/:：\\*?\"<>|]", "-", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"-{2,}", "-", name)
    return name.strip(" .-") or "微信文章"


def load_links_json(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def collect_image_urls(html_text: str, metadata: dict) -> list[str]:
    urls: list[str] = []
    for image in metadata.get("images", []):
        url = image.get("url") or image.get("data_src") or image.get("src")
        if url and url not in urls:
            urls.append(url)
    for match in REMOTE_IMAGE_RE.finditer(html_text):
        url = html.unescape(match.group(0))
        if url not in urls:
            urls.append(url)
    return urls


def image_output_extension(url: str) -> str:
    lowered = url.lower()
    if "wx_fmt=gif" in lowered or "/mmbiz_gif/" in lowered:
        return ".gif"
    if "wx_fmt=svg" in lowered or "/mmbiz_svg/" in lowered:
        return ".svg"
    if "wx_fmt=webp" in lowered or "/mmbiz_webp/" in lowered:
        return ".webp"
    return ".png"


def save_referenced_image(url: str, output: Path, preserve_format: bool) -> None:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X) "
                "AppleWebKit/605.1.15 MicroMessenger"
            ),
        },
    )
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp_path = Path(temp.name)
        with urlopen(request, timeout=30) as response:
            shutil.copyfileobj(response, temp)
    try:
        if preserve_format:
            shutil.copyfile(temp_path, output)
        elif shutil.which("sips"):
            subprocess.run(
                [
                    "/usr/bin/sips",
                    "-s",
                    "format",
                    "png",
                    str(temp_path),
                    "--out",
                    str(output),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            shutil.copyfile(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)


def replace_all_url_forms(html_text: str, mapping: dict[str, str]) -> str:
    result = html_text
    for remote, local in mapping.items():
        forms = {
            remote,
            remote.replace("&", "&amp;"),
            html.escape(remote, quote=True),
        }
        for value in forms:
            result = result.replace(value, local)
    return result


def ensure_img_src(html_text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        data_src = re.search(r'data-src="([^"]+)"', tag)
        src_attr = re.search(r'\ssrc="([^"]*)"', tag)
        local = None
        if data_src and data_src.group(1).startswith("./img/"):
            local = data_src.group(1)
        elif src_attr and src_attr.group(1).startswith("./img/"):
            local = src_attr.group(1)
        if not local:
            return tag
        if src_attr:
            return re.sub(r'\ssrc="[^"]*"', f' src="{local}"', tag, count=1)
        return tag.replace("<img", f'<img src="{local}"', 1)

    return IMG_TAG_RE.sub(replace, html_text)


def parse_attrs(tag: str) -> dict[str, str]:
    return {
        key.lower(): html.unescape(value[1:-1])
        for key, value in ATTR_RE.findall(tag)
    }


def local_video_block(index: int, source: str, vid: str = "") -> str:
    source_attr = html.escape(source, quote=True)
    vid_attr = f' data-video-vid="{html.escape(vid, quote=True)}"' if vid else ""
    return (
        f'<section class="local-video-wrp">'
        f'<div class="local-video-label">视频 {index}</div>'
        f'<video class="local-video" controls playsinline preload="metadata" '
        f'data-video-index="{index}"{vid_attr}>'
        f'<source src="{source_attr}" type="video/mp4" />'
        f"当前浏览器不支持 HTML5 video。"
        f"</video>"
        f"</section>"
    )


def video_metadata(tag: str) -> tuple[str, str]:
    attrs = parse_attrs(tag)
    src = attrs.get("src") or attrs.get("data-src") or ""
    vid = (
        attrs.get("data-mpvid")
        or attrs.get("data-vid")
        or attrs.get("vid")
        or ""
    )
    if not vid and src:
        vid_match = re.search(r"[?&]vid=([^&]+)", src)
        if vid_match:
            vid = html.unescape(vid_match.group(1))
    return vid, src


def replace_videos(html_text: str) -> tuple[str, list[dict]]:
    video_items: list[dict] = []
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        tag = match.group(0)
        vid, src = video_metadata(tag)
        count += 1
        local_src = f"./video/{count}.mp4"
        item = {"index": count, "url": local_src}
        if vid:
            item["vid"] = vid
        if src:
            item["remote"] = src
        video_items.append(item)
        return local_video_block(count, local_src, vid)

    return VIDEO_PLACEHOLDER_RE.sub(replace, html_text), video_items


def trim_cached_url(raw: str) -> str:
    raw = html.unescape(raw)
    mmversion = re.search(r"(mmversion=[0-9.]+)", raw)
    if mmversion:
        raw = raw[: mmversion.end()]
    return re.split(r"[\x00-\x08\r\n\ufffd]", raw, maxsplit=1)[0]


def collect_cached_mpvideo_urls(
    profile_root: Path, video_items: list[dict]
) -> list[dict]:
    videos_by_vid = {
        item["vid"]: item
        for item in video_items
        if item.get("vid")
    }
    if not videos_by_vid:
        return video_items

    encoded_vids = {
        vid: vid.encode()
        for vid in videos_by_vid
    }
    for path in iter_discovery_files(profile_root) or []:
        try:
            if path.stat().st_size > 40 * 1024 * 1024:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        present = [
            vid
            for vid, encoded in encoded_vids.items()
            if encoded in data
        ]
        if not present:
            continue
        for match in URL_RE.finditer(data):
            url = trim_cached_url(match.group(0).decode("utf-8", errors="replace"))
            if "mpvideo.qpic.cn" not in url or ".mp4" not in url:
                continue
            for vid in present:
                if vid not in url:
                    continue
                item = videos_by_vid[vid]
                if not item.get("mp4_url"):
                    item["mp4_url"] = url
    return video_items


def build_video_urls_txt(video_items: list[dict]) -> str:
    lines: list[str] = []
    for item in video_items:
        index = item["index"]
        lines.append(f"视频 {index}")
        lines.append(f"本地文件: video/{index}.mp4")
        if item.get("vid"):
            lines.append(f"vid: {item['vid']}")
        if item.get("remote"):
            lines.append(f"原始地址: {item['remote']}")
        if item.get("mp4_url"):
            lines.append(f"mp4: {item['mp4_url']}")
        else:
            lines.append("mp4: ")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def wrap_html(body: str, title: str) -> str:
    if re.search(r"<!doctype|<html\b", body, re.I):
        return body
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ margin: 0 auto; max-width: 760px; padding: 24px 16px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.7; }}
img {{ max-width: 100%; height: auto; }}
pre, code {{ white-space: pre-wrap; word-break: break-word; }}
.local-video-wrp {{ margin: 16px 0; }}
.local-video-label {{ margin: 0 0 6px; color: #666; font-size: 13px; }}
.local-video {{ display: block; width: 100%; max-width: 100%; background: #000; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    if not args.html and not args.url:
        print("需要提供 --url 或 --html。", file=sys.stderr)
        return 2
    if args.html and not args.html.exists():
        print(f"HTML file not found: {args.html}", file=sys.stderr)
        return 2
    if args.webview_path and not args.webview_path.exists():
        print(f"提示: WebView 路径不存在或不可见: {args.webview_path}", file=sys.stderr)

    local_source_path: Path | None = None
    if args.html:
        body = read_text(args.html)
        local_source_path = args.html
    else:
        try:
            body, local_source_path = locate_local_page_copy(
                args.url, args.profile_root
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 3

    source_for_title = body
    if args.source_html and args.source_html.exists():
        source_for_title = read_text(args.source_html)
    fallback_title = article_key(args.url) if args.url else local_source_path.stem
    title = args.title or infer_title(source_for_title, fallback_title)
    body = extract_article_body(body)

    output_dir = args.output_dir
    if not output_dir:
        default_output_root = (
            Path.home() / "Desktop" if args.url else local_source_path.parent
        )
        output_root = args.output_root or default_output_root
        output_dir = output_root / f"{safe_name(title)}"

    img_dir = output_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    video_dir = output_dir / "video"
    video_loader_path = output_dir / "video-loader.js"
    old_video_map_json = output_dir / "视频映射.json"
    old_video_map_txt = output_dir / "视频映射.txt"
    for obsolete in (video_loader_path, old_video_map_json, old_video_map_txt):
        obsolete.unlink(missing_ok=True)

    metadata = load_links_json(args.links_json)
    image_urls = collect_image_urls(body, metadata)
    image_mapping: dict[str, str] = {}
    for index, url in enumerate(image_urls, start=1):
        ext = image_output_extension(url)
        local_rel = f"./img/{index}{ext}"
        output = img_dir / f"{index}{ext}"
        image_mapping[url] = local_rel
        if not output.exists() or output.stat().st_size == 0:
            save_referenced_image(
                url, output, preserve_format=ext in {".gif", ".svg", ".webp"}
            )

    packaged = replace_all_url_forms(body, image_mapping)
    packaged = ensure_img_src(packaged)
    packaged = remove_wechat_artifacts(packaged)
    packaged, video_items = replace_videos(packaged)
    if video_items:
        video_items = collect_cached_mpvideo_urls(args.profile_root, video_items)
        video_dir.mkdir(parents=True, exist_ok=True)
    elif (
        video_dir.exists()
        and video_dir.is_dir()
        and not any(video_dir.iterdir())
    ):
        video_dir.rmdir()
    packaged = wrap_html(packaged, title)

    (output_dir / "index.html").write_text(packaged, encoding="utf-8")
    if video_items:
        (output_dir / "视频地址.txt").write_text(
            build_video_urls_txt(video_items),
            encoding="utf-8",
        )
    else:
        (output_dir / "视频地址.txt").unlink(missing_ok=True)
    if args.include_maps:
        (output_dir / "图片映射.txt").write_text(
            "\n".join(
                f"{idx}.png\t{url}" for idx, url in enumerate(image_urls, start=1)
            )
            + "\n",
            encoding="utf-8",
        )

    print(f"输出目录: {output_dir}")
    print(f"WebView路径: {args.webview_path}")
    if args.url:
        print(f"文章地址: {args.url}")
        print(f"本地页面副本: {local_source_path}")
    print(f"图片数量: {len(image_urls)}")
    print(f"视频数量: {len(video_items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
