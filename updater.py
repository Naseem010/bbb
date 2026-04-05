import httpx

import logger

UPDATE_URL = "https://api.example.com/bms-bot/version"
CURRENT_VERSION = "1.0.0"


async def check_for_updates() -> None:
    """Check a mock endpoint for new versions. Non-blocking, best-effort."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(UPDATE_URL)
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("version", CURRENT_VERSION)
                if latest != CURRENT_VERSION:
                    logger.warn(f"Update available: v{latest} (current: v{CURRENT_VERSION})")
                    logger.info(f"Download from: {data.get('url', 'N/A')}")
                else:
                    logger.info(f"You are on the latest version (v{CURRENT_VERSION})")
            else:
                logger.debug("Update check returned non-200, skipping.")
    except Exception:
        logger.debug("Could not reach update server — skipping update check.")
