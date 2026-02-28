import os
import json
import time
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# ================= Настройка =================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")          
GROUP_ID = int(os.getenv("GROUP_ID"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# VK и LongPoll
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы для данных =================
admins_file = "admins.json"          # Мл. администраторы онлайн
senior_admins_file = "senior_admins.json"
management_file = "management.json"

# ================= Загрузка данных =================
def load_json(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

admins = load_json(admins_file, {})
senior_admins = load_json(senior_admins_file, [])
management = load_json(management_file, [])

# ================= Сохранение данных =================
def save_admins():
    with open(admins_file, "w", encoding="utf-8") as f:
        json.dump(admins, f, ensure_ascii=False, indent=2)

def save_senior_admins():
    with open(senior_admins_file, "w", encoding="utf-8") as f:
        json.dump(senior_admins, f, ensure_ascii=False, indent=2)

def save_management():
    with open(management_file, "w", encoding="utf-8") as f:
        json.dump(management, f, ensure_ascii=False, indent=2)

# ================= Роли =================
def is_management(user_id): return str(user_id) in [str(m) for m in management]
def is_senior_admin(user_id): return str(user_id) in [str(sa) for sa in senior_admins]
def is_junior_admin(user_id): return str(user_id) in admins

def get_user_role(user_id):
    if is_management(user_id): return "management"
    elif is_senior_admin(user_id): return "senior"
    elif is_junior_admin(user_id): return "junior"
    return "none"

# ================= Вспомогательные =================
def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h and m: return f"{h}ч {m}м"
    if h: return f"{h}ч"
    if m: return f"{m}м"
    return "меньше минуты"

def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

def parse_user_input(input_text):
    input_text = input_text.strip()
    if input_text.startswith('@'): input_text = input_text[1:]
    if input_text.startswith('[id') and '|' in input_text:
        try: return input_text.split('[id')[1].split('|')[0]
        except: pass
    if 'vk.com/' in input_text:
        try:
            parts = input_text.split('vk.com/')[1].split('/')[0]
            if parts.startswith('id'): return parts[2:]
            users = vk.users.get(user_ids=parts)
            if users: return str(users[0]['id'])
        except: pass
    if input_text.isdigit(): return input_text
    return None

# ================= Клавиатура =================
def get_keyboard(user_id=None):
    keyboard = VkKeyboard(one_time=False)
    role = get_user_role(user_id) if user_id else "none"

    keyboard.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload=json.dumps({"command": "entered"}))
    keyboard.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"command": "exited"}))
    keyboard.add_line()
    keyboard.add_button("👥 Мл. Администрация", VkKeyboardColor.SECONDARY, payload=json.dumps({"command": "junior_admins"}))
    keyboard.add_button("👤 Ст. Администрация", VkKeyboardColor.PRIMARY, payload=json.dumps({"command": "senior_admins"}))
    keyboard.add_line()
    keyboard.add_button("👑 Руководство", VkKeyboardColor.PRIMARY, payload=json.dumps({"command": "management"}))

    if role == "management":
        keyboard.add_line()
        keyboard.add_button("➕ Дать мл.админа", VkKeyboardColor.POSITIVE, payload=json.dumps({"command": "add_junior"}))
        keyboard.add_button("➖ Убрать мл.админа", VkKeyboardColor.NEGATIVE, payload=json.dumps({"command": "remove_junior"}))
        keyboard.add_line()
        keyboard.add_button("➕ Дать ст.админа", VkKeyboardColor.POSITIVE, payload=json.dumps({"command": "add_senior"}))
        keyboard.add_button("➖ Убрать ст.админа", VkKeyboardColor.NEGATIVE, payload=json.dumps({"command": "remove_senior"}))
        keyboard.add_line()
        keyboard.add_button("➕ Дать руководство", VkKeyboardColor.POSITIVE, payload=json.dumps({"command": "add_management"}))
        keyboard.add_button("➖ Убрать руководство", VkKeyboardColor.NEGATIVE, payload=json.dumps({"command": "remove_management"}))

    return keyboard.get_keyboard()

