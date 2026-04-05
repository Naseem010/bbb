"""
BookMyShow IPL Ticket Booking Flow — based on real DOM exploration.

Actual BMS flow (sports/IPL events):
  1. Event page → click "Book Now" (or "Login to book" if not logged in)
     - CTA is inside div.sc-8ofzm8-2[data-index="0"]
     - Text is a <span class="sc-1qdowf4-0"> inside it
  2. Info popup → click ✕ (close icon, or press Escape)
  3. Seat count → numbers 1-10 displayed, click desired count → click "Continue"
  4. Category panel (left side) → prices like 1000, 1250, 1500...
     - Click a price to expand → shows sub-stands (e.g., "SBI Life Lower 4 (₹1250.00)")
     - Click sub-stand → stadium canvas highlights that block
  5. Stadium canvas → click highlighted (coloured) block to enter seat view
  6. Seat circles → purple/coloured = available, grey = occupied
     - Click available circles to select seats
  7. "Book" button at bottom-left with total price
  8. Payment page → fill email/phone + UPI → STOP before final pay

BMS uses styled-components with generated class names (sc-XXXXX-N).
We rely primarily on text content and structural patterns, not class names.
"""

import asyncio
import re

from playwright.async_api import Page

from config import BotConfig
from browser import launch_browser, close_browser
from payment import fill_payment
from utils import safe_click
import logger


# ---------------------------------------------------------------------------
# Step 1: Click "Book Now" on event page
# ---------------------------------------------------------------------------
async def click_book_now(page: Page, acc: int) -> bool:
    """
    Click the Book Now CTA.  When not logged in it reads "Login to book"
    and the site will show a login modal — the bot should already have
    session cookies loaded so it should say "Book Now".
    """
    selectors = [
        # Primary: the CTA div with data-index (BMS swiper pattern)
        'div[data-index="0"]:has(span:text-is("Book Now"))',
        'span:text-is("Book Now")',
        'text="Book Now"',
        # If user needs to login (shouldn't happen with cookies)
        'span:text-is("Login to book")',
        'text="Login to book"',
        # Fallback generic
        'button:has-text("Book Now")',
        'a:has-text("Book Now")',
        'button:has-text("Book Tickets")',
    ]
    for sel in selectors:
        if await safe_click(page, sel, timeout=5000):
            logger.success("Clicked booking CTA", acc)
            return True

    logger.error("Could not find 'Book Now' button — check if cookies are loaded", acc)
    return False


# ---------------------------------------------------------------------------
# Step 2: Dismiss Info popup
# ---------------------------------------------------------------------------
async def dismiss_info_popup(page: Page, acc: int) -> None:
    """
    BMS shows an "Important Note" popup about M-Tickets.
    Click the ✕ button on the top-right corner of the popup.
    """

    # Strategy 1: Find the ✕/close icon — it's usually an SVG or span in top-right of popup
    try:
        closed = await page.evaluate("""
        (() => {
            // Find modal/popup overlay
            const modals = document.querySelectorAll('[class*="modal"], [class*="Modal"], [class*="popup"], [class*="Popup"], [class*="dialog"], [role="dialog"], [class*="overlay"]');
            for (const modal of modals) {
                if (modal.offsetParent === null && window.getComputedStyle(modal).display === 'none') continue;
                // Find close button inside or near modal
                const closeEls = modal.querySelectorAll('svg, [class*="close"], [class*="Close"], button, span');
                for (const el of closeEls) {
                    const rect = el.getBoundingClientRect();
                    // Close button is typically small and in top-right area of the popup
                    if (rect.width > 5 && rect.width < 60 && rect.height > 5 && rect.height < 60) {
                        const cursor = window.getComputedStyle(el).cursor;
                        if (cursor === 'pointer' || el.tagName === 'svg' || el.tagName === 'SVG' || el.tagName === 'BUTTON') {
                            el.click();
                            return true;
                        }
                    }
                }
            }
            // Also try standalone close elements
            const closes = document.querySelectorAll('[aria-label="Close"], [aria-label="close"]');
            for (const c of closes) {
                if (c.offsetParent !== null) { c.click(); return true; }
            }
            return false;
        })()
        """)
        if closed:
            logger.success("Dismissed popup (✕)", acc)
            return
    except Exception:
        pass

    # Strategy 2: Playwright selectors
    for sel in ['[aria-label="Close"]', 'button:has-text("✕")', 'button:has-text("×")']:
        if await safe_click(page, sel, timeout=1500):
            logger.success("Dismissed popup", acc)
            return

    # Strategy 3: Escape
    await page.keyboard.press("Escape")
    logger.info("Pressed Escape to dismiss popup", acc)


