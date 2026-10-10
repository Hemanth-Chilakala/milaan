"""Capture silent, real-time presentation shots with Xvfb, ffmpeg and event logs."""

import argparse
import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from milaan.analytics import showcase_id
from milaan.config import ROOT
from milaan.db import connect, scope
from milaan.live import snapshot

URL = "http://127.0.0.1:8501/?present=1"
REGIONS = {
    "kpi_tiles": ".metric-grid",
    "kpi_matched_pct": "#live-matched",
    "kpi_unreconciled": "#live-unreconciled",
    "timer": "#live-timer",
    "pass_list": "#pass-list",
    "source_comparison": ".batch-comparison",
    "settlement_equation": "#settlement-equation",
    "explanation_callout": "#explanation-callout",
    "decision_panel": ".st-key-panel_decision",
    "queue": '[data-testid="stDataFrame"]',
}


def probe(path):
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
    )


@contextmanager
def screen(width, height, log_dir):
    output = (log_dir / "xvfb.log").open("a")
    process = subprocess.Popen(
        [
            "Xvfb",
            ":99",
            "-screen",
            "0",
            f"{width}x{height}x24",
            "-ac",
            "-nolisten",
            "tcp",
        ],
        stdout=output,
        stderr=output,
    )
    try:
        time.sleep(1)
        if process.poll() is not None:
            raise RuntimeError("Xvfb did not start; inspect the private capture log.")
        yield ":99"
    finally:
        process.terminate()
        process.wait(timeout=10)
        output.close()


def settle(page):
    page.wait_for_function("() => !document.querySelector('[data-stale=\"true\"]')", timeout=90000)
    page.wait_for_timeout(600)


def navigate(page, name, title):
    page.get_by_test_id("stSidebar").get_by_role("button", name=name).click()
    page.get_by_role("heading", name=title, exact=True).wait_for(timeout=90000)
    settle(page)


def screenshot_2x(page, folder, name, selector=None):
    box = (
        page.locator(selector).first.bounding_box()
        if selector
        else {"x": 0, "y": 0, "width": 1920, "height": 1080}
    )
    if not box:
        return
    # Preserve the visible browser density throughout real-time recording.
    # Idle shots render at 2x. Live-run stills retain their native 1080p density.
    page.screenshot(path=str(folder / "stills" / f"{name}.png"), clip=box)


class Shot:
    def __init__(self, page, folder, name, display, width, height, dsf, fps):
        self.page, self.folder, self.name = page, folder, name
        self.raw = folder / "raw" / f"{name}.mp4"
        self.data = {
            "shot": name,
            "video_file": f"footage/{name}.mp4",
            "resolution": [width, height],
            "css_viewport": [1920, 1080],
            "device_scale_factor": dsf,
            "fps": fps,
            "events": [],
            "regions_css": {},
            "run_id": None,
        }
        self.log = (folder / "raw" / f"{name}.ffmpeg.log").open("w")
        self.data["capture_started_epoch_ms"] = time.time() * 1000
        self.process = subprocess.Popen(
            [
                "nice",
                "-n",
                "19",
                "ffmpeg",
                "-y",
                "-f",
                "x11grab",
                "-draw_mouse",
                "0",
                "-probesize",
                "32",
                "-analyzeduration",
                "0",
                "-framerate",
                str(fps),
                "-video_size",
                f"{width}x{height}",
                "-i",
                display,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                str(self.raw),
            ],
            stdin=subprocess.PIPE,
            stdout=self.log,
            stderr=self.log,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            self.log.flush()
            if "frame=" in (folder / "raw" / f"{name}.ffmpeg.log").read_text():
                break
            page.wait_for_timeout(100)
        page.wait_for_timeout(1000)
        self.data["capture_ready_epoch_ms"] = time.time() * 1000
        if self.process.poll() is not None:
            raise RuntimeError("ffmpeg capture failed; inspect its private log.")
        self.zero = page.evaluate("""async () => {
            const marker=document.createElement('div'); marker.id='capture-sync-marker';
            marker.style='position:fixed;inset:0;background:#FF00FF;z-index:2147483647;pointer-events:none';
            document.body.appendChild(marker);
            await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
            return Date.now();
        }""")
        self.data["sync_marker_epoch_ms"] = self.zero
        page.wait_for_timeout(300)
        self.data["sync_marker_end_epoch_ms"] = page.evaluate(
            "() => {document.getElementById('capture-sync-marker').remove();return Date.now();}"
        )
        self.record("sync_marker_end")
        self.regions()

    def record(self, kind, **kwargs):
        self.data["events"].append(
            {"t": round((time.time() * 1000 - self.zero) / 1000, 3), "type": kind, **kwargs}
        )

    def regions(self):
        for name, selector in REGIONS.items():
            locator = self.page.locator(selector).first
            if locator.count() and locator.is_visible():
                box = locator.bounding_box()
                if box:
                    self.data["regions_css"][name] = [
                        round(box[k], 2) for k in ("x", "y", "width", "height")
                    ]

    def hold(self, seconds):
        self.record("hold_start", seconds=seconds)
        self.page.wait_for_timeout(seconds * 1000)
        self.record("hold_end")

    def move(self, locator, target):
        box = locator.bounding_box()
        if not box:
            raise RuntimeError(f"No bounding box for {target}")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x, y, steps=25)
        self.record("mouse_move", to_css=[round(x, 2), round(y, 2)])
        self.record(
            "hover", target=target, bbox_css=[box[k] for k in ("x", "y", "width", "height")]
        )
        return box

    def hover(self, locator, target):
        self.hold(1.5)
        self.move(locator, target)
        self.hold(2)

    def click(self, locator, target):
        self.hold(1.5)
        box = self.move(locator, target)
        self.record(
            "click", target=target, bbox_css=[box[k] for k in ("x", "y", "width", "height")]
        )
        locator.click()
        self.page.wait_for_timeout(2500)

    def scroll(self, pixels):
        self.hold(1.5)
        self.record("scroll_start", delta_css=pixels)
        self.page.mouse.move(1600, 700, steps=25)
        steps = max(1, int(abs(pixels) / 35))
        for _ in range(steps):
            self.page.mouse.wheel(0, pixels / steps)
            self.page.wait_for_timeout(65)
        self.record("scroll_end")
        self.hold(2)
        self.regions()

    def end(self):
        self.regions()
        self.record("shot_end")
        self.process.communicate(b"q", timeout=30)
        self.log.close()
        if self.process.returncode != 0:
            raise RuntimeError("ffmpeg did not complete the shot")
        raw = probe(self.raw)
        stream = next(s for s in raw["streams"] if s["codec_type"] == "video")
        frames = int(stream["nb_read_frames"])
        duration = float(stream["duration"])
        self.data["raw_probe"] = {
            "duration": duration,
            "frames": frames,
            "expected_frames": round(duration * self.data["fps"]),
            "frame_count_difference": frames - round(duration * self.data["fps"]),
        }
        (self.folder / f"{self.name}.events.json").write_text(
            json.dumps(self.data, indent=2) + "\n"
        )
        print(f"CAPTURED {self.name}: {duration:.2f}s, {frames} frames", flush=True)


