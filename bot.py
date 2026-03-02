import os
import json
import time
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

# ================= ЛОГИ =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= ЗАГРУЗКА .ENV =================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= ФАЙЛЫ =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")

# ================= JSON =================
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

admins = load_json(ADMINS_FILE, {})
senior_admins = load_json(SENIOR_FILE, [])
management = load_json(MANAGEMENT_FILE, [])

# ================= РОЛИ =================
def get_role(user_id):
    uid = int(user_id)
    if uid in management:
        return "Руководитель"
    if uid in senior_admins:
        return "Ст. Администратор"
    return "Мл. Администратор"

# ================= ПОЛЬЗОВАТЕЛЬ =================
def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

def parse_user_input(text):
    if text.startswith('[id') and '|' in text:
        return text.split('[id')[1].split('|')[0]
    if text.startswith('@id'):
        return text.replace('@id', '')
    if text.isdigit():
        return text
    return None

# ================= КЛАВИАТУРА =================
def build_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "entered"}))
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "exited"}))
    kb.add_line()
    kb.add_button("🌐 Общий онлайн", VkKeyboardColor.SECONDARY, payload=json.dumps({"cmd": "all_online"}))
    return kb.get_keyboard()

# ================= ОТПРАВКА =================
def send_msg(peer_id, text):
    vk.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id(),
        keyboard=build_keyboard()
    )

# ================= ОНЛАЙН =================
def get_chat_admins(peer_id):
    peer_id = str(peer_id)
    if peer_id not in admins:
        admins[peer_id] = {}
    return admins[peer_id]

def format_duration(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}ч {m}м {s}с"

def enter_user(user_id, peer_id):
    chat_admins = get_chat_admins(peer_id)
    if user_id in chat_admins:
        send_msg(peer_id, "⚠️ Вы уже в сети")
        return

    first, last = get_user_info(user_id)
    chat_admins[user_id] = {
        "first_name": first,
        "last_name": last,
        "start_time": time.time()
    }

    save_json(ADMINS_FILE, admins)
    role = get_role(user_id)
    send_msg(peer_id, f"✅ {role} [id{user_id}|{first} {last}] вошел в сеть!")

def exit_user(user_id, peer_id):
    chat_admins = get_chat_admins(peer_id)
    if user_id not in chat_admins:
        send_msg(peer_id, "⚠️ Вы не в сети")
        return

    info = chat_admins[user_id]
    duration = format_duration(int(time.time() - info["start_time"]))
    role = get_role(user_id)

    send_msg(peer_id, f"❌ {role} [id{user_id}|{info['first_name']} {info['last_name']}] вышел. Онлайн: {duration}")

    del chat_admins[user_id]
    save_json(ADMINS_FILE, admins)

def list_online(peer_id):
    chat_admins = get_chat_admins(peer_id)
    if not chat_admins:
        return "❌ Никто не в сети"

    now = time.time()
    text = "🌐 Онлайн:\n\n"

    for uid, info in chat_admins.items():
        duration = format_duration(int(now - info["start_time"]))
        text += f"[id{uid}|{info['first_name']} {info['last_name']}] — 🟢 {duration}\n"

    text += f"\nОбщее количество: {len(chat_admins)}"
    return text

# ================= ГЛАВНЫЙ ЦИКЛ =================
logger.info("Бот запущен...")

for event in longpoll.listen():
    if event.type != VkBotEventType.MESSAGE_NEW:
        continue

    msg = event.message
    user_id = str(msg["from_id"])
    peer_id = msg["peer_id"]
    text = msg.get("text", "")
    payload = msg.get("payload")

    text_lower = text.lower()

    # ================= КОМАНДЫ =================
    def require_manager():
        if get_role(user_id) != "Руководитель":
            send_msg(peer_id, "⛔ Недостаточно прав")
            return False
        return True

    def get_target():
        parts = text.split()
        if len(parts) < 2:
            send_msg(peer_id, "❌ Использование: /команда @пользователь")
            return None
        return parse_user_input(parts[1])

    if text_lower.startswith("/addmoder"):
        if not require_manager(): continue
        target_id = get_target()
        if not target_id: continue

        first, last = get_user_info(target_id)
        chat_admins = get_chat_admins(peer_id)
        chat_admins[target_id] = {
            "first_name": first,
            "last_name": last,
            "start_time": time.time()
        }
        save_json(ADMINS_FILE, admins)
        send_msg(peer_id, f"✅ [id{target_id}|{first} {last}] назначен Мл. Администратором")
        continue

    if text_lower.startswith("/addmanager"):
        if not require_manager(): continue
        target_id = get_target()
        if not target_id: continue

        tid = int(target_id)
        if tid not in management:
            management.append(tid)
            save_json(MANAGEMENT_FILE, management)

        first, last = get_user_info(target_id)
        send_msg(peer_id, f"👑 [id{target_id}|{first} {last}] добавлен в руководство")
        continue

    # ================= КНОПКИ =================
    if payload:
        payload = json.loads(payload)
        cmd = payload.get("cmd")

        if cmd == "entered":
            enter_user(user_id, peer_id)
        elif cmd == "exited":
            exit_user(user_id, peer_id)
        elif cmd == "all_online":
            send_msg(peer_id, list_online(peer_id))
        continue

    # ================= ТЕКСТ =================
    if "вошел" in text_lower:
        enter_user(user_id, peer_id)

    elif "вышел" in text_lower:
        exit_user(user_id, peer_id)
