import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


@dataclass
class BotConfig:
    email: str = ""
    phone: str = ""
    upi_id: str = ""
    payment_pin: str = ""
    event_url: str = ""
    target_prices: list[int] = field(default_factory=list)  # e.g. [1250, 1000, 2000]
    preferred_stands: list[str] = field(default_factory=list)  # e.g. ["SBI Life Lower 4", "Jio Lower 7"]
    num_accounts: int = 1
    num_seats: int = 10  # default to max (10)
    mode: int = 1  # 1=login, 2=booking
    proxy: str = ""  # e.g. http://user:pass@host:port
    headless: bool = False
    retry_interval: float = 0.5  # seconds between availability checks
    max_retries: int = 600  # ~5 minutes at 0.5s interval

    def save(self) -> None:
        safe = asdict(self)
        safe.pop("payment_pin", None)  # never persist PIN
        CONFIG_PATH.write_text(json.dumps(safe, indent=2))

    @classmethod
    def load(cls) -> "BotConfig":
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            data.pop("payment_pin", None)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()


def cookies_path(account_index: int) -> Path:
    if account_index == 0:
        return Path(__file__).parent / "cookies.json"
    return Path(__file__).parent / f"cookies_{account_index + 1}.json"
