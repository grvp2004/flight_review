"""Check the running local upload form with the installed Edge browser."""
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    screenshots = Path(__file__).resolve().parents[2] / 'data'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context()
        page = context.new_page()
        uploads = []
        page.on('request', lambda request: uploads.append(request.url)
                if request.method == 'POST' else None)
        page.goto('http://127.0.0.1:5006/upload', wait_until='domcontentloaded')
        expect(page.locator('input[name="email"]')).to_have_count(0)
        expect(page.locator('select[name="type"]')).to_have_count(0)
        expect(page.locator('#upload-form')).to_have_attribute('data-max-size', '1073741824')
        for name, width, height in [('desktop', 1280, 800), ('mobile', 390, 844)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.screenshot(path=str(screenshots / f'local-upload-{name}.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')

        page.locator('#file').set_input_files({
            'name': 'invalid.ulg', 'mimeType': 'application/octet-stream',
            'buffer': b'This is deliberately not a ULog file.',
        })
        page.locator('#upload-button').click()
        expect(page.locator('#upload-failure')).to_have_text('Invalid File')
        expect(page.locator('#upload-button')).to_be_enabled()
        assert uploads and all(urlsplit(url).hostname == '127.0.0.1' for url in uploads)

        previous_uploads = len(uploads)
        page.locator('#file').evaluate('input => Object.defineProperty(input.files[0], "size", {value: 1073741825})')
        page.locator('#upload-button').click()
        expect(page.locator('#upload-failure')).to_have_text('The log exceeds the 1 GB file limit.')
        assert len(uploads) == previous_uploads
        browser.close()
    print('PASS: desktop/mobile form, local POST, invalid-file retry, client size limit')


if __name__ == '__main__':
    main()