# ---------------------------------------------------------------------------
# Step 3: Select seat count (1-10)
# ---------------------------------------------------------------------------
async def select_seat_count(page: Page, num_seats: int, acc: int) -> bool:
    """
    BMS shows "How many seats?" with numbers 1-10 in a row.
    Click the desired number, then click "Continue".
    """
    # Wait up to 8s for the seat picker — check using JS, not Playwright locators
    picker_found = False
    for _ in range(16):
        found = await page.evaluate("""
        (() => {
            const text = document.body?.innerText || '';
            return text.includes('How many seats') || text.includes('how many seats');
        })()
        """)
        if found:
            picker_found = True
            break
        await page.wait_for_timeout(500)

    if not picker_found:
        logger.warn("Seat count picker not detected — may have auto-skipped", acc)
        return True

    logger.success("Seat count picker visible", acc)

    # Click the number
    num_str = str(num_seats)
    clicked = await page.evaluate(f"""
    (() => {{
        const all = document.querySelectorAll('*');
        for (const el of all) {{
            if (el.children.length > 0) continue;
            const text = (el.textContent || '').trim();
            if (text !== '{num_str}') continue;
            const rect = el.getBoundingClientRect();
            // Must be in the center area (seat picker modal) and reasonable size
            if (rect.width > 10 && rect.height > 10 && rect.x > 200 && rect.x < 1200) {{
                el.click();
                return true;
            }}
        }}
        return false;
    }})()
    """)
    if clicked:
        logger.success(f"Selected {num_seats} seat(s)", acc)
    else:
        logger.warn(f"Could not click number {num_seats}", acc)

    await page.wait_for_timeout(300)

    # Click "Continue" — must be the one inside the seat picker modal
    continue_clicked = await page.evaluate("""
    (() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const text = (el.textContent || '').trim();
            if (text !== 'Continue') continue;
            const rect = el.getBoundingClientRect();
            // Continue button is wide and in the center/bottom of the modal
            if (rect.width > 100 && rect.height > 30 && rect.x > 200) {
                el.click();
                return true;
            }
        }
        return false;
    })()
    """)
    if continue_clicked:
        logger.success("Clicked 'Continue'", acc)
    else:
        # Fallback
        for sel in ['text="Continue"', 'button:has-text("Continue")']:
            if await safe_click(page, sel, timeout=3000):
                logger.success("Clicked 'Continue' (fallback)", acc)
                continue_clicked = True
                break
        if not continue_clicked:
            logger.warn("Could not find 'Continue' button", acc)

    # Wait for the seat picker to dismiss and category panel to load
    await page.wait_for_timeout(2000)

    # Verify the picker is gone
    picker_gone = await page.evaluate("""
    (() => {
        const text = document.body?.innerText || '';
        return text.includes('Please select the category') || text.includes('select the category');
    })()
    """)
    if picker_gone:
        logger.success("Category panel ready", acc)
    else:
        logger.info("Waiting for category panel...", acc)
        await page.wait_for_timeout(2000)

    return True



# ---------------------------------------------------------------------------
# Step 4: Select price category and sub-stand (SIMPLIFIED)
# ---------------------------------------------------------------------------
async def select_category(page: Page, target_prices: list[int], preferred_stands: list[str], acc: int) -> bool:
    """
    Simple approach:
      1. Click target price in left panel (or first available)
      2. Click first sub-stand that appears
      3. Click coloured stadium block
    """
    # Wait for category panel
    try:
        await page.locator('text="Please select the category"').wait_for(state="visible", timeout=8000)
    except Exception:
        pass

    # --- Step A: Click a price from user's target list (priority order) ---
    price_clicked = False
    for price in target_prices:
        price_clicked = await _click_price(page, str(price), acc)
        if price_clicked:
            break

    if not price_clicked:
        logger.error(f"None of your target prices {target_prices} found on the page", acc)
        try:
            await page.screenshot(path="debug_category_fail.png")
        except Exception:
            pass
        return False


    # --- Step B: Click a sub-stand (this should navigate to seat view) ---
    stand_clicked = await _click_first_substand(page, preferred_stands, acc)

    if stand_clicked:
        # Wait for seat view to load (canvas should change to show individual seats)
        await page.wait_for_timeout(2000)

        # Verify we're in seat view by checking for "Chosen Stand" or "Please select seat"
        has_seat_view = await page.evaluate("""
        (() => {
            const text = document.body?.innerText || '';
            return text.includes('Please select seat') || text.includes('Chosen Stand') ||
                   text.includes('select seat');
        })()
        """)
        if has_seat_view:
            logger.success("Seat view loaded", acc)
        else:
            logger.info("Sub-stand clicked — waiting for seat view...", acc)
            await page.wait_for_timeout(2000)

    return True


async def _click_price(page: Page, price_str: str, acc: int) -> bool:
    """Click a specific price number in the left panel."""
    # Strategy 1: Playwright get_by_text — exact match in left panel
    try:
        loc = page.get_by_text(price_str, exact=True)
        count = await loc.count()
        for i in range(count):
            el = loc.nth(i)
            box = await el.bounding_box()
            if box and box['x'] < 400:
                await el.click()
                logger.success(f"Clicked price ₹{price_str}", acc)
                return True
    except Exception:
        pass

    # Strategy 2: JS — match textContent (own text only, not children)
    try:
        clicked = await page.evaluate(f"""
        (() => {{
            const target = '{price_str}';
            const all = document.querySelectorAll('*');
            for (const el of all) {{
                if (el.offsetParent === null) continue;
                const rect = el.getBoundingClientRect();
                if (rect.x > 400 || rect.height < 10 || rect.height > 80) continue;
                // Check own text content (not children)
                const ownText = Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join('');
                if (ownText === target) {{
                    el.click();
                    return 'ownText';
                }}
                // Also check full textContent
                const text = (el.textContent || '').trim();
                if (text === target) {{
                    el.click();
                    return 'textContent';
                }}
            }}
            return null;
        }})()
        """)
        if clicked:
            logger.success(f"Clicked price ₹{price_str} (JS-{clicked})", acc)
            return True
    except Exception:
        pass

    # Strategy 3: Click parent row containing the price
    try:
        clicked = await page.evaluate(f"""
        (() => {{
            const target = '{price_str}';
            const all = document.querySelectorAll('*');
            for (const el of all) {{
                if (el.offsetParent === null) continue;
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                // Match element whose innerText starts with the price
                if (rect.x < 400 && rect.height > 20 && rect.height < 80 &&
                    (text === target || text.startsWith(target + '\\n') || text.startsWith(target + ' '))) {{
                    el.click();
                    return text.slice(0, 30);
                }}
            }}
            return null;
        }})()
        """)
        if clicked:
            logger.success(f"Clicked price row: '{clicked}'", acc)
            return True
    except Exception:
        pass

    logger.debug(f"₹{price_str} not found in left panel", acc)
    return False



