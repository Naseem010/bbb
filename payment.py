"""
BookMyShow Payment Flow — based on real UI screenshots.

After clicking "Book" on the seat selection page:
  1. "Play Fair, Stay Safe" popup → click "Agree & Proceed"
  2. Ticket options page (M-Ticket, price summary, "Proceed to Pay") → click "Proceed to Pay"
  3. Contact Details popup (email + mobile) → fill email → click "Submit"
  4. Payment options page (UPI, Card, Wallets, etc.) → click "Scan QR code"
  5. STOP — ask user for confirmation before paying
"""
import asyncio

from playwright.async_api import Page

from config import BotConfig
from utils import safe_click
import logger


async def fill_payment(page: Page, config: BotConfig, account: int = 0) -> None:
    """Handle the full post-Book payment flow."""
    logger.step("Starting payment flow...", account)

    # --- Step 1: "Play Fair, Stay Safe" popup → Agree & Proceed ---
    await _wait_and_log(page, account, "Agree & Proceed popup")
    await _click_agree_proceed(page, account)

    # --- Step 2: Ticket options page → "Proceed to Pay" ---
    await _wait_for_navigation(page, account, "ticket-options", "Proceed to Pay", timeout=10)
    await _click_proceed_to_pay(page, account)

    # --- Step 3: Contact Details popup → fill email → Submit ---
    await _wait_for_navigation(page, account, "order-summary", "Contact Details", timeout=10)
    await _fill_contact_details(page, config, account)

    # --- Step 4: Payment page → click "Scan QR code" (UPI) ---
    await _wait_for_navigation(page, account, "order-summary", "Payment options", timeout=10)
    await _select_upi_qr(page, account)

    # --- Step 5: STOP — ask for confirmation ---
    logger.success("Ready to pay! QR code should be visible.", account)
    logger.warn("BOT STOPPED — waiting for your confirmation before proceeding.", account)


async def _wait_and_log(page: Page, account: int, step_name: str) -> None:
    """Brief wait with log."""
    logger.info(f"Waiting for: {step_name}", account)


async def _wait_for_navigation(page: Page, account: int, url_contains: str, text_contains: str, timeout: int = 10) -> None:
    """Wait until URL contains a keyword OR page text contains a keyword."""
    import asyncio as _aio
    for _ in range(timeout * 2):
        url = page.url
        if url_contains in url:
            logger.info(f"Page loaded: ...{url_contains}...", account)
            return
        try:
            has_text = await page.locator(f'text="{text_contains}"').count()
            if has_text > 0:
                logger.info(f"Found: '{text_contains}'", account)
                return
        except Exception:
            pass
        await _aio.sleep(0.5)
    logger.warn(f"Timeout waiting for '{text_contains}' — proceeding anyway", account)


async def _click_agree_proceed(page: Page, account: int) -> None:
    """Click 'Agree & Proceed' on the Play Fair popup."""
    for sel in [
        'text="Agree & Proceed"',
        'button:has-text("Agree & Proceed")',
        'button:has-text("Agree")',
        'div:text-is("Agree & Proceed")',
    ]:
        if await safe_click(page, sel, timeout=5000):
            logger.success("Clicked 'Agree & Proceed'", account)
            return

    # Fallback: find red button in the popup
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const text = (el.innerText || '').trim();
                if (text.includes('Agree') && text.includes('Proceed')) {
                    el.click();
                    return true;
                }
            }
            return false;
        })()
        """)
        if result:
            logger.success("Clicked Agree & Proceed (JS)", account)
            return
    except Exception:
        pass

    # Try closing with X or Escape
    await page.keyboard.press("Escape")
    logger.info("No Agree popup found (may have auto-dismissed)", account)


async def _click_proceed_to_pay(page: Page, account: int) -> None:
    """Click 'Proceed to Pay' on the ticket options/summary page."""
    for sel in [
        'text="Proceed to Pay"',
        'button:has-text("Proceed to Pay")',
        'div:text-is("Proceed to Pay")',
        'span:text-is("Proceed to Pay")',
        'button:has-text("Proceed")',
        'text="Make Payment"',
    ]:
        if await safe_click(page, sel, timeout=8000):
            logger.success("Clicked 'Proceed to Pay'", account)
            return

    # Fallback: find red CTA button
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const bg = window.getComputedStyle(el).backgroundColor;
                const rgbMatch = bg.match(/rgba?\\(\\s*(\\d+).*?(\\d+).*?(\\d+)/);
                if (!rgbMatch) continue;
                const [_, r, g, b] = rgbMatch.map(Number);
                // Red/pink CTA
                if (r > 170 && g < 160 && b < 160) {
                    const text = (el.innerText || '').trim();
                    if (text.includes('Proceed') || text.includes('Pay') || text.includes('Continue')) {
                        el.click();
                        return text;
                    }
                }
            }
            return null;
        })()
        """)
        if result:
            logger.success(f"Clicked '{result}' (red CTA)", account)
            return
    except Exception:
        pass

    logger.warn("Could not find 'Proceed to Pay' button", account)


async def _fill_contact_details(page: Page, config: BotConfig, account: int) -> None:
    """Fill the Contact Details popup (email + mobile number) and click Submit."""

    # Wait for the Contact Details popup
    try:
        await page.locator('text="Contact Details"').wait_for(state="visible", timeout=10000)
        logger.info("Contact Details popup visible", account)
    except Exception:
        logger.info("Contact Details popup not detected — may not appear", account)
        return


    # Fill email
    if config.email:
        try:
            email_input = page.locator('input[placeholder*="email" i], input[placeholder*="abc@gmail" i], input[type="email"]').first
            await email_input.click()
            await email_input.fill("")
            await email_input.type(config.email, delay=50)
            logger.success(f"Filled email: {config.email}", account)
        except Exception:
            logger.warn("Could not fill email field", account)


    # Click Submit
    for sel in [
        'text="Submit"',
        'button:has-text("Submit")',
        'div:text-is("Submit")',
    ]:
        if await safe_click(page, sel, timeout=5000):
            logger.success("Clicked 'Submit' on Contact Details", account)
            return

    # Fallback: find Submit button by red/coloured background
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const text = (el.innerText || '').trim();
                if (text === 'Submit') {
                    el.click();
                    return true;
                }
            }
            return false;
        })()
        """)
        if result:
            logger.success("Clicked Submit (JS)", account)
            return
    except Exception:
        pass

    logger.warn("Could not click Submit button", account)


async def _select_upi_qr(page: Page, account: int) -> None:
    """On the payment page, click 'Scan QR code' under UPI."""

    # Wait for payment options page
    try:
        await page.locator('text="Payment options"').wait_for(state="visible", timeout=10000)
        logger.info("Payment options page loaded", account)
    except Exception:
        logger.info("Waiting for payment page...", account)

    # UPI / "Pay by any UPI App" should already be selected (first option)
    # Click "Scan QR code"
    for sel in [
        'text="Scan QR code"',
        'div:has-text("Scan QR code")',
        'text="Scan QR"',
    ]:
        if await safe_click(page, sel, timeout=5000):
            logger.success("Clicked 'Scan QR code'", account)
            return

    # Fallback: click on the QR code row (it has a > chevron)
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.offsetParent === null) continue;
                const text = (el.innerText || '').trim();
                if (text.includes('Scan QR') || text.includes('QR code')) {
                    el.click();
                    return true;
                }
            }
            return false;
        })()
        """)
        if result:
            logger.success("Clicked Scan QR code (JS)", account)
            return
    except Exception:
        pass

    logger.warn("Could not find 'Scan QR code' option", account)
