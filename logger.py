import logging
import sys
from datetime import datetime
from pathlib import Path

from colorama import Fore, Style, init

init(autoreset=True)

LOG_FILE = Path(__file__).parent / "logs.txt"

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

_logger = logging.getLogger("bms_bot")
_logger.setLevel(logging.DEBUG)
_logger.addHandler(_file_handler)

COLOR_MAP = {
    "info": Fore.CYAN,
    "success": Fore.GREEN,
    "warn": Fore.YELLOW,
    "error": Fore.RED,
    "debug": Fore.MAGENTA,
    "step": Fore.BLUE,
}


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _print(level: str, msg: str, account: int | None = None) -> None:
    color = COLOR_MAP.get(level, "")
    tag = level.upper().ljust(7)
    prefix = f"[ACC-{account}] " if account is not None else ""
    line = f"{color}[{_ts()}] [{tag}] {prefix}{msg}{Style.RESET_ALL}"
    print(line)


def info(msg: str, account: int | None = None) -> None:
    _print("info", msg, account)
    _logger.info(f"{'[ACC-' + str(account) + '] ' if account else ''}{msg}")


def success(msg: str, account: int | None = None) -> None:
    _print("success", msg, account)
    _logger.info(f"{'[ACC-' + str(account) + '] ' if account else ''}SUCCESS: {msg}")


def warn(msg: str, account: int | None = None) -> None:
    _print("warn", msg, account)
    _logger.warning(f"{'[ACC-' + str(account) + '] ' if account else ''}{msg}")


def error(msg: str, account: int | None = None) -> None:
    _print("error", msg, account)
    _logger.error(f"{'[ACC-' + str(account) + '] ' if account else ''}{msg}")


def debug(msg: str, account: int | None = None) -> None:
    _print("debug", msg, account)
    _logger.debug(f"{'[ACC-' + str(account) + '] ' if account else ''}{msg}")


def step(msg: str, account: int | None = None) -> None:
    _print("step", msg, account)
    _logger.info(f"{'[ACC-' + str(account) + '] ' if account else ''}STEP: {msg}")


def banner() -> None:
    art = f"""
{Fore.CYAN}{Style.BRIGHT}
 ____              _    __  __       ____  _                 ____        _
| __ )  ___   ___ | | _|  \\/  |_   _/ ___|| |__   _____      | __ )  ___ | |_
|  _ \\ / _ \\ / _ \\| |/ / |\\/| | | | \\___ \\| '_ \\ / _ \\ \\ /\\ / /  _ \\ / _ \\| __|
| |_) | (_) | (_) |   <| |  | | |_| |___) | | | | (_) \\ V  V /| |_) | (_) | |_
|____/ \\___/ \\___/|_|\\_\\_|  |_|\\__, |____/|_| |_|\\___/ \\_/\\_/ |____/ \\___/ \\__|
                                |___/
{Style.RESET_ALL}
{Fore.YELLOW}  Ticket Booking Automation Tool{Style.RESET_ALL}
{Fore.RED}  Use responsibly. Respect platform ToS.{Style.RESET_ALL}
"""
    print(art)
