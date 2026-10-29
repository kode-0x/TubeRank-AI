from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class ScrapeError(Exception):
    pass


@dataclass
class VideoMetadata:
    video_id: str
    title: str | None = None
    channel: str | None = None
    views: str | None = None
    length_seconds: str | None = None
    publish_date: str | None = None
    thumbnail: str | None = None
    description: str | None = None
    keywords: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        lines = [
            f"Title: {self.title or 'N/A'}",
            f"Channel: {self.channel or 'N/A'}",
            f"Views: {self.views or 'N/A'}",
            f"Length (seconds): {self.length_seconds or 'N/A'}",
            f"Publish date: {self.publish_date or 'N/A'}",
            f"Existing keywords: {', '.join(self.keywords) if self.keywords else 'N/A'}",
            "Description:",
            (self.description or "N/A")[:2000],
        ]
        return "\n".join(lines)


def extract_video_id(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host in ("youtu.be", "www.youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
        if _is_video_id(candidate):
            return candidate

    if "youtube.com" in host:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
            if _is_video_id(candidate):
                return candidate
        for prefix in ("/embed/", "/shorts/", "/v/", "/live/"):
            if parsed.path.startswith(prefix):
                candidate = parsed.path[len(prefix):].split("/")[0]
                if _is_video_id(candidate):
                    return candidate

    if _is_video_id(url):
        return url

    raise ScrapeError(
        "Could not find a YouTube video id in the provided URL. "
        "Paste a full watch URL, a youtu.be link, or a Shorts URL."
    )


def _is_video_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Za-z_-]{11}", value or ""))


def fetch_metadata(url: str, timeout: int = 20) -> VideoMetadata:
    video_id = extract_video_id(url)
    watch_url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        response = requests.get(
            watch_url,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise ScrapeError(f"Failed to fetch the video page: {exc}") from exc

    if response.status_code != 200:
        raise ScrapeError(
            f"YouTube returned HTTP {response.status_code} for video {video_id}."
        )

    html = response.text
    meta = VideoMetadata(video_id=video_id)

    _apply_player_response(html, meta)
    _apply_og_tags(html, meta)

    if not meta.thumbnail:
        meta.thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    if not meta.title:
        raise ScrapeError(
            "The page loaded but no video title was found. The video may be "
            "private, age-restricted, removed, or the URL is not a video."
        )

    return meta


def _apply_player_response(html: str, meta: VideoMetadata) -> None:
    match = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;", html)
    if not match:
        return
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return

    details = data.get("videoDetails", {})
    if not isinstance(details, dict):
        return

    meta.title = details.get("title") or meta.title
    meta.channel = details.get("author") or meta.channel
    meta.length_seconds = details.get("lengthSeconds") or meta.length_seconds
    meta.description = details.get("shortDescription") or meta.description

    view_count = details.get("viewCount")
    if view_count:
        meta.views = f"{int(view_count):,}" if view_count.isdigit() else view_count

    keywords = details.get("keywords")
    if isinstance(keywords, list):
        meta.keywords = [str(k) for k in keywords]

    thumbs = details.get("thumbnail", {}).get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        meta.thumbnail = thumbs[-1].get("url") or meta.thumbnail

    microformat = (
        data.get("microformat", {})
        .get("playerMicroformatRenderer", {})
    )
    if isinstance(microformat, dict):
        meta.publish_date = microformat.get("publishDate") or meta.publish_date


def _apply_og_tags(html: str, meta: VideoMetadata) -> None:
    soup = BeautifulSoup(html, "html.parser")

    def og(prop: str) -> str | None:
        tag = soup.find("meta", property=prop)
        return tag["content"] if tag and tag.get("content") else None

    def named(name: str) -> str | None:
        tag = soup.find("meta", attrs={"name": name})
        return tag["content"] if tag and tag.get("content") else None

    meta.title = meta.title or og("og:title")
    meta.thumbnail = meta.thumbnail or og("og:image")
    meta.description = meta.description or og("og:description") or named("description")

    if not meta.keywords:
        kw = named("keywords")
        if kw:
            meta.keywords = [k.strip() for k in kw.split(",") if k.strip()]
