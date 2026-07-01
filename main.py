# Idea to do: Server/PC resource check with tg possible idea connect wia ssh and get the info from that if tg is not possible on server
# What to do up a local server (container obviously) or connect via ssh and use psutil for interface tg or web depends on what to use
import asyncio
import logging
import time
from datetime import timedelta, datetime

import psutil
import os
from telegram.ext import Application, CommandHandler, ContextTypes, ApplicationBuilder
from telegram import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import load_config


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


config = load_config()
cpu_alert, ram_alert = 90, 90
global_interval = 10
message_to_edit = 0

def get_server_usage():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    return cpu, ram.percent, round(ram.used / 1e9, 2)


async def monitoring_job(context: ContextTypes.DEFAULT_TYPE):
    global cpu_alert, ram_alert
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()
    await context.bot.edit_message_text(chat_id=context.job.chat_id, message_id=int(context.job.data.id), text=f"CPU Usage: {cpu_usage}%\nRAM usage (%): {ram_usage_perc}%"
            f"\nRAM usage (Gb): {ram_usage_gig}")
    alert = []
    if cpu_usage > cpu_alert:
        alert.append(f"CPU usage exceeded {cpu_alert}%")
    if ram_usage_perc > ram_alert:
        alert.append(f"RAM usage exceeded {ram_alert}%")

    if alert:
        await context.bot.send_message(chat_id=context.job.chat_id, text="\n".join(alert))


async def start_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global message_to_edit
    os_name = "Linux" if os.name == "posix" else "Windows"
    server_time = time.ctime()
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()
    await update.message.reply_text(f"Server OS: {os_name}\nServer Time: {server_time}\n")
    message_to_edit = await update.message.reply_text(f"CPU Usage: {cpu_usage}%\nRAM usage (%): {ram_usage_perc}%"
            f"\nRAM usage (Gb): {ram_usage_gig}")
    await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=message_to_edit.message_id, disable_notification=True)
    context.job_queue.run_repeating(monitoring_job, interval=global_interval, first=3, chat_id=update.effective_chat.id, data=message_to_edit, name="monitoring_job")

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cpu_alert, ram_alert, global_interval
    if not context.args:
        await update.message.reply_text(
            f"Текущие настройки:\n"
            f"Интервал: {global_interval} сек\n"
            f"Порог CPU: {cpu_alert}%\n"
            f"Порог RAM: {ram_alert}%\n\n"
            f"Изменить: /settings <интервал(с)> <порог_cpu(%)> <порог_ram(%)>\n"
            f"Пример: /settings 10 90 90"
        )
    else:
        global_interval, cpu_alert, ram_alert = int(context.args[0]), int(context.args[1]), int(context.args[2])


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.job_queue.stop(wait=True)
    await update.message.reply_text(f"Stopped monitoring")


async def got_it(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name("monitoring_job")
    if not current_jobs:
        await update.message.reply_text("Мониторинг не запущен")
        return
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_once(auto_restart, when=timedelta(minutes=15), chat_id=chat_id, name="restart_job")

    await update.message.reply_text(f"Остановка оповещений на 15 минут\nПродолжение оповещений в {(datetime.now() + timedelta(minutes=15)).strftime('%H:%M:%S')}")


async def auto_restart(context: ContextTypes.DEFAULT_TYPE):
    global message_to_edit
    chat_id = context.job.chat_id
    context.job_queue.run_repeating(monitoring_job, interval=global_interval, first=3, chat_id=chat_id, data=message_to_edit, name="monitoring_job")

def __main__():
    print(config.tg_token)
    bot_app = Application.builder().token(token=config.tg_token).build()
    bot_app.add_handler(CommandHandler("start", start_up))
    bot_app.add_handler(CommandHandler("settings", settings))
    bot_app.add_handler(CommandHandler("stop", stop))
    bot_app.add_handler(CommandHandler("got_it", got_it))
    bot_app.run_polling()


if __name__ == "__main__":
    __main__()