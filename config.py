import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


#dataclass for possible future updates (but I guess it will be more reasonable to do in db)
@dataclass
class Config:
    tg_token: str
    admin_id: int


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


def load_config() -> Config:
    return Config(
        tg_token=os.getenv("TG_TOKEN"),
        admin_id=int(os.getenv("ADMIN_ID")),
    )

def create_user(id: int, cpu: int, ram: int, restart_time: int, interval: int, message_id: int, language:str, started:bool) -> User:
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