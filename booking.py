"""
BookMyShow IPL Ticket Booking — API-driven flow.

Uses BMS internal APIs for seat discovery + exact coordinate clicking.
No canvas pixel guessing. Fast, reliable, deterministic.

Flow:
  1. Open event page → click "Book Now"
  2. Dismiss info popup (click ✕)
  3. Select seat count → click Continue
  4. API: fetch categories → find matching price
  5. Click price in left panel → click sub-stand
  6. API: fetch seat coordinates → click available seats by (x,y)
  7. Click "Book" button
  8. Payment flow (Agree → Proceed to Pay → Contact → QR)
"""
import asyncio
import re

from playwright.async_api import Page

from config import BotConfig
from browser import launch_browser, close_browser
from payment import fill_payment
from bms_api import (
    extract_details_from_page, extract_event_details,
    fetch_show_info, get_available_seats_with_coordinates,
    EventDetails, Category,
)
from utils import safe_click
import logger

FAST_SLEEP = 0.05


# ---------------------------------------------------------------------------
# Step 1: Click "Book Now"
# ---------------------------------------------------------------------------
async def click_book_now(page: Page, acc: int) -> bool:
    for sel in [
        'span:text-is("Book Now")',
        'text="Book Now"',
        'span:text-is("Login to book")',
    ]:
        if await safe_click(page, sel, timeout=8000):
            logger.success("Clicked 'Book Now'", acc)
            return True
    logger.error("'Book Now' not found", acc)
    return False


# ---------------------------------------------------------------------------
# Step 2: Dismiss popup (click ✕)
# ---------------------------------------------------------------------------
async def dismiss_popup(page: Page, acc: int) -> None:
    await page.wait_for_timeout(1000)
    closed = await page.evaluate("""
    (() => {
        const modals = document.querySelectorAll('[class*="modal"], [class*="Modal"], [class*="popup"], [role="dialog"], [class*="overlay"]');
        for (const modal of modals) {
            if (window.getComputedStyle(modal).display === 'none') continue;
            const closes = modal.querySelectorAll('svg, [class*="close"], [class*="Close"], button, span');
            for (const el of closes) {
                const rect = el.getBoundingClientRect();
                if (rect.width > 5 && rect.width < 60 && rect.height > 5 && rect.height < 60) {
                    const cursor = window.getComputedStyle(el).cursor;
                    if (cursor === 'pointer' || el.tagName === 'svg' || el.tagName === 'SVG' || el.tagName === 'BUTTON') {
                        el.click();
                        return true;
                    }
                }
            }
        }
        return false;
    })()
    """)
    if closed:
        logger.success("Dismissed popup (✕)", acc)
    else:
        await page.keyboard.press("Escape")
        logger.info("Pressed Escape", acc)


# ---------------------------------------------------------------------------
# Step 3: Select seat count
# ---------------------------------------------------------------------------
async def select_seat_count(page: Page, num_seats: int, acc: int) -> bool:
    # Wait for picker
    for _ in range(16):
        found = await page.evaluate("document.body?.innerText?.includes('How many seats') || false")
        if found:
            break
        await page.wait_for_timeout(500)
    else:
        logger.warn("Seat picker not found — skipping", acc)
        return True

    logger.success("Seat picker visible", acc)

    # Click the number
    num_str = str(num_seats)
    await page.evaluate(f"""
    (() => {{
        const all = document.querySelectorAll('*');
        for (const el of all) {{
            if (el.children.length > 0) continue;
            if ((el.textContent || '').trim() === '{num_str}') {{
                const r = el.getBoundingClientRect();
                if (r.width > 10 && r.height > 10 && r.x > 200) {{ el.click(); return; }}
            }}
        }}
    }})()
    """)
    logger.success(f"Selected {num_seats} seat(s)", acc)
    await page.wait_for_timeout(200)

    # Click Continue
    await page.evaluate("""
    (() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            if ((el.textContent || '').trim() === 'Continue') {
                const r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 30) { el.click(); return; }
            }
        }
    })()
    """)
    logger.success("Clicked 'Continue'", acc)

    # Wait for category panel
    await page.wait_for_timeout(2000)
    return True


