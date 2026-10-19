"""Real browser acceptance: blank beam, canvas edits, section/support/load, response."""

import subprocess, time, json, sys, math, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

project = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix="structure-lab-browser-"))
server = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        "8530",
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ],
    cwd=project,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1700, "height": 1100})
        page.set_default_timeout(15000)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        for _ in range(40):
            try:
                page.goto("http://127.0.0.1:8530", wait_until="domcontentloaded")
                break
            except Exception:
                time.sleep(0.25)
        try:
            page.get_by_role("heading", name="Structure Lab", exact=True).wait_for()
            page.get_by_test_id("stSidebar").get_by_text(
                "Examples & files", exact=True
            ).first.click()
            page.get_by_text("Confirm replacing the current model", exact=True).click()
            page.wait_for_timeout(350)
            page.get_by_role("button", name="Start empty model", exact=True).click()
            page.wait_for_timeout(700)
            page.wait_for_function(
                'Array.from(document.querySelectorAll("iframe")).some(f=>f.src.includes("structure_canvas"))'
            )
            for _ in range(40):
                candidates = [
                    f
                    for f in page.frames
                    if "structure_canvas" in f.url and not f.is_detached()
                ]
                if candidates:
                    frame = candidates[0]
                    break
                page.wait_for_timeout(100)
            frame.locator("#canvas").wait_for()

            def wait_model(expression):
                global frame
                for _ in range(100):
                    try:
                        frame = next(
                            f
                            for f in page.frames
                            if "structure_canvas" in f.url and not f.is_detached()
                        )
                        if frame.evaluate(expression):
                            return
                    except Exception:
                        pass
                    page.wait_for_timeout(100)
                raise AssertionError("Canvas state not reached: " + expression)

            def click_world(x, y):
                frame.locator("#canvas").scroll_into_view_if_needed()
                pt = frame.evaluate(
                    "([x,y])=>{const p=screen(x,y),r=svg.getBoundingClientRect();return {x:r.left+p[0],y:r.top+p[1]}}",
                    [x, y],
                )
                # frame-relative CSS coordinates passed through iframe bounding box
                box = (
                    page.locator("iframe").filter(visible=True).first.bounding_box()
                    if False
                    else frame.frame_element().bounding_box()
                )
                page.mouse.click(box["x"] + pt["x"], box["y"] + pt["y"])

            frame.get_by_role("button", name="Add node", exact=True).click()
            click_world(0, 0)
            wait_model("model.nodes.length===1")
            frame.get_by_role("button", name="Add node", exact=True).click()
            click_world(6, 0)
            wait_model("model.nodes.length===2")
            print("canvas nodes created", flush=True)
            frame.get_by_role("button", name="Draw member", exact=True).click()
            frame.locator('[data-node="1"]').click()
            frame.locator('[data-node="2"]').click()
            wait_model("model.elements.length===1")
            # Select/move: drag N2 up one grid unit, then Undo and Redo through toolbar.
            frame.get_by_role("button", name="Select / move", exact=True).click()
            pt = frame.evaluate(
                "()=>{let p=screen(6,.5),r=svg.getBoundingClientRect();return {x:r.left+p[0],y:r.top+p[1]}}"
            )
            box = frame.frame_element().bounding_box()
            nodebox = frame.locator('[data-node="2"]').bounding_box()
            page.mouse.move(
                nodebox["x"] + nodebox["width"] / 2,
                nodebox["y"] + nodebox["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(box["x"] + pt["x"], box["y"] + pt["y"], steps=8)
            page.mouse.up()
            wait_model("model.nodes[1].y===0.5")
            page.get_by_role("button", name="Undo", exact=True).click()
            wait_model("model.nodes[1].y===0")
            page.get_by_role("button", name="Redo", exact=True).click()
            wait_model("model.nodes[1].y===0.5")
            page.get_by_role("button", name="Undo", exact=True).click()
            wait_model("model.nodes[1].y===0")
            frame.locator("#canvas").focus()
            page.keyboard.press("Control+y")
            wait_model("model.nodes[1].y===0.5")
            frame.locator("#canvas").focus()
            page.keyboard.press("Control+z")
            wait_model("model.nodes[1].y===0")
            frame.get_by_role("button", name="Reset view", exact=True).click()
            print(
                "draw, drag, undo/redo buttons and keyboard shortcuts passed",
                flush=True,
            )
            page.get_by_test_id("stSidebar").get_by_text(
                "Properties", exact=True
            ).first.click()
            page.wait_for_timeout(300)
            page.get_by_label("Width b [mm]", exact=True).fill("100")
            page.get_by_label("Depth h [mm]", exact=True).fill("200")
            page.get_by_role("button", name="Save properties", exact=True).click()
            page.wait_for_timeout(400)
            frame.locator('[data-node="1"]').click()
            page.wait_for_timeout(350)
            page.get_by_role("button", name="Add support", exact=True).click()
            page.get_by_label("Restraint", exact=True).click()
            page.get_by_role("option", name="Pinned", exact=True).click()
            page.get_by_role("button", name="Save support", exact=True).click()
            wait_model('model.nodes[0].support==="Pinned"')
            frame.locator('[data-node="2"]').click()
            page.wait_for_timeout(400)
            page.get_by_label("Restraint", exact=True).click()
            page.get_by_role("option", name="Roller Y", exact=True).click()
            page.get_by_role("button", name="Save support", exact=True).click()
            wait_model('model.nodes[1].support==="Roller Y"')
            page.get_by_role("button", name="Apply load", exact=True).click()
            page.wait_for_timeout(400)
            page.get_by_role("button", name="Add distributed load", exact=True).click()
            wait_model("model.distributed_loads.length===1")
            page.screenshot(path=str(root / "qa_edit.png"), full_page=True)
            page.get_by_role("button", name="Analyse", exact=True).click()
            page.get_by_text("Analysis complete", exact=False).wait_for()
            page.get_by_text("Drawing controls", exact=True).click()
            page.get_by_text("Show deformed shape", exact=True).click()
            page.get_by_test_id("stSidebar").get_by_text(
                "Results", exact=True
            ).first.click()
            page.wait_for_timeout(800)
            page.get_by_text("12.0536 mm", exact=True).first.wait_for()
            page.get_by_role("tab", name="Limit assessment", exact=True).click()
            page.get_by_text("Governing assessed limit:", exact=False).wait_for()
            with page.expect_download() as download:
                page.get_by_role("button", name="Export model JSON", exact=True).click()
            download.value.save_as(str(root / "browser_model.json"))
            m = json.loads((root / "browser_model.json").read_text())
            assert len(m["nodes"]) == 2 and len(m["elements"]) == 1
            assert (
                math.isclose(m["elements"][0]["A"], 0.02)
                and m["distributed_loads"][0]["q"] == -10000
            )
            page.screenshot(path=str(root / "qa_result.png"), full_page=True)
            assert not page.get_by_test_id("stException").count()
            print(
                json.dumps(
                    {
                        "blank_to_loaded_beam": True,
                        "canvas_draw_drag_undo_redo": True,
                        "section_support_load_forms": True,
                        "deflection_mm": 12.0536,
                        "stress_assessment": True,
                        "json_download": True,
                        "browser_errors": errors,
                    }
                ),
                flush=True,
            )
        except Exception:
            page.screenshot(path=str(root / "qa_error.png"), full_page=True)
            print(page.locator("body").inner_text()[-5000:], flush=True)
            print("frames", [(f.name, f.url) for f in page.frames], flush=True)
            raise
        finally:
            browser.close()
finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