def watch_run(shot, scope_name):
    with scope(scope_name), connect() as connection:
        previous = snapshot(connection).get("RUN_ID")
        button = "Run today's close" if scope_name == "day" else "Run reconciliation (full month)"
        shot.click(shot.page.get_by_role("button", name=button, exact=False), button)
        shot.page.mouse.move(1800, 970, steps=25)
        shot.record("mouse_move", to_css=[1800, 970], purpose="Leave button hover tooltip")
        seen, active = set(), None
        deadline = time.monotonic() + 600
        still_done = False
        while time.monotonic() < deadline:
            state = snapshot(connection)
            if state and state["RUN_ID"] != previous:
                shot.data["run_id"] = state["RUN_ID"]
                if state["STATUS"] == "FAILED":
                    raise RuntimeError("The recorded reconciliation failed")
                for row in state["PASSES"]:
                    if row["PASS_NAME"] not in seen:
                        seen.add(row["PASS_NAME"])
                        shot.record(
                            "pass_end",
                            pass_name=row["PASS_NAME"],
                            seconds=row["SECONDS"],
                            links=row["LINKS_ADDED"],
                            matched_pct=100 * state["MEMBERS"] / state["SOURCE_ROWS"],
                            unreconciled_paise=state["OPEN_PAISE"],
                            observed_epoch_ms=time.time() * 1000,
                        )
                if state["CURRENT_PASS"] != active:
                    active = state["CURRENT_PASS"]
                    shot.record(
                        "pass_start"
                        if active
                        in {
                            "EXACT",
                            "PG_BATCH",
                            "FEE_AWARE",
                            "TOLERANT",
                            "FUZZY",
                            "SPLIT_MERGE",
                            "CLASSIFY",
                        }
                        else "stage_start",
                        pass_name=active,
                    )
                shot.regions()
                if not still_done and len(seen) >= 2 and shot.page.locator("#pass-list").count():
                    screenshot_2x(shot.page, shot.folder, f"{shot.name}_mid_run")
                    screenshot_2x(shot.page, shot.folder, f"{shot.name}_pass_list", "#pass-list")
                    still_done = True
                if state["STATUS"] == "COMPLETE":
                    shot.data["run_snapshot"] = state
                    shot.record(
                        "run_end",
                        seconds=state["ELAPSED_SECONDS"],
                        run_id=state["RUN_ID"],
                        timer_basis="database core timer; UI explanation preparation follows",
                    )
                    break
            shot.page.wait_for_timeout(350)
        else:
            raise RuntimeError("The recorded run exceeded ten minutes")
        shot.page.get_by_text(
            "Results and evidence-backed explanations are ready.", exact=True
        ).wait_for(timeout=120000)
        settle(shot.page)
        shot.record("ui_results_ready")
        shot.hold(5)


