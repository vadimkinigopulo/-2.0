import os
import json
import time
import logging
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from dotenv import load_dotenv

# ================== Настройка ==================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", 0))

if not TOKEN or GROUP_ID == 0:
    raise ValueError("VK_TOKEN или GROUP_ID не указаны в .env")

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создание папки для логов
os.makedirs("logs", exist_ok=True)

# ================== VK API ==================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================== Файлы хранения ==================
admins_file = "admins.json"          # младшие админы
senior_file = "senior_admins.json"   # старшие админы
management_file = "management.json"  # руководство

# ================== Загрузка данных ==================
def load_json(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

admins = load_json(admins_file, {})
senior_admins = load_json(senior_file, [])
management = load_json(management_file, [])

# ================== Сохранение ==================
def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== Вспомогательные функции ==================
def is_management(user_id):
    return str(user_id) in [str(m) for m in management]

def is_senior(user_id):
    return int(user_id) in senior_admins

def is_junior(user_id):
    return str(user_id) in admins

def get_user_role(user_id):
    if is_management(user_id): return "Руководство"
    elif is_senior(user_id): return "Старший админ"
    elif is_junior(user_id): return "Мл.админ"
    return "Нет роли"

def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h and m: return f"{h}ч {m}м"
    elif h: return f"{h}ч"
    elif m: return f"{m}м"
    return "меньше минуты"

def parse_user_input(text):
    text = text.strip()
    if text.startswith('@'): text = text[1:]
    if text.startswith('[id') and '|' in text:
        try: return text.split('[id')[1].split('|')[0]
        except: return None
    if 'vk.com/' in text:
        try:
            part = text.split('vk.com/')[1].split('/')[0]
            if part.startswith('id'): return part[2:]
            user = vk.users.get(user_ids=part)
            if user: return str(user[0]['id'])
        except: return None
    if text.isdigit(): return text
    return None

# ================== Клавиатуры ==================
def online_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE)
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("👥 Мл.админы", VkKeyboardColor.SECONDARY)
    kb.add_button("👤 Ст.админы", VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("👑 Руководство", VkKeyboardColor.PRIMARY)
    return kb.get_keyboard()

def management_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE)
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("👥 Мл.админы", VkKeyboardColor.SECONDARY)
    kb.add_button("👤 Ст.админы", VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("👑 Руководство", VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("➕ Мл.админ", VkKeyboardColor.POSITIVE)
    kb.add_button("➖ Мл.админ", VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("➕ Ст.админ", VkKeyboardColor.POSITIVE)
    kb.add_button("➖ Ст.админ", VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("➕ Руководство", VkKeyboardColor.POSITIVE)
    kb.add_button("➖ Руководство", VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()

# ================== Отправка сообщений ==================
def send_message(peer_id, text, user_id=None):
    try:
        vk.messages.send(peer_id=peer_id, message=text, random_id=get_random_id(),
                         keyboard=management_keyboard() if is_management(user_id) else online_keyboard())
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# ================== Главный цикл ==================
waiting_for_input = {}

logger.info("Бот запущен")
for event in longpoll.listen():
    try:
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue
        msg = event.message
        peer_id = msg["peer_id"]
        user_id = str(msg["from_id"])
        text = msg.get("text", "").lower()

        # Обработка ожидания роли
        if user_id in waiting_for_input:
            action = waiting_for_input[user_id]
            target_id = parse_user_input(text)
            if not target_id:
                send_message(peer_id, "❌ Не удалось распознать пользователя", user_id)
                waiting_for_input.pop(user_id)
                continue

            first, last = get_user_info(target_id)
            target_name = f"{first} {last}"

            if action == "➕ мл.админ":
                if target_id in admins:
                    send_message(peer_id, f"⚠️ {target_name} уже Мл.админ", user_id)
                else:
                    admins[target_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                    save_json(admins_file, admins)
                    send_message(peer_id, f"✅ {target_name} назначен Мл.админом", user_id)

            elif action == "➖ мл.админ":
                if target_id not in admins:
                    send_message(peer_id, f"⚠️ {target_name} не Мл.админ", user_id)
                else:
                    admins.pop(target_id)
                    save_json(admins_file, admins)
                    send_message(peer_id, f"✅ {target_name} удален из Мл.админов", user_id)

            elif action == "➕ ст.админ":
                if int(target_id) in senior_admins:
                    send_message(peer_id, f"⚠️ {target_name} уже Ст.админ", user_id)
                else:
                    senior_admins.append(int(target_id))
                    save_json(senior_file, senior_admins)
                    send_message(peer_id, f"✅ {target_name} назначен Ст.админом", user_id)

            elif action == "➖ ст.админ":
                if int(target_id) not in senior_admins:
                    send_message(peer_id, f"⚠️ {target_name} не Ст.админ", user_id)
                else:
                    senior_admins.remove(int(target_id))
                    save_json(senior_file, senior_admins)
                    send_message(peer_id, f"✅ {target_name} удален из Ст.админов", user_id)

            elif action == "➕ руководство":
                if int(target_id) in management:
                    send_message(peer_id, f"⚠️ {target_name} уже Руководство", user_id)
                else:
                    management.append(int(target_id))
                    save_json(management_file, management)
                    send_message(peer_id, f"✅ {target_name} назначен Руководством", user_id)

            elif action == "➖ руководство":
                if int(target_id) not in management:
                    send_message(peer_id, f"⚠️ {target_name} не Руководство", user_id)
                else:
                    management.remove(int(target_id))
                    save_json(management_file, management)
                    send_message(peer_id, f"✅ {target_name} удален из Руководства", user_id)

            waiting_for_input.pop(user_id)
            continue

        # Команда старт
        if text == "старт":
            send_message(peer_id, "👋 Главное меню", user_id)
            continue

        # Вход/Выход
        if text == "вошел":
            if user_id in admins:
                send_message(peer_id, "⚠️ Вы уже авторизованы", user_id)
            else:
                first, last = get_user_info(user_id)
                admins[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                save_json(admins_file, admins)
                send_message(peer_id, f"✅ Мл.админ {first} {last} вошел", user_id)

        elif text == "вышел":
            if user_id not in admins:
                send_message(peer_id, "⚠️ Вы не авторизованы", user_id)
            else:
                first, last = admins[user_id]["first_name"], admins[user_id]["last_name"]
                admins.pop(user_id)
                save_json(admins_file, admins)
                send_message(peer_id, f"❌ Мл.админ {first} {last} вышел", user_id)

        elif text == "список":
            lines = []
            now = time.time()
            if admins:
                lines.append("👥 Мл.админы онлайн:")
                for uid, info in admins.items():
                    role = get_user_role(uid)
                    lines.append(f"[id{uid}|{info['first_name']} {info['last_name']}] — {role} — {format_time(now - info['start_time'])}")
            if senior_admins:
                lines.append("\n👤 Старшие админы:")
                for uid in senior_admins:
                    first, last = get_user_info(uid)
                    status = "✅ В сети" if str(uid) in admins else "❌ Не в сети"
                    lines.append(f"[id{uid}|{first} {last}] — {status}")
            if management:
                lines.append("\n👑 Руководство:")
                for uid in management:
                    first, last = get_user_info(uid)
                    status = "✅ В сети" if str(uid) in admins else "❌ Не в сети"
                    lines.append(f"[id{uid}|{first} {last}] — {status}")
            send_message(peer_id, "\n".join(lines), user_id)

        # Обработка кнопок роли
        if text in ["➕ мл.админ","➖ мл.админ","➕ ст.админ","➖ ст.админ","➕ руководство","➖ руководство"]:
            if not is_management(user_id):
                send_message(peer_id, "⛔ Недостаточно прав", user_id)
            else:
                waiting_for_input[user_id] = text
                send_message(peer_id, "Введите ID или ссылку на пользователя:", user_id)

    except Exception as e:
        logger.error(f"Ошибка события: {e}", exc_info=True)
        try:
            send_message(peer_id, "❌ Произошла ошибка. Попробуйте позже.", user_id)
        except: pass
