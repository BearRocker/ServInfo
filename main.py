import asyncio
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta

import psutil
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from config import load_config, create_user, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
config = load_config()

USERS_FILE = os.path.join(config.data_dir, "users.json")
APPROVED_FILE = os.path.join(config.data_dir, "approved_ids.json")

LANGUAGE = {
    "RUS": {"start": "Привет! Это бот для мониторинга ресурсов сервера.\n",
            "stop": "Мониторинг остановлен",
            "off": "Мониторинг не запущен",
            "status_off": "Мониторинг не запущен\nРестарт не производится",
            "already_started": "Мониторинг уже запущен",
            "monitoring": "Мониторинг запущен",
            "pause": "Остановка оповещений на {time_for_restart} минут\nПродолжение оповещений в {resume_time}",
            "restart": "Мониторинг перезапускается",
            "CPU_LIMIT": "Процессор загружен больше, чем на {cpu_alert}%",
            "RAM_LIMIT": "Оперативная память загружена более, чем на {ram_alert}%",
            "wrong_settings": "Не правильная команда.\nВозможно вы имели ввиду: /settings <интервал(с)> <порог_cpu(%)> <порог_ram(%)> [пауза(мин)]?\n Пауза не обязательна, принимаемые значения от 1 до 30 минут",
            "settings_updated": "Настройки обновлены\nИнтервал: {global_interval}с\nCPU: {cpu_alert}%\nRAM: {ram_alert}%\nПауза: {time_for_restart} мин",
            "start_btn": "Старт",
            "status_btn": "Статус",
            "settings_btn": "Настройки",
            "stop_btn": "Стоп",
            "time_stop_btn": "Стоп {time_for_restart} минут",
            "admin_btn": "Добавить пользователя",
            "starting": "Стартую мониторинг...",
            "stopping": "Останавливаю мониторинг...",
            "timeout": "Останавливаю на время",
            "settings_msg": "Текущие настройки:\n"
                            "Интервал: {global_interval} сек\n"
                            "Порог CPU: {cpu_alert}%\n"
                            "Порог RAM: {ram_alert}%\n"
                            "Пауза: {time_for_restart} мин\n\n"
                            "Изменить: /settings <интервал(с)> <порог_cpu(%)> <порог_ram(%)> [пауза(мин)]\n"
                            "Пример: /settings 10 90 90 15",
            "admin_msg": "Введите id пользователя, которому вы хотите дать доступ",
            "can't_understand": "Ты чего понаписал я не понимаю",
            "successfully_added": "Пользователь с ID: {id} успешно добавлен",
            "invalid_id": "Проблема с id пользователя"
            },
    "ENG": {"start": "Hi! This is simple bot for monitoring server resources.\n",
            "stop": "Stopping monitoring",
            "off": "Monitoring is off",
            "status_off": "Monitoring is off\nRestart is not planned",
            "already_started": "Monitoring has already started",
            "monitoring": "Monitoring is on",
            "pause": "Stopping notifications for {time_for_restart} minutes\nNotifications will continue sending after {resume_time}",
            "restart": "Monitoring is restarting",
            "CPU_LIMIT": "CPU usage over {cpu_alert}%",
            "RAM_LIMIT": "RAM usage over {ram_alert}%",
            "wrong_settings": "Wrong command.\nMaybe you mean: /settings <interval(sec)> <cpu_limit(%)> <ram_limit(%)> [pause(min)]? Pause is optional, from 1 to 30 minutes.\n",
            "settings_updated": "Settings updated\nInterval: {global_interval} seconds\nCPU: {cpu_alert}%\nRAM: {ram_alert}%\nPause: {time_for_restart} min",
            "start_btn": "Start",
            "status_btn": "Status",
            "settings_btn": "Settings",
            "stop_btn": "Stop",
            "time_stop_btn": "Stop {time_for_restart} minutes",
            "admin_btn": "Add user",
            "starting": "Starting monitoring...",
            "stopping": "Stopping monitoring...",
            "timeout": "Stopping monitoring for sometime",
            "settings_msg": "Current settings:\n"
                            "Interval: {global_interval} seconds\n"
                            "CPU usage limit: {cpu_alert}%\n"
                            "RAM usage limit: {ram_alert}%\n"
                            "Pause: {time_for_restart} min\n\n"
                            "Change: /settings <interval(seconds)> <cpu_limit(%)> <ram_limit(%)> [pause(min)]\n"
                            "Example: /settings 10 90 90 15",
            "admin_msg": "Enter user id to give him permission",
            "can't_understand": "There's no such command!",
            "successfully_added": "User with {id} has been added",
            "invalid_id": "There's a problem with id"
            }
}

