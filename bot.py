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

# ================= В ПАМЯТИ =================
online = {}            # peer_id: {user_id: {"first_name", "last_name", "start_time"}}
management = set()     # Руководители
senior_admins = set()  # Ст. Администраторы
junior_admins = set()  # Мл. Администраторы

# ================= РОЛИ =================
def get_role(user_id):
    uid = int(user_id)
    if uid in management:
        return "Руководитель"
    if uid in senior_admins:
        return "Ст. Администратор"
    if uid in junior_admins:
        return "Мл. Администратор"
    return "Не назначен"

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

# ================= ВРЕМЯ =================
def format_duration(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}ч {m}м {s}с"

# ================= КЛАВИАТУРА =================
def build_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел(а)", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "entered"}))
    kb.add_button("❌ Вышел(а)", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "exited"}))
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
def enter_user(user_id, peer_id):
    if peer_id not in online:
        online[peer_id] = {}
    chat = online[peer_id]

    if user_id in chat:
        send_msg(peer_id, "⚠️ Вы уже в сети")
        return

    first, last = get_user_info(user_id)
    chat[user_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
    role = get_role(user_id)
    send_msg(peer_id, f"✅ {role} [id{user_id}|{first} {last}] Вошел(а)")

def exit_user(user_id, peer_id):
    chat = online.get(peer_id, {})
    if user_id not in chat:
        send_msg(peer_id, "⚠️ Вы не в сети")
        return
    info = chat[user_id]
    duration = format_duration(int(time.time() - info["start_time"]))
    role = get_role(user_id)
    send_msg(peer_id, f"❌ {role} [id{user_id}|{info['first_name']} {info['last_name']}] Вышел(а) Онлайн: {duration}")
    del chat[user_id]

def list_online(peer_id):
    chat = online.get(peer_id, {})
    now = time.time()
    if not chat:
        return "Никто не в сети"
    lines = [f"[id{uid}|{info['first_name']} {info['last_name']}] — {get_role(uid)} 🟢 {format_duration(int(now - info['start_time']))}" for uid, info in chat.items()]
    return "\n".join(lines)

def reset_online(peer_id):
    online[peer_id] = {}
    send_msg(peer_id, "✅ Онлайн очищен полностью")

def set_user(target_id, peer_id):
    if peer_id not in online:
        online[peer_id] = {}
    chat = online[peer_id]
    if target_id in chat:
        send_msg(peer_id, "⚠️ Пользователь уже в онлайн")
        return
    first, last = get_user_info(target_id)
    chat[target_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
    role = get_role(target_id)
    send_msg(peer_id, f"✅ {role} [id{target_id}|{first} {last}] добавлен в онлайн вручную")

def show_roles(peer_id):
    chat = online.get(peer_id, {})
    if not chat:
        send_msg(peer_id, "Никто не в сети")
        return
    lines = [f"[id{uid}|{info['first_name']} {info['last_name']}] — {get_role(uid)}" for uid, info in chat.items()]
    send_msg(peer_id, "📜 Онлайн с ролями:\n" + "\n".join(lines))

# ================= ПРОВЕРКА РУКОВОДИТЕЛЯ =================
def require_manager(user_id, peer_id):
    if get_role(user_id) != "Руководитель":
        send_msg(peer_id, "⛔ Недостаточно прав")
        return False
    return True

def get_target(text):
    parts = text.split()
    if len(parts) < 2:
        return None
    return parse_user_input(parts[1])

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

    # ===== КОМАНДЫ =====
    if text_lower.startswith("/start"):
        send_msg(peer_id, "👋 Здравствуйте! Это ваш помощник для контроля активности админов. Начнем работу!")
        continue

    if text_lower.startswith("/ahelp"):
        if not require_manager(user_id, peer_id): continue
        help_text = (
            "📜 Команды для Руководителей:\n\n"
            "/addmoder @ник — назначить Мл. Администратором\n"
            "/unmoder @ник — снять Мл. Администратора\n"
            "/addadmins @ник — назначить Ст. Администратором\n"
            "/unadmin @ник — снять Ст. Администратора\n"
            "/addmanager @ник — добавить в Руководство\n"
            "/unmanager @ник — снять из Руководства\n"
            "/astaff — показать всех онлайн с ролями\n"
            "/setuser @ник — добавить пользователя в онлайн вручную\n"
            "/resetonline — полностью очистить онлайн\n"
            "✅ Вошел(а) — отметить себя в сети\n"
            "❌ Вышел(а) — отметить себя оффлайн\n"
            "🌐 Общий онлайн — посмотреть всех онлайн"
        )
        send_msg(peer_id, help_text)
        continue

    if text_lower.startswith("/astaff"):
        if not require_manager(user_id, peer_id): continue
        show_roles(peer_id)
        continue

    if text_lower.startswith("/setuser"):
        if not require_manager(user_id, peer_id): continue
        target_id = get_target(text)
        if not target_id:
            send_msg(peer_id, "❌ Использование: /setuser @id")
            continue
        set_user(target_id, peer_id)
        continue

    if text_lower.startswith("/resetonline"):
        if not require_manager(user_id, peer_id): continue
        reset_online(peer_id)
        continue

    # ===== КНОПКИ =====
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

    # ===== ТЕКСТ =====
    if "вошел" in text_lower:
        enter_user(user_id, peer_id)
    elif "вышел" in text_lower:
        exit_user(user_id, peer_id)
