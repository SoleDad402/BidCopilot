"""Human-like input simulation — typing, mouse, scrolling."""
from __future__ import annotations
import asyncio
import random

async def human_type(page, selector: str, text: str):
    elem = await page.query_selector(selector)
    if not elem:
        return
    await elem.click()
    for char in text:
        delay = max(0.03, min(0.2, random.gauss(0.08, 0.03)))
        await page.keyboard.type(char, delay=delay * 1000)
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.3, 1.0))

async def human_delay(min_s: float, max_s: float):
    await asyncio.sleep(random.uniform(min_s, max_s))

async def human_scroll(page, direction: str = "down", amount: int = 300):
    steps = random.randint(3, 8)
    per_step = amount / steps
    for _ in range(steps):
        delta = per_step + random.uniform(-20, 20)
        await page.mouse.wheel(0, delta if direction == "down" else -delta)
        await asyncio.sleep(random.uniform(0.05, 0.15))

async def human_mouse_move(page, x: int, y: int):
    steps = random.randint(15, 30)
    current = {"x": random.randint(100, 500), "y": random.randint(100, 500)}
    for i in range(steps + 1):
        t = i / steps
        bx = current["x"] + (x - current["x"]) * t + random.uniform(-5, 5)
        by = current["y"] + (y - current["y"]) * t + random.uniform(-5, 5)
        await page.mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.005, 0.02))
