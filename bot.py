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
from oauth2client.service_account import ServiceAccountCredentials

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
    raise ValueError("VK_TOKEN или GROUP_ID не указаны в .env")

GROUP_ID = int(GROUP_ID)

# ================= Инициализация VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Google Sheets =================
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
gc = gspread.authorize(creds)
sheet = gc.open("VK_Bot_Roles").sheet1  # Название таблицы

# ================= Файлы для хранения =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
ONLINE_FILE = os.path.join(DATA_DIR, "online.json")

# ================= Загрузка/сохранение онлайн =================
def load_online():
    if os.path.exists(ONLINE_FILE):
        try:
            with open(ONLINE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_online(data):
    try:
        with open(ONLINE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения online.json: {e}")

online = load_online()

# ================= Роли =================
def get_role(user_id):
    try:
        records = sheet.get_all_records()
        for row in records:
            if str(row["user_id"]) == str(user_id):
                return row.get("role", "Гость")
    except Exception as e:
        logger.error(f"Ошибка чтения Google Sheets: {e}")
    return "Гость"

# ================= VK =================
def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ч {m}м {s}с"

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
        kb.add_button("➕ Руководитель", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_management"}))
        kb.add_button("➖ Руководитель", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_management"}))
    return kb.get_keyboard()

def send_msg(peer_id, text, target_user_id=None, sticker_id=None):
    try:
        keyboard = build_keyboard(get_role(target_user_id)) if target_user_id else VkKeyboard.get_empty_keyboard()
        params = {
            "peer_id": peer_id,
            "message": text,
            "random_id": get_random_id(),
            "keyboard": keyboard
        }
        if sticker_id:
            params["sticker_id"] = sticker_id
        vk.messages.send(**params)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# ================= Вход/выход =================
def enter_user(user_id, peer_id):
    user_chat = online.setdefault(str(peer_id), {})
    if user_id in user_chat:
        send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
        return
    first, last = get_user_info(user_id)
    user_chat[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
    save_online(online)
    role = get_role(user_id)
    if role == "Руководитель":
        send_msg(peer_id, f"👑 {role} [id{user_id}|{first} {last}] успешно добавлен ✅", user_id)
    else:
        send_msg(peer_id, f"✅ {role} [id{user_id}|{first} {last}] вошел в сеть", user_id)

def exit_user(user_id, peer_id):
    user_chat = online.get(str(peer_id), {})
    if user_id not in user_chat:
        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
        return
    start_time = user_chat[user_id]["start_time"]
    first = user_chat[user_id]["first_name"]
    last = user_chat[user_id]["last_name"]
    duration = format_duration(int(time.time() - start_time))
    del user_chat[user_id]
    save_online(online)
    send_msg(peer_id, f"❌ [id{user_id}|{first} {last}] вышел из сети. Провел(а) онлайн: {duration}", user_id)

# ================= Главное =================
waiting_input = {}

logger.info("Бот запущен...")

while True:
    try:
        for event in longpoll.listen():
            if event.type != VkBotEventType.MESSAGE_NEW:
                continue
            msg = event.message
            user_id = str(msg["from_id"])
            peer_id = msg["peer_id"]
            text = msg.get("text", "")
            payload = msg.get("payload")

            action = None
            if payload:
                try:
                    payload_data = json.loads(payload) if isinstance(payload, str) else payload
                    action = payload_data.get("cmd")
                except:
                    pass

            # /start
            if text.lower() == "/start":
                send_msg(peer_id, "👋 Привет! Добро пожаловать в группу Логирования!", user_id)
                continue

            # payload команды
            if action:
                role = get_role(user_id)
                if action == "entered":
                    enter_user(user_id, peer_id)
                elif action == "exited":
                    exit_user(user_id, peer_id)
                elif action == "all_online":
                    online_list = []
                    for chat_id, users in online.items():
                        for uid, info in users.items():
                            duration = format_duration(int(time.time() - info["start_time"]))
                            online_list.append(f"[id{uid}|{info['first_name']} {info['last_name']}] — {duration}")
                    send_msg(peer_id, "👥 Онлайн:\n" + "\n".join(online_list), user_id)
                continue

            # обычный текст
            if text.lower() == "вошел":
                enter_user(user_id, peer_id)
            elif text.lower() == "вышел":
                exit_user(user_id, peer_id)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        time.sleep(5)
