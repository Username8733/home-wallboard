"""Capture English screenshots from the synthetic, read-only local demo only."""

import argparse
import base64
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import websocket


def capture(browser_path, output, url):
    if urlparse(url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only the local synthetic demo is allowed")
    marker = requests.get(url + "/api/state", timeout=5).json()
    if marker.get("demo") != "synthetic-public-data-v1":
        raise ValueError("This is not the synthetic demo; refusing to capture real household data")
    profile = tempfile.mkdtemp(prefix="wallboard-public-screenshots-")
    process = None
    ws = None
    output.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.Popen(
            [
                browser_path,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-background-networking",
                "--disable-component-update",
                "--remote-debugging-port=0",
                "--remote-allow-origins=*",
                "--user-data-dir=" + profile,
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        port_file = Path(profile) / "DevToolsActivePort"
        for _ in range(100):
            if port_file.exists():
                break
            time.sleep(0.1)
        port = port_file.read_text().splitlines()[0]
        page = next(
            p
            for p in requests.get("http://127.0.0.1:" + port + "/json/list", timeout=5).json()
            if p["type"] == "page"
        )
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], suppress_origin=True, timeout=30
        )
        counter = 0
        errors = []
        origins = set()

        def command(method, params=None):
            nonlocal counter
            counter += 1
            ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
            while True:
                reply = json.loads(ws.recv())
                if reply.get("method") == "Runtime.exceptionThrown":
                    errors.append(reply["params"]["exceptionDetails"].get("text", "Script error"))
                if reply.get("method") == "Network.requestWillBeSent":
                    request_url = reply["params"]["request"]["url"]
                    parsed = urlparse(request_url)
                    if parsed.scheme in {"http", "https"}:
                        origins.add(parsed.scheme + "://" + parsed.netloc)
                if reply.get("id") == counter:
                    if "error" in reply:
                        raise RuntimeError(reply["error"])
                    return reply.get("result", {})

        def evaluate(code):
            result = command(
                "Runtime.evaluate",
                {"expression": code, "returnByValue": True, "awaitPromise": True},
            )
            if "exceptionDetails" in result:
                raise RuntimeError(result["exceptionDetails"].get("text", "Script error"))
            return result.get("result", {}).get("value")

        def wait(code):
            for _ in range(100):
                if evaluate(code):
                    return
                time.sleep(0.1)
            raise AssertionError("Demo not ready: " + code)

        def shot(name):
            time.sleep(1.1)
            assert evaluate("document.documentElement.lang") == "en"
            untranslated = evaluate(
                """(()=>{const untranslated=[],walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);for(let node;node=walker.nextNode();){const p=node.parentElement,text=node.textContent.trim();if(!text||!p?.getClientRects().length||getComputedStyle(p).visibility!=='visible')continue;const english=WallboardMessages[text];if((english&&english!==text)||/[åäöÅÄÖ]/.test(text))untranslated.push(text);}return [...new Set(untranslated)];})()"""
            )
            assert not untranslated, {"screenshot": name, "untranslated": untranslated}

            data = command(
                "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
            )["data"]
            (output / (name + ".png")).write_bytes(base64.b64decode(data))
            print("Captured", name, flush=True)

        command("Runtime.enable")
        command("Page.enable")
        command("Network.enable")
        command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1200, "height": 800, "deviceScaleFactor": 1, "mobile": False},
        )
        command(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """localStorage.setItem('wallboard-locale',JSON.stringify({language:'en',time_format:'24h'}));
const RealDate=Date;window.Date=class extends RealDate{constructor(...args){super(...(args.length?args:['2026-05-15T08:41:00Z']));}static now(){return new RealDate('2026-05-15T08:41:00Z').getTime();}};
const originalFetch=window.fetch.bind(window);window.fetch=async(...args)=>{const response=await originalFetch(...args);if(args[0]==='/api/state'&&window.demoTheme){const data=await response.json();data.settings.theme=window.demoTheme;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});}return response;};"""
            },
        )
        command("Page.navigate", {"url": url + "/"})
        wait(
            "typeof state!=='undefined'&&state?.demo==='synthetic-public-data-v1'&&document.querySelectorAll('.light').length===9"
        )
        evaluate("document.fonts.ready")
        shot("home")
        evaluate(
            "WallboardPages.setPage('music');document.getElementById('music-view-library').click()"
        )
        wait("document.querySelectorAll('.music-item').length===6")
        shot("music-library")
        evaluate("document.getElementById('music-view-queue').click()")
        wait("document.querySelectorAll('.queue-play').length===6")
        shot("music-queue")
        evaluate("WallboardPages.setPage('security')")
        wait(
            "document.querySelectorAll('#camera-grid img').length===3&&[...document.querySelectorAll('#camera-grid img')].every(x=>x.complete&&x.naturalWidth>0)"
        )
        shot("security")
        evaluate("WallboardPages.setPage('home');WallboardSettings.open()")
        wait(
            "!document.getElementById('settings-panel').hidden&&document.getElementById('settings-form').elements.language.value==='en'"
        )
        shot("settings")
        evaluate("WallboardSettingsNavigation.open('lights')")
        shot("light-selection")
        evaluate("WallboardSettingsNavigation.open('night')")
        shot("night-schedule")
        evaluate(
            "document.getElementById('settings-cancel').click();window.demoTheme='dark';state.settings.theme='dark';render()"
        )
        shot("dark-mode")
        evaluate(
            "window.demoTheme='day';state.settings.theme='day';render();document.getElementById('photos-button').click()"
        )
        wait(
            "document.body.classList.contains('sleep')&&!!document.querySelector('.slide.visible')?.naturalWidth"
        )
        shot("slideshow")
        assert not errors, errors
        assert origins == {url.rstrip("/")}, origins
        report = {
            "language": "en",
            "synthetic_data_only": True,
            "screenshots": 9,
            "runtime_errors": len(errors),
            "external_network_requests": False,
            "source": "examples/demo.py",
        }
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        if ws:
            ws.close()
        if process:
            process.terminate()
            process.wait(timeout=15)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser", required=True, help="Path to a Chromium-compatible browser binary"
    )
    parser.add_argument("--output", type=Path, default=Path("docs/screenshots"))
    parser.add_argument("--url", default="http://127.0.0.1:18990")
    args = parser.parse_args()
    capture(args.browser, args.output, args.url)