async def _click_first_substand(page: Page, preferred_stands: list[str], acc: int) -> bool:
    """Click first sub-stand row (e.g. 'BLOCK B BAY 1-LOWER (₹1500.00)')."""

    for name in preferred_stands:
        try:
            loc = page.get_by_text(name).first
            if await loc.is_visible(timeout=1500):
                await loc.click()
                logger.success(f"Selected preferred: {name}", acc)
                return True
        except Exception:
            continue

    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.offsetParent === null) continue;
                if (el.children.length > 2) continue;
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.includes('\u20b9') && text.length > 10 && text.length < 150 &&
                    rect.x < 400 && rect.height > 15 && rect.height < 60) {
                    el.click();
                    return text;
                }
            }
            return null;
        })()
        """)
        if result:
            logger.success(f"Selected stand: {result}", acc)
            return True
    except Exception:
        pass

    logger.info("No sub-stands visible (may go straight to stadium)", acc)
    return False



async def _click_stadium_block(page: Page, acc: int) -> bool:
    """
    Click a highlighted (coloured) block on the stadium map.
    BMS uses '/aerialcanvas/' pages with canvas-based rendering.

    Strategy:
      1. Try SVG elements first (some events use SVG)
      2. Try canvas pixel scanning — sample pixels to find coloured (non-grey) areas
      3. Try Playwright click on coloured regions using page.mouse
    """
    # Strategy 1: SVG elements
    try:
        result = await page.evaluate("""
        (() => {
            const greyish = ['#ccc', '#ddd', '#eee', '#999', '#aaa', '#bbb', '#c8c8c8',
                'gray', 'grey', '#d0d0d0', '#e0e0e0', '#f0f0f0', '#fff', '#ffffff',
                'white', 'none', 'transparent',
                'rgb(200', 'rgb(189', 'rgb(204', 'rgb(224', 'rgb(240', 'rgb(158',
                'rgb(153', 'rgb(170', 'rgb(187', 'rgb(221', 'rgb(238', 'rgb(255'];
            const svgEls = document.querySelectorAll('svg path, svg rect, svg polygon, svg g[fill], svg text');
            for (const el of svgEls) {
                const fill = (el.getAttribute('fill') || window.getComputedStyle(el).fill || '').toLowerCase();
                if (!fill) continue;
                const isGrey = greyish.some(g => fill.includes(g));
                if (isGrey) continue;
                const rect = el.getBoundingClientRect();
                if (rect.x > 250 && rect.width > 15 && rect.height > 15 && rect.width < 500) {
                    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    return { method: 'svg', fill, x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
                }
            }
            return null;
        })()
        """)
        if result:
            logger.success(f"Clicked SVG block ({result['fill']}) at ({result['x']:.0f},{result['y']:.0f})", acc)
            return True
    except Exception:
        pass

    # Strategy 2: Canvas pixel scanning — find coloured (non-grey, non-green/field) spots
    try:
        coloured_spots = await page.evaluate("""
        (() => {
            const canvases = document.querySelectorAll('canvas');
            const spots = [];

            for (const canvas of canvases) {
                const rect = canvas.getBoundingClientRect();
                if (rect.width < 200 || rect.height < 200) continue;

                const ctx = canvas.getContext('2d');
                if (!ctx) continue;

                const w = canvas.width;
                const h = canvas.height;
                const scaleX = w / rect.width;
                const scaleY = h / rect.height;

                // Sample grid of points across the canvas
                const step = 20;  // pixels
                for (let px = 50; px < w - 50; px += step) {
                    for (let py = 50; py < h - 50; py += step) {
                        const pixel = ctx.getImageData(px, py, 1, 1).data;
                        const [r, g, b, a] = pixel;
                        if (a < 128) continue;  // Skip transparent

                        // Skip grey (R ≈ G ≈ B, all > 140)
                        const spread = Math.max(r, g, b) - Math.min(r, g, b);
                        if (spread < 30 && Math.min(r, g, b) > 140) continue;

                        // Skip white/near-white
                        if (r > 230 && g > 230 && b > 230) continue;

                        // Skip dark/black
                        if (r < 40 && g < 40 && b < 40) continue;

                        // Skip green (cricket field)
                        if (g > r * 1.3 && g > b * 1.3 && g > 80) continue;

                        // This is a coloured spot — likely a stadium section
                        const viewX = rect.x + px / scaleX;
                        const viewY = rect.y + py / scaleY;
                        spots.push({ x: viewX, y: viewY, r, g, b, canvasX: px, canvasY: py });
                    }
                }
            }

            // Group nearby spots and pick the cluster with most points (biggest coloured block)
            if (spots.length === 0) return null;

            // Simple: just return the spot closest to center that's coloured
            const centerX = spots.reduce((s, p) => s + p.x, 0) / spots.length;
            const centerY = spots.reduce((s, p) => s + p.y, 0) / spots.length;

            // Sort by distance from center
            spots.sort((a, b) => {
                const da = Math.hypot(a.x - centerX, a.y - centerY);
                const db = Math.hypot(b.x - centerX, b.y - centerY);
                return da - db;
            });

            // Return top 5 candidates
            return spots.slice(0, 5).map(s => ({x: s.x, y: s.y, r: s.r, g: s.g, b: s.b}));
        })()
        """)

        if coloured_spots and len(coloured_spots) > 0:
            spot = coloured_spots[0]
            logger.info(f"Found coloured canvas spot at ({spot['x']:.0f},{spot['y']:.0f}) RGB=({spot['r']},{spot['g']},{spot['b']})", acc)
            await page.mouse.click(spot['x'], spot['y'])
            logger.success(f"Clicked stadium block on canvas", acc)

            # Check if page changed (zoomed into seat view)
            new_url = page.url
            if 'seatLayout' in new_url or 'seat' in new_url.lower():
                logger.success("Navigated to seat layout", acc)
                return True

            # May need to try multiple spots if first didn't work
            for i, spot in enumerate(coloured_spots[1:], 1):
                await page.mouse.click(spot['x'], spot['y'])
                logger.info(f"Trying spot {i+1} at ({spot['x']:.0f},{spot['y']:.0f})", acc)

            return True
    except Exception as e:
        logger.debug(f"Canvas scan error: {e}", acc)

    # Strategy 3: Just click the stadium area using Playwright mouse (center-right of page)
    try:
        viewport = page.viewport_size
        if viewport:
            # Stadium is typically in the right ~60% of the page, vertically centered
            cx = viewport['width'] * 0.6
            cy = viewport['height'] * 0.5
            await page.mouse.click(cx, cy)
            logger.info(f"Clicked center of stadium area ({cx:.0f},{cy:.0f})", acc)
            return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Step 5-6: Select available seats (coloured circles)
# ---------------------------------------------------------------------------
async def select_available_seats(page: Page, num_seats: int, acc: int) -> int:
    """
    BMS seat view shows seats as circles/elements.
    Available = coloured (purple/blue/etc), Occupied = grey.
    This function first diagnoses the DOM to find the right selectors,
    then clicks available seats.
    """
    # Wait for seat view to be ready — look for "Please select seat" or "Chosen Stand"
    for _ in range(10):
        is_seat_view = await page.evaluate("""
        (() => {
            const text = document.body?.innerText || '';
            return text.includes('select seat') || text.includes('Select seat') ||
                   text.includes('Chosen Stand');
        })()
        """)
        if is_seat_view:
            break
        await page.wait_for_timeout(500)

    logger.info(f"Selecting up to {num_seats} available seats...", acc)

    # First: diagnose what seat elements exist on the page
    diag = await page.evaluate("""
    (() => {
        const info = {
            circles: 0, circleAttrs: [],
            svgCount: document.querySelectorAll('svg').length,
            canvasCount: document.querySelectorAll('canvas').length,
            seatDivs: 0, seatDivSamples: [],
            allClickables: 0,
        };

        // Check SVG circles
        const circles = document.querySelectorAll('circle');
        info.circles = circles.length;
        for (let i = 0; i < Math.min(20, circles.length); i++) {
            const c = circles[i];
            const comp = window.getComputedStyle(c);
            info.circleAttrs.push({
                fill: c.getAttribute('fill'),
                styleFill: c.style.fill,
                computedFill: comp.fill,
                cls: (c.getAttribute('class') || '').slice(0, 80),
                r: c.getAttribute('r'),
                cx: c.getAttribute('cx'),
                cy: c.getAttribute('cy'),
                cursor: comp.cursor,
                pointerEvents: comp.pointerEvents,
                opacity: comp.opacity,
                parentTag: c.parentElement?.tagName,
                parentCls: (c.parentElement?.className?.baseVal || '').slice(0, 80),
            });
        }

        // Check div/span seats
        const seatEls = document.querySelectorAll('[class*="seat"], [class*="Seat"], [data-seat], [data-id]');
        info.seatDivs = seatEls.length;
        for (let i = 0; i < Math.min(10, seatEls.length); i++) {
            const s = seatEls[i];
            info.seatDivSamples.push({
                tag: s.tagName,
                cls: (s.className?.toString() || '').slice(0, 120),
                text: (s.innerText || s.textContent || '').trim().slice(0, 30),
                dataAttrs: Array.from(s.attributes).filter(a => a.name.startsWith('data-')).map(a => a.name + '=' + a.value).join(', '),
            });
        }

        // Check any elements with cursor:pointer in the seat area (right side)
        const allEls = document.querySelectorAll('svg *, [class*="seat"], [class*="Seat"]');
        let clickable = 0;
        for (const el of allEls) {
            if (window.getComputedStyle(el).cursor === 'pointer') clickable++;
        }
        info.allClickables = clickable;

        return info;
    })()
    """)

    logger.debug(f"Seat diagnostics: {diag['circles']} circles, {diag['svgCount']} SVGs, "
                 f"{diag['canvasCount']} canvases, {diag['seatDivs']} seat divs, "
                 f"{diag['allClickables']} clickable elements", acc)

    if diag['circleAttrs']:
        sample = diag['circleAttrs'][0]
        logger.debug(f"Sample circle: fill={sample['fill']} computed={sample['computedFill']} "
                     f"cls={sample['cls']} r={sample['r']} cursor={sample['cursor']}", acc)

    if diag['seatDivSamples']:
        sample = diag['seatDivSamples'][0]
        logger.debug(f"Sample seat div: <{sample['tag']}> cls={sample['cls'][:60]} data={sample['dataAttrs'][:60]}", acc)

    # Now try multiple strategies to select seats
    selected = await page.evaluate(f"""
    (() => {{
        let selected = 0;
        const target = {num_seats};

        // Grey/occupied colour patterns to skip
        const isGreyFill = (fill) => {{
            if (!fill) return true;
            fill = fill.toLowerCase().trim();
            if (fill === 'none' || fill === 'transparent' || fill === 'white' ||
                fill === '#fff' || fill === '#ffffff' || fill === '') return true;
            // Parse rgb values — grey means R ≈ G ≈ B and relatively high (>140)
            const rgbMatch = fill.match(/rgb[a]?\\(\\s*([0-9]+)\\s*,\\s*([0-9]+)\\s*,\\s*([0-9]+)/);
            if (rgbMatch) {{
                const [_, r, g, b] = rgbMatch.map(Number);
                const spread = Math.max(r, g, b) - Math.min(r, g, b);
                if (spread < 30 && Math.min(r, g, b) > 140) return true;  // Grey
                if (r > 240 && g > 240 && b > 240) return true;  // Near-white
            }}
            // Hex grey check
            const hexMatch = fill.match(/^#([0-9a-f]{{6}})$/);
            if (hexMatch) {{
                const hex = hexMatch[1];
                const r = parseInt(hex.slice(0,2), 16);
                const g = parseInt(hex.slice(2,4), 16);
                const b = parseInt(hex.slice(4,6), 16);
                const spread = Math.max(r, g, b) - Math.min(r, g, b);
                if (spread < 30 && Math.min(r, g, b) > 140) return true;
                if (r > 240 && g > 240 && b > 240) return true;
            }}
            // Short hex
            const shortHex = fill.match(/^#([0-9a-f]{{3}})$/);
            if (shortHex) {{
                const hex = shortHex[1];
                const r = parseInt(hex[0]+hex[0], 16);
                const g = parseInt(hex[1]+hex[1], 16);
                const b = parseInt(hex[2]+hex[2], 16);
                const spread = Math.max(r, g, b) - Math.min(r, g, b);
                if (spread < 30 && Math.min(r, g, b) > 140) return true;
                if (r > 240 && g > 240 && b > 240) return true;
            }}
            // Named greys
            const greyNames = ['gray', 'grey', 'silver', 'gainsboro', 'lightgray', 'lightgrey', 'darkgray', 'darkgrey'];
            if (greyNames.includes(fill)) return true;
            return false;
        }};

        const isOccupiedClass = (cls) => {{
            cls = (cls || '').toLowerCase();
            return cls.includes('occupied') || cls.includes('sold') || cls.includes('booked') ||
                   cls.includes('blocked') || cls.includes('unavailable') || cls.includes('disabled') ||
                   cls.includes('taken') || cls.includes('reserved');
        }};

        const isAvailableClass = (cls) => {{
            cls = (cls || '').toLowerCase();
            return cls.includes('available') || cls.includes('free') || cls.includes('open') ||
                   cls.includes('selectable') || cls.includes('active');
        }};

        // STRATEGY 1: SVG circles — check both fill attribute and computed fill
        const circles = document.querySelectorAll('circle');
        for (const c of circles) {{
            if (selected >= target) break;
            const r = parseFloat(c.getAttribute('r') || '0');
            if (r < 3) continue;  // Skip tiny decorative circles

            const cls = (c.getAttribute('class') || c.className?.baseVal || '');
            if (isOccupiedClass(cls)) continue;

            // Check fill from multiple sources
            const attrFill = c.getAttribute('fill') || '';
            const styleFill = c.style.fill || '';
            const computedFill = window.getComputedStyle(c).fill || '';
            const fill = attrFill || styleFill || computedFill;

            if (isGreyFill(fill)) continue;

            // Check if cursor is pointer (clickable seat)
            const cursor = window.getComputedStyle(c).cursor;
            const isClickable = cursor === 'pointer' || isAvailableClass(cls);

            // If it has a non-grey fill, it's likely available
            if (fill || isClickable) {{
                c.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                selected++;
            }}
        }}

        // STRATEGY 2: SVG groups (g) or rects that represent seats
        if (selected < target) {{
            const seatGroups = document.querySelectorAll('svg g[class], svg g[data-seat], svg g[id]');
            for (const g of seatGroups) {{
                if (selected >= target) break;
                const cls = (g.getAttribute('class') || g.className?.baseVal || '');
                if (isOccupiedClass(cls)) continue;
                if (isAvailableClass(cls)) {{
                    g.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                    selected++;
                }}
            }}
        }}

        // STRATEGY 3: Any SVG element with cursor:pointer that isn't grey
        if (selected < target) {{
            const allSvgEls = document.querySelectorAll('svg circle, svg rect, svg path, svg g');
            for (const el of allSvgEls) {{
                if (selected >= target) break;
                const cursor = window.getComputedStyle(el).cursor;
                if (cursor !== 'pointer') continue;
                const cls = (el.getAttribute('class') || el.className?.baseVal || '');
                if (isOccupiedClass(cls)) continue;
                const fill = el.getAttribute('fill') || window.getComputedStyle(el).fill || '';
                if (isGreyFill(fill)) continue;
                el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                selected++;
            }}
        }}

        // STRATEGY 4: Div/span seat elements
        if (selected < target) {{
            const divSeats = document.querySelectorAll('[class*="seat"], [class*="Seat"], [data-seat], [data-seatid]');
            for (const s of divSeats) {{
                if (selected >= target) break;
                const cls = (s.className?.toString() || '');
                if (isOccupiedClass(cls)) continue;
                if (isAvailableClass(cls) || window.getComputedStyle(s).cursor === 'pointer') {{
                    s.click();
                    selected++;
                }}
            }}
        }}

        // STRATEGY 5: Elements with data- attributes related to seats
        if (selected < target) {{
            const dataSeats = document.querySelectorAll('[data-id][class], [data-row][data-col], [data-seatno]');
            for (const s of dataSeats) {{
                if (selected >= target) break;
                const cls = (s.className?.toString() || '');
                if (isOccupiedClass(cls)) continue;
                const cursor = window.getComputedStyle(s).cursor;
                if (cursor === 'pointer' || isAvailableClass(cls)) {{
                    s.click();
                    selected++;
                }}
            }}
        }}

        return selected;
    }})()
    """)

    if selected and selected > 0:
        logger.success(f"Selected {selected}/{num_seats} seat(s) via DOM", acc)
        return selected

    # STRATEGY 6: Canvas-based seat selection
    # BMS aerialcanvas renders seats on <canvas> — scan pixels for coloured circles
    logger.info("Trying canvas-based seat selection...", acc)
    canvas_selected = await _select_seats_canvas(page, num_seats, acc)
    if canvas_selected > 0:
        return canvas_selected

    logger.warn("No seats selected via any method", acc)
    return 0


async def _select_seats_canvas(page: Page, num_seats: int, acc: int) -> int:
    """
    Scan canvas pixels to find available seat circles (coloured, non-grey).
    BMS seat view: circles in a grid, grey outline = available, filled colour = selected.
    Available seats appear as circles with a coloured outline but mostly white/light inside.
    We need to find the circle outlines/borders.
    """
    try:
        seat_spots = await page.evaluate(f"""
        (() => {{
            const canvases = document.querySelectorAll('canvas');
            const spots = [];

            for (const canvas of canvases) {{
                const rect = canvas.getBoundingClientRect();
                if (rect.width < 100 || rect.height < 100) continue;

                const ctx = canvas.getContext('2d');
                if (!ctx) continue;

                const w = canvas.width;
                const h = canvas.height;
                const scaleX = w / rect.width;
                const scaleY = h / rect.height;

                // First pass: find ALL non-white, non-transparent pixels that could be seat outlines
                const candidates = [];
                const step = 4;  // Fine scan
                for (let px = 10; px < w - 10; px += step) {{
                    for (let py = 10; py < h - 10; py += step) {{
                        const pixel = ctx.getImageData(px, py, 1, 1).data;
                        const [r, g, b, a] = pixel;
                        if (a < 100) continue;

                        // Skip pure white / near-white (background)
                        if (r > 235 && g > 235 && b > 235) continue;
                        // Skip black/dark (text/lines)
                        if (r < 30 && g < 30 && b < 30) continue;

                        // Check colour saturation
                        const max = Math.max(r, g, b);
                        const min = Math.min(r, g, b);
                        const spread = max - min;

                        // Grey = low spread, high value
                        const isGrey = spread < 25 && min > 120;
                        // Light grey (seat outline for available seats)
                        const isLightGrey = spread < 15 && min > 160 && max < 230;

                        // We want coloured OR light-grey circles (both are available seats)
                        // Purple/blue seats (filled/highlighted) have spread > 30
                        const isColoured = spread > 30;

                        if (isColoured || isLightGrey) {{
                            const viewX = rect.x + px / scaleX;
                            const viewY = rect.y + py / scaleY;
                            candidates.push({{ x: viewX, y: viewY, r, g, b, coloured: isColoured }});
                        }}
                    }}
                }}

                // Cluster nearby candidates into seat positions
                const seats = [];
                for (const c of candidates) {{
                    const existing = seats.find(s => Math.hypot(s.x - c.x, s.y - c.y) < 8);
                    if (existing) {{
                        // Prefer coloured spots over grey
                        if (c.coloured && !existing.coloured) {{
                            existing.x = c.x; existing.y = c.y;
                            existing.r = c.r; existing.g = c.g; existing.b = c.b;
                            existing.coloured = true;
                        }}
                        existing.pixelCount = (existing.pixelCount || 1) + 1;
                    }} else {{
                        seats.push({{ ...c, pixelCount: 1 }});
                    }}
                }}

                // Filter: real seats have multiple pixels in their cluster
                // and are within a reasonable grid pattern
                for (const s of seats) {{
                    if (s.pixelCount >= 2) {{
                        spots.push(s);
                    }}
                }}
            }}

            // Sort: coloured seats first (they're more likely to be clickable/available),
            // then by position (top-left to bottom-right)
            spots.sort((a, b) => {{
                if (a.coloured !== b.coloured) return a.coloured ? -1 : 1;
                if (Math.abs(a.y - b.y) > 15) return a.y - b.y;
                return a.x - b.x;
            }});

            return spots.slice(0, {num_seats * 3});
        }})()
        """)

        if not seat_spots or len(seat_spots) == 0:
            logger.debug("No seat spots found on canvas", acc)
            return 0

        coloured_count = sum(1 for s in seat_spots if s.get('coloured'))
        grey_count = len(seat_spots) - coloured_count
        logger.info(f"Found {len(seat_spots)} seat candidates ({coloured_count} coloured, {grey_count} grey outlines)", acc)

        clicked = 0
        for spot in seat_spots:
            if clicked >= num_seats:
                break
            await page.mouse.click(spot['x'], spot['y'])
            clicked += 1
            c = "coloured" if spot.get('coloured') else "outline"
            logger.info(f"Clicked seat {clicked}/{num_seats} at ({spot['x']:.0f},{spot['y']:.0f}) [{c}] RGB({spot['r']},{spot['g']},{spot['b']})", acc)

        # Wait for BMS to register the selections

        # Verify how many seats were actually selected by checking the UI
        try:
            seat_count_text = await page.evaluate("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const text = (el.innerText || '').trim();
                    if (text.match(/[0-9]+ seats?/i) && el.offsetParent !== null) {
                        const rect = el.getBoundingClientRect();
                        if (rect.x < 400) return text;
                    }
                }
                return '';
            })()
            """)
            if seat_count_text:
                logger.info(f"BMS shows: '{seat_count_text}'", acc)
        except Exception:
            pass

        if clicked > 0:
            logger.success(f"Canvas: clicked {clicked} seat spots", acc)
        return clicked

    except Exception as e:
        logger.debug(f"Canvas seat scan error: {e}", acc)
        return 0


# ---------------------------------------------------------------------------
# Step 7: Click "Book" button
# ---------------------------------------------------------------------------
async def click_book_button(page: Page, acc: int) -> bool:
    """
    Click the 'Book' button at bottom-left of the seat selection panel.
    The button is a red/pink rectangle with white "Book" text inside.
    """

    # First: scroll the left panel to bottom to make sure Book button is visible
    try:
        await page.evaluate("""
        (() => {
            // Find ALL scrollable containers in the left panel and scroll them down
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const rect = el.getBoundingClientRect();
                if (rect.x > 450 || rect.width < 100 || rect.height < 100) continue;
                if (el.scrollHeight > el.clientHeight + 20) {
                    el.scrollTop = el.scrollHeight;
                }
            }
            window.scrollTo(0, document.body.scrollHeight);
        })()
        """)
        await page.wait_for_timeout(300)
    except Exception:
        pass

    # Strategy 1: Find element with "Book" text, scroll it into view, then click
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            const candidates = [];
            for (const el of all) {
                // Check own text (not children) to avoid matching "BookMyShow"
                const ownText = Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join('');
                const innerText = (el.innerText || '').trim();

                if (ownText === 'Book' || innerText === 'Book') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 30 && rect.x < 500) {
                        candidates.push({ el, x: rect.x, y: rect.y, w: rect.width });
                    }
                }
            }

            if (candidates.length === 0) return null;

            // Pick the one lowest on page (the actual Book CTA, not header)
            candidates.sort((a, b) => b.y - a.y);
            const best = candidates[0];

            // Scroll into view first
            best.el.scrollIntoView({ behavior: 'instant', block: 'center' });

            // Click after scroll
            setTimeout(() => {
                best.el.click();
                if (best.el.parentElement) best.el.parentElement.click();
            }, 100);

            return { x: best.x, y: best.y };
        })()
        """)
        if result:
            await page.wait_for_timeout(200)
            logger.success(f"Clicked 'Book' button at ({result['x']:.0f},{result['y']:.0f})", acc)
            return True
    except Exception:
        pass

    # Strategy 2: Playwright — find element with exact text "Book" using textContent (not innerText)
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            let best = null;
            for (const el of all) {
                if (el.offsetParent === null) continue;
                // Use textContent which is just this element's own text
                const ownText = Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join('');
                if (ownText === 'Book') {
                    const rect = el.getBoundingClientRect();
                    if (rect.x < 400) {
                        if (!best || rect.y > best.y) {
                            best = { el, x: rect.x, y: rect.y };
                        }
                    }
                }
            }
            if (best) {
                best.el.click();
                // Also click parent in case the text node isn't the clickable element
                if (best.el.parentElement) best.el.parentElement.click();
                return { x: best.x, y: best.y };
            }
            return null;
        })()
        """)
        if result:
            logger.success(f"Clicked 'Book' text at ({result['x']:.0f},{result['y']:.0f})", acc)
            return True
    except Exception:
        pass

    # Strategy 3: Playwright locators
    for sel in [
        'div:text-is("Book")',
        'span:text-is("Book")',
        'button:text-is("Book")',
        'a:text-is("Book")',
    ]:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                el = loc.nth(i)
                box = await el.bounding_box()
                if box and box['x'] < 400:
                    await el.click()
                    logger.success(f"Clicked 'Book' via {sel}", acc)
                    return True
        except Exception:
            continue

    # Strategy 4: Search ENTIRE DOM including hidden/fixed elements for "Book" text
    try:
        result = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.textContent || '').trim();
                if (text === 'Book' || text === 'BOOK') {
                    el.scrollIntoView({ block: 'center' });
                    el.click();
                    if (el.parentElement) el.parentElement.click();
                    if (el.parentElement?.parentElement) el.parentElement.parentElement.click();
                    return { tag: el.tagName, text, class: (el.className?.toString() || '').slice(0, 60) };
                }
            }
            return null;
        })()
        """)
        if result:
            await page.wait_for_timeout(200)
            logger.success(f"Clicked 'Book' (deep scan) <{result['tag']}>", acc)
            return True
    except Exception:
        pass

    # Strategy 5: The Book button might not exist because no seat was actually
    # selected on BMS's side (canvas click didn't register). Take screenshot
    # and look for ANY clickable CTA in the page.
    try:
        await page.screenshot(path="debug_no_book.png")
        logger.debug("Saved debug_no_book.png", acc)
    except Exception:
        pass

    # Try clicking at the known position where Book button appears (~x:235, y:790)
    # based on previous successful run where it was at (235,855)
    try:
        # First check if there's a "Chosen Stand" text which means seats are selected
        has_chosen = await page.locator('text="Chosen Stand"').count()
        has_price = await page.evaluate("""
        (() => {
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.innerText || '').trim();
                if (text.match(/₹[0-9,]+/) && text.includes('seat') && el.getBoundingClientRect().x < 400) {
                    return text.slice(0, 50);
                }
            }
            return null;
        })()
        """)
        logger.debug(f"Chosen Stand visible: {has_chosen > 0}, Price text: {has_price}", acc)

        if has_chosen > 0 or has_price:
            # Seats ARE selected — Book button should exist, scroll harder
            await page.evaluate("""
            (() => {
                // Scroll EVERYTHING to bottom
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.scrollHeight > el.clientHeight + 5) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            })()
            """)
            await page.wait_for_timeout(500)

            # Try finding Book button again after aggressive scroll
            result = await page.evaluate("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const text = (el.textContent || '').trim();
                    if (text === 'Book') {
                        const rect = el.getBoundingClientRect();
                        el.click();
                        if (el.parentElement) el.parentElement.click();
                        return { x: rect.x, y: rect.y };
                    }
                }
                return null;
            })()
            """)
            if result:
                logger.success(f"Clicked 'Book' after scroll at ({result['x']:.0f},{result['y']:.0f})", acc)
                return True
    except Exception:
        pass

    logger.error("Could not find 'Book' button — seat may not have been selected", acc)
    return False


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
async def booking_flow(config: BotConfig, account_index: int = 0) -> None:
    """Full booking pipeline for a single account."""
    acc = account_index
    logger.step(f"Starting booking flow — account {acc + 1}", acc)
    pw, browser, context, page = await launch_browser(config, acc)

    try:
        # Load event page
        logger.info(f"Opening {config.event_url}", acc)
        await page.goto(config.event_url, wait_until="domcontentloaded", timeout=30000)

        # Check if logged in
        has_book = await page.locator('text="Book Now"').count() > 0
        has_login = await page.locator('text="Login to book"').count() > 0

        if has_login and not has_book:
            logger.error("Page shows 'Login to book' — session cookies may be missing or expired.", acc)
            logger.error("Run in Login mode first (mode=1) to save fresh cookies.", acc)
            return

        # Step 1: Book Now
        if not await click_book_now(page, acc):
            return

        # Step 2: Dismiss Info popup
        await dismiss_info_popup(page, acc)

        # Step 3: Select seat count
        await select_seat_count(page, config.num_seats, acc)

        # Step 4: Select category + stand (single attempt — should work first try)
        category_selected = await select_category(
            page, config.target_prices, config.preferred_stands, acc
        )
        if not category_selected:
            logger.error("Category selection failed", acc)
            return

        # Step 5-6: Select seats
        seats = await select_available_seats(page, config.num_seats, acc)
        if seats == 0:
            logger.error("No seats selected", acc)
            return
        logger.success(f"Total seats: {seats}", acc)

        # Step 7: Click Book
        if not await click_book_button(page, acc):
            return

        # Step 8: Payment flow (Agree → Proceed to Pay → Contact → QR)
        await fill_payment(page, config, acc)

        # Step 9: Ask for confirmation before paying
        logger.success("=" * 50, acc)
        logger.success("QR CODE READY — Scan to pay", acc)
        logger.success("=" * 50, acc)

        confirm = await asyncio.get_event_loop().run_in_executor(
            None, input, "\n  Confirm payment? (yes/no): "
        )
        if confirm.strip().lower() in ("yes", "y"):
            logger.success("Payment confirmed by user. Complete in browser.", acc)
        else:
            logger.warn("Payment cancelled by user.", acc)

        # Keep browser open for manual completion
        logger.info("Press ENTER to close browser...", acc)
        await asyncio.get_event_loop().run_in_executor(None, input, "")

    except Exception as e:
        logger.error(f"Booking error: {e}", acc)
        import traceback
        logger.debug(traceback.format_exc(), acc)
    finally:
        await close_browser(pw, browser)


async def run_booking(config: BotConfig) -> None:
    """Run booking for all accounts in parallel."""
    if config.num_accounts <= 1:
        await booking_flow(config, 0)
    else:
        tasks = [booking_flow(config, i) for i in range(config.num_accounts)]
        await asyncio.gather(*tasks, return_exceptions=True)
