import os
import json
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

SENIOR_FILE = os.path.join(DATA_DIR, "senior_admins.json")
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")
JUNIOR_FILE = os.path.join(DATA_DIR, "junior_admins.json")  # для Мл. Админов

# ================= JSON =================
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

senior_admins = load_json(SENIOR_FILE, {})
management = load_json(MANAGEMENT_FILE, {})
junior_admins = load_json(JUNIOR_FILE, {})

# ================= ПОЛЬЗОВАТЕЛЬ =================
def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return f"{user['first_name']} {user['last_name']}"
    except:
        return "Неизвестно"

def parse_user_input(text):
    if text.startswith('[id') and '|' in text:
        return text.split('[id')[1].split('|')[0]
    if text.startswith('@id'):
        return text.replace('@id', '')
    if text.isdigit():
        return text
    return None

# ================= РОЛИ =================
def get_role(user_id, peer_id):
    uid = str(user_id)
    peer = str(peer_id)
    if peer in management and uid in management[peer]:
        return "Руководитель"
    if peer in senior_admins and uid in senior_admins[peer]:
        return "Ст. Администратор"
    if peer in junior_admins and uid in junior_admins[peer]:
        return "Мл. Администратор"
    return None

# ================= КЛАВИАТУРА =================
def build_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел(а)", VkKeyboardColor.POSITIVE)
    kb.add_button("❌ Вышел(а)", VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("🌐 Общий онлайн", VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

# ================= ОТПРАВКА =================
def send_msg(peer_id, text):
    vk.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=get_random_id(),
        keyboard=build_keyboard()
    )

# ================= ИНИЦИАЛИЗАЦИЯ =================
def ensure_peer(peer_id):
    peer = str(peer_id)
    for dic in [management, senior_admins, junior_admins]:
        if peer not in dic:
            dic[peer] = []

# ================= ГЛАВНЫЙ ЦИКЛ =================
logger.info("Бот запущен...")

for event in longpoll.listen():
    if event.type != VkBotEventType.MESSAGE_NEW:
        continue

    msg = event.message
    user_id = str(msg["from_id"])
    peer_id = msg["peer_id"]
    text = msg.get("text", "").lower()

    ensure_peer(peer_id)

    def get_target():
        parts = msg.get("text", "").split()
        if len(parts) < 2:
            send_msg(peer_id, "❌ Использование: /команда @пользователь")
            return None
        return parse_user_input(parts[1])

    # ===== /start =====
    if text.startswith("/start"):
        send_msg(peer_id, "👋 Здравствуйте! Это помощник для управления ролями админов. Начнем работу!")
        continue

    # ===== /astaff =====
    if text.startswith("/astaff"):
        # показать только роли
        peer = str(peer_id)
        lines = []

        # Руководители
        leaders = management.get(peer, [])
        if leaders:
            leader_names = [f"[id{uid}|{get_user_info(uid)}]" for uid in leaders]
            lines.append("👑 Руководители:\n" + "\n".join(leader_names))
        else:
            lines.append("👑 Руководителей нет")

        # Старшие админы
        seniors = senior_admins.get(peer, [])
        if seniors:
            senior_names = [f"[id{uid}|{get_user_info(uid)}]" for uid in seniors]
            lines.append("👤 Ст. Администраторы:\n" + "\n".join(senior_names))
        else:
            lines.append("👤 Ст. Администрации нет")

        # Младшие админы
        juniors = junior_admins.get(peer, [])
        if juniors:
            junior_names = [f"[id{uid}|{get_user_info(uid)}]" for uid in juniors]
            lines.append("👥 Мл. Администраторы:\n" + "\n".join(juniors_names))
        else:
            lines.append("👥 Мл. Администрации нет")

        send_msg(peer_id, "\n\n".join(lines))
        continue

    # ===== команды добавления ролей =====
    if text.startswith("/addmanager"):
        target = get_target()
        if not target: continue
        if target not in management[str(peer_id)]:
            management[str(peer_id)].append(target)
            save_json(MANAGEMENT_FILE, management)
        send_msg(peer_id, f"✅ [id{target}|{get_user_info(target)}] добавлен в Руководство")
        continue

    if text.startswith("/unmanager"):
        target = get_target()
        if not target: continue
        if target in management[str(peer_id)]:
            management[str(peer_id)].remove(target)
            save_json(MANAGEMENT_FILE, management)
        send_msg(peer_id, f"❌ [id{target}|{get_user_info(target)}] снят из Руководства")
        continue

    if text.startswith("/addadmins"):
        target = get_target()
        if not target: continue
        if target not in senior_admins[str(peer_id)]:
            senior_admins[str(peer_id)].append(target)
            save_json(SENIOR_FILE, senior_admins)
        send_msg(peer_id, f"👤 [id{target}|{get_user_info(target)}] назначен Ст. Администратором")
        continue

    if text.startswith("/unadmin"):
        target = get_target()
        if not target: continue
        if target in senior_admins[str(peer_id)]:
            senior_admins[str(peer_id)].remove(target)
            save_json(SENIOR_FILE, senior_admins)
        send_msg(peer_id, f"❌ [id{target}|{get_user_info(target)}] снят со Ст. Администратора")
        continue

    if text.startswith("/addmoder"):
        target = get_target()
        if not target: continue
        if target not in junior_admins[str(peer_id)]:
            junior_admins[str(peer_id)].append(target)
            save_json(JUNIOR_FILE, junior_admins)
        send_msg(peer_id, f"✅ [id{target}|{get_user_info(target)}] назначен Мл. Администратором")
        continue

    if text.startswith("/unmoder"):
        target = get_target()
        if not target: continue
        if target in junior_admins[str(peer_id)]:
            junior_admins[str(peer_id)].remove(target)
            save_json(JUNIOR_FILE, junior_admins)
        send_msg(peer_id, f"❌ [id{target}|{get_user_info(target)}] снят с Мл. Администратора")
        continue
