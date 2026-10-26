# --- Patch 7 (Fixed) ---
import json
import os
import re
from datetime import datetime
import disnake
from disnake.ext import commands

# --- НАСТРОЙКИ ---
# ID канала, куда бот БУДЕТ ОТПРАВЛЯТЬ готовые отчеты
TARGET_CHANNEL_ID = 1563938198659276810
# ID канала, откуда бот ЧИТАЕТ текст из игры
SOURCE_CHANNEL_ID = 1518641028813295767
HISTORY_FILE = "price_history.json"

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
intents = disnake.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    default_max_prices = {
        "Медь": 72, "Изумруд": 444, "Рубин": 840, "Алмаз": 4800,
        "Бензин": 240, "Солярка": 240, "Керосин": 240, "Окунь": 60,
        "Карп": 444, "Форель": 678, "Лосось": 4800, "Идеальное мясо": 1200,
        "Хорошее мясо": 1800, "Фальшивые деньги": 12000, "Жемчуг": 1920,
        "Шкура": 2400, "Капуста": 750, "Тыква": 850, "Мандарины": 950, "Ананасы": 1150
    }
    return {"normal": default_max_prices.copy(), "four_hours": default_max_prices.copy()}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def parse_and_analyze_prices(text_content):
    if not text_content:
        return None

    # Регулярка для поиска ресурсов и цен со скобками и без
    pattern = re.compile(r"(?:-\s*|•\s*)?([^:—]+)\s*[:—]\s*(?:\$)?(\d+)(?:\s*\((?:\$)?(\d+)\))?")
    current_best = {}
    history = load_history()
    current_buyer = "Неизвестный скупщик"

    for line in text_content.split("\n"):
        line_clean = line.replace("```md", "").replace("```", "").replace("*", "").replace("_", "").strip()
        if not line_clean:
            continue

        # Очистка от Discord-эмодзи вида :text:
        line_clean = re.sub(r':[a-zA-Z0-9_]+:', '', line_clean).strip()

        # Добавлены скобки \( и \) в список разрешенных символов, чтобы не ломать 4ч цены
        line_clean = re.sub(r'[^\w\s\d.,!?:\-_~()─]', '', line_clean).strip()
        if not line_clean:
            continue

        if "скупщик" in line_clean.lower() or "продуктов" in line_clean.lower():
            buyer_name = re.sub(r'^[*\-\s]+', '', line_clean)
            buyer_name = buyer_name.replace("Скупщик сырья", "Скупщик").replace("Скупщик продуктов", "Продукты")
            current_buyer = buyer_name.strip()
            continue

        match = pattern.search(line_clean)
        if match:
            resource = match.group(1).strip()
            if "изменение" in resource.lower() or "скупщик" in resource.lower():
                continue

            normal_price = int(match.group(2))
            four_hours_price = int(match.group(3)) if match.group(3) else -1

            if resource not in current_best:
                current_best[resource] = {
                    "max_normal": -1, "buyer_normal": "",
                    "max_4h": -1, "buyer_4h": ""
                }

            if normal_price > current_best[resource]["max_normal"]:
                current_best[resource]["max_normal"] = normal_price
                current_best[resource]["buyer_normal"] = current_buyer

            if four_hours_price != -1:
                if four_hours_price > current_best[resource]["max_4h"]:
                    current_best[resource]["max_4h"] = four_hours_price
                    current_best[resource]["buyer_4h"] = current_buyer

            actual_4h = four_hours_price if four_hours_price != -1 else normal_price

            if resource not in history["normal"] or normal_price > history["normal"][resource]:
                history["normal"][resource] = normal_price
            if resource not in history["four_hours"] or actual_4h > history["four_hours"][resource]:
                history["four_hours"][resource] = actual_4h

    if not current_best:
        return None

    save_history(history)

    lines_output = []
    for res, data in current_best.items():
        hist_norm = history["normal"].get(res, data['max_normal'])
        hist_4h = history["four_hours"].get(res, data['max_4h'])
        buyer_name = data['buyer_normal']

        # Если у товара была четырехчасовая цена, выводим её в скобках
        if data['max_4h'] == -1:
            price_str = f"${data['max_normal']}"
            max_str = f"${hist_norm}"
        else:
            price_str = f"${data['max_normal']} (${data['max_4h']})"
            max_str = f"${hist_4h}"

        line_str = f"▫️ **{res}** ➔ Цена: `{price_str}` ➔ *{buyer_name}* | Max: `{max_str}`"
        lines_output.append(line_str)

    return lines_output

@bot.event
async def on_ready():
    print(f"[+] Бот успешно запущен напрямую без вебхуков!")
    print(f"[+] Читаю канал: {SOURCE_CHANNEL_ID} | Пишу отчеты в канал: {TARGET_CHANNEL_ID}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.id == SOURCE_CHANNEL_ID:
        text_to_analyze = ""
        if message.content:
            text_to_analyze += message.content
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    text_to_analyze += f"\n{embed.title}\n"
                if embed.description:
                    text_to_analyze += embed.description
                for field in embed.fields:
                    text_to_analyze += f"\n{field.name}\n{field.value}"

        if text_to_analyze.strip():
            print(f"[...] Обработка новых цен от {message.author}...")
            lines_report = parse_and_analyze_prices(text_to_analyze)
            if lines_report:
                target_channel = bot.get_channel(TARGET_CHANNEL_ID)
                if target_channel is None:
                    try:
                        target_channel = await bot.fetch_channel(TARGET_CHANNEL_ID)
                    except Exception:
                        print(f"[X] Критическая ошибка: Бот не имеет доступа к каналу {TARGET_CHANNEL_ID}!")
                        return

                current_time = datetime.now().strftime('%d.%m.%Y в %H:%M')
                chunks = []
                current_chunk = (
                    f"## 📊 Лучшие предложения у скупщиков NovaRP\n"
                    f"⏰ *Анализ базы выполнен: {current_time}*\n"
                    f"──────────────────────────────\n"
                )

                for line in lines_report:
                    if len(current_chunk) + len(line) > 1850:
                        chunks.append(current_chunk)
                        current_chunk = ""
                    current_chunk += line + "\n"

                if current_chunk:
                    current_chunk += f"──────────────────────────────\n"
                    chunks.append(current_chunk)

                try:
                    for chunk in chunks:
                        await target_channel.send(content=chunk)
                    print("[+] Отчет БОТА успешно опубликован в канале отчетов!")
                except disnake.errors.Forbidden:
                    print("[X] Ошибка: У роли бота нет прав 'Отправлять сообщения' в целевом канале!")
                except Exception as e:
                    print(f"[X] Ошибка отправки сообщения: {e}")

    await bot.process_commands(message)

# Запуск бота с вашим токеном
bot.run(os.getenv("DISCORD_TOKEN").strip()) 
