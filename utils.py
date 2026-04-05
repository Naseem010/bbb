import asyncio
import random


async def human_delay(low: float = 0.3, high: float = 1.2) -> None:
    """Random delay to mimic human behaviour."""
    await asyncio.sleep(random.uniform(low, high))


async def human_type(page, selector: str, text: str, *, clear: bool = True) -> None:
    """Type text character-by-character with random inter-key delays."""
    el = page.locator(selector)
    if clear:
        await el.click()
        await el.press("Control+a")
        await el.press("Backspace")
        await human_delay(0.1, 0.3)
    for ch in text:
        await el.press_sequentially(ch, delay=random.randint(50, 150))
    await human_delay(0.2, 0.5)


async def safe_click(page, selector: str, timeout: int = 5000) -> bool:
    """Click an element if it exists within timeout, return success."""
    try:
        loc = page.locator(selector)
        await loc.wait_for(state="visible", timeout=timeout)
        await human_delay(0.1, 0.4)
        await loc.click()
        return True
    except Exception:
        return False


async def wait_and_click(page, selector: str, timeout: int = 30000) -> None:
    """Wait for element then click with human delay."""
    loc = page.locator(selector)
    await loc.wait_for(state="visible", timeout=timeout)
    await human_delay(0.2, 0.6)
    await loc.click()
