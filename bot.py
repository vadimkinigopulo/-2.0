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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= Загрузка токенов =================
load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")

# ================= Работа с JSON =================
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

# ================= Роли =================
def get_role(user_id: int):
    if user_id in management:
        return "Руководитель"
    elif user_id in senior_admins:
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

# ================= Отправка =================
def send_msg(peer_id, text, user_id=None):
    keyboard = VkKeyboard.get_empty_keyboard()

    if user_id is not None:
        role = get_role(int(user_id))
        keyboard = build_keyboard(role)

    vk.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id(),
        keyboard=keyboard
    )

# ================= Онлайн =================
def get_chat_admins(peer_id):
    peer_id = str(peer_id)
    if peer_id not in admins:
        admins[peer_id] = {}
    return admins[peer_id]

def enter_user(user_id: int, peer_id):
    chat_admins = get_chat_admins(peer_id)
    key = str(user_id)

    if key in chat_admins:
        send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
        return

    user = vk.users.get(user_ids=user_id)[0]
    chat_admins[key] = {
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "start_time": time.time()
    }

    save_json(ADMINS_FILE, admins)
    role = get_role(user_id)

    send_msg(
        peer_id,
        f"{'👑' if role=='Руководитель' else '✅'} {role} "
        f"[id{user_id}|{user['first_name']} {user['last_name']}] вошел в сеть!",
        user_id
    )

# ================= Главный цикл =================
logger.info("Бот запущен...")

while True:
    try:
        for event in longpoll.listen():

            if event.type != VkBotEventType.MESSAGE_NEW:
                continue

            msg = event.message
            user_id = int(msg["from_id"])
            peer_id = msg["peer_id"]
            text = msg.get("text", "")
            payload = msg.get("payload")

            action = None
            if payload:
                if isinstance(payload, str):
                    payload = json.loads(payload)
                action = payload.get("cmd")

            if text.lower() == "/start":
                send_msg(peer_id, "👋 Привет! Добро пожаловать!", user_id)
                continue

            if action == "entered":
                enter_user(user_id, peer_id)

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        time.sleep(5)