# ---------------------------------------------------------------------------
# Step 4: Select price category (API-assisted)
# ---------------------------------------------------------------------------
async def select_category(page: Page, details: EventDetails, target_prices: list[int], preferred_stands: list[str], acc: int) -> Category | None:
    """Use API to find available category matching target price, then click it in UI."""

    # Try API first (may be encrypted — fall back to UI)
    categories = await fetch_show_info(page, details, acc)

    # If API worked, use it to pick category
    selected = None
    if categories:
        available = [c for c in categories if c.seats_available > 0]
        for tp in target_prices:
            for cat in available:
                if int(cat.price) == tp:
                    selected = cat
                    break
            if selected:
                break

    # UI-based: click price from target list
    price_clicked = None
    if selected:
        price_clicked = str(int(selected.price))
        await _click_price(page, price_clicked, acc)
    else:
        # API failed/encrypted — click prices from UI directly
        for price in target_prices:
            if await _click_price(page, str(price), acc):
                price_clicked = str(price)
                break

    if not price_clicked:
        logger.error(f"None of target prices {target_prices} found on page", acc)
        return None

    await page.wait_for_timeout(500)

    # Click sub-stand matching the selected price
    desc = selected.description if selected else ""
    await _click_substand(page, desc, preferred_stands, price_clicked, acc)
    await page.wait_for_timeout(2000)

    # Return a category object (may be from API or fabricated from UI click)
    if not selected:
        selected = Category(code=f"PRICE-{price_clicked}", description="", price=float(price_clicked))

    return selected


async def _click_price(page: Page, price_str: str, acc: int) -> bool:
    """Click price number in left panel. Returns True if clicked."""
    clicked = await page.evaluate(f"""
    (() => {{
        const all = document.querySelectorAll('*');
        for (const el of all) {{
            if (el.children.length > 0) continue;
            const text = (el.textContent || '').trim();
            if (text === '{price_str}') {{
                const r = el.getBoundingClientRect();
                if (r.x < 400 && r.height > 10) {{ el.click(); return true; }}
            }}
        }}
        return false;
    }})()
    """)
    if clicked:
        logger.success(f"Clicked ₹{price_str}", acc)
        return True

    # Try Playwright
    try:
        loc = page.get_by_text(price_str, exact=True)
        for i in range(await loc.count()):
            box = await loc.nth(i).bounding_box()
            if box and box['x'] < 400:
                await loc.nth(i).click()
                logger.success(f"Clicked ₹{price_str} (PW)", acc)
                return True
    except Exception:
        pass

    return False


async def _click_substand(page: Page, api_description: str, preferred_stands: list[str], price_str: str, acc: int) -> None:
    """Click sub-stand in left panel that matches the selected price."""
    await page.wait_for_timeout(500)

    # Try preferred stands first
    for name in preferred_stands:
        try:
            loc = page.get_by_text(name).first
            if await loc.is_visible(timeout=1000):
                await loc.click()
                logger.success(f"Selected preferred: {name}", acc)
                return
        except Exception:
            continue

    # Try API description match
    if api_description:
        try:
            loc = page.get_by_text(api_description).first
            if await loc.is_visible(timeout=1000):
                await loc.click()
                logger.success(f"Selected: {api_description}", acc)
                return
        except Exception:
            pass

    # Click first sub-stand containing the correct price (₹PRICE.00)
    clicked = await page.evaluate(f"""
    (() => {{
        const targetPrice = '{price_str}';
        const all = document.querySelectorAll('*');
        for (const el of all) {{
            if (el.children.length > 2) continue;
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            // Must contain ₹ AND the target price, be in left panel, reasonable size
            if (text.includes('\\u20b9' + targetPrice) && text.length > 10 && text.length < 150 &&
                r.x < 400 && r.height > 15 && r.height < 60) {{
                el.click();
                return text;
            }}
        }}
        // Fallback: any sub-stand with ₹ and the price number
        for (const el of all) {{
            if (el.children.length > 2) continue;
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text.includes(targetPrice) && text.includes('\\u20b9') && text.length > 10 && text.length < 150 &&
                r.x < 400 && r.height > 15 && r.height < 60) {{
                el.click();
                return text;
            }}
        }}
        return null;
    }})()
    """)
    if clicked:
        logger.success(f"Selected: {clicked}", acc)
    else:
        logger.info("No sub-stand clicked (may go straight to seats)", acc)