# ================= Отправка сообщений =================
def send_message(peer_id, message, user_id=None):
    try:
        vk.messages.send(peer_id=peer_id, message=message, random_id=get_random_id(), keyboard=get_keyboard(user_id))
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

# ================= Обработчик входа =================
def handle_entered(user_id, peer_id):
    role = get_user_role(user_id)
    first_name, last_name = get_user_info(user_id)

    if role == "management":
        send_message(peer_id, f"👑 {first_name} {last_name}, вы вошли как руководство", user_id)
        return

    if user_id in admins:
        send_message(peer_id, "⚠️ Вы уже авторизованы", user_id)
        return

    admins[user_id] = {"start_time": time.time(), "first_name": first_name, "last_name": last_name}
    save_admins()

    role_text = "Мл. Администрация"
    if role == "senior": role_text = "Ст. Администрация"

    send_message(peer_id,
        f"✅ {role_text} — [id{user_id}|{first_name} {last_name}] успешно авторизован!\n"
        f"👥 Онлайн: {len(admins)}", user_id
    )

# ================= Списки =================
def get_junior_admins_list():
    if not admins: return "👥 Мл. Администрация:\n\nСейчас никто не в сети."
    now = time.time()
    result = [f"{i}. [id{uid}|{info['first_name']} {info['last_name']}] — ⏱ {format_time(now - info['start_time'])}" 
              for i, (uid, info) in enumerate(admins.items(), 1)]
    return "👥 Мл. Администрация:\n\n" + "\n".join(result)

def get_senior_admins_list():
    if not senior_admins: return "👤 Ст. Администрация:\n\nСписок пуст."
    now = time.time()
    result = []
    for i, uid in enumerate(senior_admins, 1):
        first_name, last_name = get_user_info(uid)
        status = "✅ В сети" if str(uid) in admins else "❌ Не в сети"
        result.append(f"{i}. [id{uid}|{first_name} {last_name}] — {status}")
    return "👤 Ст. Администрация:\n\n" + "\n".join(result)

def get_management_list():
    if not management: return "👑 Руководство:\n\nСписок пуст."
    now = time.time()
    result = []
    for i, uid in enumerate(management, 1):
        first_name, last_name = get_user_info(uid)
        status = "✅ В сети" if str(uid) in admins else "❌ Не в сети"
        result.append(f"{i}. [id{uid}|{first_name} {last_name}] — {status}")
    return "👑 Руководство:\n\n" + "\n".join(result)

# ================= Главный цикл =================
waiting_for_input = {}  # для руководства
for event in longpoll.listen():
    try:
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue
        msg = event.message
        peer_id = msg["peer_id"]
        user_id = str(msg["from_id"])
        text = msg.get("text", "")
        payload = msg.get("payload")
        if isinstance(payload, str):
            try: payload = json.loads(payload)
            except: payload = None
        action = payload.get("command") if payload else None

        # ================= Команды через кнопки =================
        if action == "entered":
            handle_entered(user_id, peer_id)
            continue
        if action == "exited":
            if user_id in admins:
                del admins[user_id]
                save_admins()
                send_message(peer_id, f"❌ Вы вышли из сети", user_id)
            else:
                send_message(peer_id, "⚠️ Вы не были в сети", user_id)
            continue
        if action == "junior_admins":
            send_message(peer_id, get_junior_admins_list(), user_id)
            continue
        if action == "senior_admins":
            send_message(peer_id, get_senior_admins_list(), user_id)
            continue
        if action == "management":
            send_message(peer_id, get_management_list(), user_id)
            continue

        # ================= Команды текста =================
        if text.startswith("/start"):
            send_message(peer_id, "👋 Добро пожаловать! Используйте кнопки ниже для навигации.", user_id)
        elif text.lower() == "вошел":
            handle_entered(user_id, peer_id)
        elif text.lower() == "вышел":
            if user_id in admins:
                del admins[user_id]
                save_admins()
                send_message(peer_id, "❌ Вы вышли из сети", user_id)
            else:
                send_message(peer_id, "⚠️ Вы не были в сети", user_id)

    except Exception as e:
        logger.error(f"Ошибка события: {e}", exc_info=True)
