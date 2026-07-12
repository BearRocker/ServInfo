import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


#dataclass for possible future updates (but I guess it will be more reasonable to do in db)
@dataclass
class Config:
    tg_token: str


def load_config() -> Config:
    return Config(
        tg_token=os.getenv("TG_TOKEN")
    )