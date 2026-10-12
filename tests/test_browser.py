from io import BytesIO

from playwright.sync_api import expect
from pypdf import PdfReader
import pytest


@pytest.mark.parametrize("entry_type", ["section", "bullet"])
@pytest.mark.parametrize("cancel_action", ["escape", "clear"])
def test_in_flight_creation_stays_visible(
    client, browser_page, entry_type, cancel_action
):
    page = browser_page
    if entry_type == "section":
        endpoint = "/sections"
        field_name = "title"
        button_name = "Add section"
    else:
        client.post("/sections", data={"title": "Experience"})
        section_id = client.get("/api/resume").json()["sections"][0]["id"]
        page.reload()
        endpoint = f"/sections/{section_id}/bullets"
        field_name = "content"
        button_name = "Add bullet"

    held_requests = []
    page.route(
        f"http://testserver{endpoint}", lambda route: held_requests.append(route)
    )
    page.get_by_role("button", name=button_name, exact=True).click()
    draft = page.locator(f"[data-new-{entry_type}]")
    draft.fill("Slow save entry")
    draft.press("Enter")
    page.wait_for_function("pendingMutations.size === 1")
    draft.focus()
    if cancel_action == "escape":
        draft.press("Escape")
    else:
        draft.fill("")
        draft.press("Tab")
    expect(draft).to_be_visible()
    expect(draft).to_have_text("Slow save entry")
    expect(page.locator("#error")).to_have_text(
        "This entry is being saved. Wait for it to finish before deleting it."
    )

    response = client.post(
        endpoint,
        data={field_name: "Slow save entry"},
        headers={"X-Inline-Create": "true"},
    )
    held_requests[0].fulfill(
        status=response.status_code, body=response.content, content_type="text/html"
    )
    expect(draft).to_have_count(0)
    saved = page.locator(f'[data-field="{field_name}"]').filter(
        has_text="Slow save entry"
    )
    expect(saved).to_be_visible()
    expect(page.locator("#error")).to_be_hidden()
    sections = client.get("/api/resume").json()["sections"]
    assert len(sections) == 1
    entry = sections[0] if entry_type == "section" else sections[0]["children"][0]
    assert entry[field_name] == "Slow save entry"


def test_deleting_last_section_restores_empty_message(client, browser_page):
    client.post("/sections", data={"title": "Temporary section"})
    page = browser_page
    page.reload()
    expect(page.locator(".empty-resume")).to_have_count(0)
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete section and all its bullets").click()
    expect(page.locator("section")).to_have_count(0)
    expect(page.locator(".empty-resume")).to_be_visible()
    assert client.get("/api/resume").json()["sections"] == []


@pytest.mark.parametrize("cancel_key", ["Escape", "Tab"])
def test_cancelling_new_section_restores_empty_message(browser_page, cancel_key):
    page = browser_page
    page.get_by_role("button", name="Add section", exact=True).click()
    expect(page.locator(".empty-resume")).to_have_count(0)
    assert page.locator("[data-new-section]").evaluate("el => el.matches(':empty')")
    page.get_by_role("textbox", name="Section title", exact=True).press(cancel_key)
    expect(page.locator("section")).to_have_count(0)
    expect(page.locator(".empty-resume")).to_be_visible()


def test_export_waits_for_deletion_and_preserves_button_layout(client, browser_page):
    client.post("/sections", data={"title": "Remove this section"})
    section_id = client.get("/api/resume").json()["sections"][0]["id"]
    page = browser_page
    page.reload()
    plus = page.get_by_role("button", name="Add section", exact=True).bounding_box()
    pdf = page.get_by_role("button", name="Export PDF", exact=True).bounding_box()
    web = page.get_by_role("button", name="Export to web (coming soon)").bounding_box()
    assert plus["width"] == pdf["width"] == web["width"]
    assert plus["height"] == pdf["height"] == web["height"]
    assert plus["x"] < pdf["x"] < web["x"]
    assert (
        page.locator(".section-row").evaluate("el => getComputedStyle(el).opacity")
        == "1"
    )
    assert (
        page.locator("section").evaluate("el => getComputedStyle(el).backgroundColor")
        == "rgb(243, 243, 243)"
    )

    held_requests = []
    page.route(
        f"**/sections/{section_id}/delete", lambda route: held_requests.append(route)
    )
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete section and all its bullets").click()
    page.wait_for_function("pendingMutations.size === 1")
    page.get_by_role("button", name="Export PDF", exact=True).click()
    expect(page.locator("#editor")).to_have_attribute("inert", "")
    assert (
        page.evaluate(
            "performance.getEntriesByType('resource').filter(e => e.name.endsWith('/export.pdf')).length"
        )
        == 0
    )
    assert len(held_requests) == 1
    response = client.post(f"/sections/{section_id}/delete")
    with page.expect_download() as download_event:
        held_requests[0].fulfill(
            status=response.status_code,
            body=response.content,
            content_type="application/json",
        )
    download = download_event.value
    assert download.suggested_filename == "resume.pdf"
    with open(download.path(), "rb") as exported:
        text = PdfReader(BytesIO(exported.read())).pages[0].extract_text()
    assert "Remove this section" not in text
    expect(page.locator("#editor")).not_to_have_attribute("inert", "")


def test_invalid_header_blocks_export(browser_page):
    page = browser_page
    page.get_by_role("textbox", name="Name", exact=True).fill("x" * 5001)
    page.get_by_role("button", name="Export PDF", exact=True).click()
    expect(page.locator("#error")).to_have_text(
        "Please fix unsaved changes before exporting."
    )
    expect(page.get_by_role("button", name="Export PDF", exact=True)).to_be_enabled()


def test_reverting_failed_header_save_clears_error(browser_page):
    page = browser_page
    page.route(
        "**/header/name/edit",
        lambda route: route.fulfill(status=500, body="Save failed"),
    )
    name = page.get_by_role("textbox", name="Name", exact=True)
    name.fill("Unsaved name")
    name.press("Tab")
    expect(name).to_have_attribute("data-save-failed", "true")
    name.fill("")
    name.press("Tab")
    expect(name).not_to_have_attribute("data-save-failed", "true")
    expect(page.locator("#error")).to_be_hidden()


def test_export_blocks_when_pending_deletion_fails(client, browser_page):
    client.post("/sections", data={"title": "Keep this section"})
    page = browser_page
    page.reload()
    held_requests = []
    page.route("**/delete", lambda route: held_requests.append(route))
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Delete section and all its bullets").click()
    page.wait_for_function("pendingMutations.size === 1")
    page.get_by_role("button", name="Export PDF", exact=True).click()
    expect(page.locator("#editor")).to_have_attribute("inert", "")
    held_requests[0].fulfill(status=500, body="Delete failed")
    expect(page.locator("#error")).to_have_text(
        "A pending change failed. Please retry it before exporting."
    )
    expect(page.get_by_role("button", name="Export PDF", exact=True)).to_be_enabled()
    expect(page.locator("section h2")).to_have_text("Keep this section")