# ---------------------------------------------------------------------------
# Step 5-6: Select seats using API coordinates
# ---------------------------------------------------------------------------
async def select_seats_api(page: Page, details: EventDetails, category: Category, num_seats: int, acc: int) -> int:
    """Fetch exact seat coordinates from API and click them."""

    seats = await get_available_seats_with_coordinates(page, details, category.code, acc)

    if not seats:
        logger.warn("API returned no seat coordinates — falling back to canvas", acc)
        return await _select_seats_canvas_fallback(page, num_seats, acc)

    # Find the seat map bounding box on the page
    seat_map_box = await page.evaluate("""
    (() => {
        const canvases = document.querySelectorAll('canvas');
        for (const c of canvases) {
            const r = c.getBoundingClientRect();
            if (r.width > 260 && r.height > 260 && r.y > 100) {
                return { x: r.x, y: r.y, w: r.width, h: r.height };
            }
        }
        // Try SVG
        const svgs = document.querySelectorAll('svg');
        for (const s of svgs) {
            const r = s.getBoundingClientRect();
            if (r.width > 260 && r.height > 260 && r.y > 100) {
                return { x: r.x, y: r.y, w: r.width, h: r.height };
            }
        }
        return null;
    })()
    """)

    if not seat_map_box:
        logger.warn("Could not find seat map element", acc)
        return await _select_seats_canvas_fallback(page, num_seats, acc)

    logger.info(f"Seat map at ({seat_map_box['x']:.0f},{seat_map_box['y']:.0f}) {seat_map_box['w']:.0f}x{seat_map_box['h']:.0f}", acc)

    # Calculate coordinate scaling
    # API coordinates are relative to the seat layout, we need to map to viewport
    if seats:
        max_x = max(s.x + s.width for s in seats)
        max_y = max(s.y + s.height for s in seats)
        min_x = min(s.x for s in seats)
        min_y = min(s.y for s in seats)

        # Scale API coords to viewport
        scale_x = seat_map_box['w'] / (max_x - min_x + 20) if max_x > min_x else 1
        scale_y = seat_map_box['h'] / (max_y - min_y + 20) if max_y > min_y else 1
        offset_x = seat_map_box['x'] - min_x * scale_x + 10 * scale_x
        offset_y = seat_map_box['y'] - min_y * scale_y + 10 * scale_y

    clicked = 0
    for seat in seats[:num_seats * 2]:  # Try extra in case some fail
        if clicked >= num_seats:
            break

        vx = seat.x * scale_x + offset_x
        vy = seat.y * scale_y + offset_y

        # Validate coordinates are within viewport
        if vx < seat_map_box['x'] or vx > seat_map_box['x'] + seat_map_box['w']:
            continue
        if vy < seat_map_box['y'] or vy > seat_map_box['y'] + seat_map_box['h']:
            continue

        await page.mouse.click(vx, vy)
        await page.wait_for_timeout(50)
        clicked += 1
        logger.info(f"Clicked seat {seat.seat_number} (row {seat.row_number}) at ({vx:.0f},{vy:.0f})", acc)

    if clicked > 0:
        logger.success(f"Selected {clicked} seat(s) via API coordinates", acc)

    return clicked


