import logging
import time
from datetime import timedelta, datetime
import psutil
import os
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


config = load_config()
cpu_alert, ram_alert = 90, 90
global_interval = 10
message_to_edit = 0
started = False


def get_server_usage():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    return cpu, ram.percent, round(ram.used / 1e9, 2)


async def monitoring_job(context: ContextTypes.DEFAULT_TYPE):
    global cpu_alert, ram_alert
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()
    await context.bot.edit_message_text(chat_id=context.job.chat_id, message_id=int(context.job.data.message_id), text=f"CPU Usage: {cpu_usage}%\nRAM usage (%): {ram_usage_perc}%"
            f"\nRAM usage (Gb): {ram_usage_gig}")
    alert = []
    if cpu_usage > cpu_alert:
        alert.append(f"CPU usage exceeded {cpu_alert}%")
    if ram_usage_perc > ram_alert:
        alert.append(f"RAM usage exceeded {ram_alert}%")

    if alert:
        await context.bot.send_message(chat_id=context.job.chat_id, text="\n".join(alert))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Старт")],
        [KeyboardButton("Статус")],
        [KeyboardButton("Настройки")]
    ]
    await update.message.reply_text("Привет! Это бот для мониторинга ресурсов сервера\n", reply_markup=ReplyKeyboardMarkup(keyboard))


async def start_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global message_to_edit
    chat_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name("restart_job"):
        job.schedule_removal()

    monitoring_jobs = context.job_queue.get_jobs_by_name("monitoring_job")
    if monitoring_jobs:
        await context.bot.send_message(text="Мониторинг уже запущен", chat_id=chat_id)
        return

    os_name = "Linux" if os.name == "posix" else "Windows"
    server_time = time.ctime()
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()

    await context.bot.send_message(text=f"Server OS: {os_name}\nServer Time: {server_time}\n", chat_id=chat_id)
    message_to_edit = await context.bot.send_message(text=f"CPU Usage: {cpu_usage}%\nRAM usage (%): {ram_usage_perc}%"
            f"\nRAM usage (Gb): {ram_usage_gig}", chat_id=chat_id)

    await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_to_edit.message_id, disable_notification=True)
    context.job_queue.run_repeating(monitoring_job, interval=global_interval, first=3, chat_id=chat_id, data=message_to_edit, name="monitoring_job")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cpu_alert, ram_alert, global_interval
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Error! Не правильная команда.\nВозможно вы иммели ввиду: /setting <интервал(с)> <порог_cpu(%)> <порог_ram(%)>?")
    else:
        global_interval, cpu_alert, ram_alert = int(context.args[0]), int(context.args[1]), int(context.args[2])
        await context.bot.send_message(text=
            f"Настройки обновлены\nИнтервал: {global_interval}с\nCPU: {cpu_alert}%\nRAM: {ram_alert}%", chat_id=chat_id)


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cpu_alert, ram_alert, global_interval
    chat_id = update.effective_chat.id
    await context.bot.send_message(text=
                                   f"Текущие настройки:\n"
                                   f"Интервал: {global_interval} сек\n"
                                   f"Порог CPU: {cpu_alert}%\n"
                                   f"Порог RAM: {ram_alert}%\n\n"
                                   f"Изменить: /settings <интервал(с)> <порог_cpu(%)> <порог_ram(%)>\n"
                                   f"Пример: /settings 10 90 90", chat_id=chat_id
                                   )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_jobs = context.job_queue.get_jobs_by_name("monitoring_job")
    chat_id = update.effective_chat.id
    if not current_jobs:
        await context.bot.send_message(text="Мониторинг не запущен", chat_id=chat_id)
        return
    for job in current_jobs:
        job.schedule_removal()
    await context.bot.send_message(text="Мониторинг остановлен", chat_id=chat_id)
    message = current_jobs[0].data
    await context.bot.unpin_chat_message(chat_id=update.effective_chat.id, message_id=message.id)


async def got_it(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name("monitoring_job")
    if not current_jobs:
        await context.bot.send_message(text="Мониторинг не запущен", chat_id=chat_id)
        return
    for job in current_jobs:
        job.schedule_removal()

    message_restart = await context.bot.send_message(
        text=f"Остановка оповещений на 15 минут\nПродолжение оповещений в {(datetime.now() + timedelta(minutes=15)).strftime('%H:%M:%S')}", chat_id=chat_id)

    context.job_queue.run_once(auto_restart, when=timedelta(minutes=15), chat_id=chat_id, data=message_restart, name="restart_job")


async def auto_restart(context: ContextTypes.DEFAULT_TYPE):
    global message_to_edit
    chat_id = context.job.chat_id
    await context.bot.delete_message(chat_id=chat_id, message_id=int(context.job.data.message_id))
    context.job_queue.run_repeating(monitoring_job, interval=global_interval, first=3, chat_id=chat_id, data=message_to_edit, name="monitoring_job")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    monitoring_jobs = context.job_queue.get_jobs_by_name("monitoring_job")
    chat_id = update.effective_chat.id
    if not monitoring_jobs:
        restart_job = context.job_queue.get_jobs_by_name("restart_job")
        if not restart_job:
            await context.bot.send_message(text="Мониторинг не запущен\nРестарт не производится", chat_id=chat_id)
        else:
            await context.bot.send_message(text="Мониторинг перезапускается", chat_id=chat_id)
    else:
        await context.bot.send_message(text="Мониторинг запущен", chat_id=chat_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global started
    text = update.message.text
    if text == "Старт":
        await start_up(update, context)
        started = True
        await update.message.reply_text(reply_markup=get_keyboard())
    elif text == "Стоп":
        await stop(update, context)
        started = False
        await update.message.reply_text(reply_markup=get_keyboard())
    elif text == "Got it":
        await got_it(update, context)
        started = False
        await update.message.reply_text(reply_markup=get_keyboard())
    elif text == "Статус":
        await status(update, context)
    elif text == "Настройки":
        await show_settings(update, context)
    else:
        await update.message.reply_text("Ты чего понаписал, я не понимаю")


def get_keyboard():
    global started
    if started:
        keyboard = [
            [KeyboardButton("Стоп")],
            [KeyboardButton("Got it"),
            KeyboardButton("Статус")],
            [KeyboardButton("Настройки")]
        ]
    else:
        keyboard = [
            [KeyboardButton("Старт")],
            [KeyboardButton("Статус")],
            [KeyboardButton("Настройки")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def __main__():
    bot_app = Application.builder().token(token=config.tg_token).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("settings", settings))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    bot_app.run_polling()


if __name__ == "__main__":
    __main__()