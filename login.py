import asyncio

from config import BotConfig
from browser import launch_browser, save_cookies, close_browser
import logger

BMS_HOME = "https://in.bookmyshow.com"


async def run_login(config: BotConfig, account_index: int = 0) -> None:
    """Open browser, let user log in manually, then save session."""
    logger.step(f"Starting login flow for account {account_index + 1}", account_index)
    pw, browser, context, page = await launch_browser(config, account_index)

    try:
        await page.goto(BMS_HOME, wait_until="domcontentloaded")
        logger.info("Browser opened. Please log in manually on BookMyShow.", account_index)
        logger.info("After logging in, come back here and press ENTER to save session.", account_index)

        # Wait for user to finish login
        await asyncio.get_event_loop().run_in_executor(None, input, "")

        await save_cookies(context, account_index)
        logger.success("Login session saved successfully!", account_index)
    except Exception as e:
        logger.error(f"Login failed: {e}", account_index)
    finally:
        await close_browser(pw, browser)


async def login_multiple_accounts(config: BotConfig) -> None:
    """Login to multiple accounts sequentially (each needs manual interaction)."""
    for i in range(config.num_accounts):
        logger.step(f"--- Account {i + 1} of {config.num_accounts} ---")
        await run_login(config, i)
        if i < config.num_accounts - 1:
            logger.info("Prepare next account. Press ENTER when ready...")
            await asyncio.get_event_loop().run_in_executor(None, input, "")
