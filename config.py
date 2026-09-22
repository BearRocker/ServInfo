import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


#dataclass for possible future updates (but I guess it will be more reasonable to do in db)
@dataclass
class Config:
    tg_token: str
    admin_id: int
    auto_save: int
    data_dir: str


@dataclass
class User:
    chat_id: int
    cpu_alert: int
    ram_alert: int
    time_for_restart: int
    interval: int
    message_to_edit: int
    language: str
    started: bool


def load_config():
    missing = [name for name in ("TG_TOKEN", "ADMIN_ID", "AUTO_SAVE") if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    return Config(
        tg_token=os.getenv("TG_TOKEN"),
        admin_id=int(os.getenv("ADMIN_ID")),
        auto_save=int(os.getenv("AUTO_SAVE")),
        data_dir=os.getenv("DATA_DIR", "."),
    )


def create_user(id: int, cpu: int, ram: int, restart_time: int, interval: int, message_id: int, language: str, started: bool):
    return User(
        chat_id=id,
        cpu_alert=cpu,
        ram_alert=ram,
        time_for_restart=restart_time,
        interval=interval,
        message_to_edit=message_id,
        language=language,
        started=started
    )
