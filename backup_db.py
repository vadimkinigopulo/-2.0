import shutil
import datetime
import os

def backup_database():
    """Создание бэкапа базы данных"""
    
    # Проверяем, существует ли БД
    if not os.path.exists('data/bot_database.db'):
        print("❌ База данных не найдена!")
        return
    
    # Создаем папку для бэкапов
    os.makedirs('backups', exist_ok=True)
    
    # Имя файла бэкапа с датой и временем
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"backups/bot_database_{timestamp}.db"
    
    # Копируем файл
    shutil.copy2('data/bot_database.db', backup_name)
    
    # Получаем размер файла
    size = os.path.getsize(backup_name)
    size_mb = size / (1024 * 1024)
    
    print(f"✅ Бэкап создан: {backup_name}")
    print(f"📊 Размер: {size_mb:.2f} МБ")
    
    # Удаляем старые бэкапы (оставляем последние 10)
    backups = sorted([f for f in os.listdir('backups') if f.endswith('.db')])
    if len(backups) > 10:
        for old_backup in backups[:-10]:
            os.remove(os.path.join('backups', old_backup))
            print(f"🗑 Удален старый бэкап: {old_backup}")

def restore_database(backup_file):
    """Восстановление базы данных из бэкапа"""
    
    backup_path = os.path.join('backups', backup_file)
    
    if not os.path.exists(backup_path):
        print(f"❌ Бэкап {backup_file} не найден!")
        return
    
    # Создаем бэкап текущей БД перед восстановлением
    if os.path.exists('data/bot_database.db'):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2('data/bot_database.db', f'backups/before_restore_{timestamp}.db')
        print(f"📦 Создан бэкап текущей БД")
    
    # Восстанавливаем
    shutil.copy2(backup_path, 'data/bot_database.db')
    print(f"✅ База данных восстановлена из {backup_file}")

def list_backups():
    """Список всех бэкапов"""
    if not os.path.exists('
