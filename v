import os
import json
import time
import logging
import sqlite3
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
    logger.error("VK_TOKEN или GROUP_ID не указан в .env")
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

# ================= Инициализация базы данных =================
DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            start_time REAL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS senior_admins (
            user_id TEXT PRIMARY KEY
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS management (
            user_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    if fetch:
        result = c.fetchall()
    else:
        result = None
    conn.commit()
    conn.close()
    return result

# ================= Функции для работы с ролями =================
def get_role(user_id):
    if db_execute("SELECT 1 FROM management WHERE user_id=?", (str(user_id),), fetch=True):
        return "Р СѓРєРѕРІРѕРґРёС‚РµР»СЊ"
    elif db_execute("SELECT 1 FROM senior_admins WHERE user_id=?", (str(user_id),), fetch=True):
        return "РЎС‚. РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ"
    elif db_execute("SELECT 1 FROM admins WHERE user_id=?", (str(user_id),), fetch=True):
        return "РњР». РђРґРјРёРЅРёСЃС‚СЂР°С‚РѕСЂ"
    return "Р“РѕСЃС‚СЊ"

def add_junior(user_id, first, last):
    db_execute("INSERT OR REPLACE INTO admins (user_id, first_name, last_name, start_time) VALUES (?, ?, ?, ?)",
               (str(user_id), first, last, time.time()))

def remove_junior(user_id):
    db_execute("DELETE FROM admins WHERE user_id=?", (str(user_id),))

def add_senior(user_id):
    db_execute("INSERT OR REPLACE INTO senior_admins (user_id) VALUES (?)", (str(user_id),))

def remove_senior(user_id):
    db_execute("DELETE FROM senior_admins WHERE user_id=?", (str(user_id),))

def add_management(user_id):
    db_execute("INSERT OR REPLACE INTO management (user_id) VALUES (?)", (str(user_id),))

def remove_management(user_id):
    db_execute("DELETE FROM management WHERE user_id=?", (str(user_id),))

def get_admins():
    return {row[0]: {"first_name": row[1], "last_name": row[2], "start_time": row[3]} 
            for row in db_execute("SELECT * FROM admins", fetch=True)}

def get_senior_admins():
    return [row[0] for row in db_execute("SELECT * FROM senior_admins", fetch=True)]

def get_management():
    return [row[0] for row in db_execute("SELECT * FROM management", fetch=True)]

# ================= VK функции =================
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

def build_keyboard(role):
    try:
        kb = VkKeyboard(one_time=False)
        kb.add_button("вњ… Вашел", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "entered"}))
        kb.add_button("вќЊ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "exited"}))
        kb.add_line()
        kb.add_button("рџЊђ Общий онлайн", VkKeyboardColor.SECONDARY, payload=json.dumps({"cmd": "all_online"}))
        if role == "Р СѓРєРѕРІРѕРґРёС‚РµР»СЊ":
            kb.add_line()
            kb.add_button("вћ• Мл. Администратор", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_junior"}))
            kb.add_button("вћ– Мл. Администратор", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_junior"}))
            kb.add_line()
            kb.add_button("вћ• Ст. Администратор", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_senior"}))
            kb.add_button("вћ– Ст. Администратор", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_senior"}))
            kb.add_line()
            kb.add_button("вћ• Руководство", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_management"}))
            kb.add_button("вћ– Руководство", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_management"}))
        return kb.get_keyboard()
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры: {e}")
        return VkKeyboard.get_empty_keyboard()

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

# ================= Основной цикл бота =================
waiting_input = {}

logger.info("Бот запущен...")

while True:
    try:
        admins = get_admins()
        senior_admins = get_senior_admins()
        management = get_management()
        
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

                    if text.lower() == "/start":
                        send_msg(peer_id, "👋 Привет! Добро пожаловать в группу Логирования!", user_id)
                        continue

                    if action:
                        role = get_role(user_id)
                        # Здесь вставляются все функции enter_user, exit_user, add/remove roles
                        # их реализация такая же, как в твоем коде, но с вызовами функций работы с БД
                        # например:
                        # if action == "entered": enter_user(user_id, peer_id)
                        # if action == "exited": exit_user(user_id, peer_id)
                        # if action == "add_junior": add_junior(target_id, first, last)
                        # и т.д.
            except Exception as e:
                logger.error(f"Ошибка обработки события: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        time.sleep(5)
