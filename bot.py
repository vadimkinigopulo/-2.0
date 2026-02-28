import os
import time
import json
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

# ================= Настройка =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", 0))

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы данных =================
os.makedirs("data", exist_ok=True)
admins_file = "admins.json"
senior_admins_file = "senior_admins.json"
management_file = "management.json"

def load_json(file, default):
    path = os.path.join("data", file)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(file, data):
    path = os.path.join("data", file)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

admins = load_json(admins_file, {})
senior_admins = load_json(senior_admins_file, [])
management = load_json(management_file, [])

# ================= Проверка прав =================
def is_management(user_id):
    return int(user_id) in management

def is_senior_admin(user_id):
    return int(user_id) in senior_admins

def is_junior_admin(user_id):
    return str(user_id) in admins

def get_user_role(user_id):
    if is_management(user_id):
        return "Руководство"
    elif is_senior_admin(user_id):
        return "Ст.админ"
    elif is_junior_admin(user_id):
        return "Мл.админ"
    return "Неизвестно"

# ================= Вспомогательные =================
def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}ч {m}м" if h or m else "меньше минуты"

def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

# ================= Клавиатуры =================
def online_keyboard(user_id=None):
    keyboard = VkKeyboard(one_time=False)
    now = time.time()

    for uid, info in admins.items():
        keyboard.add_button(f"{info['first_name']} {info['last_name']} — Мл.админ — {format_time(now - info['start_time'])}", color=VkKeyboardColor.SECONDARY)
        keyboard.add_line()

    for uid in senior_admins:
        first, last = get_user_info(uid)
        keyboard.add_button(f"{first} {last} — Ст.админ — онлайн", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()

    for uid in management:
        first, last = get_user_info(uid)
        keyboard.add_button(f"{first} {last} — Руководство — онлайн", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()

    return keyboard.get_keyboard()

def management_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button("➕ Мл.админ", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("➖ Мл.админ", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("➕ Ст.админ", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("➖ Ст.админ", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("➕ Руководство", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("➖ Руководство", color=VkKeyboardColor.NEGATIVE)
    return keyboard.get_keyboard()

# ================= Управление пользователями =================
waiting_for_input = {}

def send_message(peer_id, message, user_id=None):
    if is_management(user_id):
        kb = management_keyboard()
    else:
        kb = online_keyboard()
    vk.messages.send(peer_id=peer_id, message=message, random_id=get_random_id(), keyboard=kb)

def process_role_action(user_id, text, peer_id):
    """Добавление или удаление ролей через ввод пользователя"""
    parts = text.split()
    if len(parts) < 3:
        send_message(peer_id, "❌ Формат: ➕/➖ Роль ID_пользователя", user_id)
        return

    action = parts[0]
    role = parts[1].lower()
    target_id = parts[2]

    # Получение имени
    first, last = get_user_info(target_id)

    if role == "мл.админ":
        if action == "➕":
            admins[target_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
        elif action == "➖":
            if target_id in admins: del admins[target_id]
        save_json(admins_file, admins)

    elif role == "ст.админ":
        if action == "➕" and int(target_id) not in senior_admins:
            senior_admins.append(int(target_id))
        elif action == "➖" and int(target_id) in senior_admins:
            senior_admins.remove(int(target_id))
        save_json(senior_admins_file, senior_admins)

    elif role == "руководство":
        if action == "➕" and int(target_id) not in management:
            management.append(int(target_id))
        elif action == "➖" and int(target_id) in management:
            management.remove(int(target_id))
        save_json(management_file, management)

    send_message(peer_id, f"✅ {action} {role} для {first} {last}", user_id)

# ================= Основной цикл =================
logger.info("Бот запущен")
for event in longpoll.listen():
    if event.type == VkBotEventType.MESSAGE_NEW:
        msg = event.message
        peer_id = msg["peer_id"]
        user_id = str(msg["from_id"])
        text = msg.get("text", "")

        if user_id in waiting_for_input:
            process_role_action(user_id, text, peer_id)
            waiting_for_input.pop(user_id, None)
            continue

        # Вход/выход
        if text.lower() == "вошел":
            if user_id in admins:
                send_message(peer_id, "⚠️ Вы уже авторизованы", user_id)
            else:
                first, last = get_user_info(user_id)
                admins[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                save_json(admins_file, admins)
                send_message(peer_id, f"✅ Мл.админ {first} {last} вошел в систему", user_id)

        elif text.lower() == "вышел":
            if user_id not in admins:
                send_message(peer_id, "⚠️ Вы не авторизованы", user_id)
            else:
                first = admins[user_id]["first_name"]
                last = admins[user_id]["last_name"]
                del admins[user_id]
                save_json(admins_file, admins)
                send_message(peer_id, f"❌ Мл.админ {first} {last} вышел из системы", user_id)

        elif text.lower() == "список":
            send_message(peer_id, "Список онлайн:", user_id)

        # Кнопки роли (только для руководства)
        elif text in ["➕ Мл.админ","➖ Мл.админ","➕ Ст.админ","➖ Ст.админ","➕ Руководство","➖ Руководство"]:
            if not is_management(user_id):
                send_message(peer_id, "⛔ Недостаточно прав", user_id)
            else:
                waiting_for_input[user_id] = text
                send_message(peer_id, "Введите ID или ссылку на пользователя для действия:", user_id)
