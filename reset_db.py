#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import datetime

def reset_database():
    """Сброс базы данных (с созданием бэкапа)"""
    
    print("\n⚠️  ВНИМАНИЕ! Это действие удалит ВСЕ данные из базы!")
    print("Будет автоматически создан бэкап перед сбросом.\n")
    
    # Запрашиваем подтверждение
    confirm = input("Вы уверены? (да/нет): ").lower()
    
    if confirm not in ['да', 'yes', 'y', 'д']:
        print("❌ Операция отменена")
        return
    
    # Проверяем существование БД
    db_path = 'data/bot_database.db'
    backup_created = False
    
    if os.path.exists(db_path):
        # Создаем бэкап
        os.makedirs('backups', exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"backups/before_reset_{timestamp}.db"
        
        try:
            shutil.copy2(db_path, backup_name)
            print(f"✅ Создан бэкап: {backup_name}")
            backup_created = True
        except Exception as e:
            print(f"⚠️ Не удалось создать бэкап: {e}")
    
    # Удаляем старую БД
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            print("🗑 Старая база данных удалена")
    except Exception as e:
        print(f"❌ Ошибка удаления БД: {e}")
        return
    
    # Импортируем бота для инициализации новой БД
    try:
        import bot
        bot.init_database()
        print("✅ Новая база данных создана")
        
        # Логируем сброс
        print("\n📊 База данных успешно сброшена!")
        if backup_created:
            print("🔐 Для восстановления используйте:")
            print(f"   python backup_db.py restore before_reset_{timestamp}.db")
            
    except Exception as e:
        print(f"❌ Ошибка создания новой БД: {e}")

def main():
    """Главная функция"""
    reset_database()

if __name__ == '__main__':
    main()
