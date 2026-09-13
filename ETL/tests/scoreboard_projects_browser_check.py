"""Manual browser smoke test using isolated, temporary project storage."""
import importlib.util
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

from playwright.sync_api import sync_playwright

app = Path(__file__).resolve().parents[1] / "extras/apps/leaderBoardGen"


def module(name):
    spec = importlib.util.spec_from_file_location(name, app / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


core, web = module("scoreboard_app"), module("scoreboard_web")
with tempfile.TemporaryDirectory() as temporary:
    runtime = web.ScoreboardWebRuntime(core, Path(temporary) / "uploads")
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(runtime))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            first = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors = []
            first.on("pageerror", lambda error: errors.append(str(error)))
            url = f"http://127.0.0.1:{server.server_port}/scoreboard"
            first.goto(url)
            first.wait_for_function("boot && boot.shared_projects && configs.t5")
            first.locator("#saveProject").click()
            first.locator("#projectName").fill("Shared match test")
            first.locator("#confirmProjectSave").click()
            first.wait_for_function("serverProject && serverProject.revision === 1")
            second = browser.new_page()
            second.goto(url)
            second.wait_for_function("boot && boot.shared_projects")
            second.on("dialog", lambda dialog: dialog.accept())
            second.locator("#openProject").click()
            second.locator("#projectSearch").fill("shared match")
            second.locator("#projectList button").click()
            second.wait_for_function("serverProject && serverProject.revision === 1")
            first.locator("#saveProject").click()
            first.locator("#confirmProjectSave").click()
            first.wait_for_function("serverProject.revision === 2")
            second.locator("#saveProject").click()
            second.locator("#confirmProjectSave").click()
            second.wait_for_function("document.querySelector('#projectSaveError').textContent.includes('Another operator')")
            second.locator("#saveProjectCopy").click()
            second.wait_for_function("!document.querySelector('#saveDialog').open")
            assert len(runtime.list_projects()) == 2
            # Inspect the deployed editor without changing its project contents.
            first.goto("http://127.0.0.1:8080/scoreboard")
            first.wait_for_function("boot && boot.shared_projects")
            first.locator("#openProject").click()
            artifacts = Path(__file__).resolve().parents[1] / "output/scoreboard_web"
            artifacts.mkdir(parents=True, exist_ok=True)
            first.screenshot(path=str(artifacts / "shared_projects_desktop.png"))
            first.set_viewport_size({"width": 390, "height": 844})
            first.screenshot(path=str(artifacts / "shared_projects_mobile.png"))
            assert first.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            browser.close()
            print("PASS: shared save/open, independent sessions, conflict, save copy, deployed UI")
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
