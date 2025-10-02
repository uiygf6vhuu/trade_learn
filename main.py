import json
import hmac
import hashlib
import time
import threading
import urllib.request
import urllib.parse
import numpy as np
import websocket
import logging
import requests
import os
import math
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Cấu hình logging chi tiết
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_errors.log')
    ]
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
    logging.error(f"Lỗi phân tích cấu hình BOT_CONFIGS: {e}")
    BOT_CONFIGS = []

API_KEY = BINANCE_API_KEY
API_SECRET = BINANCE_SECRET_KEY

# ========== HÀM GỬI TELEGRAM VÀ XỬ LÝ LỖI ==========
def send_telegram(message, chat_id=None, reply_markup=None):
    """Gửi thông báo qua Telegram với xử lý lỗi chi tiết"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Cấu hình Telegram Bot Token chưa được thiết lập")
        return
    
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not chat_id:
        logger.warning("Cấu hình Telegram Chat ID chưa được thiết lập")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            error_msg = response.text
            logger.error(f"Lỗi gửi Telegram ({response.status_code}): {error_msg}")
    except Exception as e:
        logger.error(f"Lỗi kết nối Telegram: {str(e)}")

# ========== HÀM TẠO MENU TELEGRAM ==========
def create_menu_keyboard():
    """Tạo menu 3 nút cho Telegram"""
    return {
        "keyboard": [
            [{"text": "📊 Danh sách Bot"}],
            [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
            [{"text": "💰 Số dư tài khoản"}, {"text": "📈 Vị thế đang mở"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def create_cancel_keyboard():
    """Tạo bàn phím hủy"""
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard():
    """Tạo bàn phím chọn cặp coin"""
    popular_symbols = ["SUIUSDT", "DOGEUSDT", "1000PEPEUSDT", "TRUMPUSDT", "XRPUSDT", "ADAUSDT"]
    keyboard = []
    row = []
    for symbol in popular_symbols:
        row.append({"text": symbol})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([{"text": "❌ Hủy bỏ"}])
    
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_leverage_keyboard():
    """Tạo bàn phím chọn đòn bẩy"""
    leverages = ["3", "8", "10", "20", "30", "50", "75", "100"]
    keyboard = []
    row = []
    for lev in leverages:
        row.append({"text": f" {lev}x"})
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([{"text": "❌ Hủy bỏ"}])
    
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

# ========== HÀM HỖ TRỢ API BINANCE VỚI XỬ LÝ LỖI CHI TIẾT ==========
def sign(query):
    try:
        return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"Lỗi tạo chữ ký: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI SIGN:</b> {str(e)}")
        return ""

def binance_api_request(url, method='GET', params=None, headers=None):
    """Hàm tổng quát cho các yêu cầu API Binance với xử lý lỗi chi tiết"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if method.upper() == 'GET':
                if params:
                    query = urllib.parse.urlencode(params)
                    url = f"{url}?{query}"
                req = urllib.request.Request(url, headers=headers or {})
            else:
                data = urllib.parse.urlencode(params).encode() if params else None
                req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
            
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    return json.loads(response.read().decode())
                else:
                    logger.error(f"Lỗi API ({response.status}): {response.read().decode()}")
                    if response.status == 429:  # Rate limit
                        time.sleep(2 ** attempt)  # Exponential backoff
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            logger.error(f"Lỗi HTTP ({e.code}): {e.reason}")
            if e.code == 429:  # Rate limit
                time.sleep(2 ** attempt)  # Exponential backoff
            elif e.code >= 500:
                time.sleep(1)
            continue
        except Exception as e:
            logger.error(f"Lỗi kết nối API: {str(e)}")
            time.sleep(1)
    
    logger.error(f"Không thể thực hiện yêu cầu API sau {max_retries} lần thử")
    return None

def get_step_size(symbol):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        data = binance_api_request(url)
        if not data:
            return 0.001
            
        for s in data['symbols']:
            if s['symbol'] == symbol.upper():
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        return float(f['stepSize'])
    except Exception as e:
        logger.error(f"Lỗi lấy step size: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI STEP SIZE:</b> {symbol} - {str(e)}")
    return 0.001

def set_leverage(symbol, lev):
    try:
        ts = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "leverage": lev,
            "timestamp": ts
        }
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/leverage?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        
        response = binance_api_request(url, method='POST', headers=headers)
        if response and 'leverage' in response:
            return True
    except Exception as e:
        logger.error(f"Lỗi thiết lập đòn bẩy: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI ĐÒN BẨY:</b> {symbol} - {str(e)}")
    return False