BUTTONS = ("start_btn", "stop_btn", "time_stop_btn", "status_btn", "settings_btn", "admin_btn")
DEFAULT_USER = create_user(0, 90, 90, 15, 10, 0, "eng", False)
PAUSE_MIN, PAUSE_MAX = 1, 30
users: dict[int, User] = {}
approved_ids: list[int] = [config.admin_id]


def get_language_text(chat_id: int, shortcut: str, **extra):
    user = users.get(chat_id) or DEFAULT_USER
    language = "RUS" if user.language == "rus" else "ENG"
    values = dict(time_for_restart=user.time_for_restart, cpu_alert=user.cpu_alert, ram_alert=user.ram_alert,
                  global_interval=user.interval, id=approved_ids[-1])
    values.update(extra)
    return LANGUAGE[language][shortcut].format(**values)


def is_approved(update: Update):
    return update.effective_user.id in approved_ids


def get_jobs(context: ContextTypes.DEFAULT_TYPE, kind: str, chat_id: int):
    return context.job_queue.get_jobs_by_name(f"{kind}_{chat_id}")


def start_monitoring_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    context.job_queue.run_repeating(monitoring_job, interval=users[chat_id].interval, first=3,
                                    chat_id=chat_id, name=f"monitoring_{chat_id}")


def get_server_usage():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    return cpu, ram.percent, round(ram.used / 1e9, 2)


def usage_text(cpu_usage, ram_usage_perc, ram_usage_gig):
    return f"CPU: {cpu_usage}%\nRAM (%): {ram_usage_perc}%\nRAM (GB): {ram_usage_gig}"


def save_data():
    with open(USERS_FILE, "w", encoding="utf-8") as save_file:
        json.dump({str(chat_id): asdict(user) for chat_id, user in users.items()}, save_file, indent=4)
    with open(APPROVED_FILE, "w", encoding="utf-8") as save_file:
        json.dump(approved_ids, save_file, indent=4)


def load_data():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as save_file:
            users.update({int(chat_id): User(**data) for chat_id, data in json.load(save_file).items()})
    except FileNotFoundError:
        pass
    try:
        with open(APPROVED_FILE, "r", encoding="utf-8") as save_file:
            approved_ids[:] = [int(user_id) for user_id in json.load(save_file)]
    except FileNotFoundError:
        pass
    if config.admin_id not in approved_ids:
        approved_ids.append(config.admin_id)
    # Monitoring jobs live in memory only, so after a restart nothing is running
    for user in users.values():
        user.started = False


async def auto_save(context: ContextTypes.DEFAULT_TYPE):
    save_data()


async def add_approved_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    context.user_data["waiting_message"] = True
    await update.message.reply_text(text=get_language_text(chat_id, "admin_msg"))


