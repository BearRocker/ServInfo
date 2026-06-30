import os
from dataclasses import dataclass
from dotenv import load_dotenv

FETCH_INTERVAL_MINUTES = 5
load_dotenv()

@dataclass
class Config:
    tg_token: str


def load_config() -> Config:
    return Config(
        tg_token=os.getenv("TG_TOKEN")
    )