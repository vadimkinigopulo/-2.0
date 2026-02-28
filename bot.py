# -*- coding: utf-8 -*-
import os
import json
import time
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id

# ================= Настройка =================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")          # Токен группы
GROUP_ID = int(os.getenv("GROUP_ID"))  # ID группы

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ================= VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")

# ================= Загрузка данных =================
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

admins = load_json(ADMINS_FILE, {})           # младшие админы
senior_admins = load_json(SENIOR_FILE, [])    # старшие админы
management = load_json(MANAGEMENT_FILE, [])   # руководство

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= Проверка ролей =================
def is_management(user_id):
    return int(user_id) in management

def is_senior(user_id):
    return int(user_id) in senior_admins

def is_junior(user_id):
    return str(user_id) in admins

def get_role_text(user_id):
    if is_management(user_id):
        return "Руководство"
    elif is_senior(user_id):
        return "Старший администратор"
    elif is_junior(user_id):
        return "Младший администратор"
    return "Гость"

# ================= Вспомогательные функции =================
def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}ч {m}м" if h or m else "меньше минуты"

def get_user_name(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return f"{user['first_name']} {user['last_name']}"
    except:
        return "Неизвестно"

def parse_user(input_text):
    input_text = input_text.strip()
    if input_text.startswith("@"):
        input_text = input_text[1:]
    if input_text.startswith("[id") and "|" in input_text:
        return input_text.split("[id")[1].split("|")[0]
    if "vk.com/" in input_text:
        parts = input_text.split("vk.com/")[1].split("/")[0]
        if parts.startswith("id"):
            return parts[2:]
        try:
            users = vk.users.get(user_ids=parts)
            if users: return str(users[0]["id"])
        except: pass
    if input_text.isdigit(): return input_text
    return None

def send_message(peer_id, text):
    vk.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id()
    )

def list_online():
    now = time.time()
    lines = ["👑 Руководство:"]
    for uid in management:
        status = "✅ В сети" if str(uid) in admins else "❌ Не в сети"
        lines.append(f"[id{uid}|{get_user_name(uid)}] — {status}")

    lines.append("\n👤 Старшие админы:")
    for uid in senior_admins:
        status = "✅ В сети" if str(uid) in admins else "❌ Не в сети"
        lines.append(f"[id{uid}|{get_user_name(uid)}] — {status}")

    lines.append("\n👥 Младшие админы:")
    for uid, info in admins.items():
        online_time = now - info.get("start_time", now)
        lines.append(f"[id{uid}|{info['first_name']} {info['last_name']}] — ⏱ {format_time(online_time)}")
    
    return "\n".join(lines)

# ================= Основная обработка сообщений =================
waiting_input = {}

def handle_command(user_id, peer_id, text):
    user_role = get_role_text(user_id)
    text_lower = text.lower()

    # Авто авторизация как младший админ
    if text_lower == "вошел":
        if not is_junior(user_id):
            first_name = get_user_name(user_id).split()[0]
            last_name = get_user_name(user_id).split()[1]
            admins[str(user_id)] = {"first_name": first_name, "last_name": last_name, "start_time": time.time()}
            save_json(ADMINS_FILE, admins)
            send_message(peer_id, f"✅ {first_name} {last_name} вошел как Младший администратор")
        else:
            send_message(peer_id, "⚠️ Вы уже авторизованы")
        return

    if text_lower == "вышел":
        if is_junior(user_id):
            first_name = admins[str(user_id)]["first_name"]
            last_name = admins[str(user_id)]["last_name"]
            del admins[str(user_id)]
            save_json(ADMINS_FILE, admins)
            send_message(peer_id, f"❌ {first_name} {last_name} вышел")
        else:
            send_message(peer_id, "⚠️ Вы не авторизованы")
        return

    if text_lower in ["список", "онлайн"]:
        send_message(peer_id, list_online())
        return

    # Только руководство может управлять ролями
    if user_role != "Руководство": return

    # Добавление/удаление ролей
    args = text.split()
    if len(args) >= 3:
        cmd, role, target_text = args[0].lower(), args[1].lower(), " ".join(args[2:])
        target_id = parse_user(target_text)
        if not target_id:
            send_message(peer_id, "❌ Не удалось распознать пользователя")
            return

        name = get_user_name(target_id)
        if cmd == "/addgroup":
            if role == "junior":
                if target_id in admins: send_message(peer_id, "⚠️ Уже младший админ")
                else:
                    first, last = name.split()
                    admins[target_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                    save_json(ADMINS_FILE, admins)
                    send_message(peer_id, f"✅ {name} назначен младшим администратором")
            elif role == "senior":
                if int(target_id) in senior_admins: send_message(peer_id, "⚠️ Уже старший админ")
                else:
                    senior_admins.append(int(target_id))
                    save_json(SENIOR_FILE, senior_admins)
                    send_message(peer_id, f"✅ {name} назначен старшим администратором")
            elif role == "management":
                if int(target_id) in management: send_message(peer_id, "⚠️ Уже руководство")
                else:
                    management.append(int(target_id))
                    save_json(MANAGEMENT_FILE, management)
                    send_message(peer_id, f"✅ {name} назначен в руководство")
            else:
                send_message(peer_id, "❌ Неизвестная группа")
        elif cmd == "/removegroup":
            if role == "junior":
                if target_id in admins:
                    del admins[target_id]
                    save_json(ADMINS_FILE, admins)
                    send_message(peer_id, f"✅ {name} удален из младших админов")
            elif role == "senior":
                if int(target_id) in senior_admins:
                    senior_admins.remove(int(target_id))
                    save_json(SENIOR_FILE, senior_admins)
                    send_message(peer_id, f"✅ {name} удален из старших админов")
            elif role == "management":
                if int(target_id) in management:
                    management.remove(int(target_id))
                    save_json(MANAGEMENT_FILE, management)
                    send_message(peer_id, f"✅ {name} удален из руководства")
        return

# ================= Запуск бота =================
logger.info("🤖 Бот запущен!")

for event in longpoll.listen():
    try:
        if event.type == VkBotEventType.MESSAGE_NEW:
            msg = event.message
            peer_id = msg["peer_id"]
            user_id = str(msg["from_id"])
            text = msg.get("text", "")
            handle_command(user_id, peer_id, text)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