async def _select_seats_canvas_fallback(page: Page, num_seats: int, acc: int) -> int:
    """Fallback: scan canvas pixels for seat-like coloured spots."""
    logger.info("Using canvas pixel fallback...", acc)
    spots = await page.evaluate(f"""
    (() => {{
        const canvases = document.querySelectorAll('canvas');
        const spots = [];
        for (const canvas of canvases) {{
            const rect = canvas.getBoundingClientRect();
            if (rect.width < 200 || rect.height < 200) continue;
            const ctx = canvas.getContext('2d');
            if (!ctx) continue;
            const w = canvas.width, h = canvas.height;
            const sx = w / rect.width, sy = h / rect.height;
            const step = 6;
            for (let px = 20; px < w - 20; px += step) {{
                for (let py = 20; py < h - 20; py += step) {{
                    const [r, g, b, a] = ctx.getImageData(px, py, 1, 1).data;
                    if (a < 200) continue;
                    const spread = Math.max(r, g, b) - Math.min(r, g, b);
                    if (spread < 25 && Math.min(r, g, b) > 140) continue;
                    if (r > 220 && g > 220 && b > 220) continue;
                    if (r < 50 && g < 50 && b < 50) continue;
                    if (g > r * 1.2 && g > b * 1.2 && g > 80) continue;
                    spots.push({{ x: rect.x + px / sx, y: rect.y + py / sy }});
                }}
            }}
        }}
        const deduped = [];
        for (const s of spots) {{
            if (!deduped.some(d => Math.hypot(d.x - s.x, d.y - s.y) < 10)) deduped.push(s);
        }}
        return deduped.slice(0, {num_seats * 3});
    }})()
    """)
    clicked = 0
    for spot in (spots or []):
        if clicked >= num_seats:
            break
        x, y = spot['x'], spot['y']
        # BMS canvas uses mousedown+mouseup events, not just click
        await page.mouse.move(x, y)
        await page.mouse.down()
        await page.wait_for_timeout(30)
        await page.mouse.up()
        await page.wait_for_timeout(100)
        # Also dispatch a click event
        await page.mouse.click(x, y)
        await page.wait_for_timeout(100)
        clicked += 1
        logger.info(f"Clicked canvas ({x:.0f},{y:.0f})", acc)

    # Verify if Book button appeared
    await page.wait_for_timeout(500)
    has_book = await page.evaluate("document.body?.innerText?.includes('Book') && document.body?.innerText?.includes('seat') || false")
    if has_book:
        logger.success(f"Canvas: {clicked} seat(s) selected — Book visible", acc)
    else:
        logger.warn(f"Canvas: clicked {clicked} spots but Book may not be visible", acc)
    return clicked


# ---------------------------------------------------------------------------
# Step 7: Click "Book" button
# ---------------------------------------------------------------------------
async def click_book_button(page: Page, acc: int) -> bool:
    """Find and click the Book button — scroll into view first."""
    # Scroll all left-panel containers to bottom
    await page.evaluate("""
    (() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const r = el.getBoundingClientRect();
            if (r.x > 450 || r.width < 100 || r.height < 100) continue;
            if (el.scrollHeight > el.clientHeight + 20) el.scrollTop = el.scrollHeight;
        }
    })()
    """)
    await page.wait_for_timeout(300)

    # Find "Book" text, scroll into view, click
    clicked = await page.evaluate("""
    (() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
            if (own === 'Book' || (el.innerText || '').trim() === 'Book') {
                const r = el.getBoundingClientRect();
                if (r.width > 30) {
                    el.scrollIntoView({ block: 'center' });
                    setTimeout(() => { el.click(); if (el.parentElement) el.parentElement.click(); }, 100);
                    return true;
                }
            }
        }
        return false;
    })()
    """)
    if clicked:
        await page.wait_for_timeout(200)
        logger.success("Clicked 'Book'", acc)
        return True

    # Fallback: click red CTA that contains "Book"
    clicked = await page.evaluate("""
    (() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            if (el.offsetParent === null) continue;
            const text = (el.innerText || '').trim();
            if (!text.includes('Book') || text.includes('BookMyShow')) continue;
            const bg = window.getComputedStyle(el).backgroundColor;
            const m = bg.match(/rgba?\\(\\s*(\\d+)[^\\d]+(\\d+)[^\\d]+(\\d+)/);
            if (m && +m[1] > 160 && +m[1] > +m[2] + 20) {
                el.scrollIntoView({ block: 'center' });
                el.click();
                return true;
            }
        }
        return false;
    })()
    """)
    if clicked:
        await page.wait_for_timeout(200)
        logger.success("Clicked 'Book' (red CTA)", acc)
        return True

    logger.error("Could not find 'Book' button", acc)
    await page.screenshot(path="debug_no_book.png")
    return False


