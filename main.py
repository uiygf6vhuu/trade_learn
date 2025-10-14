# main.py
from trading_bot_lib import BotManager
import os
import json
import time
import logging

# ========== CẤU HÌNH LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trading_system.log')
    ]
)
logger = logging.getLogger()

# Lấy cấu hình từ biến môi trường
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

def print_banner():
    """In banner hệ thống"""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                   🤖 TRADING BOT SYSTEM 🤖                   ║
    ║                                                              ║
    ║  🎯 HỆ THỐNG GIAO DỊCH FUTURES TỰ ĐỘNG ĐA LUỒNG            ║
    ║  📊 Tích hợp phân tích xác suất & kỳ vọng thống kê         ║
    ║  🔄 Rotation Coin thông minh theo hệ thống 5 bước          ║
    ║  📱 Điều khiển qua Telegram Menu đầy đủ                    ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def validate_environment():
    """Kiểm tra biến môi trường"""
    errors = []
    
    if not BINANCE_API_KEY:
        errors.append("❌ Chưa thiết lập BINANCE_API_KEY")
    
    if not BINANCE_SECRET_KEY:
        errors.append("❌ Chưa thiết lập BINANCE_SECRET_KEY")
    
    if not TELEGRAM_BOT_TOKEN:
        errors.append("❌ Chưa thiết lập TELEGRAM_BOT_TOKEN")
    
    if not TELEGRAM_CHAT_ID:
        errors.append("❌ Chưa thiết lập TELEGRAM_CHAT_ID")
    
    return errors

def main():
    # In banner
    print_banner()
    
    # Kiểm tra biến môi trường
    logger.info("🔧 Đang kiểm tra cấu hình môi trường...")
    
    errors = validate_environment()
    if errors:
        logger.error("❌ LỖI CẤU HÌNH:")
        for error in errors:
            logger.error(f"   {error}")
        
        logger.info("\n💡 HƯỚNG DẪN CẤU HÌNH:")
        logger.info("1. Thiết lập các biến môi trường sau:")
        logger.info("   - BINANCE_API_KEY: API Key từ Binance")
        logger.info("   - BINANCE_SECRET_KEY: API Secret từ Binance") 
        logger.info("   - TELEGRAM_BOT_TOKEN: Token từ BotFather")
        logger.info("   - TELEGRAM_CHAT_ID: Chat ID Telegram của bạn")
        logger.info("2. Khởi động lại hệ thống")
        return
    
    # Hiển thị thông tin cấu hình (ẩn key bí mật)
    logger.info("✅ CẤU HÌNH HỢP LỆ")
    logger.info(f"   🔑 Binance API Key: {BINANCE_API_KEY[:10]}...{BINANCE_API_KEY[-4:]}")
    logger.info(f"   🔐 Binance Secret: ***")
    logger.info(f"   🤖 Telegram Bot: Đã kết nối")
    logger.info(f"   💬 Chat ID: {TELEGRAM_CHAT_ID}")
    
    logger.info("🟢 Đang khởi động hệ thống bot...")
    
    try:
        # Khởi tạo hệ thống
        manager = BotManager(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_SECRET_KEY,
            telegram_bot_token=TELEGRAM_BOT_TOKEN,
            telegram_chat_id=TELEGRAM_CHAT_ID
        )
        
        logger.info("🎉 HỆ THỐNG ĐÃ KHỞI ĐỘNG THÀNH CÔNG!")
        logger.info("📱 Truy cập Telegram để sử dụng menu điều khiển")
        logger.info("🤖 Sử dụng nút '➕ Thêm Bot' để tạo bot giao dịch")
        logger.info("⏹️  Nhấn Ctrl+C để dừng hệ thống")
        
        # Giữ chương trình chạy
        while manager.running:
            # Kiểm tra mỗi 30 giây
            time.sleep(30)
            
            # Log trạng thái định kỳ
            active_bots = len([b for b in manager.bots.values() if b.position_open])
            searching_bots = len([b for b in manager.bots.values() if b.status == "searching"])
            total_bots = len(manager.bots)
            
            if total_bots > 0:
                logger.info(f"📊 Trạng thái hệ thống: {active_bots} đang trade, {searching_bots} đang tìm coin, Tổng: {total_bots} bot")
            
    except KeyboardInterrupt:
        logger.info("⏹️  Nhận tín hiệu dừng từ người dùng...")
        if 'manager' in locals():
            manager.stop_all()
        logger.info("🔴 Hệ thống đã dừng an toàn")
    except Exception as e:
        logger.error(f"❌ LỖI HỆ THỐNG: {str(e)}")
        import traceback
        logger.error(f"Chi tiết lỗi: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
