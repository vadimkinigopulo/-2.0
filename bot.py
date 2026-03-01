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

try:
    GROUP_ID = int(GROUP_ID)
except ValueError:
    logger.error("GROUP_ID должен быть числом")
    exit(1)

# ================= Инициализация VK =================
vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

# ================= Файлы для хранения =================
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
    try:
        with open(ADMINS_FILE, "w", encoding="utf-8") as f:
            json.dump(admins, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения admins: {e}")

def save_senior():
    try:
        with open(SENIOR_FILE, "w", encoding="utf-8") as f:
            json.dump(senior_admins, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения senior: {e}")

def save_management():
    try:
        with open(MANAGEMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(management, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения management: {e}")

# ================= Вспомогательные функции =================
def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)[0]
        return user["first_name"], user["last_name"]
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
        return "Неизвестно", "Неизвестно"

def parse_user_input(input_text):
    try:
        input_text = input_text.strip()
        if not input_text:
            return None
        if input_text.startswith('@'):
            input_text = input_text[1:]
        if input_text.startswith('[id') and '|' in input_text:
            return input_text.split('[id')[1].split('|')[0]
        if 'vk.com/' in input_text:
            parts = input_text.split('vk.com/')[1].split('/')[0]
            if parts.startswith('id'):
                return parts[2:]
            try:
                users = vk.users.get(user_ids=parts)
                if users:
                    return str(users[0]['id'])
            except:
                return None
        if input_text.isdigit():
            return input_text
        return None
    except Exception as e:
        logger.error(f"Ошибка парсинга ввода: {e}")
        return None

def get_role(user_id):
    try:
        uid = int(user_id)
        if uid in management:
            return "Руководитель"
        elif uid in senior_admins:
            return "Ст. Администратор"
        elif str(uid) in admins:
            return "Мл. Администратор"
        return "Гость"
    except:
        return "Гость"

# ================= Клавиатура =================
def build_keyboard(role):
    try:
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
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры: {e}")
        return VkKeyboard.get_empty_keyboard()

# ================= Отправка сообщений =================
def send_msg(peer_id, text, target_user_id=None, sticker_id=None):
    try:
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
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

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

# ================= Ожидание ввода от руководства =================
waiting_input = {}

# ================= Главный цикл =================
logger.info("Бот запущен...")

while True:
    try:
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

                    # /start
                    if text.lower() == "/start":
                        send_msg(peer_id, "👋 Привет! Добро пожаловать в группу Логирования!", user_id)
                        continue

                    # payload
                    if action:
                        role = get_role(user_id)
                        if action == "entered":
                            enter_user(user_id, peer_id)
                        elif action == "exited":
                            exit_user(user_id, peer_id)
                        elif action == "all_online":
                            send_msg(peer_id, list_all_online(), user_id)

                        # Управление ролями
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
                        target_id = parse_user_input(text)
                        if not target_id:
                            send_msg(peer_id, "❌ Не удалось распознать пользователя. Отправьте ID или ссылку.", user_id)
                            del waiting_input[user_id]
                            continue
                        first, last = get_user_info(target_id)
                        target_name = f"[id{target_id}|{first} {last}]"

                        # Добавление/удаление
                        if act == "add_junior":
                            if target_id in admins:
                                send_msg(peer_id, f"⚠️ {target_name} уже Мл. Администратор", user_id)
                            else:
                                admins[target_id] = {"first_name": first, "last_name": last, "start_time": time.time()}
                                save_admins()
                                send_msg(peer_id, f"✅ {target_name} назначен Мл. Администратором", user_id)
                        elif act == "remove_junior":
                            if target_id not in admins:
                                send_msg(peer_id, f"⚠️ {target_name} не является Мл. Администратором", user_id)
                            else:
                                del admins[target_id]
                                save_admins()
                                send_msg(peer_id, f"❌ {target_name} удален из Мл. Администраторов", user_id)
                        elif act == "add_senior":
                            target_id_int = int(target_id)
                            if target_id_int in senior_admins:
                                send_msg(peer_id, f"⚠️ {target_name} уже Ст. Администратор", user_id)
                            else:
                                senior_admins.append(target_id_int)
                                save_senior()
                                send_msg(peer_id, f"✅ {target_name} назначен Ст. Администратором", user_id)
                        elif act == "remove_senior":
                            target_id_int = int(target_id)
                            if target_id_int not in senior_admins:
                                send_msg(peer_id, f"⚠️ {target_name} не Ст. Администратор", user_id)
                            else:
                                senior_admins.remove(target_id_int)
                                save_senior()
                                send_msg(peer_id, f"❌ {target_name} удален из Ст. Администраторов", user_id)
                        elif act == "add_management":
                            target_id_int = int(target_id)
                            if target_id_int in management:
                                send_msg(peer_id, f"⚠️ {target_name} уже Руководитель", user_id)
                            else:
                                management.append(target_id_int)
                                save_management()
                                send_msg(peer_id, f"👑 {target_name} назначается Руководителем!", user_id, sticker_id=145)
                        elif act == "remove_management":
                            target_id_int = int(target_id)
                            if target_id_int not in management:
                                send_msg(peer_id, f"⚠️ {target_name} не руководство", user_id)
                            else:
                                management.remove(target_id_int)
                                save_management()
                                send_msg(peer_id, f"❌ {target_name} удален из руководства", user_id)

                        del waiting_input[user_id]
                        continue

                    # Текст без payload
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
