import os
import json
import hashlib
import base64
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# کانفیگ فایل‌ها و کانال‌های تلگرامی
FILE_TO_CHANNEL = {
    "top20.txt": "@ApexConfigVpn",
    "batch_01.txt": "@QuantumConfigX",
    "batch_02.txt": "@HyperConfigPro",
    "batch_03.txt": "@HyperConfigPro",
}

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")

STATE_FILE = "sent_state.json"


def get_stable_key(line: str) -> str:
    """
    استخراج بخش «پایدار» کانفیگ که با تغییر رمارک/پینگ عوض نمی‌شود.
    برای vmess (که payload آن base64 JSON است) فیلد 'ps' (اسم/رمارک) حذف می‌شود.
    برای بقیه پروتکل‌ها (vless/trojan/ss/ssr و ...) که رمارک بعد از '#'
    به صورت fragment در URI می‌آید، همان بخش fragment کنار گذاشته می‌شود.
    """
    line = line.strip()

    if line.startswith("vmess://"):
        try:
            b64_part = line[len("vmess://"):]
            padded = b64_part + "=" * (-len(b64_part) % 4)
            decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
            data = json.loads(decoded)
            # 'ps' معمولاً فیلد اسم/رمارک (شامل پینگ) است؛ حذفش می‌کنیم
            data.pop("ps", None)
            return json.dumps(data, sort_keys=True)
        except Exception:
            # اگر پارس نشد، حداقل fragment را کنار بگذاریم
            return line.split("#")[0]

    # vless / trojan / ss / ssr و غیره: رمارک بعد از '#' می‌آید
    return line.split("#")[0]


def get_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


async def send_in_chunks(client, channel, configs):
    """
    ارسال کانفیگ‌ها به تلگرام و برگرداندن لیستِ کانفیگ‌هایی که
    *واقعاً و با موفقیت* ارسال شدند (برای ثبت درست در state).
    """
    sent_successfully = []
    chunk_configs = []
    current_length = 0

    header = "```\n"
    footer = f"\n```\n\n🆔 **Channel:** {channel}"

    async def flush(chunk):
        if not chunk:
            return
        message = header + "\n".join(chunk) + footer
        await client.send_message(channel, message)
        sent_successfully.extend(chunk)
        await asyncio.sleep(1.5)

    for config in configs:
        config_len = len(config) + 1

        if current_length + config_len + len(header) + len(footer) > 4000:
            try:
                await flush(chunk_configs)
            except Exception as e:
                print(f"Failed to send a chunk to {channel}: {e}")
                # این chunk موفق نبود؛ به sent_successfully اضافه نشد
                # پس دفعه بعد دوباره تلاش می‌شود
            chunk_configs = [config]
            current_length = config_len
        else:
            chunk_configs.append(config)
            current_length += config_len

    if chunk_configs:
        try:
            await flush(chunk_configs)
        except Exception as e:
            print(f"Failed to send final chunk to {channel}: {e}")

    return sent_successfully


async def main():
    if not API_ID or not API_HASH or not SESSION_STRING:
        print("Error: Missing Telegram API credentials in Environment Variables!")
        return

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    print("Successfully connected to Telegram.")

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    else:
        state = {}

    state_changed = False

    for filename, channel in FILE_TO_CHANNEL.items():
        if not os.path.exists(filename):
            print(f"File {filename} not found in repository. Skipping.")
            continue

        if filename not in state:
            state[filename] = []

        with open(filename, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        # نگاشت هش -> خط اصلی، تا بعد از ارسال موفق بتوانیم هش را ثبت کنیم
        candidate_configs = []  # لیستی از (hash, raw_line)
        for line in lines:
            line = line.strip()
            if not line:
                continue

            stable_key = get_stable_key(line)
            config_hash = get_hash(stable_key)

            if config_hash not in state[filename]:
                candidate_configs.append((config_hash, line))

        if not candidate_configs:
            print(f"No new configs in {filename}.")
            continue

        print(f"Found {len(candidate_configs)} new configs in {filename}. Sending to {channel}...")

        raw_lines = [c[1] for c in candidate_configs]
        try:
            sent_lines = await send_in_chunks(client, channel, raw_lines)
        except Exception as e:
            print(f"Unexpected error sending to {channel}: {e}")
            sent_lines = []

        # فقط هش‌های کانفیگ‌هایی که *واقعاً* ارسال شدند را ثبت می‌کنیم
        sent_set = set(sent_lines)
        for config_hash, line in candidate_configs:
            if line in sent_set:
                state[filename].append(config_hash)
                state_changed = True

        not_sent = len(candidate_configs) - len(sent_lines)
        if not_sent > 0:
            print(f"Warning: {not_sent} configs from {filename} were NOT sent and will be retried next run.")
        else:
            print(f"Successfully sent all new configs from {filename} to {channel}.")

    if state_changed:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
        print("State file updated successfully.")
    else:
        print("No updates needed. Exiting.")


if __name__ == "__main__":
    asyncio.run(main())
