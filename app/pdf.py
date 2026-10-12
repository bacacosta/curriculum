from playwright.sync_api import sync_playwright


def render_pdf(html: str) -> bytes:
    """Render the resume HTML with Chrome's print styles and page numbering."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.set_content(html)
            page.evaluate("document.fonts.ready")
            return page.pdf(
                prefer_css_page_size=True,
                print_background=True,
                display_header_footer=False,
            )
        finally:
            browser.close()
