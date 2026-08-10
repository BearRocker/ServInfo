import json
import logging
import time
from datetime import timedelta
import psutil
import os
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, \
    CallbackContext
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from config import load_config, create_user, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

config = load_config()

LANGUAGE = {
    "RUS": {"start": "Привет! Это бот для мониторинга ресурсов сервера.\n",
            "stop": "Мониторинг остановлен",
            "off": "Мониторинг не запущен",
            "status_off": "Мониторинг не запущен\nРестарт не производится",
            "already_started": "Мониторинг уже запущен",
            "monitoring": "Мониторинг запущен",
            "pause": "Остановка оповещений на {time_for_restart} минут\nПродолжение оповещений в {(datetime.now() + timedelta(minutes=time_for_restart)).strftime('%H:%M:%S')}",
            "restart": "Мониторинг перезапускается",
            "CPU_LIMIT": "Процессор загружен больше, чем на {cpu_alert}%",
            "RAM_LIMIT": "Оперативная память загружена более, чем на {ram_alert}%",
            "wrong_settings": "Не правильная команда.\nВозможно вы имели ввиду: /setting <интервал(с)> <порог_cpu(%)> <порог_ram(%)>?",
            "settings_updated": "Настройки обновлены\nИнтервал: {global_interval}с\nCPU: {cpu_alert}%\nRAM: {ram_alert}%",
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
                            "Порог RAM: {ram_alert}%\n\n"
                            "Изменить: /settings <интервал(с)> <порог_cpu(%)> <порог_ram(%)>\n"
                            "Пример: /settings 10 90 90",
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
            "pause": "Stopping notifications for {time_for_restart} minutes\nNotifications will continue sending after {(datetime.now() + timedelta(minutes=time_for_restart)).strftime('%H:%M:%S')}",
            "restart": "Monitoring is restarting",
            "CPU_LIMIT": "CPU usage over {cpu_alert}%",
            "RAM_LIMIT": "RAM usage over {ram_alert}%",
            "wrong_settings": "Wrong command.\nMaybe you mean: /setting <interval(sec)> <cpu_limit(%)> <ram_limit(%)>?",
            "settings_updated": "Settings updated\nInterval: {global_interval} seconds\nCPU: {cpu_alert}%\nRAM: {ram_alert}%",
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
                            "RAM usage limit: {ram_alert}%\n\n"
                            "Change: /settings <interval(seconds)> <cpu_limit(%)> <ram_limit(%)>\n"
                            "Example: /settings 10 90 90",
            "admin_msg": "Enter user id to give him permission",
            "can't_understand": "There's no such command!",
            "successfully_added": "User with {id} has been added",
            "invalid_id": "There's a problem with id"
            }
}

users = {}
approved_ids = [config.admin_id]


def get_language_text(id:int, shortcut: str) -> str:
    user = users.get(id)
    user_language = user.language if user else None
    if user_language == "rus":
        return LANGUAGE["RUS"][shortcut].format(time_for_restart=user.time_for_restart, cpu_alert=user.cpu_alert, ram_alert=user.ram_alert, global_interval=user.interval, id=approved_ids[-1])
    else:
        return LANGUAGE["ENG"][shortcut].format(time_for_restart=user.time_for_restart, cpu_alert=user.cpu_alert, ram_alert=user.ram_alert, global_interval=user.interval, id=approved_ids[-1])


def get_server_usage():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    return cpu, ram.percent, round(ram.used / 1e9, 2)


async def add_approved_users(update: Update, context: CallbackContext):
    chat_id = update.effective_user.id
    context.user_data["waiting_message"] = True
    await update.message.reply_text(text=get_language_text(chat_id, "admin_msg"))


