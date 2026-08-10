import os
import json
import hashlib
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# کانفیگ فایل‌ها و کانال‌های تلگرامی
# در این بخش می‌توانید به راحتی تعیین کنید که هر فایل به کدام کانال ارسال شود.
# می‌توانید آیدی عددی کانال (مثل -100123456) یا یوزرنیم کانال (مثل @my_channel) را وارد کنید.
FILE_TO_CHANNEL = {
    "top20.txt": "@ApexConfigVpn",      # کانال اول شما
    "batch_01.txt": "@QuantumConfigX",   # کانال دوم شما
    "batch_02.txt": "@HyperConfigPro",   # کانال سوم شما
    # شما می‌توانید بقیه فایل‌ها مثل batch_03 تا batch_10 را هم به همین شکل اضافه کنید
    # "batch_03.txt": "@your_channel_3",
}

# دریافت اطلاعات احراز هویت از Environment Variables (تنظیم شده در GitHub Secrets)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# فایلی که وضعیت کانفیگ‌های ارسال شده را ذخیره می‌کند تا از ارسال تکراری جلوگیری شود
STATE_FILE = "sent_state.json"

def get_hash(text):
    """تولید هش MD5 برای هر کانفیگ جهت تشخیص تکراری بودن یا نبودن آن"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

async def send_in_chunks(client, channel, configs):
    """
    ارسال کانفیگ‌ها به تلگرام.
    محدودیت هر پیام در تلگرام ۴۰۹۶ کاراکتر است، این تابع پیام‌های طولانی را می‌شکند.
    """
    chunk = ""
    for config in configs:
        # قرار دادن کانفیگ در تگ کد برای کپی راحت‌تر توسط کاربران
        formatted_config = f"```\n{config}\n```\n\n"
        
        if len(chunk) + len(formatted_config) > 4000:
            await client.send_message(channel, chunk, parse_mode='md')
            chunk = formatted_config
            await asyncio.sleep(1.5) # جلوگیری از محدودیت ارسال تلگرام (Flood Wait)
        else:
            chunk += formatted_config
            
    if chunk:
        await client.send_message(channel, chunk, parse_mode='md')

async def main():
    if not API_ID or not API_HASH or not SESSION_STRING:
        print("Error: Missing Telegram API credentials in Environment Variables!")
        return

    # اتصال به اکانت تلگرام با استفاده از String Session
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    print("Successfully connected to Telegram.")

    # لود کردن وضعیت قبلی از فایل JSON
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {}

    state_changed = False

    # بررسی تک تک فایل‌های تعریف شده در دیکشنری
    for filename, channel in FILE_TO_CHANNEL.items():
        if not os.path.exists(filename):
            print(f"File {filename} not found in repository. Skipping.")
            continue

        if filename not in state:
            state[filename] = []

        new_configs = []
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

        # بررسی خط به خط فایل‌ها
        for line in lines:
            line = line.strip()
            if not line: 
                continue

            # اگر هش این کانفیگ در دیتابیس ما نباشد، یعنی جدید است یا تغییر کرده
            config_hash = get_hash(line)
            if config_hash not in state[filename]:
                new_configs.append(line)
                state[filename].append(config_hash)
                state_changed = True

        # اگر کانفیگ جدیدی پیدا شد، به کانال مربوطه ارسال می‌شود
        if new_configs:
            print(f"Found {len(new_configs)} new/updated configs in {filename}. Sending to {channel}...")
            try:
                await send_in_chunks(client, channel, new_configs)
                print(f"Successfully sent new configs from {filename} to {channel}.")
            except Exception as e:
                print(f"Failed to send messages to {channel}: {e}")
        else:
            print(f"No new configs in {filename}.")

    # اگر وضعیت تغییر کرده باشد، فایل وضعیت جدید را ذخیره می‌کنیم تا گیت‌هاب اکشن آن را کامیت کند
    if state_changed:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
        print("State file updated successfully.")
    else:
        print("No updates needed. Exiting.")

if __name__ == "__main__":
    asyncio.run(main())
