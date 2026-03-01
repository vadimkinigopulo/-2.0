import os
import json
import time
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

import gspread
from google.oauth2.service_account import Credentials

import datetime

print("UTC:", datetime.datetime.utcnow())

# ================= Настройка логирования =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= Загрузка токенов =================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

if not TOKEN or not GROUP_ID:
    logger.error("VK_TOKEN или GROUP_ID не указаны в .env")
    exit(1)

GROUP_ID = int(GROUP_ID)

# ================= Инициализация VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы локального хранения =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")           # Мл. Администраторы онлайн
SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")   # Ст. Администраторы
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")  # Руководство

# ================= Загрузка данных =================
def load_json(file_path, default):
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки {file_path}: {e}")
    return default

admins = load_json(ADMINS_FILE, {})        # {user_id: {first_name, last_name, start_time}}
senior_admins = load_json(SENIOR_FILE, []) # [user_id]
management = load_json(MANAGEMENT_FILE, [])# [user_id]

# ================= Сохранение данных =================
def save_admins(): 
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f, ensure_ascii=False, indent=2)

def save_senior():
    with open(SENIOR_FILE, "w", encoding="utf-8") as f:
        json.dump(senior_admins, f, ensure_ascii=False, indent=2)

def save_management():
    with open(MANAGEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(management, f, ensure_ascii=False, indent=2)

# ================= Вспомогательные функции =================
def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

def get_role(user_id):
    uid = int(user_id)
    if uid in management:
        return "Руководитель"
    elif uid in senior_admins:
        return "Ст. Администратор"
    elif str(uid) in admins:
        return "Мл. Администратор"
    return "Гость"

# ================= Клавиатура =================
def build_keyboard(role):
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "entered"}))
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "exited"}))
    kb.add_line()
    kb.add_button("🌐 Общий онлайн", VkKeyboardColor.SECONDARY, payload=json.dumps({"cmd": "all_online"}))
    if role == "Руководитель":
        kb.add_line()
        kb.add_button("➕ Мл. Администратор", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_junior"}))
        kb.add_button("➖ Мл. Администратор", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_junior"}))
        kb.add_line()
        kb.add_button("➕ Ст. Администратор", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_senior"}))
        kb.add_button("➖ Ст. Администратор", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_senior"}))
        kb.add_line()
        kb.add_button("➕ Руководство", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_management"}))
        kb.add_button("➖ Руководство", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_management"}))
    return kb.get_keyboard()

# ================= Отправка сообщений =================
def send_msg(peer_id, text, target_user_id=None, sticker_id=None):
    if target_user_id is not None:
        role = get_role(target_user_id)
        keyboard = build_keyboard(role)
    else:
        keyboard = VkKeyboard.get_empty_keyboard()
    params = {
        "peer_id": peer_id,
        "message": text,
        "random_id": get_random_id(),
        "keyboard": keyboard
    }
    if sticker_id:
        params["sticker_id"] = sticker_id
    vk.messages.send(**params)

# ================= Онлайн функции =================
def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ч {m}м {s}с"

def list_junior():
    now = time.time()
    lines = []
    online_admins = {uid: info for uid, info in admins.items() if int(uid) not in senior_admins and int(uid) not in management}
    if not online_admins:
        return "👥 Мл. Администраторов нет онлайн.", 0
    for uid, info in online_admins.items():
        start_time = info['start_time']
        online_str = format_duration(int(now - start_time))
        first = info.get('first_name', 'Неизвестно')
        last = info.get('last_name', 'Неизвестно')
        lines.append(f"[id{uid}|{first} {last}] — 🟢 {online_str}")
    return "👥 Мл. Администраторы онлайн:\n" + "\n".join(lines), len(online_admins)

def list_senior():
    now = time.time()
    lines = []
    online_count = 0
    if not senior_admins:
        return "👤 Ст. Администраторов нет онлайн.", 0
    for uid in senior_admins:
        uid_str = str(uid)
        if uid_str in admins:
            start_time = admins[uid_str]['start_time']
            online_str = format_duration(int(now - start_time))
            status = f"🟢 {online_str}"
            online_count += 1
        else:
            status = "🔴 Не в сети"
        first, last = get_user_info(uid)
        lines.append(f"[id{uid}|{first} {last}] — {status}")
    return "👤 Ст. Администраторы:\n" + "\n".join(lines), online_count

def list_management():
    now = time.time()
    lines = []
    online_count = 0
    if not management:
        return "👑 Руководство отсутствует.", 0
    for uid in management:
        uid_str = str(uid)
        if uid_str in admins:
            start_time = admins[uid_str]['start_time']
            online_str = format_duration(int(now - start_time))
            status = f"🟢 {online_str}"
            online_count += 1
        else:
            status = "🔴 Не в сети"
        first, last = get_user_info(uid)
        lines.append(f"[id{uid}|{first} {last}] — {status}")
    return "👑 Руководство:\n" + "\n".join(lines), online_count

def list_all_online():
    management_text, management_count = list_management()
    senior_text, senior_count = list_senior()
    junior_text, junior_count = list_junior()
    total_online = management_count + senior_count + junior_count
    return f"{management_text}\n\n{senior_text}\n\n{junior_text}\n\nОбщее количество онлайн: {total_online}"

# ================= Вход/выход =================
def enter_user(user_id, peer_id):
    if user_id in admins:
        send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
        return
    first, last = get_user_info(user_id)
    admins[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
    save_admins()
    role = get_role(user_id)
    if role == "Руководитель":
        send_msg(peer_id, f"👑 {role} [id{user_id}|{first} {last}] вошел в сеть!", user_id)
    else:
        send_msg(peer_id, f"✅ {role} [id{user_id}|{first} {last}] вошел в сеть", user_id)

def exit_user(user_id, peer_id):
    now = time.time()
    if user_id not in admins:
        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
        return
    first = admins[user_id].get('first_name', 'Неизвестно')
    last = admins[user_id].get('last_name', 'Неизвестно')
    start_time = admins[user_id].get('start_time', now)
    duration_str = format_duration(int(now - start_time))
    del admins[user_id]
    save_admins()
    send_msg(peer_id, f"❌ [id{user_id}|{first} {last}] вышел из сети. Провел(а) онлайн: {duration_str}", user_id)

# ================= Ожидание ввода руководителя =================
waiting_input = {}

# ================= Подключение к Google Sheet =================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
# Подставь свой файл ключа
SERVICE_ACCOUNT_FILE = "credentials.json"  

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
sheet = gc.open("VK_Bot_Roles").sheet1  # Название таблицы

def update_roles_from_sheet():
    """Синхронизация ролей из Google Sheet в локальные словари"""
    global admins, senior_admins, management
    try:
        data = sheet.get_all_records()
        admins.clear()
        senior_admins.clear()
        management.clear()
        for row in data:
            uid = str(row['user_id'])
            role = row['role']
            first = row.get('first_name', 'Неизвестно')
            last = row.get('last_name', 'Неизвестно')
            if role == "Мл. Администратор":
                admins[uid] = {"first_name": first, "last_name": last, "start_time": time.time()}
            elif role == "Ст. Администратор":
                senior_admins.append(int(uid))
            elif role == "Руководитель":
                management.append(int(uid))
        save_admins()
        save_senior()
        save_management()
    except Exception as e:
        logger.error(f"Ошибка синхронизации с Google Sheet: {e}")

# ================= Главный цикл =================
logger.info("Бот запущен...")

while True:
    try:
        update_roles_from_sheet()  # Проверяем роли каждые 10 секунд
        for event in longpoll.listen():
            try:
                if event.type == VkBotEventType.MESSAGE_NEW:
                    msg = event.message
                    user_id = str(msg["from_id"])
                    peer_id = msg["peer_id"]
                    text = msg.get("text", "")
                    payload = msg.get("payload")
                    
                    action = None
                    if payload:
                        try:
                            if isinstance(payload, str):
                                payload_data = json.loads(payload)
                            else:
                                payload_data = payload
                            action = payload_data.get("cmd")
                        except Exception as e:
                            logger.error(f"Ошибка парсинга payload: {e}")

                    if text.lower() == "/start":
                        send_msg(peer_id, "👋 Привет! Добро пожаловать в группу Логирования!", user_id)
                        continue

                    if action:
                        role = get_role(user_id)
                        if action == "entered":
                            enter_user(user_id, peer_id)
                        elif action == "exited":
                            exit_user(user_id, peer_id)
                        elif action == "all_online":
                            send_msg(peer_id, list_all_online(), user_id)
                        # Управление ролями через бота
                        elif action in ["add_junior", "remove_junior", "add_senior", "remove_senior",
                                        "add_management", "remove_management"]:
                            if role != "Руководитель":
                                send_msg(peer_id, "⛔ Недостаточно прав", user_id)
                                continue
                            waiting_input[user_id] = action
                            send_msg(peer_id, "📩 Отправьте ID или ссылку администратора для изменения должности", user_id)
                        continue

                    # Ввод от руководителя
                    if user_id in waiting_input:
                        act = waiting_input[user_id]
                        # здесь можно добавить парсинг ID и изменение локальных словарей
                        del waiting_input[user_id]
                        continue

                    if text.lower() == "вошел":
                        enter_user(user_id, peer_id)
                    elif text.lower() == "вышел":
                        exit_user(user_id, peer_id)

            except Exception as e:
                logger.error(f"Ошибка обработки события: {e}", exc_info=True)
        time.sleep(10)  # пауза перед следующей проверкой Google Sheet
    except Exception as e:
        logger.error(f"Критическая ошибка в главном цикле: {e}", exc_info=True)
        time.sleep(5)
