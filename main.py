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

# Cấu hình bot từ biến môi trường (dạng JSON)
bot_config_json = os.getenv('BOT_CONFIGS', '[]')
try:
    BOT_CONFIGS = json.loads(bot_config_json)
except Exception as e:
    print(f"Lỗi phân tích cấu hình BOT_CONFIGS: {e}")
    BOT_CONFIGS = []

def main():
    # Kiểm tra cấu hình
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        print("❌ Chưa cấu hình API Key và Secret Key!")
        return
    
    # Khởi tạo hệ thống
    manager = BotManager(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_SECRET_KEY,
        telegram_bot_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    
    # Thêm các bot từ cấu hình
    if BOT_CONFIGS:
        for config in BOT_CONFIGS:
            if len(config) >= 6:
                symbol, lev, percent, tp, sl, strategy = config[0], config[1], config[2], config[3], config[4], config[5]
                if manager.add_bot(symbol, lev, percent, tp, sl, strategy):
                    manager.log(f"✅ Bot {strategy} cho {symbol} khởi động thành công")
                else:
                    manager.log(f"❌ Bot {strategy} cho {symbol} khởi động thất bại")
    else:
        manager.log("⚠️ Không tìm thấy cấu hình bot! Vui lòng thiết lập biến môi trường BOT_CONFIGS.")
    
    try:
        # Giữ chương trình chạy
        while manager.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        manager.log("👋 Nhận tín hiệu dừng từ người dùng...")
    except Exception as e:
        manager.log(f"❌ LỖI HỆ THỐNG: {str(e)}")
    finally:
        manager.stop_all()

if __name__ == "__main__":
    main()