async def monitoring_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()
    await context.bot.edit_message_text(chat_id=context.job.chat_id, message_id=int(context.job.data.message_id),
                                        text=f"CPU: {cpu_usage}%\nRAM (%): {ram_usage_perc}%\nRAM (GB): {ram_usage_gig}")
    alert = []
    if cpu_usage > users.get(chat_id).cpu_alert:
        alert.append(get_language_text(chat_id, "CPU_LIMIT"))
    if ram_usage_perc > users.get(chat_id).ram_alert:
        alert.append(get_language_text(chat_id, "RAM_LIMIT"))

    if alert:
        await context.bot.send_message(chat_id=chat_id, text="\n".join(alert))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in approved_ids:
        keyboard = [
            [InlineKeyboardButton("RUS", callback_data="RUS")],
            [InlineKeyboardButton("ENG", callback_data="ENG")],
        ]
        if not(context.job_queue.get_jobs_by_name("auto_save")):
            context.job_queue.run_repeating(auto_save, interval=config.auto_save, first=3, chat_id=update.effective_user.id, name="auto_save")
        await update.message.reply_text("RUS: Привет! Это бот для мониторинга ресурсов сервера.\n"
                                            "Для начала использования выбери язык.\n"
                                            "ENG: Hi! This is simple bot for monitoring server resources.\n"
                                            "To start using bot you need to choose language.\n", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("RUS: Извини, но тебе не выдали сюда доступ, ты знаешь кому обратиться\n"
                                        "ENG: Sorry but you didn't get access you know who you need to message")

async def start_after_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    keyboard = [
        [KeyboardButton(get_language_text(chat_id,"start_btn"))],
        [KeyboardButton(get_language_text(chat_id,"status_btn"))],
        [KeyboardButton(get_language_text(chat_id, "settings_btn"))],
        [KeyboardButton(get_language_text(chat_id, "admin_btn"))] if chat_id == config.admin_id else [],
    ]
    await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "start"), reply_markup=ReplyKeyboardMarkup(keyboard))

async def start_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    for job in context.chat_data.get("restart_job"):
        job.schedule_removal()

    monitoring_jobs = context.chat_data.get("monitoring_job") # Check logic for multi users
    if monitoring_jobs:
        await context.bot.send_message(text=get_language_text(chat_id, "already_started"), chat_id=chat_id)
        return

    os_name = "Linux" if os.name == "posix" else "Windows"
    server_time = time.ctime()
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()

    await context.bot.send_message(text=f"Server OS: {os_name}\nServer Time: {server_time}\n", chat_id=chat_id)
    message_to_edit = await context.bot.send_message(text=f"CPU: {cpu_usage}%\nRAM (%): {ram_usage_perc}%"
            f"\nRAM (Gb): {ram_usage_gig}", chat_id=chat_id)
    users.get(chat_id).message = message_to_edit
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_to_edit.message_id, disable_notification=True)
    context.job_queue.run_repeating(monitoring_job, interval=users.get(chat_id).interval, first=3, chat_id=chat_id, data=message_to_edit, name="monitoring_job")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(get_language_text(chat_id, "wrong_settings"))
    else:
        users.get(chat_id).interval, users.get(chat_id).cpu_alert, users.get(chat_id).ram_alert = int(context.args[0]), int(context.args[1]), int(context.args[2])
        await context.bot.send_message(text=get_language_text(chat_id, "settings_updated"), chat_id=chat_id)
        await auto_save(context)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    await context.bot.send_message(text=get_language_text(chat_id, "settings_msg"), chat_id=chat_id)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_jobs = context.chat_data.get("monitoring_job")
    chat_id = update.effective_user.id
    if not current_jobs:
        await context.bot.send_message(text=get_language_text(chat_id, "off"), chat_id=chat_id)
        return
    current_jobs.schedule_removal()
    await context.bot.send_message(text=get_language_text(chat_id, "stop"), chat_id=chat_id)
    message = current_jobs[0].data
    await context.bot.unpin_chat_message(chat_id=update.effective_user.id, message_id=message.id)


