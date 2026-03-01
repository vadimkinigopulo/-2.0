import os
import json
import time
import logging
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
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

if not TOKEN or not GROUP_ID:
    logger.error("VK_TOKEN или GROUP_ID не указаны в .env")
    exit(1)

try:
    GROUP_ID = int(GROUP_ID)
except ValueError:
    logger.error("GROUP_ID должен быть числом")
    exit(1)

# ================= Инициализация VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Google Sheets =================
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open("VK_Bot_Roles").sheet1  # название таблицы

def get_role(user_id):
    records = sheet.get_all_records()
    for row in records:
        if str(row['user_id']) == str(user_id):
            return row['role']
    return "Гость"

def get_name(user_id):
    records = sheet.get_all_records()
    for row in records:
        if str(row['user_id']) == str(user_id):
            first = row.get('first_name', 'Неизвестно')
            last = row.get('last_name', 'Неизвестно')
            return first, last
    # fallback через VK API
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

# ================= Файлы для онлайн =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
ONLINE_FILE = os.path.join(DATA_DIR, "online.json")

def load_online():
    try:
        if os.path.exists(ONLINE_FILE):
            with open(ONLINE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки {ONLINE_FILE}: {e}")
    return {}

def save_online(data):
    try:
        with open(ONLINE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {ONLINE_FILE}: {e}")

online = load_online()  # {peer_id: {user_id: {"start_time", "first_name", "last_name"}}}

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
def send_msg(peer_id, text, user_id=None, sticker_id=None):
    if user_id:
        role = get_role(user_id)
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

def list_online_peer(peer_id):
    now = time.time()
    lines = []
    count = 0
    if str(peer_id) not in online:
        return "👥 Никто не онлайн.", 0
    for uid, info in online[str(peer_id)].items():
        start_time = info.get("start_time", now)
        online_str = format_duration(int(now - start_time))
        first = info.get('first_name', 'Неизвестно')
        last = info.get('last_name', 'Неизвестно')
        lines.append(f"[id{uid}|{first} {last}] — 🟢 {online_str}")
        count += 1
    return "👥 Онлайн:\n" + "\n".join(lines), count

def list_all_online():
    total_count = 0
    text_list = []
    for peer_id in online.keys():
        text, count = list_online_peer(peer_id)
        text_list.append(f"Чат {peer_id}:\n{text}")
        total_count += count
    text_list.append(f"\nОбщее количество онлайн: {total_count}")
    return "\n\n".join(text_list)

# ================= Вход/выход =================
def enter_user(user_id, peer_id):
    peer_str = str(peer_id)
    if peer_str not in online:
        online[peer_str] = {}
    if user_id in online[peer_str]:
        send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
        return
    first, last = get_name(user_id)
    online[peer_str][user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
    save_online(online)
    role = get_role(user_id)
    if role == "Руководитель":
        send_msg(peer_id, f"👑 {role} [id{user_id}|{first} {last}] вошел в сеть! ✅", user_id)
    else:
        send_msg(peer_id, f"✅ {role} [id{user_id}|{first} {last}] вошел в сеть", user_id)

def exit_user(user_id, peer_id):
    now = time.time()
    peer_str = str(peer_id)
    if peer_str not in online or user_id not in online[peer_str]:
        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
        return
    info = online[peer_str][user_id]
    first = info.get('first_name', 'Неизвестно')
    last = info.get('last_name', 'Неизвестно')
    start_time = info.get('start_time', now)
    duration_str = format_duration(int(now - start_time))
    del online[peer_str][user_id]
    save_online(online)
    send_msg(peer_id, f"❌ [id{user_id}|{first} {last}] вышел из сети. Провел(а) онлайн: {duration_str}", user_id)

# ================= Главный цикл =================
logger.info("Бот запущен...")

waiting_input = {}  # для команд руководителя

while True:
    try:
        for event in longpoll.listen():
            try:
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
                        if isinstance(payload, str):
                            payload_data = json.loads(payload)
                        else:
                            payload_data = payload
                        action = payload_data.get("cmd")
                    except:
                        pass

                # Старт
                if text.lower() == "/start":
                    send_msg(peer_id, "👋 Привет! Добро пожаловать в группу Логирования!", user_id)
                    continue

                # Payload
                if action:
                    role = get_role(user_id)
                    if action == "entered":
                        enter_user(user_id, peer_id)
                    elif action == "exited":
                        exit_user(user_id, peer_id)
                    elif action == "all_online":
                        send_msg(peer_id, list_all_online(), user_id)
                    continue

                # Текстовые команды
                if text.lower() == "вошел":
                    enter_user(user_id, peer_id)
                elif text.lower() == "вышел":
                    exit_user(user_id, peer_id)

            except Exception as e:
                logger.error(f"Ошибка обработки события: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Критическая ошибка в главном цикле: {e}", exc_info=True)
        logger.info("Перезапуск через 5 секунд...")
        time.sleep(5)
