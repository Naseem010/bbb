# BookMyShow Ticket Booking Bot

Automated ticket booking tool for BookMyShow using Playwright browser automation.

> **Disclaimer:** This tool is for educational purposes. Use responsibly and respect BookMyShow's Terms of Service.

## Setup

### 1. Install Python 3.11+

```bash
python3 --version  # ensure 3.11 or higher
```

### 2. Create virtual environment

```bash
cd bookmyshow-bot
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### Step 1: Login (save session)

```bash
python main.py
```

Select **mode 1** (Login). The browser opens — log into BookMyShow manually. Press ENTER in the terminal after login. Session cookies are saved automatically.

For multiple accounts, repeat with each account.

### Step 2: Book tickets

```bash
python main.py
```

Select **mode 2** (Booking). Provide:
- Event URL (e.g. `https://in.bookmyshow.com/events/...`)
- Target prices in priority order (e.g. `499,999,1499`)
- Number of seats
- Email/phone and UPI ID
- Payment PIN (not saved to disk)

The bot will:
1. Load your saved session
2. Open the event page
3. Monitor ticket availability
4. Select tickets matching your price priorities
5. Proceed to checkout
6. Fill payment details
7. **Stop before final payment** — you confirm manually

### Multi-Account Mode

Set accounts > 1 during configuration. Each account:
- Has its own cookie file (`cookies.json`, `cookies_2.json`, etc.)
- Runs in its own browser instance in parallel during booking

### Proxy Support

Enter proxy URL when prompted (e.g. `http://user:pass@host:port`).

## Project Structure

```
bookmyshow-bot/
├── main.py           # CLI entry point
├── config.py         # Configuration dataclass + persistence
├── browser.py        # Playwright browser launch + stealth
├── login.py          # Manual login + session save
├── booking.py        # Ticket monitoring + booking flow
├── payment.py        # Payment form autofill
├── updater.py        # Version check (mock endpoint)
├── utils.py          # Human-like delays and typing
├── logger.py         # Colored console + file logging
├── config.json       # Saved preferences (auto-generated)
├── cookies.json      # Session cookies (auto-generated)
├── logs.txt          # Execution logs (auto-generated)
└── requirements.txt  # Python dependencies
```

## Configuration

After first run, `config.json` is created with your preferences (excluding payment PIN). Edit it directly to change defaults without re-entering everything.

## Logs

All actions are logged to `logs.txt` with timestamps.