async def got_it(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    current_jobs = context.chat_data.get("monitoring_job")
    if not current_jobs:
        await context.bot.send_message(text=get_language_text(chat_id, "off"), chat_id=chat_id)
        return
    current_jobs.schedule_removal()

    message_restart = await context.bot.send_message(text=get_language_text(chat_id, "pause"), chat_id=chat_id)

    context.job_queue.run_once(auto_restart, when=timedelta(minutes=15), chat_id=chat_id, data=message_restart, name="restart_job")


async def auto_restart(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    await context.bot.delete_message(chat_id=chat_id, message_id=int(context.job.data.message_id))
    context.job_queue.run_repeating(monitoring_job, interval=users.get(chat_id).interval, first=3, chat_id=chat_id, data=users.get(chat_id).message, name="monitoring_job")


async def auto_save(context: ContextTypes.DEFAULT_TYPE):
    with open("users.json", "w") as save_file:
        json.dump(users, save_file, indent=4)
    with open("approved_ids.json", "w") as save_file:
        json.dump(approved_ids, save_file, indent=4)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    monitoring_jobs = context.chat_data.get("monitoring_job")
    chat_id = update.effective_user.id
    if not monitoring_jobs:
        restart_job = context.chat_data.get("restart_job")
        if not restart_job:
            await context.bot.send_message(text=get_language_text(chat_id, "status_off"), chat_id=chat_id)
        else:
            await context.bot.send_message(text=get_language_text(chat_id, "restart"), chat_id=chat_id)
    else:
        await context.bot.send_message(text=get_language_text(chat_id, "monitoring"), chat_id=chat_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_user.id
    if chat_id in users:
        if text == "Старт" or text == "Start":
            users.get(chat_id).started = True
            await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "starting"), reply_markup=get_keyboard(update.effective_user.id))
            await start_up(update, context)
        elif text == "Стоп" or text == "Stop":
            users.get(chat_id).started = False
            await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "stopping"), reply_markup=get_keyboard(update.effective_user.id))
            await stop(update, context)
        elif text == "Стоп 15 минут" or text == "Stop 15 minutes":
            users.get(chat_id).started = False
            await context.bot.send_message(chat_id=chat_id, text=get_language_text(chat_id, "timeout"), reply_markup=get_keyboard(update.effective_user.id))
            await got_it(update, context)
        elif text == "Статус" or text == "Status":
            await status(update, context)
        elif text == "Настройки" or text == "Settings":
            await show_settings(update, context)
        elif (text == "Добавить пользователя" or text == "Add user") and update.effective_user.id == config.admin_id:
            await add_approved_users(update, context)
        elif update.effective_user.id == config.admin_id and context.user_data.get("waiting_message"):
            context.user_data["waiting_message"] = False
            try:
                approved_ids.append(int(text))
                await update.message.reply_text(get_language_text(chat_id, "successfully_added"))
            except ValueError:
                await update.message.reply_text(get_language_text(chat_id, "invalid_id"))
        else:
            await update.message.reply_text(get_language_text(chat_id, "can't_understand"))


def get_keyboard(chat_id: int):
    if users.get(chat_id).started:
        keyboard = [
            [KeyboardButton(get_language_text(chat_id, "stop_btn"))],
            [KeyboardButton(get_language_text(chat_id, "time_stop_btn")),
            KeyboardButton(get_language_text(chat_id, "status_btn"))],
            [KeyboardButton(get_language_text(chat_id, "settings_btn"))],
            [KeyboardButton(get_language_text(chat_id, "admin_btn"))] if chat_id == config.admin_id else [],
        ]
    else:
        keyboard = [
            [KeyboardButton(get_language_text(chat_id, "start_btn"))],
            [KeyboardButton(get_language_text(chat_id, "status_btn"))],
            [KeyboardButton(get_language_text(chat_id, "settings_btn"))],
            [KeyboardButton(get_language_text(chat_id, "admin_btn"))] if chat_id == config.admin_id else [],
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "RUS" and update.effective_user.id not in users:
        new_user = create_user(update.effective_user.id, 90, 90, 15, 10, 0, "rus", False)
        users[update.effective_user.id] = new_user
        await start_after_language(update, context)
    elif query.data == "ENG" and update.effective_user.id not in users:
        new_user = create_user(update.effective_user.id, 90, 90, 15, 10, 0, "eng", False)
        users[update.effective_user.id] = new_user
        await start_after_language(update, context)


def load_save_files():
    global users, approved_ids
    try:
        with open("users.json", "r") as save_file:
            users = json.load(save_file)
        with open("approved_ids.json", "r") as save_file:
            approved_ids = json.load(save_file)
    except FileNotFoundError:
        pass

def __main__():
    bot_app = Application.builder().token(token=config.tg_token).build()

    load_save_files()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("settings", settings))
    bot_app.add_handler(CallbackQueryHandler(handle_callback))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    bot_app.run_polling()


if __name__ == "__main__":
    __main__()