def get_balance():
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        
        data = binance_api_request(url, headers=headers)
        if not data:
            return 0
            
        for asset in data['assets']:
            if asset['asset'] == 'USDT':
                return float(asset['availableBalance'])
    except Exception as e:
        logger.error(f"Lỗi lấy số dư: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI SỐ DƯ:</b> {str(e)}")
    return 0

def place_order(symbol, side, qty):
    try:
        ts = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "side": side,
            "type": "MARKET",
            "quantity": qty,
            "timestamp": ts
        }
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/order?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        
        return binance_api_request(url, method='POST', headers=headers)
    except Exception as e:
        logger.error(f"Lỗi đặt lệnh: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI ĐẶT LỆNH:</b> {symbol} - {str(e)}")
    return None

def cancel_all_orders(symbol):
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/allOpenOrders?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        
        binance_api_request(url, method='DELETE', headers=headers)
        return True
    except Exception as e:
        logger.error(f"Lỗi hủy lệnh: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI HỦY LỆNH:</b> {symbol} - {str(e)}")
    return False

def get_current_price(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            return float(data['price'])
    except Exception as e:
        logger.error(f"Lỗi lấy giá: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI GIÁ:</b> {symbol} - {str(e)}")
    return 0

def get_positions(symbol=None):
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        if symbol:
            params["symbol"] = symbol.upper()
            
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v2/positionRisk?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        
        positions = binance_api_request(url, headers=headers)
        if not positions:
            return []
            
        if symbol:
            for pos in positions:
                if pos['symbol'] == symbol.upper():
                    return [pos]
            
        return positions
    except Exception as e:
        logger.error(f"Lỗi lấy vị thế: {str(e)}")
        send_telegram(f"⚠️ <b>LỖI VỊ THẾ:</b> {symbol if symbol else ''} - {str(e)}")
    return []

# ========== HÀM BIẾN ĐỘNG 24H (LOGIC TỪ FILE 49) ==========
def get_24h_ticker_data():
    """Lấy dữ liệu ticker 24h cho tất cả symbol từ Binance"""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        return data if data else []
    except Exception as e:
        logger.error(f"Lỗi lấy dữ liệu ticker 24h: {str(e)}")
        return []

def get_24h_change(symbol):
    """Lấy % thay đổi giá 24h cho một symbol"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'priceChangePercent' in data:
            return float(data['priceChangePercent'])
    except Exception as e:
        logger.error(f"Lỗi lấy biến động 24h cho {symbol}: {str(e)}")
    return 0

def get_signal(symbol, threshold=30):
    """
    LOGIC TỪ FILE 49: Tín hiệu dựa trên biến động 24h
    - Tăng >threshold% -> SELL (kỳ vọng điều chỉnh giảm)
    - Giảm >threshold% -> BUY (kỳ vọng phục hồi)
    
    CÓ THỂ THAY ĐỔI threshold 30% THÀNH GIÁ TRỊ KHÁC
    """
    change_24h = get_24h_change(symbol)
    
    if abs(change_24h) >= threshold:
        if change_24h > 0:
            return "SELL", change_24h
        else:
            return "BUY", abs(change_24h)
    
    return None, change_24h

# ========== QUẢN LÝ WEBSOCKET HIỆU QUẢ VỚI KIỂM SOÁT LỖI ==========
class WebSocketManager:
    def __init__(self):
        self.connections = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
    def add_symbol(self, symbol, callback):
        symbol = symbol.upper()
        with self._lock:
            if symbol not in self.connections:
                self._create_connection(symbol, callback)
                
    def _create_connection(self, symbol, callback):
        if self._stop_event.is_set():
            return
            
        stream = f"{symbol.lower()}@trade"
        url = f"wss://fstream.binance.com/ws/{stream}"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if 'p' in data:
                    price = float(data['p'])
                    self.executor.submit(callback, price)
            except Exception as e:
                logger.error(f"Lỗi xử lý tin nhắn WebSocket {symbol}: {str(e)}")
                
        def on_error(ws, error):
            logger.error(f"Lỗi WebSocket {symbol}: {str(error)}")
            if not self._stop_event.is_set():
                time.sleep(5)
                self._reconnect(symbol, callback)
            
        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket đóng {symbol}: {close_status_code} - {close_msg}")
            if not self._stop_event.is_set() and symbol in self.connections:
                time.sleep(5)
                self._reconnect(symbol, callback)
                
        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()
        
        self.connections[symbol] = {
            'ws': ws,
            'thread': thread,
            'callback': callback
        }
        logger.info(f"WebSocket bắt đầu cho {symbol}")
        
    def _reconnect(self, symbol, callback):
        logger.info(f"Kết nối lại WebSocket cho {symbol}")
        self.remove_symbol(symbol)
        self._create_connection(symbol, callback)
        
    def remove_symbol(self, symbol):
        symbol = symbol.upper()
        with self._lock:
            if symbol in self.connections:
                try:
                    self.connections[symbol]['ws'].close()
                except Exception as e:
                    logger.error(f"Lỗi đóng WebSocket {symbol}: {str(e)}")
                del self.connections[symbol]
                logger.info(f"WebSocket đã xóa cho {symbol}")
                
    def stop(self):
        self._stop_event.set()
        for symbol in list(self.connections.keys()):
            self.remove_symbol(symbol)

# ========== BOT CHÍNH VỚI LOGIC BIẾN ĐỘNG 24H ==========
class IndicatorBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, threshold=30):
        self.symbol = symbol.upper()
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.threshold = threshold  # Ngưỡng biến động - CÓ THỂ TUỲ CHỈNH
        self.ws_manager = ws_manager
        
        self.check_position_status()
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []

        self._stop = False
        self.position_open = False
        self.last_trade_time = 0
        self.position_check_interval = 30
        self.last_position_check = 0
        self.last_error_log_time = 0
        self.last_signal_check = 0
        self.signal_check_interval = 300  # Kiểm tra tín hiệu mỗi 5 phút
        self.cooldown_period = 1800  # Thời gian chờ 30 phút sau khi đóng lệnh
        
        # THÊM BIẾN MỚI ĐỂ QUẢN LÝ TRẠNG THÁI
        self.is_closing = False  # Tránh đóng lệnh nhiều lần
        self.is_opening = False  # Tránh mở lệnh nhiều lần
        self.last_position_verified = 0
        self.position_verify_interval = 10  # Xác minh position mỗi 10 giây
        
        # Start WebSocket and main loop
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot khởi động cho {self.symbol} | ĐB: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}% | Ngưỡng: {threshold}%")

    def calculate_roi(self):
        """Tính ROI hiện tại của position"""
        if not self.position_open or self.entry == 0:
            return 0.0
        
        current_price = self.prices[-1] if self.prices else self.entry
        if self.side == "BUY":
            roi = ((current_price - self.entry) / self.entry) * self.lev * 100
        else:  # SELL
            roi = ((self.entry - current_price) / self.entry) * self.lev * 100
        
        return roi

    def log(self, message, is_critical=True):
        """Ghi log và gửi Telegram cho thông báo quan trọng"""
        logger.info(f"[{self.symbol}] {message}")
        if is_critical:
            send_telegram(f"<b>{self.symbol}</b>: {message}")

    def _handle_price_update(self, price):
        """Xử lý cập nhật giá real-time từ WebSocket"""
        if self._stop:
            return
        
        if not self.prices or price != self.prices[-1]:
            self.prices.append(price)
            if len(self.prices) > 100:
                self.prices = self.prices[-100:]
            
            # Kiểm tra TP/SL real-time - CHỈ KHI KHÔNG ĐANG ĐÓNG LỆNH
            if self.position_open and not self.is_closing:
                self.check_tp_sl()

    def _run(self):
        """Luồng chính với giám sát biến động 24h"""
        self.log("🔍 Bắt đầu vòng lặp chính với giám sát biến động 24h...")
        
        while not self._stop:
            try:
                current_time = time.time()
                
                # Xác minh position định kỳ để tránh sai lệch
                if current_time - self.last_position_verified > self.position_verify_interval:
                    self.verify_position_status()
                    self.last_position_verified = current_time
                
                # Kiểm tra trạng thái vị thế mỗi 30 giây
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                # Kiểm tra tín hiệu giao dịch mỗi 5 phút - CHỈ KHI KHÔNG CÓ POSITION VÀ KHÔNG ĐANG ĐÓNG
                if (current_time - self.last_signal_check > self.signal_check_interval and 
                    not self.position_open and not self.is_closing):
                    
                    signal, change_percent = get_signal(self.symbol, self.threshold)
                    
                    if signal:
                        log_msg = f"📈 Biến động 24h: {change_percent:.2f}% | Tín hiệu: {signal} | Ngưỡng: {self.threshold}%"
                        self.log(log_msg, is_critical=False)
                        
                        # THÊM ĐIỀU KIỆN BẢO VỆ: Chỉ mở lệnh khi không đang đóng và đủ thời gian chờ
                        if (current_time - self.last_trade_time > self.cooldown_period and 
                            not self.is_closing and not self.is_opening):
                            
                            self.open_position(signal, change_percent)
                            self.last_trade_time = current_time
                    
                    self.last_signal_check = current_time
                
                # Kiểm tra TP/SL cho position đang mở - CHỈ KHI KHÔNG ĐANG ĐÓNG
                if self.position_open and not self.is_closing:
                    self.check_tp_sl()
                
                time.sleep(5)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 30:
                    self.log(f"❌ Lỗi vòng lặp chính: {str(e)}", is_critical=False)
                    self.last_error_log_time = time.time()
                time.sleep(10)

    def verify_position_status(self):
        """Xác minh kỹ trạng thái position từ Binance"""
        try:
            positions = get_positions(self.symbol)
            if not positions:
                if self.position_open:
                    self.log("⚠️ Position không khớp: Local nói open nhưng Binance nói closed")
                    self.position_open = False
                    self.status = "waiting"
                    self.side = ""
                    self.qty = 0
                    self.entry = 0
                return
                
            for pos in positions:
                if pos['symbol'] == self.symbol:
                    position_amt = float(pos.get('positionAmt', 0))
                    if abs(position_amt) > 0:
                        # Có position trên Binance
                        if not self.position_open:
                            self.log("⚠️ Position không khớp: Local nói closed nhưng Binance nói open")
                            self.position_open = True
                            self.status = "open"
                            self.side = "BUY" if position_amt > 0 else "SELL"
                            self.qty = position_amt
                            self.entry = float(pos.get('entryPrice', 0))
                        return
                    else:
                        # Không có position trên Binance
                        if self.position_open:
                            self.log("⚠️ Position không khớp: Local nói open nhưng Binance nói closed")
                            self.position_open = False
                            self.status = "waiting"
                            self.side = ""
                            self.qty = 0
                            self.entry = 0
                        
        except Exception as e:
            logger.error(f"Lỗi xác minh position cho {self.symbol}: {str(e)}")

    def check_position_status(self):
        """Kiểm tra trạng thái position với xử lý lỗi tốt hơn"""
        try:
            positions = get_positions(self.symbol)
            if not positions:
                if self.position_open:
                    self.log("📭 Position đã đóng từ bên ngoài")
                self._reset_position_state()
                return
                
            for pos in positions:
                if pos['symbol'] == self.symbol:
                    position_amt = float(pos.get('positionAmt', 0))
                    if abs(position_amt) > 0:
                        # Có position đang mở
                        if not self.position_open or abs(self.qty - position_amt) > 0.0001:
                            self.position_open = True
                            self.status = "open"
                            self.side = "BUY" if position_amt > 0 else "SELL"
                            self.qty = position_amt
                            self.entry = float(pos.get('entryPrice', 0))
                        return
                    else:
                        # Position đã đóng
                        if self.position_open:
                            self.log("📭 Position đã đóng")
                        self._reset_position_state()
                        return
                        
            # Không tìm thấy position cho symbol
            if self.position_open:
                self.log("📭 Không tìm thấy position cho symbol")
            self._reset_position_state()
            
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"Lỗi kiểm tra position: {str(e)}")
                self.last_error_log_time = time.time()

    def _reset_position_state(self):
        """Reset trạng thái position về mặc định"""
        self.position_open = False
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.is_closing = False
        self.is_opening = False

    def check_tp_sl(self):
        """Kiểm tra TP/SL với cơ chế bảo vệ"""
        if not self.position_open or not self.entry or not self.qty or self.is_closing:
            return
            
        try:
            current_price = self.prices[-1] if self.prices else get_current_price(self.symbol)
            if current_price <= 0:
                return
                
            roi = self.calculate_roi()
            
            if roi >= self.tp:
                self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
                self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"Lỗi kiểm tra TP/SL: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side, change_percent):
        """Mở position với cơ chế chống trùng lặp"""
        if self.is_opening or self.is_closing:
            self.log("⚠️ Đang trong quá trình mở/đóng, bỏ qua")
            return
            
        self.is_opening = True
        try:
            # Kiểm tra lại trạng thái trước khi mở
            self.check_position_status()
            if self.position_open:
                self.log("⚠️ Position đã mở, bỏ qua mở mới")
                self.is_opening = False
                return
                
            # Hủy lệnh tồn đọng
            cancel_all_orders(self.symbol)
            
            # Đặt đòn bẩy
            if not set_leverage(self.symbol, self.lev):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}")
                self.is_opening = False
                return
                
            # Tính toán khối lượng
            balance = get_balance()
            if balance <= 0:
                self.log("❌ Không đủ số dư USDT")
                self.is_opening = False
                return
                
            usdt_amount = balance * (min(max(self.percent, 1), 100) / 100)
            price = get_current_price(self.symbol)
            if price <= 0:
                self.log("❌ Lỗi lấy giá")
                self.is_opening = False
                return
                
            step = get_step_size(self.symbol)
            if step <= 0:
                step = 0.001
                
            qty = (usdt_amount * self.lev) / price
            if step > 0:
                qty = math.floor(qty / step) * step
                
            qty = max(qty, step)
            qty = round(qty, 8)
            
            if qty < step:
                self.log(f"⚠️ Khối lượng quá nhỏ: {qty} < {step}")
                self.is_opening = False
                return
                
            # Đặt lệnh
            res = place_order(self.symbol, side, qty)
            if not res:
                self.log("❌ Lỗi đặt lệnh")
                self.is_opening = False
                return
                
            executed_qty = float(res.get('executedQty', 0))
            if executed_qty <= 0:
                self.log(f"❌ Lệnh không khớp: {executed_qty}")
                self.is_opening = False
                return
                
            # Đợi một chút để hệ thống cập nhật
            time.sleep(2)
            
            # Xác minh position đã được mở
            self.check_position_status()
            
            if not self.position_open:
                self.log("❌ Xác minh position thất bại sau khi mở")
                self.is_opening = False
                return

            # Gửi thông báo với thông tin biến động 24h
            message = (f"✅ <b>ĐÃ MỞ VỊ THẾ {self.symbol}</b>\n"
                       f"📌 Hướng: {side}\n"
                       f"🎯 Chiến lược: Reverse Biến động 24h\n"
                       f"📈 Biến động 24h: {change_percent:.2f}%\n"
                       f"🎯 Ngưỡng kích hoạt: {self.threshold}%\n"
                       f"🏷️ Giá vào: {self.entry:.4f}\n"
                       f"📊 Khối lượng: {executed_qty}\n"
                       f"💵 Giá trị: {executed_qty * self.entry:.2f} USDT\n"
                       f" Đòn bẩy: {self.lev}x\n"
                       f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%")
            
            self.log(message, is_critical=True)
            
        except Exception as e:
            self.log(f"❌ Lỗi khi vào lệnh: {str(e)}")
        finally:
            self.is_opening = False

    def close_position(self, reason=""):
        """Đóng position với cơ chế chống trùng lặp"""
        if self.is_closing:
            self.log("⚠️ Đang trong quá trình đóng, bỏ qua")
            return
            
        self.is_closing = True
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Kiểm tra lại trạng thái trước khi đóng
                self.check_position_status()
                if not self.position_open or abs(self.qty) == 0:
                    self.log("📭 Không có position để đóng")
                    self._reset_position_state()
                    return
                
                cancel_all_orders(self.symbol)
                
                close_side = "SELL" if self.side == "BUY" else "BUY"
                close_qty = abs(self.qty)
                
                # Làm tròn khối lượng chính xác
                step = get_step_size(self.symbol)
                if step > 0:
                    steps = close_qty / step
                    close_qty = math.floor(steps) * step  # Luôn làm tròn xuống để đảm bảo không vượt quá
                
                close_qty = max(close_qty, 0)
                close_qty = round(close_qty, 8)
                
                if close_qty <= 0:
                    self.log("❌ Khối lượng đóng không hợp lệ")
                    break
                
                res = place_order(self.symbol, close_side, close_qty)
                if res:
                    price = float(res.get('avgPrice', 0))
                    roi = self.calculate_roi()

                    message = (f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ {self.symbol}</b>\n"
                              f"📌 Lý do: {reason}\n"
                              f"🏷️ Giá ra: {price:.4f}\n"
                              f"📊 Khối lượng: {close_qty}\n"
                              f"💵 Giá trị: {close_qty * price:.2f} USDT\n"
                              f"🔥 ROI: {roi:.2f}%")
                    self.log(message)
                    
                    # Đợi một chút để hệ thống cập nhật
                    time.sleep(3)
                    
                    # Xác minh position đã đóng
                    self.check_position_status()
                    
                    if self.position_open:
                        self.log("⚠️ Position vẫn mở sau khi thử đóng, thử lại...")
                        retry_count += 1
                        continue
                    
                    # Cập nhật trạng thái
                    self._reset_position_state()
                    self.last_trade_time = time.time()
                    break
                else:
                    self.log(f"❌ Lỗi đóng position (lần thử {retry_count + 1})")
                    retry_count += 1
                    time.sleep(2)
                    
            except Exception as e:
                self.log(f"❌ Lỗi đóng position (lần thử {retry_count + 1}): {str(e)}")
                retry_count += 1
                time.sleep(2)
        
        if retry_count >= max_retries:
            self.log("❌ Không thể đóng position sau nhiều lần thử")
        
        self.is_closing = False

    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        try:
            cancel_all_orders(self.symbol)
        except Exception as e:
            self.log(f"Lỗi hủy lệnh: {str(e)}")
        self.log(f"🔴 Bot dừng cho {self.symbol}")

# ========== QUẢN LÝ BOT CHẠY NỀN VÀ TƯƠNG TÁC TELEGRAM ==========
class BotManager:
    def __init__(self):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}  # Lưu trạng thái người dùng
        self.admin_chat_id = TELEGRAM_CHAT_ID
        
        self.log("🟢 HỆ THỐNG BOT ĐÃ KHỞI ĐỘNG - CHIẾN LƯỢC REVERSE 24H")
        
        # Bắt đầu thread kiểm tra trạng thái
        self.status_thread = threading.Thread(target=self._status_monitor, daemon=True)
        self.status_thread.start()
        
        # Bắt đầu thread lắng nghe Telegram
        self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
        self.telegram_thread.start()
        
        # Gửi menu chính khi khởi động
        if self.admin_chat_id:
            self.send_main_menu(self.admin_chat_id)

    def log(self, message, is_critical=True):
        """Ghi log hệ thống và gửi Telegram cho thông báo quan trọng"""
        logger.info(f"[SYSTEM] {message}")
        if is_critical:
            send_telegram(f"<b>SYSTEM</b>: {message}")

    def send_main_menu(self, chat_id):
        """Gửi menu chính cho người dùng"""
        welcome = (
            "🤖 <b>BOT GIAO DỊCH FUTURES BINANCE</b>\n\n"
            "🎯 <b>Chiến lược: Reverse Biến động 24h >30%</b>\n\n"
            "Chọn một trong các tùy chọn bên dưới:"
        )
        send_telegram(welcome, chat_id, create_menu_keyboard())

    def add_bot(self, symbol, lev, percent, tp, sl, threshold=30):
        if sl == 0:
            sl = None
        symbol = symbol.upper()
        if symbol in self.bots:
            self.log(f"⚠️ Đã có bot cho {symbol}")
            return False
            
        # Kiểm tra API key
        if not API_KEY or not API_SECRET:
            self.log("❌ Chưa cấu hình API Key và Secret Key!")
            return False
            
        try:
            # Kiểm tra kết nối API
            price = get_current_price(symbol)
            if price <= 0:
                self.log(f"❌ Không thể lấy giá cho {symbol}")
                return False
            
            # Tạo bot mới
            bot = IndicatorBot(symbol, lev, percent, tp, sl, self.ws_manager, threshold)
            self.bots[symbol] = bot
            self.log(f"✅ Đã thêm bot: {symbol} | ĐB: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}% | Ngưỡng: {threshold}%")
            return True
            
        except Exception as e:
            self.log(f"❌ Lỗi tạo bot {symbol}: {str(e)}")
            return False

    def stop_bot(self, symbol):
        symbol = symbol.upper()
        bot = self.bots.get(symbol)
        if bot:
            bot.stop()
            self.log(f"⛔ Đã dừng bot cho {symbol}")
            del self.bots[symbol]
            return True
        return False

    def stop_all(self):
        self.log("⛔ Đang dừng tất cả bot...")
        for symbol in list(self.bots.keys()):
            self.stop_bot(symbol)
        self.ws_manager.stop()
        self.running = False
        self.log("🔴 Hệ thống đã dừng")

    def _status_monitor(self):
        """Kiểm tra và báo cáo trạng thái định kỳ"""
        while self.running:
            try:
                # Tính thời gian hoạt động
                uptime = time.time() - self.start_time
                hours, rem = divmod(uptime, 3600)
                minutes, seconds = divmod(rem, 60)
                uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                
                # Báo cáo số bot đang chạy
                active_bots = [s for s, b in self.bots.items() if not b._stop]
                
                # Báo cáo số dư tài khoản
                balance = get_balance()
                
                # Tạo báo cáo
                status_msg = (
                    f"📊 <b>BÁO CÁO HỆ THỐNG</b>\n"
                    f"⏱ Thời gian hoạt động: {uptime_str}\n"
                    f"🤖 Số bot đang chạy: {len(active_bots)}\n"
                    f"📈 Bot hoạt động: {', '.join(active_bots) if active_bots else 'Không có'}\n"
                    f"💰 Số dư khả dụng: {balance:.2f} USDT"
                )
                send_telegram(status_msg)
                
            except Exception as e:
                logger.error(f"Lỗi báo cáo trạng thái: {str(e)}")
            
            # Kiểm tra mỗi 6 giờ
            time.sleep(6 * 3600)

    def _telegram_listener(self):
        """Lắng nghe và xử lý tin nhắn từ Telegram"""
        last_update_id = 0
        
        while self.running:
            try:
                if not TELEGRAM_BOT_TOKEN:
                    time.sleep(60)
                    continue
                    
                # Lấy tin nhắn mới
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id+1}&timeout=30"
                response = requests.get(url, timeout=35)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        for update in data['result']:
                            update_id = update['update_id']
                            message = update.get('message', {})
                            chat_id = str(message.get('chat', {}).get('id'))
                            text = message.get('text', '').strip()
                            
                            # Chỉ xử lý tin nhắn từ admin
                            if chat_id != self.admin_chat_id:
                                continue
                            
                            # Cập nhật ID tin nhắn cuối
                            if update_id > last_update_id:
                                last_update_id = update_id
                            
                            # Xử lý tin nhắn
                            self._handle_telegram_message(chat_id, text)
                elif response.status_code == 409:
                    # Xử lý xung đột - chỉ có một instance của bot có thể lắng nghe
                    logger.error("Lỗi xung đột: Chỉ một instance bot có thể lắng nghe Telegram")
                    time.sleep(60)
                else:
                    time.sleep(10)
                
            except Exception as e:
                logger.error(f"Lỗi Telegram listener: {str(e)}")
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        """Xử lý tin nhắn từ người dùng"""
        # Lưu trạng thái người dùng
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        # Xử lý theo bước hiện tại
        if current_step == 'waiting_symbol':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_menu_keyboard())
            else:
                symbol = text.upper()
                self.user_states[chat_id] = {
                    'step': 'waiting_leverage',
                    'symbol': symbol
                }
                send_telegram(f"Chọn đòn bẩy cho {symbol}:", chat_id, create_leverage_keyboard())
        
        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_menu_keyboard())
            elif 'x' in text:
                leverage = int(text.replace('', '').replace('x', '').strip())
                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                send_telegram(
                    f"📌 Cặp: {user_state['symbol']}\n Đòn bẩy: {leverage}x\n\nNhập % số dư muốn sử dụng (1-100):",
                    chat_id,
                    create_cancel_keyboard()
                )
        
        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_menu_keyboard())
            else:
                try:
                    percent = float(text)
                    if 1 <= percent <= 100:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        send_telegram(
                            f"📌 Cặp: {user_state['symbol']}\n ĐB: {user_state['leverage']}x\n📊 %: {percent}%\n\nNhập % Take Profit (ví dụ: 10):",
                            chat_id,
                            create_cancel_keyboard()
                        )
                    else:
                        send_telegram("⚠️ Vui lòng nhập % từ 1-100", chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
        
        elif current_step == 'waiting_tp':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_menu_keyboard())
            else:
                try:
                    tp = float(text)
                    if tp > 0:
                        user_state['tp'] = tp
                        user_state['step'] = 'waiting_sl'
                        send_telegram(
                            f"📌 Cặp: {user_state['symbol']}\n ĐB: {user_state['leverage']}x\n📊 %: {user_state['percent']}%\n🎯 TP: {tp}%\n\nNhập % Stop Loss (ví dụ: 5, 0 để tắt SL):",
                            chat_id,
                            create_cancel_keyboard()
                        )
                    else:
                        send_telegram("⚠️ TP phải lớn hơn 0", chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
        
        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_menu_keyboard())
            else:
                try:
                    sl = float(text)
                    if sl >= 0:
                        # Thêm bot
                        symbol = user_state['symbol']
                        leverage = user_state['leverage']
                        percent = user_state['percent']
                        tp = user_state['tp']
                        
                        if self.add_bot(symbol, leverage, percent, tp, sl):
                            send_telegram(
                                f"✅ <b>ĐÃ THÊM BOT THÀNH CÔNG</b>\n\n"
                                f"📌 Cặp: {symbol}\n"
                                f" Đòn bẩy: {leverage}x\n"
                                f"📊 % Số dư: {percent}%\n"
                                f"🎯 TP: {tp}%\n"
                                f"🛡️ SL: {sl}%\n"
                                f"🎯 Chiến lược: Reverse 24h",
                                chat_id,
                                create_menu_keyboard()
                            )
                        else:
                            send_telegram("❌ Không thể thêm bot, vui lòng kiểm tra log", chat_id, create_menu_keyboard())
                        
                        # Reset trạng thái
                        self.user_states[chat_id] = {}
                    else:
                        send_telegram("⚠️ SL phải lớn hơn hoặc bằng 0", chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
        
        # Xử lý các lệnh chính
        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id)
            else:
                message = "🤖 <b>DANH SÁCH BOT ĐANG CHẠY</b>\n\n"
                for symbol, bot in self.bots.items():
                    status = "🟢 Mở" if bot.status == "open" else "🟡 Chờ"
                    message += f"🔹 {symbol} | {status} | {bot.side} | ĐB: {bot.lev}x\n"
                send_telegram(message, chat_id)
        
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_symbol'}
            send_telegram("Chọn cặp coin:", chat_id, create_symbols_keyboard())
        
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id)
            else:
                message = "⛔ <b>CHỌN BOT ĐỂ DỪNG</b>\n\n"
                keyboard = []
                row = []
                
                for i, symbol in enumerate(self.bots.keys()):
                    message += f"🔹 {symbol}\n"
                    row.append({"text": f"⛔ {symbol}"})
                    if len(row) == 2 or i == len(self.bots) - 1:
                        keyboard.append(row)
                        row = []
                
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                
                send_telegram(
                    message, 
                    chat_id, 
                    {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True}
                )
        
        elif text.startswith("⛔ "):
            symbol = text.replace("⛔ ", "").strip().upper()
            if symbol in self.bots:
                self.stop_bot(symbol)
                send_telegram(f"⛔ Đã gửi lệnh dừng bot {symbol}", chat_id, create_menu_keyboard())
            else:
                send_telegram(f"⚠️ Không tìm thấy bot {symbol}", chat_id, create_menu_keyboard())
        
        elif text == "💰 Số dư tài khoản":
            try:
                balance = get_balance()
                send_telegram(f"💰 <b>SỐ DƯ KHẢ DỤNG</b>: {balance:.2f} USDT", chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy số dư: {str(e)}", chat_id)
        
        elif text == "📈 Vị thế đang mở":
            try:
                positions = get_positions()
                if not positions:
                    send_telegram("📭 Không có vị thế nào đang mở", chat_id)
                    return
                
                message = "📈 <b>VỊ THẾ ĐANG MỞ</b>\n\n"
                for pos in positions:
                    position_amt = float(pos.get('positionAmt', 0))
                    if position_amt != 0:
                        symbol = pos.get('symbol', 'UNKNOWN')
                        entry = float(pos.get('entryPrice', 0))
                        side = "LONG" if position_amt > 0 else "SHORT"
                        pnl = float(pos.get('unRealizedProfit', 0))
                        
                        message += (
                            f"🔹 {symbol} | {side}\n"
                            f"📊 Khối lượng: {abs(position_amt):.4f}\n"
                            f"🏷️ Giá vào: {entry:.4f}\n"
                            f"💰 PnL: {pnl:.2f} USDT\n\n"
                        )
                
                send_telegram(message, chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy vị thế: {str(e)}", chat_id)
        
        # Gửi lại menu nếu không có lệnh phù hợp
        elif text:
            self.send_main_menu(chat_id)

# ========== HÀM KHỞI CHẠY CHÍNH ==========
def main():
    # Khởi tạo hệ thống
    manager = BotManager()
    
    # Thêm các bot từ cấu hình
    if BOT_CONFIGS:
        for config in BOT_CONFIGS:
            if len(config) >= 5:
                symbol, lev, percent, tp, sl = config[0], config[1], config[2], config[3], config[4]
                threshold = config[5] if len(config) > 5 else 30  # Mặc định 30% nếu không có
                
                if manager.add_bot(symbol, lev, percent, tp, sl, threshold):
                    manager.log(f"✅ Bot cho {symbol} khởi động thành công (Chiến lược Reverse 24h - Ngưỡng: {threshold}%)")
                else:
                    manager.log(f"⚠️ Bot cho {symbol} khởi động thất bại")
    else:
        manager.log("⚠️ Không tìm thấy cấu hình bot! Vui lòng thiết lập biến môi trường BOT_CONFIGS.")
    
    # Thông báo số dư ban đầu
    try:
        balance = get_balance()
        manager.log(f"💰 SỐ DƯ BAN ĐẦU: {balance:.2f} USDT")
    except Exception as e:
        manager.log(f"⚠️ Lỗi lấy số dư ban đầu: {str(e)}")
    
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
