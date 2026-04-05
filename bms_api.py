"""
BookMyShow internal API client.

Extracts event details from URL, fetches seat layouts and coordinates
via BMS APIs using the browser's authenticated session.
"""
import re
from dataclasses import dataclass, field
from playwright.async_api import Page, BrowserContext
import logger


@dataclass
class EventDetails:
    event_code: str = ""
    venue_code: str = ""
    session_id: str = ""
    base_url: str = "https://in.bookmyshow.com"


@dataclass
class Category:
    code: str = ""
    description: str = ""
    price: float = 0
    seats_available: int = 0
    status: str = ""


@dataclass
class Seat:
    seat_number: str = ""
    row_number: str = ""
    is_booked: bool = False
    is_available: bool = True
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0


def extract_event_details(url: str) -> EventDetails:
    """Extract eventCode, venueCode, sessionID from BMS URL."""
    details = EventDetails()

    # eventCode: ET followed by digits
    m = re.search(r'(ET\d{5,8})', url)
    if m:
        details.event_code = m.group(1)

    # venueCode: uppercase letters after eventCode in path
    m = re.search(r'/(?:aerialcanvas|seatLayout)/([A-Z]{2,8})/', url)
    if m:
        details.venue_code = m.group(1)
    else:
        # Try from path segments
        parts = url.split('/')
        for i, p in enumerate(parts):
            if p.startswith('ET') and i + 2 < len(parts):
                # Pattern: /ET.../aerialcanvas/VENUE/SESSION
                candidate = parts[i + 2] if parts[i + 1] == 'aerialcanvas' else parts[i + 1]
                if re.match(r'^[A-Z]{2,8}$', candidate):
                    details.venue_code = candidate
                    break

    # sessionID: numeric at end of path or after venueCode
    m = re.search(r'/(\d{3,12})(?:\?|$)', url)
    if m:
        details.session_id = m.group(1)

    return details


async def extract_details_from_page(page: Page) -> EventDetails:
    """Extract event details from the current page URL and JS state."""
    url = page.url
    details = extract_event_details(url)

    # If missing, try extracting from page's JS state
    if not details.session_id or not details.venue_code:
        try:
            state = await page.evaluate("""
            (() => {
                const url = window.location.href;
                const state = window.__INITIAL_STATE__ || {};
                // Try URL path segments
                const parts = url.split('/');
                const sessionMatch = url.match(/(\\d{4,12})(?:\\?|$)/);
                const venueMatch = url.match(/\\/([A-Z]{2,8})\\//);
                return {
                    sessionId: sessionMatch ? sessionMatch[1] : '',
                    venueCode: venueMatch ? venueMatch[1] : '',
                    url: url,
                };
            })()
            """)
            if state.get('sessionId') and not details.session_id:
                details.session_id = state['sessionId']
            if state.get('venueCode') and not details.venue_code:
                details.venue_code = state['venueCode']
        except Exception:
            pass

    return details


async def fetch_show_info(page: Page, details: EventDetails, acc: int = 0) -> list[Category]:
    """Fetch available categories from BMS showinfo API."""
    url = f"{details.base_url}/api/le/seatLayout/showinfo"
    params = f"eventCode={details.event_code}&venueCode={details.venue_code}&sessionID={details.session_id}"
    full_url = f"{url}?{params}"
    logger.debug(f"API URL: {full_url}", acc)

    try:
        data = await page.evaluate(f"""
        (async () => {{
            try {{
                const resp = await fetch('{full_url}', {{
                    credentials: 'include',
                    headers: {{
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json',
                        'appCode': 'WEB',
                        'x-app-code': 'WEB',
                        'x-platform': 'WEB',
                        'x-platform-code': 'WEB',
                    }}
                }});
                const text = await resp.text();
                try {{ return JSON.parse(text); }}
                catch {{ return {{ _raw: text.slice(0, 500), _status: resp.status }}; }}
            }} catch (e) {{
                return {{ _error: e.message }};
            }}
        }})()
        """)

        if data.get('_error'):
            logger.warn(f"API fetch error: {data['_error']}", acc)
            return []
        if data.get('_raw'):
            logger.debug(f"API raw response ({data.get('_status')}): {data['_raw'][:200]}", acc)
            return []

        # Log top-level keys so we can see the actual structure
        if isinstance(data, dict):
            logger.debug(f"API response keys: {list(data.keys())[:15]}", acc)
            # Log first 300 chars of stringified response
            import json as _json
            logger.debug(f"API data: {_json.dumps(data, default=str)[:300]}", acc)

        categories = []
        events = data.get('events', data.get('Events', data.get('event', data.get('Event', []))))
        if isinstance(events, dict):
            events = [events]

        for event in events:
            cats = event.get('categories', event.get('Categories', []))
            if isinstance(cats, dict):
                cats = [cats]
            for cat in cats:
                c = Category(
                    code=cat.get('categoryCode', cat.get('CategoryCode', '')),
                    description=cat.get('description', cat.get('Description', '')),
                    price=float(cat.get('price', cat.get('Price', 0))),
                    seats_available=int(cat.get('seatsAvailable', cat.get('SeatsAvailable', 0))),
                    status=cat.get('status', cat.get('Status', '')),
                )
                categories.append(c)

        logger.info(f"API: {len(categories)} categories found", acc)
        return categories
    except Exception as e:
        logger.warn(f"API showinfo failed: {e}", acc)
        return []