async def monitoring_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    user = users.get(chat_id)
    if user is None:
        context.job.schedule_removal()
        return
    cpu_usage, ram_usage_perc, ram_usage_gig = await asyncio.to_thread(get_server_usage)
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=user.message_to_edit,
                                            text=usage_text(cpu_usage, ram_usage_perc, ram_usage_gig))
    except BadRequest as error:
        if "not modified" not in str(error).lower():
            logger.warning("Can't edit usage message for %s: %s", chat_id, error)
    alert = []
    if cpu_usage > user.cpu_alert:
        alert.append(get_language_text(chat_id, "CPU_LIMIT"))
    if ram_usage_perc > user.ram_alert:
        alert.append(get_language_text(chat_id, "RAM_LIMIT"))
    if alert:
        await context.bot.send_message(chat_id=chat_id, text="\n".join(alert))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_approved(update):
        keyboard = [
            [InlineKeyboardButton("RUS", callback_data="RUS")],
            [InlineKeyboardButton("ENG", callback_data="ENG")],
        ]
        await update.message.reply_text("RUS: Привет! Это бот для мониторинга ресурсов сервера.\n"
                                        "Для начала использования выбери язык.\n"
                                        "ENG: Hi! This is simple bot for monitoring server resources.\n"
                                        "To start using bot you need to choose language.\n", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("RUS: Извини, но тебе не выдали сюда доступ, ты знаешь кому обратиться\n"
                                        "ENG: Sorry but you didn't get access you know who you need to message")


async def start_after_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "start"), reply_markup=get_keyboard(chat_id))


async def start_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    for job in get_jobs(context, "restart", chat_id):
        job.schedule_removal()
    if get_jobs(context, "monitoring", chat_id):
        await context.bot.send_message(text=get_language_text(chat_id, "already_started"), chat_id=chat_id)
        return
    os_name = "Linux" if os.name == "posix" else "Windows"
    server_time = time.ctime()
    cpu_usage, ram_usage_perc, ram_usage_gig = await asyncio.to_thread(get_server_usage)
    await context.bot.send_message(text=f"Server OS: {os_name}\nServer Time: {server_time}\n", chat_id=chat_id)
    message_to_edit = await context.bot.send_message(text=usage_text(cpu_usage, ram_usage_perc, ram_usage_gig), chat_id=chat_id)
    users[chat_id].message_to_edit = message_to_edit.message_id
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_to_edit.message_id, disable_notification=True)
    start_monitoring_job(context, chat_id)
    save_data()


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if not is_approved(update) or chat_id not in users:
        return
    try:
        values = [int(arg) for arg in context.args]
        interval, cpu_alert, ram_alert = values[0], values[1], values[2]
        pause_ok = len(values) == 3 or (len(values) == 4 and PAUSE_MIN <= values[3] <= PAUSE_MAX)
    except ValueError:
        await update.message.reply_text(get_language_text(chat_id, "wrong_settings"))
        return
    except IndexError:
        await update.message.reply_text(get_language_text(chat_id, "wrong_settings"))
        return
    if interval < 1 or not 0 < cpu_alert <= 100 or not 0 < ram_alert <= 100:
        await update.message.reply_text(get_language_text(chat_id, "wrong_settings"))
        return
    if not pause_ok:
        await update.message.reply_text(get_language_text(chat_id, "wrong_settings"))
        return
    user = users[chat_id]
    user.interval, user.cpu_alert, user.ram_alert = interval, cpu_alert, ram_alert
    if len(values) == 4:
        user.time_for_restart = values[3]
    # Apply the new interval to a running monitoring job
    running_jobs = get_jobs(context, "monitoring", chat_id)
    if running_jobs:
        for job in running_jobs:
            job.schedule_removal()
        start_monitoring_job(context, chat_id)
    await context.bot.send_message(text=get_language_text(chat_id, "settings_updated"), chat_id=chat_id)
    save_data()


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    await context.bot.send_message(text=get_language_text(chat_id, "settings_msg"), chat_id=chat_id)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    current_jobs = get_jobs(context, "monitoring", chat_id) + get_jobs(context, "restart", chat_id)
    if not current_jobs:
        await context.bot.send_message(text=get_language_text(chat_id, "off"), chat_id=chat_id)
        return
    for job in current_jobs:
        job.schedule_removal()
    await context.bot.send_message(text=get_language_text(chat_id, "stop"), chat_id=chat_id)
    try:
        await context.bot.unpin_chat_message(chat_id=chat_id, message_id=users[chat_id].message_to_edit)
    except BadRequest as error:
        logger.warning("Can't unpin message for %s: %s", chat_id, error)


