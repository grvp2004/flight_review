"""Measure a real local plot session and verify its live connection."""
import argparse
import json
from pathlib import Path
from time import monotonic
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('log_id')
    parser.add_argument('--plots', default='')
    args = parser.parse_args()
    query = {'log': args.log_id}
    if args.plots:
        query['plots'] = args.plots
    url = 'http://127.0.0.1:5006/plot_app?' + urlencode(query)
    errors = []
    websocket_errors = []
    websocket_messages = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True, timeout=20000)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.on('pageerror', lambda error: errors.append(str(error)))

        def socket_opened(socket):
            socket.on('socketerror', lambda error: websocket_errors.append(str(error)))
            socket.on('framereceived', lambda payload: websocket_messages.append(len(payload)))

        page.on('websocket', socket_opened)
        start = monotonic()
        page.goto(url, wait_until='domcontentloaded', timeout=180000)
        print(f'HTML ready in {monotonic() - start:.2f}s', flush=True)
        page.wait_for_function('window.Bokeh && Bokeh.documents.length > 0 && Bokeh.documents[0].is_idle',
                               timeout=180000)
        print(f'Plots ready in {monotonic() - start:.2f}s', flush=True)
        print(json.dumps({'javascript_errors': errors, 'websocket_errors': websocket_errors,
                          'websocket_frames': len(websocket_messages),
                          'loading_visible': page.locator('#loading-plots').is_visible()}), flush=True)
        page.screenshot(path=str(Path(__file__).resolve().parents[2] / 'data' / 'local-plots.png'))
        assert websocket_messages, 'No live plot data received'
        assert not websocket_errors, websocket_errors
        assert not errors, errors
        assert not page.locator('#loading-plots').is_visible(), 'Loading indicator remained visible'
        browser.close()


if __name__ == '__main__':
    main()
