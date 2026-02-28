import os
import json
import time
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ================= Настройка логирования =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= Загрузка токенов =================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

if not TOKEN or not GROUP_ID:
    logger.error("VK_TOKEN или GROUP_ID не указаны в .env")
    exit(1)

# ================= Инициализация VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы для хранения =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")           # младшие админы онлайн
SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")   # старшие админы
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")  # руководство

# ================= Загрузка данных =================
def load_json(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
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

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h and m:
        return f"{h}ч {m}м"
    elif h:
        return f"{h}ч"
    elif m:
        return f"{m}м"
    return "меньше минуты"

def parse_user_input(input_text):
    input_text = input_text.strip()
    if input_text.startswith('@'):
        input_text = input_text[1:]
    if input_text.startswith('[id') and '|' in input_text:
        return input_text.split('[id')[1].split('|')[0]
    if 'vk.com/' in input_text:
        parts = input_text.split('vk.com/')[1].split('/')[0]
        if parts.startswith('id'):
            return parts[2:]
        try:
            return str(vk.users.get(user_ids=parts)[0]['id'])
        except:
            return None
    if input_text.isdigit():
        return input_text
    return None

def get_role(user_id):
    uid = int(user_id)
    if uid in management:
        return "Руководство"
    elif uid in senior_admins:
        return "Старший админ"
    elif str(uid) in admins:
        return "Младший админ"
    return "Гость"

# ================= Клавиатура =================
def build_keyboard(user_id):
    role = get_role(user_id)
    kb = VkKeyboard(one_time=False)

    # Кнопки для всех
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd":"entered"}))
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd":"exited"}))
    kb.add_line()
    kb.add_button("👥 Мл. админы", VkKeyboardColor.SECONDARY, payload=json.dumps({"cmd":"junior"}))
    kb.add_button("👤 Ст. админы", VkKeyboardColor.PRIMARY, payload=json.dumps({"cmd":"senior"}))
    kb.add_line()
    kb.add_button("👑 Руководство", VkKeyboardColor.PRIMARY, payload=json.dumps({"cmd":"management"}))

    # Кнопки для руководства
    if role == "Руководство":
        kb.add_line()
        kb.add_button("➕ Мл. админ", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd":"add_junior"}))
        kb.add_button("➖ Мл. админ", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd":"remove_junior"}))
        kb.add_line()
        kb.add_button("➕ Ст. админ", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd":"add_senior"}))
        kb.add_button("➖ Ст. админ", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd":"remove_senior"}))
        kb.add_line()
        kb.add_button("➕ Руководство", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd":"add_management"}))
        kb.add_button("➖ Руководство", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd":"remove_management"}))

    return kb.get_keyboard()

# ================= Отправка сообщений =================
def send_msg(peer_id, text, user_id=None):
    vk.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id(),
        keyboard=build_keyboard(user_id) if user_id else None
    )

# ================= Онлайн списки =================
def list_junior():
    now = time.time()
    lines = []
    for uid, info in admins.items():
        online = now - info['start_time']
        lines.append(f"[id{uid}|{info['first_name']} {info['last_name']}] — 🕒 {format_time(online)}")
    if not lines: return "Младших админов нет онлайн."
    return "👥 Младшие админы онлайн:\n" + "\n".join(lines)

def list_senior():
    now = time.time()
    lines = []
    for uid in senior_admins:
        online = "✅" if str(uid) in admins else "❌"
        first, last = get_user_info(uid)
        lines.append(f"[id{uid}|{first} {last}] — {online}")
    if not lines: return "Старших админов нет."
    return "👤 Старшие админы:\n" + "\n".join(lines)

def list_management():
    now = time.time()
    lines = []
    for uid in management:
        online = "✅" if str(uid) in admins else "❌"
        first, last = get_user_info(uid)
        lines.append(f"[id{uid}|{first} {last}] — {online}")
    if not lines: return "Руководство отсутствует."
    return "👑 Руководство:\n" + "\n".join(lines)

# ================= Ожидание ввода от руководства =================
waiting_input = {}

# ================= Главный цикл =================
logger.info("Бот запущен...")
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
                    action = json.loads(payload).get("cmd")
                except:
                    action = None

            # ---------- /start ----------
            if text.lower() == "/start":
                send_msg(peer_id, "👋 Привет! Меню бота:")
                continue

            # ---------- Обработка payload ----------
            if action:
                role = get_role(user_id)

                if action == "entered":
                    if user_id in admins:
                        send_msg(peer_id, "⚠️ Вы уже вошли", user_id)
                    else:
                        first, last = get_user_info(user_id)
                        admins[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                        save_admins()
                        send_msg(peer_id, f"✅ Младший админ [id{user_id}|{first} {last}] вошел", user_id)
                
                elif action == "exited":
                    if user_id not in admins:
                        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
                    else:
                        first = admins[user_id]['first_name']
                        last = admins[user_id]['last_name']
                        del admins[user_id]
                        save_admins()
                        send_msg(peer_id, f"❌ [id{user_id}|{first} {last}] вышел из сети", user_id)
                
                elif action == "junior":
                    send_msg(peer_id, list_junior(), user_id)
                elif action == "senior":
                    send_msg(peer_id, list_senior(), user_id)
                elif action == "management":
                    send_msg(peer_id, list_management(), user_id)
                
                # ---------- Управление ролями (только руководство) ----------
                elif action.startswith(("add_", "remove_")):
                    if role != "Руководство":
                        send_msg(peer_id, "⛔ Недостаточно прав", user_id)
                        continue
                    waiting_input[user_id] = action
                    send_msg(peer_id, "Отправьте ID или ссылку пользователя для действия", user_id)
                continue

            # ---------- Ввод от руководителя ----------
            if user_id in waiting_input:
                act = waiting_input[user_id]
                target_id = parse_user_input(text)
                if not target_id:
                    send_msg(peer_id, "❌ Не удалось распознать пользователя", user_id)
                    continue
                first, last = get_user_info(target_id)
                target_name = f"{first} {last}"

                # Добавление/удаление
                if act == "add_junior":
                    if target_id in admins:
                        send_msg(peer_id, "⚠️ Уже младший админ", user_id)
                    else:
                        admins[target_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                        save_admins()
                        send_msg(peer_id, f"✅ {target_name} назначен младшим админом", user_id)
                elif act == "remove_junior":
                    if target_id not in admins:
                        send_msg(peer_id, "⚠️ Не является младшим админом", user_id)
                    else:
                        del admins[target_id]
                        save_admins()
                        send_msg(peer_id, f"❌ {target_name} удален из младших админов", user_id)
                elif act == "add_senior":
                    if int(target_id) in senior_admins:
                        send_msg(peer_id, "⚠️ Уже старший админ", user_id)
                    else:
                        senior_admins.append(int(target_id))
                        save_senior()
                        send_msg(peer_id, f"✅ {target_name} назначен старшим админом", user_id)
                elif act == "remove_senior":
                    if int(target_id) not in senior_admins:
                        send_msg(peer_id, "⚠️ Не старший админ", user_id)
                    else:
                        senior_admins.remove(int(target_id))
                        save_senior()
                        send_msg(peer_id, f"❌ {target_name} удален из старших админов", user_id)
                elif act == "add_management":
                    if int(target_id) in management:
                        send_msg(peer_id, "⚠️ Уже руководство", user_id)
                    else:
                        management.append(int(target_id))
                        save_management()
                        send_msg(peer_id, f"✅ {target_name} назначен руководством", user_id)
                elif act == "remove_management":
                    if int(target_id) not in management:
                        send_msg(peer_id, "⚠️ Не руководство", user_id)
                    else:
                        management.remove(int(target_id))
                        save_management()
                        send_msg(peer_id, f"❌ {target_name} удален из руководства", user_id)

                del waiting_input[user_id]
                continue

            # ---------- Текст без payload ----------
            if text.lower() == "вошел":
                if user_id in admins:
                    send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
                else:
                    first, last = get_user_info(user_id)
                    admins[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                    save_admins()
                    send_msg(peer_id, f"✅ Младший админ [id{user_id}|{first} {last}] вошел", user_id)
            elif text.lower() == "вышел":
                if user_id not in admins:
                    send_msg(peer_id, "⚠️ Вы не в сети", user_id)
                else:
                    first = admins[user_id]['first_name']
                    last = admins[user_id]['last_name']
                    del admins[user_id]
                    save_admins()
                    send_msg(peer_id, f"❌ [id{user_id}|{first} {last}] вышел", user_id)

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