async def got_it(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    current_jobs = get_jobs(context, "monitoring", chat_id)
    if not current_jobs:
        await context.bot.send_message(text=get_language_text(chat_id, "off"), chat_id=chat_id)
        return
    for job in current_jobs:
        job.schedule_removal()
    pause = timedelta(minutes=users[chat_id].time_for_restart)
    resume_time = (datetime.now() + pause).strftime("%H:%M:%S")
    message_restart = await context.bot.send_message(text=get_language_text(chat_id, "pause", resume_time=resume_time), chat_id=chat_id)
    context.job_queue.run_once(auto_restart, when=pause, chat_id=chat_id, data=message_restart.message_id, name=f"restart_{chat_id}")


async def auto_restart(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    if chat_id not in users:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=context.job.data)
    except BadRequest as error:
        logger.warning("Can't delete pause message for %s: %s", chat_id, error)
    users[chat_id].started = True
    start_monitoring_job(context, chat_id)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if get_jobs(context, "monitoring", chat_id):
        await context.bot.send_message(text=get_language_text(chat_id, "monitoring"), chat_id=chat_id)
    elif get_jobs(context, "restart", chat_id):
        await context.bot.send_message(text=get_language_text(chat_id, "restart"), chat_id=chat_id)
    else:
        await context.bot.send_message(text=get_language_text(chat_id, "status_off"), chat_id=chat_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_user.id
    if chat_id not in users or not is_approved(update):
        return
    is_admin = chat_id == config.admin_id
    button = next((key for key in BUTTONS if text == get_language_text(chat_id, key)), None)

    if button == "start_btn":
        users[chat_id].started = True
        await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "starting"), reply_markup=get_keyboard(chat_id))
        await start_up(update, context)
    elif button == "stop_btn":
        users[chat_id].started = False
        await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "stopping"), reply_markup=get_keyboard(chat_id))
        await stop(update, context)
    elif button == "time_stop_btn":
        users[chat_id].started = False
        await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "timeout"), reply_markup=get_keyboard(chat_id))
        await got_it(update, context)
    elif button == "status_btn":
        await status(update, context)
    elif button == "settings_btn":
        await show_settings(update, context)
    elif button == "admin_btn" and is_admin:
        await add_approved_users(update, context)
    elif is_admin and context.user_data.get("waiting_message"):
        context.user_data["waiting_message"] = False
        try:
            new_id = int(text)
        except ValueError:
            await update.message.reply_text(get_language_text(chat_id, "invalid_id"))
            return
        if new_id not in approved_ids:
            approved_ids.append(new_id)
            save_data()
        await update.message.reply_text(get_language_text(chat_id, "successfully_added", id=new_id))
    else:
        await update.message.reply_text(get_language_text(chat_id, "can't_understand"))


def get_keyboard(chat_id: int):
    if users[chat_id].started:
        keyboard = [
            [KeyboardButton(get_language_text(chat_id, "stop_btn"))],
            [KeyboardButton(get_language_text(chat_id, "time_stop_btn")),
             KeyboardButton(get_language_text(chat_id, "status_btn"))],
            [KeyboardButton(get_language_text(chat_id, "settings_btn"))],
        ]
    else:
        keyboard = [
            [KeyboardButton(get_language_text(chat_id, "start_btn"))],
            [KeyboardButton(get_language_text(chat_id, "status_btn"))],
            [KeyboardButton(get_language_text(chat_id, "settings_btn"))],
        ]
    if chat_id == config.admin_id:
        keyboard.append([KeyboardButton(get_language_text(chat_id, "admin_btn"))])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_user.id
    if not is_approved(update) or query.data not in ("RUS", "ENG"):
        return
    language = query.data.lower()
    if chat_id in users:
        users[chat_id].language = language
    else:
        users[chat_id] = create_user(chat_id, 90, 90, 15, 10, 0, language, False)
    save_data()
    await start_after_language(update, context)


def main():
    os.makedirs(config.data_dir, exist_ok=True)
    load_data()
    bot_app = Application.builder().token(token=config.tg_token).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("settings", settings))
    bot_app.add_handler(CallbackQueryHandler(handle_callback))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.job_queue.run_repeating(auto_save, interval=config.auto_save, first=config.auto_save, name="auto_save")
    bot_app.run_polling()


if __name__ == "__main__":
    main()