async def fetch_seat_layout(page: Page, details: EventDetails, category_code: str, acc: int = 0) -> list[Seat]:
    """Fetch seat availability for a specific category."""
    url = f"{details.base_url}/api/le/seatLayout/{details.event_code}/{details.session_id}/{category_code}"

    try:
        data = await page.evaluate(f"""
        (async () => {{
            const resp = await fetch('{url}', {{
                credentials: 'include',
                headers: {{ 'X-Requested-With': 'XMLHttpRequest', 'appCode': 'WEB', 'x-app-code': 'WEB', 'x-platform-code': 'WEB' }}
            }});
            return await resp.json();
        }})()
        """)

        seats = []
        layout = data.get('seatLayout', data.get('SeatLayout', {}))
        seat_data = layout.get('data', layout.get('Data', {}))

        for section_key, section_seats in seat_data.items():
            if not isinstance(section_seats, list):
                section_seats = [section_seats]
            for s in section_seats:
                seat = Seat(
                    seat_number=str(s.get('seatNumber', s.get('SeatNumber', ''))),
                    row_number=str(s.get('rowNumber', s.get('RowNumber', ''))),
                    is_booked=bool(s.get('isBooked', s.get('IsBooked', 0))),
                    is_available=bool(s.get('isAvailable', s.get('IsAvailable', 1))),
                )
                if seat.is_available and not seat.is_booked:
                    seats.append(seat)

        logger.info(f"API: {len(seats)} available seats in {category_code}", acc)
        return seats
    except Exception as e:
        logger.warn(f"API seatLayout failed: {e}", acc)
        return []


async def fetch_layout_drawing(page: Page, details: EventDetails, category_code: str, acc: int = 0) -> list[Seat]:
    """Fetch canvas coordinates for seats in a category."""
    url = f"{details.base_url}/api/le/layoutDrawing/{details.event_code}/{details.session_id}/{category_code}"

    try:
        data = await page.evaluate(f"""
        (async () => {{
            const resp = await fetch('{url}', {{
                credentials: 'include',
                headers: {{ 'X-Requested-With': 'XMLHttpRequest', 'appCode': 'WEB', 'x-app-code': 'WEB', 'x-platform-code': 'WEB' }}
            }});
            return await resp.json();
        }})()
        """)

        seats = []
        drawing = data.get('layoutDrawing', data.get('LayoutDrawing', {}))
        layout = drawing.get('seatLayout', drawing.get('SeatLayout', {}))
        seat_data = layout.get('data', layout.get('Data', {}))

        for section_key, section in seat_data.items():
            items = section.get('items', section.get('Items', []))
            if not isinstance(items, list):
                items = [items]
            for item in items:
                action = item.get('action', item.get('Action', {}))
                seat_info = action.get('seat', action.get('Seat', {}))
                if seat_info:
                    seat = Seat(
                        seat_number=str(seat_info.get('seatNumber', seat_info.get('SeatNumber', ''))),
                        x=float(seat_info.get('x', seat_info.get('X', 0))),
                        y=float(seat_info.get('y', seat_info.get('Y', 0))),
                        width=float(seat_info.get('width', seat_info.get('Width', 0))),
                        height=float(seat_info.get('height', seat_info.get('Height', 0))),
                    )
                    if seat.x > 0 and seat.y > 0:
                        seats.append(seat)

        logger.info(f"API: {len(seats)} seat coordinates in {category_code}", acc)
        return seats
    except Exception as e:
        logger.warn(f"API layoutDrawing failed: {e}", acc)
        return []


async def get_available_seats_with_coordinates(
    page: Page, details: EventDetails, category_code: str, acc: int = 0
) -> list[Seat]:
    """
    Merge seat availability with canvas coordinates.
    Returns only available seats with their x,y positions.
    """
    layout_seats = await fetch_seat_layout(page, details, category_code, acc)
    drawing_seats = await fetch_layout_drawing(page, details, category_code, acc)

    # Build lookup of available seat numbers
    available_numbers = {s.seat_number for s in layout_seats if s.is_available and not s.is_booked}

    # Merge coordinates with availability
    result = []
    for ds in drawing_seats:
        if ds.seat_number in available_numbers:
            ds.is_available = True
            ds.is_booked = False
            result.append(ds)

    # If merge didn't work (different formats), return all drawing seats
    if not result and drawing_seats:
        logger.info("Using all coordinates (merge failed — assuming all available)", acc)
        result = drawing_seats

    logger.success(f"API: {len(result)} clickable seats ready", acc)
    return result