def workflow(page, folder, names, display, width, height, dsf, fps):
    for name in names:
        print("PREPARING " + name, flush=True)
        if name in {"S01_home_before", "S02_run_month_10M", "S04_home_after", "S03_run_today"}:
            page.get_by_test_id("stSidebar").get_by_role("button", name="Today's close").click()
            page.wait_for_timeout(1000)
            requested = "Today's close" if name == "S03_run_today" else "Full month (10M)"
            page.get_by_test_id("stRadio").get_by_text(requested, exact=True).click()
            page.get_by_role(
                "heading",
                name="Today's close" if name == "S03_run_today" else "Full month close",
                exact=True,
            ).wait_for(timeout=90000)
            settle(page)
            if name in {"S01_home_before", "S03_run_today"}:
                page.get_by_role("button", name="Reset demo", exact=False).click()
                page.wait_for_timeout(1500)
                settle(page)
                with scope("day" if name == "S03_run_today" else "month"), connect() as c:
                    assert snapshot(c)["STATUS"] == "READY"
        elif name == "S05_queue":
            navigate(page, "Exceptions queue", "Exceptions queue")
        elif name in {"S06_showcase_detail", "S07_decision"}:
            navigate(page, "Exception detail", "Exception detail")
            page.get_by_role("textbox", name="Exception ID", exact=True).fill(showcase_id())
            page.get_by_role("textbox", name="Exception ID", exact=True).press("Enter")
            page.get_by_role(
                "heading", name="Gateway receipt missing from ledger", exact=True
            ).wait_for(timeout=60000)
            settle(page)
            if name == "S07_decision":
                page.get_by_role("textbox", name="Decision note").fill(
                    "Reviewed bank credit, 37 gateway payments and 36 receipts. Verify the missing receipt before approved posting."
                )
                page.locator(".st-key-panel_decision").scroll_into_view_if_needed()
                page.wait_for_timeout(600)
        elif name == "S08_accuracy":
            navigate(page, "Accuracy & performance", "Accuracy & performance")
        elif name == "S09_how_it_works":
            navigate(page, "How it works", "How Milaan works")
        if name != "S07_decision":
            page.get_by_test_id("stMain").evaluate("e=>e.scrollTo(0,0)")
        page.wait_for_timeout(600)
        shot = Shot(page, folder, name, display, width, height, dsf, fps)
        if name == "S01_home_before":
            shot.hold(12)
        elif name in {"S02_run_month_10M", "S03_run_today"}:
            watch_run(shot, "day" if name == "S03_run_today" else "month")
        elif name == "S04_home_after":
            screenshot_2x(page, folder, f"{name}_kpi_tiles", ".metric-grid")
            shot.hold(10)
            for i in range(page.locator(".metric-card").count()):
                shot.hover(page.locator(".metric-card").nth(i), f"KPI tile {i + 1}")
        elif name == "S05_queue":
            shot.hold(3)
            shot.scroll(260)
            shot.scroll(-260)
            shot.click(page.get_by_role("combobox", name="Category", exact=True), "Category filter")
            shot.click(
                page.get_by_role("option", name="Gateway receipt missing from ledger", exact=True),
                "Missing in ledger",
            )
            shot.record("filter_change", filter="category", value="MISSING_IN_LEDGER")
            settle(page)
            table = page.get_by_test_id("stDataFrame").first.bounding_box()
            shot.hold(1.5)
            row_box = [table["x"], table["y"] + 36, table["width"], 35]
            x, y = table["x"] + table["width"] / 2, table["y"] + 53
            page.mouse.move(x, y, steps=25)
            shot.record("mouse_move", to_css=[x, y])
            shot.record("hover", target="Top exception row", bbox_css=row_box)
            shot.hold(2)
            shot.hold(3)
        elif name == "S06_showcase_detail":
            screenshot_2x(page, folder, f"{name}_sources")
            screenshot_2x(page, folder, f"{name}_source_comparison", ".batch-comparison")
            shot.hold(5)
            shot.scroll(350)
            screenshot_2x(page, folder, f"{name}_equation", "#settlement-equation")
            shot.hold(4)
            shot.scroll(220)
            screenshot_2x(page, folder, f"{name}_explanation", "#explanation-callout")
            shot.hold(6)
        elif name == "S07_decision":
            shot.hold(3)
            shot.click(page.get_by_role("button", name="Accept", exact=False), "Accept")
            page.get_by_text("Decision saved to the Exasol audit trail.", exact=True).wait_for(
                timeout=60000
            )
            shot.record("toast", text="Decision saved to Exasol")
            shot.scroll(200)
            shot.hold(4)
            with scope("month"), connect() as c:
                row = c.execute(
                    "SELECT decision_id,run_id,exception_id,decision_action,analyst,assignee,note,CONVERT_TZ(created_at,DBTIMEZONE,'Asia/Kolkata') decided_at_ist FROM MILAAN_AUDIT.DECISION WHERE exception_id={id!s} ORDER BY created_at DESC LIMIT 1",
                    {"id": showcase_id()},
                ).fetchone()
                shot.data["audit_decision"] = {
                    k: str(v) if v is not None else None for k, v in row.items()
                }
                shot.data["run_id"] = row["RUN_ID"]
        elif name == "S08_accuracy":
            screenshot_2x(page, folder, f"{name}_headline")
            shot.hold(4)
            for pixels in (350, 420, 360):
                shot.scroll(pixels)
                shot.hold(3)
            profiling = page.get_by_text("Exasol's execution profiling", exact=True)
            if not profiling.is_visible():
                shot.scroll(250)
            shot.click(profiling, "Exasol execution profiling")
            shot.scroll(300)
            shot.hold(5)
        elif name == "S09_how_it_works":
            screenshot_2x(page, folder, f"{name}_architecture")
            shot.hold(5)
            shot.scroll(380)
            shot.hold(5)
        state_scope = "day" if name == "S03_run_today" else "month"
        if not shot.data["run_id"]:
            with scope(state_scope), connect() as c:
                shot.data["state_snapshot"] = snapshot(c)
                shot.data["run_id"] = shot.data["state_snapshot"].get("RUN_ID")
        if page.get_by_text("Let’s reconnect your workspace", exact=False).count():
            raise RuntimeError("A recorded page showed a database error")
        shot.end()
        screenshot_2x(page, folder, f"{name}_end")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT.parent / "video_assets")
    parser.add_argument("--shots", nargs="+", required=True)
    parser.add_argument("--width", type=int, default=3840)
    parser.add_argument("--height", type=int, default=2160)
    parser.add_argument("--dsf", type=float, default=2)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    folder = args.out.resolve()
    for name in ("raw", "footage", "stills"):
        (folder / name).mkdir(parents=True, exist_ok=True)
    with screen(args.width, args.height, folder / "raw") as display, sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(folder / "raw" / "browser-profile"),
            headless=False,
            env={**os.environ, "DISPLAY": display},
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=args.dsf,
            ignore_default_args=["--no-startup-window"],
            args=[
                "--no-sandbox",
                "--kiosk",
                "--app=" + URL,
                f"--force-device-scale-factor={args.dsf}",
                "--window-size=1920,1080",
                "--window-position=0,0",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        )
        page = next(
            (page for page in context.pages if page.url.startswith("http://127.0.0.1:8501")),
            context.pages[0],
        )
        for other in context.pages:
            if other is not page:
                other.close()
        page.add_init_script(
            """(() => {const add=()=>{const s=document.createElement('style');s.textContent='*,*::before,*::after{cursor:none!important}';document.documentElement.appendChild(s);};document.documentElement?add():document.addEventListener('DOMContentLoaded',add);})();"""
        )
        if args.fps == 24:
            page.add_init_script(
                """document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent='*,*::before,*::after{animation:none!important;transition:none!important}';document.documentElement.appendChild(s);});"""
            )
        page.goto(URL)
        page.get_by_role("heading", name="Full month close", exact=True).wait_for(timeout=90000)
        settle(page)
        cdp = context.new_cdp_session(page)
        cdp.send(
            "Runtime.evaluate",
            {
                "expression": "document.documentElement.requestFullscreen()",
                "userGesture": True,
                "awaitPromise": True,
            },
        )
        window = cdp.send("Browser.getWindowForTarget")
        cdp.send(
            "Browser.setWindowBounds",
            {
                "windowId": window["windowId"],
                "bounds": {"left": 0, "top": 0, "width": 1920, "height": 1080},
            },
        )
        cdp.detach()
        page.wait_for_timeout(6000)
        page.evaluate("() => document.fonts.ready")
        geometry = page.evaluate(
            "() => ({inner:[innerWidth,innerHeight],screen:[screen.width,screen.height],dpr:devicePixelRatio})"
        )
        (folder / "raw" / "geometry.json").write_text(json.dumps(geometry, indent=2) + "\n")
        assert geometry["inner"] == [1920, 1080]
        workflow(page, folder, args.shots, display, args.width, args.height, args.dsf, args.fps)
        context.close()


if __name__ == "__main__":
    main()