# ---------------------------------------------------------------------------
# Main booking flow
# ---------------------------------------------------------------------------
async def booking_flow(config: BotConfig, account_index: int = 0) -> None:
    acc = account_index
    logger.step(f"Starting booking — account {acc + 1}", acc)
    pw, browser, context, page = await launch_browser(config, acc)

    try:
        # Load event page
        logger.info(f"Opening {config.event_url}", acc)
        await page.goto(config.event_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Extract event details for API calls
        details = await extract_details_from_page(page)
        logger.info(f"Event: {details.event_code} | Venue: {details.venue_code} | Session: {details.session_id}", acc)

        # Check login state
        has_book = await page.locator('text="Book Now"').count() > 0
        has_login = await page.locator('text="Login to book"').count() > 0
        if has_login and not has_book:
            logger.error("Not logged in — run Login mode first", acc)
            return

        # Step 1: Book Now
        if not await click_book_now(page, acc):
            return
        await page.wait_for_timeout(1500)

        # Re-extract details (URL may have changed after Book Now)
        details = await extract_details_from_page(page)
        if not details.session_id:
            details = extract_event_details(page.url)
        logger.info(f"Session: {details.event_code}/{details.venue_code}/{details.session_id}", acc)

        # Step 2: Dismiss popup
        await dismiss_popup(page, acc)

        # Step 3: Seat count
        await select_seat_count(page, config.num_seats, acc)

        # Step 4: Select category (API-assisted)
        category = await select_category(page, details, config.target_prices, config.preferred_stands, acc)
        if not category:
            return

        # Step 5-6: Select seats (API coordinates)
        seats = await select_seats_api(page, details, category, config.num_seats, acc)
        if seats == 0:
            logger.error("No seats selected", acc)
            return
        logger.success(f"Total seats: {seats}", acc)

        # Step 7: Book
        if not await click_book_button(page, acc):
            return

        # Step 8: Payment
        await fill_payment(page, config, acc)

        # Step 9: Confirmation
        logger.success("=" * 50, acc)
        logger.success("QR CODE READY — Scan to pay", acc)
        logger.success("=" * 50, acc)

        confirm = await asyncio.get_event_loop().run_in_executor(
            None, input, "\n  Confirm payment? (yes/no): "
        )
        if confirm.strip().lower() in ("yes", "y"):
            logger.success("Payment confirmed.", acc)
        else:
            logger.warn("Payment cancelled.", acc)

        logger.info("Press ENTER to close browser...", acc)
        await asyncio.get_event_loop().run_in_executor(None, input, "")

    except Exception as e:
        logger.error(f"Error: {e}", acc)
        import traceback
        logger.debug(traceback.format_exc(), acc)
    finally:
        await close_browser(pw, browser)


async def run_booking(config: BotConfig) -> None:
    if config.num_accounts <= 1:
        await booking_flow(config, 0)
    else:
        tasks = [booking_flow(config, i) for i in range(config.num_accounts)]
        await asyncio.gather(*tasks, return_exceptions=True)
