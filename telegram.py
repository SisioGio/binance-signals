import requests
from dotenv import load_dotenv
import os
load_dotenv()



TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_CHANNEL_ID = "-5168019773"

def send_telegram_signal(signal_text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": signal_text,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)


# signal = "🚀 BUY EURUSD\nEntry: 1.0825\nSL: 1.0810\nTP: 1.0860"
# send_telegram_signal(signal)