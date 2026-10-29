from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from llm_client import LLMClient, LLMError
from youtube_scraper import ScrapeError, VideoMetadata, fetch_metadata

load_dotenv()

SYSTEM_PROMPT = (
    "You are a YouTube SEO expert. Given a video's public metadata, you produce "
    "concrete, actionable optimization advice. Be specific and avoid generic "
    "filler. Use the exact section headings requested and nothing else."
)


def build_user_prompt(meta: VideoMetadata) -> str:
    return (
        "Analyze the following YouTube video metadata and return SEO insights.\n\n"
        f"{meta.to_prompt_block()}\n\n"
        "Return your answer in Markdown with exactly these sections:\n\n"
        "## SEO Tags\n"
        "Provide at least 35 comma-separated tags, ordered from most to least "
        "relevant, mixing broad and long-tail keywords.\n\n"
        "## Suggested Timestamps\n"
        "Propose chapter timestamps (MM:SS - label) inferred from the title and "
        "description. If there is not enough information, say so explicitly.\n\n"
        "## Target Audience\n"
        "Describe the ideal viewer: demographics, interests, and intent.\n\n"
        "## Content Flaws & Improvements\n"
        "List specific weaknesses in the current title, description, or tags, "
        "and how to fix each one."
    )


def render_metadata(meta: VideoMetadata) -> None:
    col_thumb, col_info = st.columns([1, 2])
    with col_thumb:
        if meta.thumbnail:
            st.image(meta.thumbnail, use_container_width=True)
    with col_info:
        st.markdown(f"**Title:** {meta.title or 'N/A'}")
        st.markdown(f"**Channel:** {meta.channel or 'N/A'}")
        st.markdown(f"**Views:** {meta.views or 'N/A'}")
        if meta.publish_date:
            st.markdown(f"**Published:** {meta.publish_date}")
        if meta.length_seconds and meta.length_seconds.isdigit():
            minutes, seconds = divmod(int(meta.length_seconds), 60)
            st.markdown(f"**Length:** {minutes}m {seconds}s")


def main() -> None:
    st.set_page_config(page_title="TubeRank AI", page_icon="🎯", layout="wide")
    st.title("🎯 TubeRank AI")
    st.caption("YouTube SEO Insights Generator")

    with st.sidebar:
        st.header("LLM Provider")
        try:
            client = LLMClient()
            st.success("Configuration loaded")
            st.code(client.describe(), language="text")
        except LLMError as exc:
            client = None
            st.error(str(exc))
        st.caption(
            "Switch providers via environment variables (LLM_PROVIDER, "
            "LLM_MODEL, and the matching base URL / key). See .env.example."
        )

    url = st.text_input(
        "YouTube video URL",
        placeholder="https://www.youtube.com/watch?v=...",
    )
    analyze = st.button("Analyze", type="primary", disabled=client is None)

    if not analyze:
        return

    if not url.strip():
        st.warning("Enter a YouTube URL to analyze.")
        return

    try:
        with st.spinner("Scraping video metadata..."):
            meta = fetch_metadata(url)
    except ScrapeError as exc:
        st.error(f"Could not read the video: {exc}")
        return

    st.subheader("Video Metadata")
    render_metadata(meta)

    try:
        with st.spinner(f"Generating SEO insights with {client.describe()}..."):
            insights = client.chat(SYSTEM_PROMPT, build_user_prompt(meta))
    except LLMError as exc:
        st.error(f"LLM request failed: {exc}")
        return

    st.subheader("SEO Insights")
    st.markdown(insights)
    st.download_button(
        "Download insights (Markdown)",
        data=insights,
        file_name=f"tuberank_{meta.video_id}.md",
        mime="text/markdown",
    )


if __name__ == "__main__":
    main()
