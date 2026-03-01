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
GROUP_ID = os.getenv("GROUP_ID")

if not TOKEN or not GROUP_ID:
    logger.error("VK_TOKEN или GROUP_ID не указаны в .env")
    exit(1)

GROUP_ID = int(GROUP_ID)

# ================= Инициализация VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")

def load_json(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

admins = load_json(ADMINS_FILE, {})  # {peer_id: {user_id: {...}}}
senior_admins = load_json(SENIOR_FILE, [])
management = load_json(MANAGEMENT_FILE, [])

def save_admins():
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f, ensure_ascii=False, indent=2)

def save_senior():
    with open(SENIOR_FILE, "w", encoding="utf-8") as f:
        json.dump(senior_admins, f)

def save_management():
    with open(MANAGEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(management, f)

# ================= ВАЖНО: разделение по чатам =================
def get_chat_admins(peer_id):
    peer_id = str(peer_id)
    if peer_id not in admins:
        admins[peer_id] = {}
    return admins[peer_id]

# ================= Утилиты =================
def get_user_info(user_id):
    user = vk.users.get(user_ids=user_id)[0]
    return user["first_name"], user["last_name"]

def get_role(user_id):
    uid = int(user_id)
    if uid in management:
        return "Руководитель"
    elif uid in senior_admins:
        return "Ст. Администратор"
    else:
        return "Мл. Администратор"

# ================= Клавиатура =================
def build_keyboard(role):
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "entered"}))
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "exited"}))
    kb.add_line()
    kb.add_button("🌐 Общий онлайн", VkKeyboardColor.SECONDARY, payload=json.dumps({"cmd": "all_online"}))
    return kb.get_keyboard()

def send_msg(peer_id, text, user_id=None):
    keyboard = build_keyboard(get_role(user_id)) if user_id else VkKeyboard.get_empty_keyboard()
    vk.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id(),
        keyboard=keyboard
    )

# ================= Онлайн =================
def format_duration(sec):
    return f"{sec//3600}ч {(sec%3600)//60}м {sec%60}с"

def enter_user(user_id, peer_id):
    chat_admins = get_chat_admins(peer_id)

    if user_id in chat_admins:
        send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
        return

    first, last = get_user_info(user_id)
    chat_admins[user_id] = {
        "first_name": first,
        "last_name": last,
        "start_time": time.time()
    }

    save_admins()
    role = get_role(user_id)

    if role == "Руководитель":
        send_msg(peer_id, f"👑 {role} [id{user_id}|{first} {last}] вошел в сеть!", user_id)
    else:
        send_msg(peer_id, f"✅ {role} [id{user_id}|{first} {last}] вошел в сеть", user_id)

def exit_user(user_id, peer_id):
    chat_admins = get_chat_admins(peer_id)
    now = time.time()

    if user_id not in chat_admins:
        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
        return

    info = chat_admins[user_id]
    duration = format_duration(int(now - info["start_time"]))

    send_msg(peer_id, f"❌ [id{user_id}|{info['first_name']} {info['last_name']}] вышел. Онлайн: {duration}", user_id)

    del chat_admins[user_id]
    save_admins()

def list_all_online(peer_id):
    chat_admins = get_chat_admins(peer_id)
    now = time.time()

    if not chat_admins:
        return "❌ Никого нет онлайн"

    lines = []
    for uid, info in chat_admins.items():
        online = format_duration(int(now - info["start_time"]))
        lines.append(f"[id{uid}|{info['first_name']} {info['last_name']}] — 🟢 {online}")

    return "🌐 Онлайн:\n" + "\n".join(lines) + f"\n\nВсего онлайн: {len(chat_admins)}"

# ================= Основной цикл =================
logger.info("Бот запущен")

while True:
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            msg = event.message
            user_id = str(msg["from_id"])
            peer_id = msg["peer_id"]
            text = msg.get("text", "")
            payload = msg.get("payload")

            action = None
            if payload:
                payload = json.loads(payload)
                action = payload.get("cmd")

            if text.lower() == "/start":
                send_msg(peer_id, "👋 Привет! Добро пожаловать в группу Логирования!", user_id)

            if action == "entered":
                enter_user(user_id, peer_id)

            elif action == "exited":
                exit_user(user_id, peer_id)

            elif action == "all_online":
                send_msg(peer_id, list_all_online(peer_id), user_id)
