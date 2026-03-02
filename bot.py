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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= ТОКЕНЫ =================
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
SYSTEM_MANAGEMENT_FILE = os.path.join(DATA_DIR, "system_management.json")

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
system_management = load_json(SYSTEM_MANAGEMENT_FILE, [])

# ================= ВСПОМОГАТЕЛЬНЫЕ =================
def get_chat_admins(peer_id):
    peer_id = str(peer_id)
    if peer_id not in admins:
        admins[peer_id] = {}
    return admins[peer_id]

def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except:
        return "Неизвестно", "Неизвестно"

def parse_user_input(text):
    text = text.strip()
    if text.startswith('[id') and '|' in text:
        return text.split('[id')[1].split('|')[0]
    if text.isdigit():
        return text
    return None

def get_role(user_id):
    uid = int(user_id)
    if uid in management:
        return "Руководитель"
    elif uid in senior_admins:
        return "Ст. Администратор"
    else:
        return "Мл. Администратор"

def format_duration(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}ч {m}м {s}с"

# ================= КЛАВА =================
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

def send_msg(peer_id, text, user_id=None, sticker_id=None):
    role = get_role(user_id) if user_id else None
    keyboard = build_keyboard(role) if role else VkKeyboard.get_empty_keyboard()

    params = {
        "peer_id": peer_id,
        "message": text,
        "random_id": get_random_id(),
        "keyboard": keyboard
    }

    if sticker_id:
        params["sticker_id"] = sticker_id

    vk.messages.send(**params)

# ================= ОНЛАЙН =================
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

    save_json(ADMINS_FILE, admins)
    role = get_role(user_id)

    send_msg(peer_id, f"{'👑' if role=='Руководитель' else '✅'} {role} [id{user_id}|{first} {last}] вошел в сеть!", user_id)

def exit_user(user_id, peer_id):
    chat_admins = get_chat_admins(peer_id)

    if user_id not in chat_admins:
        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
        return

    info = chat_admins[user_id]
    duration = format_duration(int(time.time() - info["start_time"]))
    role = get_role(user_id)

    text = f"{role} [id{user_id}|{info['first_name']} {info['last_name']}] вышел из сети. Провел время в сети: {duration}"

    if role == "Руководитель":
        send_msg(peer_id, f"👑 {text}", user_id, sticker_id=20001)
    else:
        send_msg(peer_id, text, user_id)

    del chat_admins[user_id]
    save_json(ADMINS_FILE, admins)

# ================= ОБЩИЙ ОНЛАЙН =================
def list_all_online(peer_id):
    chat_admins = get_chat_admins(peer_id)
    now = time.time()

    # Руководители
    leaders = [uid for uid in management if str(uid) in chat_admins]
    if leaders:
        leader_text = "👑 Руководители онлайн:\n" + "\n".join(
            f"[id{uid}|{chat_admins[str(uid)]['first_name']} {chat_admins[str(uid)]['last_name']}] — 🟢 {format_duration(int(now - chat_admins[str(uid)]['start_time']))}"
            for uid in leaders
        )
    else:
        leader_text = "👑 Руководители: Нет в сети"

    # Ст админы
    seniors = [uid for uid in senior_admins if str(uid) in chat_admins]
    if seniors:
        senior_text = "👤 Ст. Администраторы онлайн:\n" + "\n".join(
            f"[id{uid}|{chat_admins[str(uid)]['first_name']} {chat_admins[str(uid)]['last_name']}] — 🟢 {format_duration(int(now - chat_admins[str(uid)]['start_time']))}"
            for uid in seniors
        )
    else:
        senior_text = "👤 Ст. Администраторы: Нет в сети"

    # Мл админы
    juniors = [uid for uid in chat_admins if int(uid) not in management and int(uid) not in senior_admins]
    if juniors:
        junior_text = "👥 Мл. Администраторы онлайн:\n" + "\n".join(
            f"[id{uid}|{chat_admins[uid]['first_name']} {chat_admins[uid]['last_name']}] — 🟢 {format_duration(int(now - chat_admins[uid]['start_time']))}"
            for uid in juniors
        )
    else:
        junior_text = "👥 Мл. Администраторы: Нет в сети"

    total = len(chat_admins)

    return f"{leader_text}\n\n{senior_text}\n\n{junior_text}\n\nОбщее количество онлайн: {total}"

# ================= ОЖИДАНИЕ =================
waiting_input = {}

# ================= ЗАПУСК =================
logger.info("Бот запущен...")

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
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    action = payload.get("cmd")

                # старт
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
                        send_msg(peer_id, list_all_online(peer_id), user_id)

                    elif action in ["add_junior","remove_junior","add_senior","remove_senior","add_management","remove_management"]:
                        if role != "Руководитель":
                            send_msg(peer_id, "⛔ Недостаточно прав", user_id)
                            continue

                        waiting_input[user_id] = action
                        send_msg(peer_id, "📩 Отправьте ID или ссылку пользователя", user_id)

                    continue

                # ввод
                if user_id in waiting_input:
                    act = waiting_input[user_id]
                    target_id = parse_user_input(text)

                    if not target_id:
                        send_msg(peer_id, "❌ Ошибка ID", user_id)
                        del waiting_input[user_id]
                        continue

                    target_id_int = int(target_id)

                    if act == "remove_management" and target_id_int in system_management:
                        send_msg(peer_id, "⛔ Нельзя снять системного руководителя", user_id)
                        del waiting_input[user_id]
                        continue

                    first, last = get_user_info(target_id)
                    name = f"[id{target_id}|{first} {last}]"

                    if act == "add_management":
                        if target_id_int not in management:
                            management.append(target_id_int)
                            save_json(MANAGEMENT_FILE, management)
                            send_msg(peer_id, f"✅ {name} назначен Руководителем", user_id)

                    elif act == "remove_management":
                        if target_id_int in management:
                            management.remove(target_id_int)
                            save_json(MANAGEMENT_FILE, management)
                            send_msg(peer_id, f"❌ {name} удален из руководства", user_id)

                    del waiting_input[user_id]

            except Exception as e:
                logger.error(e, exc_info=True)

    except Exception as e:
        logger.error("CRITICAL", exc_info=True)
        time.sleep(5)
