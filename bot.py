import os
import json
import time
import logging
import sqlite3
from datetime import datetime
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

# ================= Настройка базы данных =================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "bot_database.db")

def init_database():
    """Инициализация базы данных и создание таблиц"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            role TEXT DEFAULT 'user',
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP
        )
    ''')
    
    # Таблица сессий (онлайн)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration INTEGER,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица истории действий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS actions_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# Инициализируем БД при запуске
init_database()

# ================= Классы для работы с БД =================
class DatabaseManager:
    """Менеджер для работы с базой данных"""
    
    @staticmethod
    def get_connection():
        return sqlite3.connect(DB_FILE)
    
    # ==== Пользователи ====
    @staticmethod
    def get_or_create_user(user_id, first_name="", last_name=""):
        """Получить или создать пользователя"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, first_name, last_name, registered_at, last_activity)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (user_id, first_name, last_name))
            conn.commit()
            logger.info(f"Новый пользователь добавлен в БД: {user_id}")
        
        conn.close()
    
    @staticmethod
    def update_user_activity(user_id):
        """Обновить время последней активности"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_user_role(user_id):
        """Получить роль пользователя"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "user"
    
    @staticmethod
    def set_user_role(user_id, role):
        """Установить роль пользователя"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET role = ? WHERE user_id = ?
        ''', (role, user_id))
        conn.commit()
        conn.close()
        logger.info(f"Роль пользователя {user_id} изменена на {role}")
    
    @staticmethod
    def get_all_users_by_role(role):
        """Получить всех пользователей с определенной ролью"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, first_name, last_name FROM users WHERE role = ?
        ''', (role,))
        users = cursor.fetchall()
        conn.close()
        return users
    
    # ==== Сессии (онлайн) ====
    @staticmethod
    def start_session(user_id):
        """Начать сессию пользователя"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, есть ли уже активная сессия
        cursor.execute('''
            SELECT session_id FROM sessions 
            WHERE user_id = ? AND is_active = 1
        ''', (user_id,))
        active = cursor.fetchone()
        
        if active:
            conn.close()
            return False
        
        # Создаем новую сессию
        cursor.execute('''
            INSERT INTO sessions (user_id, start_time, is_active)
            VALUES (?, CURRENT_TIMESTAMP, 1)
        ''', (user_id,))
        conn.commit()
        conn.close()
        return True
    
    @staticmethod
    def end_session(user_id):
        """Завершить сессию пользователя"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        # Получаем активную сессию
        cursor.execute('''
            SELECT session_id, start_time FROM sessions 
            WHERE user_id = ? AND is_active = 1
        ''', (user_id,))
        session = cursor.fetchone()
        
        if not session:
            conn.close()
            return None
        
        session_id, start_time = session
        end_time = datetime.now()
        
        # Вычисляем длительность в секундах
        duration = int((end_time - datetime.fromisoformat(start_time)).total_seconds())
        
        # Обновляем сессию
        cursor.execute('''
            UPDATE sessions 
            SET end_time = CURRENT_TIMESTAMP, duration = ?, is_active = 0
            WHERE session_id = ?
        ''', (duration, session_id))
        conn.commit()
        conn.close()
        return duration
    
    @staticmethod
    def get_active_sessions():
        """Получить все активные сессии"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.user_id, u.first_name, u.last_name, s.start_time
            FROM sessions s
            JOIN users u ON s.user_id = u.user_id
            WHERE s.is_active = 1
        ''')
        sessions = cursor.fetchall()
        conn.close()
        return sessions
    
    @staticmethod
    def get_user_session(user_id):
        """Получить активную сессию пользователя"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT start_time FROM sessions 
            WHERE user_id = ? AND is_active = 1
        ''', (user_id,))
        session = cursor.fetchone()
        conn.close()
        return session
    
    # ==== Логирование действий ====
    @staticmethod
    def log_action(user_id, action, details=""):
        """Записать действие в лог"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO actions_log (user_id, action, details, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, action, details))
        conn.commit()
        conn.close()
    
    # ==== Настройки ====
    @staticmethod
    def get_setting(key, default=None):
        """Получить настройку"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default
    
    @staticmethod
    def set_setting(key, value):
        """Установить настройку"""
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()

# ================= Вспомогательные функции =================
def get_user_info(user_id):
    """Получить информацию о пользователе из VK и сохранить в БД"""
    try:
        user = vk.users.get(user_ids=user_id)[0]
        first_name = user["first_name"]
        last_name = user["last_name"]
        
        # Сохраняем пользователя в БД
        DatabaseManager.get_or_create_user(user_id, first_name, last_name)
        
        return first_name, last_name
    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователе {user_id}: {e}")
        return "Неизвестно", "Неизвестно"

def parse_user_input(input_text):
    """Парсинг ввода пользователя"""
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

def get_role_name(user_id):
    """Получить название роли пользователя"""
    role = DatabaseManager.get_user_role(user_id)
    role_names = {
        "owner": "👑 Владелец",
        "management": "👑 Руководство",
        "senior": "👤 Ст. Администратор",
        "junior": "👥 Мл. Администратор",
        "user": "👤 Пользователь"
    }
    return role_names.get(role, "👤 Пользователь")

def format_duration(seconds):
    """Форматирование длительности"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}ч {m}м {s}с"
    elif m > 0:
        return f"{m}м {s}с"
    else:
        return f"{s}с"

