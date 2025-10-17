# main.py
from trading_bot_lib import BotManager
import os
import json
import time

# Lấy cấu hình từ biến môi trường
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# In ra để kiểm tra (không in secret key)
print(f"BINANCE_API_KEY: {'***' if BINANCE_API_KEY else 'Không có'}")
print(f"BINANCE_SECRET_KEY: {'***' if BINANCE_SECRET_KEY else 'Không có'}")
print(f"TELEGRAM_BOT_TOKEN: {'***' if TELEGRAM_BOT_TOKEN else 'Không có'}")
print(f"TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID if TELEGRAM_CHAT_ID else 'Không có'}")

def main():
    # Kiểm tra cấu hình
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        print("❌ Chưa cấu hình API Key và Secret Key!")
        return
    
    print("🟢 Đang khởi động hệ thống bot...")
    
    # Khởi tạo hệ thống
    manager = BotManager(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_SECRET_KEY,
        telegram_bot_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    try:
        print("🟢 Hệ thống đã sẵn sàng. Đang chạy...")
        # Giữ chương trình chạy
        while manager.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n👋 Nhận tín hiệu dừng từ người dùng...")
        manager.log("👋 Nhận tín hiệu dừng từ người dùng...")
    except Exception as e:
        print(f"❌ LỖI HỆ THỐNG: {str(e)}")
        manager.log(f"❌ LỖI HỆ THỐNG: {str(e)}")
if __name__ == "__main__":
    main()






