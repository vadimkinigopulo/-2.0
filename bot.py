import os
import json
import time
import logging
from dotenv import load_dotenv
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

vk_session = vk_api.VkApi(token=TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
SENIOR_FILE = os.path.join(DATA_DIR, "senior.json")
MANAGEMENT_FILE = os.path.join(DATA_DIR, "management.json")

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

admins = load_json(ADMINS_FILE, {})          # {peer_id:{user_id:{}}}
senior_admins = load_json(SENIOR_FILE, [])
management = load_json(MANAGEMENT_FILE, [])

def save_all():
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f, indent=2, ensure_ascii=False)
    with open(SENIOR_FILE, "w", encoding="utf-8") as f:
        json.dump(senior_admins, f)
    with open(MANAGEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(management, f)

def get_chat(peer_id):
    peer_id = str(peer_id)
    if peer_id not in admins:
        admins[peer_id] = {}
    return admins[peer_id]

def get_user(user_id):
    u = vk.users.get(user_ids=user_id)[0]
    return u["first_name"], u["last_name"]

def format_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    return f"{h}ч {m}м" if h or m else "меньше минуты"

def get_role(uid):
    uid = int(uid)
    if uid in management:
        return "Руководство"
    if uid in senior_admins:
        return "Ст. Администратор"
    return "Мл. Администратор"

def keyboard(role):
    kb = VkKeyboard(one_time=False)
    kb.add_button("✅ Вошел", VkKeyboardColor.POSITIVE, payload='{"cmd":"in"}')
    kb.add_button("❌ Вышел", VkKeyboardColor.NEGATIVE, payload='{"cmd":"out"}')
    kb.add_line()
    kb.add_button("👥 Мл. Администратор", VkKeyboardColor.SECONDARY, payload='{"cmd":"junior"}')
    kb.add_button("👤 Ст. Администратор", VkKeyboardColor.PRIMARY, payload='{"cmd":"senior"}')
    kb.add_line()
    kb.add_button("👑 Руководство", VkKeyboardColor.PRIMARY, payload='{"cmd":"management"}')
    kb.add_line()
    kb.add_button("📊 Статистика", VkKeyboardColor.PRIMARY, payload='{"cmd":"stats"}')
    kb.add_button("🌐 Общий онлайн", VkKeyboardColor.SECONDARY, payload='{"cmd":"total"}')

    if role == "Руководство":
        kb.add_line()
        kb.add_button("➕ Мл. админ", VkKeyboardColor.POSITIVE, payload='{"cmd":"add_junior"}')
        kb.add_button("➖ Мл. админ", VkKeyboardColor.NEGATIVE, payload='{"cmd":"remove_junior"}')
        kb.add_line()
        kb.add_button("➕ Ст. админ", VkKeyboardColor.POSITIVE, payload='{"cmd":"add_senior"}')
        kb.add_button("➖ Ст. админ", VkKeyboardColor.NEGATIVE, payload='{"cmd":"remove_senior"}')
        kb.add_line()
        kb.add_button("➕ Руководство", VkKeyboardColor.POSITIVE, payload='{"cmd":"add_management"}')
        kb.add_button("➖ Руководство", VkKeyboardColor.NEGATIVE, payload='{"cmd":"remove_management"}')
    return kb.get_keyboard()

def send(peer, text, user_id):
    vk.messages.send(
        peer_id=peer,
        message=text,
        random_id=get_random_id(),
        keyboard=keyboard(get_role(user_id))
    )

def parse_id(text):
    text = text.replace("https://vk.com/", "").replace("@", "")
    if text.startswith("id"):
        return text[2:]
    if text.isdigit():
        return text
    try:
        u = vk.users.get(user_ids=text)
        return str(u[0]["id"])
    except:
        return None

def total_online(chat):
    now = time.time()
    total = 0
    for uid, data in chat.items():
        if "start" in data:
            total += now - data["start"]
    return total

waiting = {}

print("Бот запущен")

while True:
    try:
        for event in longpoll.listen():
            if event.type != VkBotEventType.MESSAGE_NEW:
                continue

            msg = event.message
            peer = msg["peer_id"]

            if peer < 2000000000:
                continue  # Игнор ЛС

            user_id = str(msg["from_id"])
            text = msg.get("text","")
            payload = msg.get("payload")

            cmd = None
            if payload:
                cmd = json.loads(payload).get("cmd")

            chat = get_chat(peer)

            if text.lower() == "/start":
                send(peer, "🤖 Бот готов к работе!", user_id)
                try:
                    vk.messages.send(peer_id=peer, sticker_id=60464, random_id=get_random_id())
                except:
                    pass
                continue

            # Вошел
            if cmd == "in":
                if user_id not in chat:
                    f,l = get_user(user_id)
                    chat[user_id] = {"name":f"{f} {l}", "start":time.time(), "total_time":0, "record_time":0}
                else:
                    chat[user_id]["start"] = time.time()
                save_all()
                send(peer, "✅ Ты вошел в онлайн", user_id)

            # Вышел
            elif cmd == "out":
                if user_id in chat and "start" in chat[user_id]:
                    online = time.time() - chat[user_id]["start"]
                    chat[user_id]["total_time"] += online
                    if online > chat[user_id]["record_time"]:
                        chat[user_id]["record_time"] = online
                    del chat[user_id]["start"]
                    save_all()
                    send(peer, f"❌ Ты вышел\n⏱ Был онлайн: {format_time(online)}", user_id)

            # Статистика
            elif cmd == "stats":
                if user_id not in chat:
                    send(peer, "❌ Нет данных", user_id)
                    continue
                d = chat[user_id]
                send(peer,
                     f"📊 Статистика\n⏱ Всего: {format_time(d.get('total_time',0))}\n🏆 Рекорд: {format_time(d.get('record_time',0))}",
                     user_id)

            # Общий онлайн
            elif cmd == "total":
                total = total_online(chat)
                send(peer, f"🌐 Общий онлайн администраторов:\n⏱ {format_time(total)}", user_id)

            # Управление ролями
            elif cmd in ["add_junior","remove_junior","add_senior","remove_senior","add_management","remove_management"]:
                if get_role(user_id) != "Руководство":
                    send(peer, "⛔ Нет прав", user_id)
                    continue
                waiting[user_id] = cmd
                send(peer, "📩 Отправьте ID или ссылку администратора для изменения должности", user_id)

            elif user_id in waiting:
                target = parse_id(text)
                if not target:
                    send(peer, "❌ Ошибка ID", user_id)
                    del waiting[user_id]
                    continue

                t = int(target)
                act = waiting[user_id]

                if act == "add_junior" and t not in chat:
                    f,l = get_user(t)
                    chat[str(t)] = {"name":f"{f} {l}", "start":time.time(), "total_time":0, "record_time":0}

                elif act == "remove_junior" and str(t) in chat:
                    del chat[str(t)]

                elif act == "add_senior" and t not in senior_admins:
                    senior_admins.append(t)

                elif act == "remove_senior" and t in senior_admins:
                    senior_admins.remove(t)

                elif act == "add_management" and t not in management:
                    management.append(t)

                elif act == "remove_management" and t in management:
                    management.remove(t)

                save_all()
                send(peer, "✅ Готово", user_id)
                del waiting[user_id]

    except Exception as e:
        logger.error(e)
        time.sleep(5)