# ================= Клавиатура =================
def build_keyboard(user_id):
    """Построение клавиатуры в зависимости от роли"""
    try:
        role = DatabaseManager.get_user_role(user_id)
        kb = VkKeyboard(one_time=False)
        
        # Основные кнопки для всех
        kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "entered"}))
        kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "exited"}))
        kb.add_line()
        kb.add_button("🌐 Общий онлайн", VkKeyboardColor.SECONDARY, payload=json.dumps({"cmd": "all_online"}))
        
        # Кнопки для руководства и владельца
        if role in ["owner", "management"]:
            kb.add_line()
            kb.add_button("➕ Мл. Админ", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_junior"}))
            kb.add_button("➖ Мл. Админ", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_junior"}))
            kb.add_line()
            kb.add_button("➕ Ст. Админ", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_senior"}))
            kb.add_button("➖ Ст. Админ", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_senior"}))
            kb.add_line()
            kb.add_button("➕ Руководство", VkKeyboardColor.POSITIVE, payload=json.dumps({"cmd": "add_management"}))
            kb.add_button("➖ Руководство", VkKeyboardColor.NEGATIVE, payload=json.dumps({"cmd": "remove_management"}))
        
        return kb.get_keyboard()
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры: {e}")
        return VkKeyboard.get_empty_keyboard()

# ================= Отправка сообщений =================
def send_msg(peer_id, text, target_user_id=None, sticker_id=None):
    """Отправка сообщения"""
    try:
        params = {
            "peer_id": peer_id,
            "message": text,
            "random_id": get_random_id(),
            "keyboard": build_keyboard(target_user_id) if target_user_id else VkKeyboard.get_empty_keyboard()
        }
        if sticker_id:
            params["sticker_id"] = sticker_id
        vk.messages.send(**params)
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

# ================= Функции для отображения онлайна =================
def get_online_lists():
    """Получение списков онлайн пользователей по ролям"""
    
    # Получаем все активные сессии
    active_sessions = DatabaseManager.get_active_sessions()
    
    # Группируем по ролям
    management_online = []
    senior_online = []
    junior_online = []
    
    for session in active_sessions:
        user_id, first_name, last_name, start_time = session
        role = DatabaseManager.get_user_role(user_id)
        
        # Вычисляем длительность
        duration = int((datetime.now() - datetime.fromisoformat(start_time)).total_seconds())
        duration_str = format_duration(duration)
        
        user_line = f"[id{user_id}|{first_name} {last_name}] — 🟢 {duration_str}"
        
        if role == "owner" or role == "management":
            management_online.append(user_line)
        elif role == "senior":
            senior_online.append(user_line)
        elif role == "junior":
            junior_online.append(user_line)
    
    # Формируем текст
    result = []
    
    if management_online:
        result.append("👑 **Руководство онлайн:**")
        result.extend(management_online)
        result.append("")
    
    if senior_online:
        result.append("👤 **Ст. Администраторы онлайн:**")
        result.extend(senior_online)
        result.append("")
    
    if junior_online:
        result.append("👥 **Мл. Администраторы онлайн:**")
        result.extend(junior_online)
        result.append("")
    
    if not result:
        return "🌐 Нет пользователей онлайн"
    
    total_online = len(active_sessions)
    result.append(f"📊 **Всего онлайн:** {total_online}")
    
    return "\n".join(result)

# ================= Обработка входа/выхода =================
def handle_enter(user_id, peer_id):
    """Обработка входа"""
    
    # Проверяем, есть ли уже активная сессия
    existing = DatabaseManager.get_user_session(user_id)
    if existing:
        send_msg(peer_id, "⚠️ Вы уже в сети", user_id)
        return
    
    # Получаем информацию о пользователе
    first_name, last_name = get_user_info(user_id)
    
    # Начинаем сессию
    DatabaseManager.start_session(user_id)
    
    # Логируем действие
    DatabaseManager.log_action(user_id, "enter", f"Вход в систему")
    
    # Получаем роль
    role_name = get_role_name(user_id)
    
    # Отправляем сообщение
    send_msg(peer_id, f"✅ {role_name} [id{user_id}|{first_name} {last_name}] вошел в сеть", user_id)

def handle_exit(user_id, peer_id):
    """Обработка выхода"""
    
    # Завершаем сессию
    duration = DatabaseManager.end_session(user_id)
    
    if duration is None:
        send_msg(peer_id, "⚠️ Вы не в сети", user_id)
        return
    
    # Получаем информацию о пользователе
    first_name, last_name = get_user_info(user_id)
    
    # Логируем действие
    DatabaseManager.log_action(user_id, "exit", f"Выход из системы, пробыл {format_duration(duration)}")
    
    # Отправляем сообщение
    send_msg(peer_id, f"❌ [id{user_id}|{first_name} {last_name}] вышел из сети. Провел(а) онлайн: {format_duration(duration)}", user_id)

# ================= Управление ролями =================
def change_user_role(admin_id, target_input, new_role, action_type):
    """Изменение роли пользователя"""
    
    target_id = parse_user_input(target_input)
    if not target_id:
        return False, "❌ Не удалось распознать пользователя"
    
    # Получаем информацию о целевом пользователе
    first_name, last_name = get_user_info(target_id)
    target_name = f"[id{target_id}|{first_name} {last_name}]"
    
    # Проверяем текущую роль
    current_role = DatabaseManager.get_user_role(target_id)
    
    # Словарь соответствия ролей
    role_map = {
        "junior": "junior",
        "senior": "senior",
        "management": "management"
    }
    
    if action_type == "add":
        if current_role == new_role:
            return False, f"⚠️ {target_name} уже имеет эту роль"
        
        # Устанавливаем новую роль
        DatabaseManager.set_user_role(target_id, new_role)
        
        # Логируем действие
        DatabaseManager.log_action(admin_id, "role_change", 
                                  f"Изменил роль {target_id} на {new_role}")
        
        return True, f"✅ {target_name} назначен {get_role_name(target_id)}"
    
    else:  # remove
        if current_role != new_role:
            return False, f"⚠️ {target_name} не имеет этой роли"
        
        # Сбрасываем на обычного пользователя
        DatabaseManager.set_user_role(target_id, "user")
        
        # Логируем действие
        DatabaseManager.log_action(admin_id, "role_change", 
                                  f"Снял роль {new_role} с {target_id}")
        
        return True, f"✅ {target_name} удален из {get_role_name(target_id)}"

# ================= Инициализация первого владельца =================
def init_first_owner():
    """Инициализация первого владельца (если нет ни одного админа)"""
    management_users = DatabaseManager.get_all_users_by_role("management")
    senior_users = DatabaseManager.get_all_users_by_role("senior")
    junior_users = DatabaseManager.get_all_users_by_role("junior")
    
    if not management_users and not senior_users and not junior_users:
        # Нет ни одного администратора - делаем первого пользователя владельцем
        logger.warning("Нет ни одного администратора! Первый вошедший станет владельцем.")
        return True
    return False

need_owner = init_first_owner()

# ================= Ожидание ввода =================
waiting_input = {}

# ================= Главный цикл =================
logger.info("✅ Бот запущен и готов к работе!")

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
                    
                    # Обновляем активность пользователя
                    DatabaseManager.update_user_activity(user_id)
                    
                    # Получаем роль
                    role = DatabaseManager.get_user_role(user_id)
                    
                    # Обработка первого владельца
                    if need_owner and text.lower() == "/start":
                        # Делаем первого пользователя владельцем
                        DatabaseManager.set_user_role(user_id, "owner")
                        get_user_info(user_id)  # Сохраняем в БД
                        send_msg(peer_id, "👑 Вы назначены Владельцем бота!", user_id)
                        need_owner = False
                        logger.info(f"Первый владелец назначен: {user_id}")
                        continue
                    
                    # Парсинг payload
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
                        role_name = get_role_name(user_id)
                        welcome_text = (
                            f"👋 Привет, {role_name}!\n\n"
                            f"🤖 Бот для учета времени администраторов\n"
                            f"📊 Используйте кнопки ниже для навигации"
                        )
                        send_msg(peer_id, welcome_text, user_id)
                        continue
                    
                    # Обработка действий из payload
                    if action:
                        if action == "entered":
                            handle_enter(user_id, peer_id)
                        elif action == "exited":
                            handle_exit(user_id, peer_id)
                        elif action == "all_online":
                            send_msg(peer_id, get_online_lists(), user_id)
                        
                        # Управление ролями (только для руководства и владельца)
                        elif action in ["add_junior", "remove_junior", "add_senior", 
                                       "remove_senior", "add_management", "remove_management"]:
                            
                            if role not in ["owner", "management"]:
                                send_msg(peer_id, "⛔ Недостаточно прав", user_id)
                                continue
                            
                            waiting_input[user_id] = action
                            send_msg(peer_id, "📩 Отправьте ID или ссылку пользователя", user_id)
                        continue
                    
                    # Обработка ввода от руководства
                    if user_id in waiting_input:
                        act = waiting_input[user_id]
                        target_input = text
                        
                        # Определяем действие
                        action_map = {
                            "add_junior": ("junior", "add"),
                            "remove_junior": ("junior", "remove"),
                            "add_senior": ("senior", "add"),
                            "remove_senior": ("senior", "remove"),
                            "add_management": ("management", "add"),
                            "remove_management": ("management", "remove")
                        }
                        
                        if act in action_map:
                            new_role, action_type = action_map[act]
                            success, message = change_user_role(user_id, target_input, new_role, action_type)
                            send_msg(peer_id, message, user_id)
                        
                        del waiting_input[user_id]
                        continue
                    
                    # Обработка текстовых команд (для совместимости)
                    if text.lower() == "вошел":
                        handle_enter(user_id, peer_id)
                    elif text.lower() == "вышел":
                        handle_exit(user_id, peer_id)
                    elif text.lower() == "онлайн":
                        send_msg(peer_id, get_online_lists(), user_id)
                    
            except Exception as e:
                logger.error(f"Ошибка обработки события: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Критическая ошибка в главном цикле: {e}", exc_info=True)
        logger.info("Перезапуск через 5 секунд...")
        time.sleep(5)
