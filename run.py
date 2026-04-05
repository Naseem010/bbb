#!/usr/bin/env python3
"""Direct runner — loads config.json, runs booking, keeps browser open for manual payment."""
import asyncio
import sys

from config import BotConfig
from booking import run_booking
import logger


# Monkey-patch the booking_flow to keep browser open indefinitely
import booking as _b
_original_flow = _b.booking_flow

async def _patched_flow(config, account_index=0):
    acc = account_index
    pw, browser, context, page = None, None, None, None
    try:
        from browser import launch_browser, close_browser
        from payment import fill_payment

        logger.step(f"Starting booking — account {acc + 1}", acc)
        pw, browser, context, page = await launch_browser(config, acc)

        await page.goto(config.event_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        from bms_api import extract_details_from_page, extract_event_details
        details = await extract_details_from_page(page)
        logger.info(f"Event: {details.event_code} | Venue: {details.venue_code} | Session: {details.session_id}", acc)

        has_book = await page.locator('text="Book Now"').count() > 0
        has_login = await page.locator('text="Login to book"').count() > 0
        if has_login and not has_book:
            logger.error("Not logged in", acc)
            return

        if not await _b.click_book_now(page, acc):
            return
        await page.wait_for_timeout(1500)

        details = await extract_details_from_page(page)
        if not details.session_id:
            details = extract_event_details(page.url)

        await _b.dismiss_popup(page, acc)
        await _b.select_seat_count(page, config.num_seats, acc)

        from bms_api import Category
        category = await _b.select_category(page, details, config.target_prices, config.preferred_stands, acc)
        if not category:
            return

        seats = await _b.select_seats_api(page, details, category, config.num_seats, acc)
        if seats == 0:
            logger.error("No seats selected", acc)
            return

        if not await _b.click_book_button(page, acc):
            return

        await fill_payment(page, config, acc)

        logger.success("=" * 50, acc)
        logger.success("PAYMENT PAGE READY — Complete payment manually", acc)
        logger.success("=" * 50, acc)
        logger.info("Browser will stay open. Press ENTER here when done to close.", acc)

        # Block forever until ENTER
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error: {e}", acc)
        import traceback
        logger.debug(traceback.format_exc(), acc)
        # Still keep browser open on error
        logger.info("Browser staying open. Press Ctrl+C to exit.", acc)
        try:
            while True:
                await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
    finally:
        if pw and browser:
            from browser import close_browser
            await close_browser(pw, browser)

_b.booking_flow = _patched_flow


async def main():
    logger.banner()
    cfg = BotConfig.load()
    cfg.mode = 2

    print(f"  Event:  {cfg.event_url}")
    print(f"  Prices: {cfg.target_prices}")
    print(f"  Seats:  {cfg.num_seats}")
    print(f"  Email:  {cfg.email}")
    print()

    await run_booking(cfg)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warn("Session closed.")
        sys.exit(0)
