import sqlite3
from datetime import datetime

# Подключение к БД
conn = sqlite3.connect('data/bot_database.db')
cursor = conn.cursor()

def print_table(title, data, headers):
    """Красивый вывод таблицы"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)
    if not data:
        print(" Нет данных")
        return
    
    # Заголовки
    header_line = " | ".join(headers)
    print(header_line)
    print("-" * len(header_line))
    
    # Данные
    for row in data:
        print(" | ".join(str(x) for x in row))
    print()

# 1. Все пользователи
cursor.execute("""
    SELECT user_id, first_name, last_name, 
           CASE role
               WHEN 'owner' THEN '👑 Владелец'
               WHEN 'management' THEN '👑 Руководство'
               WHEN 'senior' THEN '👤 Ст.Админ'
               WHEN 'junior' THEN '👥 Мл.Админ'
               ELSE '👤 Пользователь'
           END as role_display,
           datetime(registered_at) as reg_time,
           datetime(last_activity) as last_act
    FROM users 
    ORDER BY 
        CASE role
            WHEN 'owner' THEN 1
            WHEN 'management' THEN 2
            WHEN 'senior' THEN 3
            WHEN 'junior' THEN 4
            ELSE 5
        END, last_name
""")
users = cursor.fetchall()
print_table("👥 ВСЕ ПОЛЬЗОВАТЕЛИ", users, 
           ["ID", "Имя", "Фамилия", "Роль", "Зарегистрирован", "Активность"])

# 2. Активные сессии (кто сейчас онлайн)
cursor.execute("""
    SELECT u.first_name || ' ' || u.last_name as name,
           CASE u.role
               WHEN 'owner' THEN '👑 Владелец'
               WHEN 'management' THEN '👑 Руководство'
               WHEN 'senior' THEN '👤 Ст.Админ'
               WHEN 'junior' THEN '👥 Мл.Админ'
               ELSE '👤 Пользователь'
           END as role_display,
           datetime(s.start_time) as start,
           strftime('%H:%M:%S', datetime('now') - datetime(s.start_time)) as duration
    FROM sessions s
    JOIN users u ON s.user_id = u.user_id
    WHERE s.is_active = 1
    ORDER BY s.start_time
""")
active = cursor.fetchall()
print_table("🟢 СЕЙЧАС ОНЛАЙН", active, 
           ["Имя", "Роль", "Начало", "Длительность"])

# 3. История входов/выходов
cursor.execute("""
    SELECT u.first_name || ' ' || u.last_name as name,
           datetime(s.start_time) as start,
           datetime(s.end_time) as end,
           CASE 
               WHEN s.duration THEN 
                   printf('%d ч %d м', s.duration/3600, (s.duration%3600)/60)
               ELSE 'Сейчас в сети'
           END as duration,
           CASE s.is_active
               WHEN 1 THEN '🟢 Онлайн'
               ELSE '🔴 Офлайн'
           END as status
    FROM sessions s
    JOIN users u ON s.user_id = u.user_id
    ORDER BY s.start_time DESC
    LIMIT 20
""")
history = cursor.fetchall()
print_table("📜 ПОСЛЕДНИЕ 20 СЕССИЙ", history,
           ["Имя", "Вход", "Выход", "Длительность", "Статус"])

# 4. Статистика по ролям
cursor.execute("""
    SELECT 
        CASE role
            WHEN 'owner' THEN '👑 Владелец'
            WHEN 'management' THEN '👑 Руководство'
            WHEN 'senior' THEN '👤 Ст.Админ'
            WHEN 'junior' THEN '👥 Мл.Админ'
            ELSE '👤 Пользователь'
        END as role_name,
        COUNT(*) as total,
        SUM(CASE WHEN user_id IN (SELECT user_id FROM sessions WHERE is_active=1) THEN 1 ELSE 0 END) as online,
        ROUND(AVG(CASE WHEN role != 'user' THEN 1 ELSE 0 END) * 100, 1) as admin_percent
    FROM users
    GROUP BY role
    ORDER BY 
        CASE role
            WHEN 'owner' THEN 1
            WHEN 'management' THEN 2
            WHEN 'senior' THEN 3
            WHEN 'junior' THEN 4
            ELSE 5
        END
""")
stats = cursor.fetchall()
print_table("📊 СТАТИСТИКА ПО РОЛЯМ", stats,
           ["Роль", "Всего", "Онлайн", "% от админов"])

# 5. Общая статистика
cursor.execute("""
    SELECT 
        COUNT(DISTINCT user_id) as total_users,
        COUNT(*) as total_sessions,
        SUM(duration) / 3600 as total_hours,
        AVG(duration) / 60 as avg_minutes,
        MAX(duration) / 60 as max_minutes,
        COUNT(CASE WHEN is_active = 1 THEN 1 END) as current_online
    FROM sessions
    WHERE duration IS NOT NULL
""")
total_stats = cursor.fetchone()
if total_stats:
    print(f"\n{'='*60}")
    print(" 📊 ОБЩАЯ СТАТИСТИКА")
    print('='*60)
    print(f"👥 Всего пользователей: {total_stats[0]}")
    print(f"📝 Всего сессий: {total_stats[1]}")
    print(f"⏱ Всего часов онлайн: {total_stats[2]}")
    print(f"📈 Средняя длительность: {total_stats[3]:.0f} минут")
    print(f"📊 Максимальная длительность: {total_stats[4]:.0f} минут")
    print(f"🟢 Сейчас онлайн: {total_stats[5]}")
    print()

# 6. Топ пользователей по времени
cursor.execute("""
    SELECT u.first_name || ' ' || u.last_name as name,
           CASE u.role
               WHEN 'owner' THEN '👑'
               WHEN 'management' THEN '👑'
               WHEN 'senior' THEN '👤'
               WHEN 'junior' THEN '👥'
               ELSE '👤'
           END as role_icon,
           COUNT(s.session_id) as sessions,
           SUM(s.duration) / 3600 as hours,
           AVG(s.duration) / 60 as avg_min
    FROM users u
    LEFT JOIN sessions s ON u.user_id = s.user_id AND s.is_active = 0
    GROUP BY u.user_id
    HAVING hours > 0
    ORDER BY hours DESC
    LIMIT 10
""")
top_users = cursor.fetchall()
print_table("🏆 ТОП-10 ПО ВРЕМЕНИ ОНЛАЙН", top_users,
           ["Пользователь", "", "Сессий", "Часов", "Среднее (мин)"])

# 7. Последние действия
cursor.execute("""
    SELECT datetime(l.created_at) as time,
           u.first_name || ' ' || u.last_name as user,
           l.action,
           l.details
    FROM actions_log l
    JOIN users u ON l.user_id = u.user_id
    ORDER BY l.created_at DESC
    LIMIT 15
""")
logs = cursor.fetchall()
print_table("📝 ПОСЛЕДНИЕ ДЕЙСТВИЯ", logs,
           ["Время", "Пользователь", "Действие", "Детали"])

conn.close()
