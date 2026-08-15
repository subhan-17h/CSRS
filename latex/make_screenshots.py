"""Capture the live interface screenshots used by CSRS_Work_Record.tex.

Prerequisites (both must already be running):

    uv run csrs-api                                  # http://127.0.0.1:8000
    uv run streamlit run src/csrs/app.py             # http://localhost:8501

and an Ollama chat model installed, so the answers in the captures are real.

Run with:  python3 latex/make_screenshots.py
Output:    latex/figures/ui_web_answer.png, ui_web_corpus.png,
           ui_streamlit.png, ui_api.png
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

FIGURES = Path(__file__).resolve().parent / "figures"
WEB = "http://127.0.0.1:8000/"
STREAMLIT = "http://localhost:8501/"
QUESTION = "What are the functions of the NIST Cybersecurity Framework?"


def settle(page: Page, timeout_ms: int = 240_000, quiet_ms: int = 4_000) -> None:
    """Wait until the page text stops growing -- i.e. streaming has finished."""
    last, stable = "", 0
    step = 1_000
    for _ in range(timeout_ms // step):
        page.wait_for_timeout(step)
        text = page.inner_text("body")
        if text == last:
            stable += step
            if stable >= quiet_ms:
                return
        else:
            last, stable = text, 0
    raise TimeoutError("page never settled")


def capture(page: Page, name: str, bottom_of: str | None = None) -> None:
    """Screenshot the viewport, trimmed to just below ``bottom_of`` if given."""
    clip = None
    if bottom_of is not None:
        box = page.locator(bottom_of).last.bounding_box()
        if box is not None:
            clip = {
                "x": 0,
                "y": 0,
                "width": page.viewport_size["width"],
                "height": min(box["y"] + box["height"] + 28, page.viewport_size["height"]),
            }
    path = FIGURES / f"{name}.png"
    page.screenshot(path=path, clip=clip)
    print(f"wrote {path.name}")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome")
        # A narrow window keeps the app's centred content column wide relative
        # to the frame, so the captures stay readable at print size.
        page = browser.new_page(
            viewport={"width": 1120, "height": 1250}, device_scale_factor=2
        )

        # --- React interface: a real question, answered by the local model,
        #     with the citation panel opened.
        page.goto(WEB, wait_until="networkidle")
        page.fill("textarea", QUESTION)
        page.keyboard.press("Enter")
        settle(page)
        page.click("button:has-text('sources')")
        page.wait_for_timeout(1_500)
        capture(page, "ui_web_answer", bottom_of=".sources-card")

        # --- React interface: the corpus explorer ---
        # The picker lists every indexed file with its chunk count: the three
        # standards first, then the per-rule Snort documents.
        page.click("button:has-text('Corpus')")
        page.wait_for_timeout(3_000)
        page.set_viewport_size({"width": 1120, "height": 720})
        page.wait_for_timeout(1_000)
        capture(page, "ui_web_corpus")

        # --- Streamlit interface ---
        page.set_viewport_size({"width": 1280, "height": 1000})
        page.goto(STREAMLIT, wait_until="networkidle")
        page.wait_for_timeout(5_000)
        chat_input = page.locator(
            "input[placeholder*='Ask a question'], input[aria-label*='Ask a question']"
        ).first
        chat_input.fill(QUESTION)
        page.keyboard.press("Enter")
        settle(page)
        capture(page, "ui_streamlit")

        # --- HTTP service ---
        page.goto(f"{WEB}docs", wait_until="networkidle")
        page.wait_for_timeout(2_500)
        capture(page, "ui_api")

        browser.close()


if __name__ == "__main__":
    main()
