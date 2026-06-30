# Idea to do: Server/PC resource check with tg possible idea connect wia ssh and get the info from that if tg is not possible on server
# What to do up a local server (container obviously) or connect via ssh and use psutil for interface tg or web depends on what to use
import logging
import time

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
    print(cpu_alert, ram_alert)
    if cpu_usage > cpu_alert:
        alert.append("CPU usage exceeded 90%")
    if ram_usage_perc > ram_alert:
        alert.append("RAM usage exceeded 90%")

    if alert:
        await context.bot.send_message(chat_id=context.job.chat_id, text="\n".join(alert))


async def start_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    os_name = "Linux" if os.name == "posix" else "Windows"
    server_time = time.ctime()
    cpu_usage, ram_usage_perc, ram_usage_gig = get_server_usage()
    await update.message.reply_text(f"Server OS: {os_name}\nServer Time: {server_time}\n")
    message = await update.message.reply_text(f"CPU Usage: {cpu_usage}%\nRAM usage (%): {ram_usage_perc}%"
            f"\nRAM usage (Gb): {ram_usage_gig}")
    await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=message.message_id, disable_notification=True)
    context.job_queue.run_repeating(monitoring_job, interval=10, first=3, chat_id=update.effective_chat.id, data=message)

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global cpu_alert, ram_alert
    cpu_alert, ram_alert = int(context.args[0]), int(context.args[1])


def __main__():
    print(config.tg_token)
    bot_app = Application.builder().token(token=config.tg_token).build()
    bot_app.add_handler(CommandHandler("start", start_up))
    bot_app.add_handler(CommandHandler("settings", settings))
    bot_app.run_polling()


if __name__ == "__main__":
    __main__()