#!/usr/bin/env python3
"""
BookMyShow Ticket Booking Bot — CLI Entry Point
"""
import asyncio
import sys
import getpass

from colorama import Fore, Style, init

init(autoreset=True)

from config import BotConfig, cookies_path
from login import run_login, login_multiple_accounts
from booking import run_booking
from updater import check_for_updates
import logger


def prompt_colored(text: str, color: str = Fore.CYAN) -> str:
    return input(f"{color}{text}{Style.RESET_ALL}")


def prompt_secret(text: str) -> str:
    return getpass.getpass(f"{Fore.CYAN}{text}{Style.RESET_ALL}")


def collect_config() -> BotConfig:
    """Interactive CLI to collect user inputs."""
    cfg = BotConfig.load()

    print(f"\n{Fore.YELLOW}{'─' * 55}")
    print(f"{Fore.YELLOW}  Configuration")
    print(f"{Fore.YELLOW}{'─' * 55}\n")

    # Mode
    print(f"{Fore.GREEN}  Select mode:")
    print(f"{Fore.WHITE}    1 = Login mode  (save session cookies)")
    print(f"{Fore.WHITE}    2 = Booking mode (use saved session to book)")
    mode_input = prompt_colored("\n  Mode [1/2]: ").strip()
    cfg.mode = int(mode_input) if mode_input in ("1", "2") else 1

    # Accounts
    acc_input = prompt_colored(f"  Number of accounts [{cfg.num_accounts}]: ").strip()
    if acc_input:
        cfg.num_accounts = max(1, int(acc_input))

    if cfg.mode == 2:
        # --- Event URL ---
        url_input = prompt_colored(f"  Event URL [{cfg.event_url or 'required'}]: ").strip()
        if url_input:
            cfg.event_url = url_input
        elif not cfg.event_url:
            logger.error("Event URL is required.")
            sys.exit(1)

        # --- Target prices ---
        current_prices = ",".join(str(p) for p in cfg.target_prices) if cfg.target_prices else "e.g. 1250,1000,2000"
        prices_input = prompt_colored(
            f"  Target prices (priority order) [{current_prices}]: "
        ).strip()
        if prices_input:
            cfg.target_prices = [int(float(p.strip())) for p in prices_input.split(",") if p.strip()]
        if not cfg.target_prices:
            logger.error("At least one target price is required.")
            sys.exit(1)

        # --- Preferred stands (optional) ---
        current_stands = ", ".join(cfg.preferred_stands) if cfg.preferred_stands else "optional, e.g. SBI Life Lower 4, Jio Lower 7"
        stands_input = prompt_colored(
            f"  Preferred stands [{current_stands}]: "
        ).strip()
        if stands_input:
            cfg.preferred_stands = [s.strip() for s in stands_input.split(",") if s.strip()]

        # --- Seats ---
        seats_input = prompt_colored(f"  Number of seats (max 10) [{cfg.num_seats}]: ").strip()
        if seats_input:
            cfg.num_seats = min(10, max(1, int(seats_input)))

        # --- Email ---
        email_input = prompt_colored(f"  Email [{cfg.email or 'e.g. name@gmail.com'}]: ").strip()
        if email_input:
            cfg.email = email_input

        # --- Phone ---
        phone_input = prompt_colored(f"  Phone [{cfg.phone or 'e.g. 9876543210'}]: ").strip()
        if phone_input:
            cfg.phone = phone_input

        # --- UPI ---
        upi_input = prompt_colored(f"  UPI ID [{cfg.upi_id or 'e.g. name@upi'}]: ").strip()
        if upi_input:
            cfg.upi_id = upi_input

        # --- PIN ---
        pin_input = prompt_secret("  Payment PIN (not saved to disk): ")
        if pin_input:
            cfg.payment_pin = pin_input

        # --- Proxy ---
        proxy_input = prompt_colored(f"  Proxy [{cfg.proxy or 'none'}]: ").strip()
        if proxy_input:
            cfg.proxy = proxy_input

    # Validate cookies
    if cfg.mode == 2:
        missing = []
        for i in range(cfg.num_accounts):
            if not cookies_path(i).exists():
                missing.append(cookies_path(i).name)
        if missing:
            logger.warn(f"Missing session files: {', '.join(missing)}")
            logger.warn("Run Login mode first to create them.")
            proceed = prompt_colored("  Continue anyway? [y/N]: ").strip().lower()
            if proceed != "y":
                sys.exit(0)

    # Save (PIN excluded)
    cfg.save()
    logger.success("Config saved to config.json (PIN excluded)")

    return cfg


async def main() -> None:
    logger.banner()
    await check_for_updates()

    cfg = collect_config()

    print(f"\n{Fore.YELLOW}{'─' * 55}")
    print(f"{Fore.YELLOW}  Summary")
    print(f"{Fore.YELLOW}{'─' * 55}")
    print(f"{Fore.WHITE}  Mode:       {'Login' if cfg.mode == 1 else 'Booking'}")
    print(f"{Fore.WHITE}  Accounts:   {cfg.num_accounts}")
    if cfg.mode == 2:
        print(f"{Fore.WHITE}  Event:      {cfg.event_url}")
        print(f"{Fore.WHITE}  Prices:     {cfg.target_prices}")
        if cfg.preferred_stands:
            print(f"{Fore.WHITE}  Stands:     {cfg.preferred_stands}")
        print(f"{Fore.WHITE}  Seats:      {cfg.num_seats}")
        print(f"{Fore.WHITE}  Email:      {cfg.email}")
        print(f"{Fore.WHITE}  Phone:      {cfg.phone}")
        print(f"{Fore.WHITE}  UPI:        {cfg.upi_id}")
        print(f"{Fore.WHITE}  Proxy:      {cfg.proxy or 'none'}")
    print()

    confirm = prompt_colored("  Start? [Y/n]: ").strip().lower()
    if confirm == "n":
        logger.info("Aborted.")
        return

    if cfg.mode == 1:
        if cfg.num_accounts > 1:
            await login_multiple_accounts(cfg)
        else:
            await run_login(cfg, 0)
    else:
        await run_booking(cfg)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warn("\nInterrupted by user.")
        sys.exit(0)
