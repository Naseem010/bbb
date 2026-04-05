import json
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext
from playwright_stealth import Stealth

from config import BotConfig, cookies_path
import logger

# Persistent profile directory — survives across runs, avoids bot fingerprinting
PROFILE_DIR = Path(__file__).parent / "chrome_profiles"

# Stealth config tuned for macOS + Chrome
_stealth = Stealth(
    navigator_languages_override=("en-IN", "en-US", "en"),
    navigator_platform_override="MacIntel",
    navigator_vendor_override="Google Inc.",
)


def _profile_path(account_index: int) -> Path:
    return PROFILE_DIR / f"account_{account_index}"


async def launch_browser(config: BotConfig, account_index: int = 0):
    """
    Launch real Chrome with persistent context to bypass Cloudflare.

    Anti-detection:
      1. channel="chrome" → real Google Chrome binary
      2. Persistent user-data-dir → consistent fingerprint
      3. playwright-stealth → patches webdriver, WebGL, plugins etc.
      4. ignore_default_args=["--enable-automation"] → removes automation flag
      5. Headed mode only — Cloudflare detects headless
    """
    pw = await async_playwright().start()

    profile = _profile_path(account_index)
    profile.mkdir(parents=True, exist_ok=True)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--disable-component-update",
    ]

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        channel="chrome",
        headless=False,
        args=launch_args,
        viewport={"width": 1440, "height": 900},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        proxy={"server": config.proxy} if config.proxy else None,
        ignore_default_args=["--enable-automation"],
    )

    # Apply stealth patches to context
    await _stealth.apply_stealth_async(context)

    # Load saved cookies
    cp = cookies_path(account_index)
    if cp.exists():
        try:
            cookies = json.loads(cp.read_text())
            await context.add_cookies(cookies)
            logger.success(f"Loaded session from {cp.name}", account_index)
        except Exception as e:
            logger.warn(f"Could not load cookies: {e}", account_index)

    # Use existing page or create new one
    page = context.pages[0] if context.pages else await context.new_page()

    return pw, context, context, page


async def save_cookies(context: BrowserContext, account_index: int = 0) -> None:
    """Persist browser cookies to disk."""
    cp = cookies_path(account_index)
    cookies = await context.cookies()
    cp.write_text(json.dumps(cookies, indent=2))
    logger.success(f"Session saved to {cp.name}", account_index)


async def close_browser(pw, browser) -> None:
    try:
        if browser:
            await browser.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass
