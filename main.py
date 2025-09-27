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
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Detailed logging configuration
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

# Get configuration from environment variables
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Get bot configuration from environment variables (JSON format)
bot_config_json = os.getenv('BOT_CONFIGS', '[]')
try:
    # BOT_CONFIGS không còn cần initial_weights
    BOT_CONFIGS = json.loads(bot_config_json)
except Exception as e:
    logging.error(f"Error parsing BOT_CONFIGS: {e}")
    BOT_CONFIGS = []

API_KEY = BINANCE_API_KEY
API_SECRET = BINANCE_SECRET_KEY

# ========== TELEGRAM FUNCTIONS ==========
def send_telegram(message, chat_id=None, reply_markup=None):
    """Sends a message via Telegram with detailed error handling."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram Bot Token is not configured.")
        return

    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not chat_id:
        logger.warning("Telegram Chat ID is not configured.")
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
            logger.error(f"Telegram send error ({response.status_code}): {error_msg}")
    except Exception as e:
        logger.error(f"Telegram connection error: {str(e)}")

def create_menu_keyboard():
    """Creates a 3-button menu for Telegram."""
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
    """Creates a cancel keyboard."""
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard():
    """Creates a keyboard for selecting coin pairs."""
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
    """Creates a keyboard for selecting leverage."""
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

# ========== BINANCE API HELPER FUNCTIONS ==========
def sign(query):
    try:
        return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"Error creating signature: {str(e)}")
        send_telegram(f"⚠️ <b>SIGN ERROR:</b> {str(e)}")
        return ""

def binance_api_request(url, method='GET', params=None, headers=None):
    """General function for Binance API requests with detailed error handling."""
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
                    logger.error(f"API Error ({response.status}): {response.read().decode()}")
                    if response.status == 429:  # Rate limit
                        time.sleep(2 ** attempt)  # Exponential backoff
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP Error ({e.code}): {e.reason}")
            if e.code == 429:  # Rate limit
                time.sleep(2 ** attempt)  # Exponential backoff
            elif e.code >= 500:
                time.sleep(1)
            continue
        except Exception as e:
            logger.error(f"API connection error: {str(e)}")
            time.sleep(1)

    logger.error(f"Failed to make API request after {max_retries} attempts")
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
        logger.error(f"Error getting step size: {str(e)}")
        send_telegram(f"⚠️ <b>STEP SIZE ERROR:</b> {symbol} - {str(e)}")
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
        logger.error(f"Error setting leverage: {str(e)}")
        send_telegram(f"⚠️ <b>LEVERAGE ERROR:</b> {symbol} - {str(e)}")
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
        logger.error(f"Error getting balance: {str(e)}")
        send_telegram(f"⚠️ <b>BALANCE ERROR:</b> {str(e)}")
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
        logger.error(f"Error placing order: {str(e)}")
        send_telegram(f"⚠️ <b>ORDER ERROR:</b> {symbol} - {str(e)}")
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
        logger.error(f"Error canceling orders: {str(e)}")
        send_telegram(f"⚠️ <b>CANCEL ORDER ERROR:</b> {symbol} - {str(e)}")
    return False

def get_current_price(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            return float(data['price'])
    except Exception as e:
        logger.error(f"Error getting price: {str(e)}")
        send_telegram(f"⚠️ <b>PRICE ERROR:</b> {symbol} - {str(e)}")
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
        logger.error(f"Error getting positions: {str(e)}")
        send_telegram(f"⚠️ <b>POSITIONS ERROR:</b> {symbol if symbol else ''} - {str(e)}")
    return []

def get_klines(symbol, interval, limit=200):
    """Lấy dữ liệu nến với xử lý lỗi tốt hơn"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
            data = binance_api_request(url)
            
            if data and len(data) > 0:
                df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", 
                                               "close_time", "quote_asset_volume", "number_of_trades", 
                                               "taker_buy_base", "taker_buy_quote", "ignore"])
                # Chuyển đổi kiểu dữ liệu
                numeric_columns = ["open", "high", "low", "close", "volume"]
                for col in numeric_columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Loại bỏ NaN values
                df = df.dropna()
                return df
                
        except Exception as e:
            logger.error(f"Error getting klines for {symbol}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)
    
    return pd.DataFrame()

# ========== TECHNICAL INDICATORS (ĐƠN GIẢN HÓA) ==========

def add_technical_indicators(df):
    """
    Chỉ giữ lại dữ liệu thô (open, close, volume) cần thiết cho chiến lược Volume.
    """
    if df.empty or len(df) < 2:
        return df

    # Đảm bảo các cột số là kiểu số
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df = df.dropna(subset=numeric_columns)
    
    # Giữ lại các cột quan trọng
    df = df[["open_time", "close_time", "open", "close", "volume"]]

    return df

# ========== SIGNAL FUNCTIONS (LOGIC MỚI THEO YÊU CẦU) ==========

def get_signal(df):
    """
    Tính tín hiệu dựa trên:
    1. So sánh Volume nến VỪA ĐÓNG với nến ĐANG CHẠY.
    2. Hướng của nến đang chạy (xanh/đỏ).
    
    Tín hiệu được tạo nếu Volume_Current > 1.2 * Volume_Closed.
    """
    # Cần ít nhất 2 nến để so sánh (nến vừa đóng và nến đang chạy)
    if len(df) < 2:
        return None, None
        
    # Nến vừa đóng (Closed Candle)
    closed_candle = df.iloc[-2]
    closed_volume = closed_candle['volume']
    
    # Nến đang chạy (Current/Forming Candle)
    current_candle = df.iloc[-1]
    current_volume = current_candle['volume']
    
    # Xác định hướng nến đang chạy
    is_green_candle = current_candle['close'] > current_candle['open']
    is_red_candle = current_candle['close'] < current_candle['open']

    # Kiểm tra điều kiện Volume
    volume_condition_met = current_volume > (closed_volume * 2)
    
    signal = None
    
    if volume_condition_met:
        if is_green_candle:
            signal = "BUY"
        elif is_red_candle:
            signal = "SELL"
            
    # Trả về tín hiệu, và Volume hiện tại/đóng để log
    volume_data = {
        "Current_Volume": current_volume, 
        "Closed_Volume": closed_volume
    }
    return signal, volume_data

def update_weights_and_stats(*args):
    """
    Hàm này không còn cần thiết và được giữ lại ở dạng tối giản để tránh lỗi.
    """
    # Không thực hiện điều chỉnh trọng số
    indicator_weights = args[2] if len(args) > 2 and isinstance(args[2], dict) else {}
    indicator_stats = args[3] if len(args) > 3 and isinstance(args[3], dict) else {}
    return indicator_weights, indicator_stats

# ========== WEBSOCKET MANAGER (Giữ nguyên) ==========
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
                logger.error(f"WebSocket message processing error {symbol}: {str(e)}")

        def on_error(ws, error):
            logger.error(f"WebSocket error {symbol}: {str(error)}")
            if not self._stop_event.is_set():
                time.sleep(5)
                self._reconnect(symbol, callback)

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed {symbol}: {close_status_code} - {close_msg}")
            if not self._stop_event.is_set() and symbol in self.connections:
                time.sleep(5)
                self._reconnect(symbol, callback)

        def on_open(ws):
            logger.info(f"WebSocket connected for {symbol}")

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()

        self.connections[symbol] = {
            'ws': ws,
            'thread': thread,
            'callback': callback
        }
        logger.info(f"WebSocket started for {symbol}")

    def _reconnect(self, symbol, callback):
        logger.info(f"Reconnecting WebSocket for {symbol}")
        self.remove_symbol(symbol)
        time.sleep(2)
        self._create_connection(symbol, callback)

    def remove_symbol(self, symbol):
        symbol = symbol.upper()
        with self._lock:
            if symbol in self.connections:
                try:
                    self.connections[symbol]['ws'].close()
                except Exception as e:
                    logger.error(f"Error closing WebSocket {symbol}: {str(e)}")
                del self.connections[symbol]
                logger.info(f"WebSocket removed for {symbol}")

    def stop(self):
        self._stop_event.set()
        for symbol in list(self.connections.keys()):
            self.remove_symbol(symbol)

# ========== MAIN BOT CLASS ==========
class IndicatorBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, initial_weights=None):
        self.symbol = symbol.upper()
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.ws_manager = ws_manager
        
        # Xóa/Đơn giản hóa logic weights/stats
        self.indicator_weights = {} 
        self.indicator_stats = {} 
        
        self.check_position_status()
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []

        self._stop = False
        self.signal_threshold = 0 # Không dùng ngưỡng
        self.position_open = False
        self.last_trade_time = 0
        self.position_check_interval = 30
        self.last_position_check = 0
        self.last_error_log_time = 0
        self.last_close_time = 0
        # Đã sửa: Cooldown 60s
        self.cooldown_period = 60 
        self.max_position_attempts = 3
        self.position_attempt_count = 0
        self.last_candle_timestamp = 0 # Dùng để theo dõi nến vừa đóng

        # Bắt đầu WebSocket và main loop
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        # Đã sửa: Logic thành Volume 1m
        self.log(f"🟢 Bot started for {self.symbol} | Lev: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}% | Logic: Volume 1m")


    def calculate_roi(self):
        """
        Tính ROI (%) của vị thế hiện tại.
        """
        if not self.position_open or self.entry == 0:
            return 0.0
        
        current_price = self.prices[-1] if self.prices else self.entry
        if self.side == "BUY":
            roi = ((current_price - self.entry) / self.entry) * self.lev * 100
        else:  # SELL
            roi = ((self.entry - current_price) / self.entry) * self.lev * 100
        
        return roi

    def log(self, message, is_critical=True):
        """Ghi log và chỉ gửi Telegram nếu là thông báo quan trọng."""
        logger.info(f"[{self.symbol}] {message}") 
        if is_critical:
            send_telegram(f"<b>{self.symbol}</b>: {message}")

    def _handle_price_update(self, price):
        """Xử lý giá real-time từ WebSocket"""
        if self._stop:
            return
        
        # Chỉ xử lý nếu có giá mới
        if not self.prices or price != self.prices[-1]:
            self.prices.append(price)
            if len(self.prices) > 100:
                self.prices = self.prices[-100:]
            
            # Kiểm tra TP/SL real-time
            if self.position_open:
                self.check_tp_sl()


    def _run(self):
        """Main loop với xử lý nến 1 phút"""
        self.log("🔍 Starting main loop with 1-minute candle processing...")
        
        while not self._stop:
            try:
                current_time = time.time()
                
                # Kiểm tra vị trí mỗi 30 giây
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                    
                # Đã sửa: Lấy dữ liệu nến 1 phút
                df = get_klines(self.symbol, "1m", 10) 
                if df.empty or len(df) < 2:
                    time.sleep(1)
                    continue

                # Chỉ cần thêm các cột thô (Volume, Open, Close)
                df = add_technical_indicators(df)
                
                # Kiểm tra dữ liệu hợp lệ
                if df.iloc[-1].isnull().any():
                    time.sleep(1)
                    continue
                    
                # Phát hiện nến vừa đóng hoàn toàn
                latest_closed_candle_timestamp = df['close_time'].iloc[-2] / 1000 
                
                if latest_closed_candle_timestamp > self.last_candle_timestamp:
                    self.last_candle_timestamp = latest_closed_candle_timestamp
                    
                    # Tính toán tín hiệu dựa trên 2 nến cuối (1 vừa đóng và 1 đang chạy)
                    signal, volume_data = get_signal(df)
                    
                    current_volume = volume_data.get("Current_Volume", 0)
                    closed_volume = volume_data.get("Closed_Volume", 0)
                    
                    # Đã sửa: Log thành Volume 1m
                    log_msg = (f"📊 1m Volume Check | Current: {current_volume:.2f} | "
                               f"Closed: {closed_volume:.2f} | Ratio: {current_volume/closed_volume if closed_volume else 0:.2f}x")
                    self.log(log_msg, is_critical=False)
                    
                    # Xử lý lệnh
                    if self.position_open:
                        if (self.side == "BUY" and signal == "SELL"):
                            # Đóng lệnh hiện tại trước, KHÔNG mở lệnh mới ngay
                            roi = self.calculate_roi()  # hàm có sẵn trong bot
                            if roi < 0 and roi != -5000 and roi != 5000:
                                self.close_position(f"🔄 Đảo chiều: {self.side} → {signal} | ROI hiện tại: {roi:.2f}%")
                                # Lệnh mới sẽ được mở ở vòng loop tiếp theo sau khi đóng hoàn tất
                        if (self.side == "SELL" and signal == "BUY"):
                            # Đóng lệnh hiện tại trước, KHÔNG mở lệnh mới ngay
                            roi = self.calculate_roi()  # hàm có sẵn trong bot
                            if (roi < -100 or roi > 10) and roi != -5000 and roi != 5000:
                                self.close_position(f"🔄 Đảo chiều: {self.side} → {signal} | ROI hiện tại: {roi:.2f}%")
                                # Lệnh mới sẽ được mở ở vòng loop tiếp theo sau khi đóng hoàn tất
                        else:
                            self.check_tp_sl()  # Kiểm tra TP/SL
                    else:
                        # Vào lệnh mới nếu có tín hiệu
                        if signal and current_time - self.last_trade_time > self.cooldown_period:
                            # Đã sửa lỗi: Truyền current_volume và closed_volume
                            self.open_position(signal, current_volume, closed_volume) 
                            self.last_trade_time = current_time
                        
                time.sleep(1)  # Sleep ngắn hơn cho khung 1m
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 30:
                    self.log(f"❌ Main loop error: {str(e)}", is_critical=False)
                    self.last_error_log_time = time.time()
                time.sleep(5)


    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        try:
            cancel_all_orders(self.symbol)
        except Exception as e:
            self.log(f"Order cancellation error: {str(e)}")
        self.log(f"🔴 Bot stopped for {self.symbol}")

    def check_position_status(self):
        try:
            positions = get_positions(self.symbol)
            if not positions or len(positions) == 0:
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
                        self.position_open = True
                        self.status = "open"
                        self.side = "BUY" if position_amt > 0 else "SELL"
                        self.qty = position_amt
                        self.entry = float(pos.get('entryPrice', 0))
                        return
                        
            self.position_open = False
            self.status = "waiting"
            self.side = ""
            self.qty = 0
            self.entry = 0
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"Position check error: {str(e)}")
                self.last_error_log_time = time.time()

    def check_tp_sl(self):
        if not self.position_open or not self.entry or not self.qty:
            return
            
        try:
            current_price = self.prices[-1] if self.prices else get_current_price(self.symbol)
            if current_price <= 0:
                return
                
            if self.side == "BUY":
                profit = (current_price - self.entry) * abs(self.qty)
            else:  # SELL
                profit = (self.entry - current_price) * abs(self.qty)
                
            invested = self.entry * abs(self.qty) / self.lev
            if invested <= 0:
                return
                
            roi = (profit / invested) * 100
            
            if roi >= self.tp:
                self.close_position(f"✅ TP hit at {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl is not None and self.sl > 0 and roi <= -self.sl: # Thêm điều kiện self.sl > 0
                self.close_position(f"❌ SL hit at {self.sl}% (ROI: {roi:.2f}%)")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"TP/SL check error: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side, current_volume=0, closed_volume=0): # Thêm tham số volume
        self.check_position_status()
        if self.position_open:
            self.log("⚠️ Position already open, skipping")
            return
            
        try:
            # Hủy tất cả orders cũ
            cancel_all_orders(self.symbol)
            
            # Set leverage
            if not set_leverage(self.symbol, self.lev):
                self.log(f"❌ Could not set leverage to {self.lev}")
                return
                
            # Tính số lượng
            balance = get_balance()
            if balance <= 0:
                self.log("❌ Insufficient USDT balance")
                return
                
            usdt_amount = balance * (min(max(self.percent, 1), 100) / 100)
            price = get_current_price(self.symbol)
            if price <= 0:
                self.log("❌ Error getting price")
                return
                
            step = get_step_size(self.symbol)
            if step <= 0:
                step = 0.001
                
            qty = (usdt_amount * self.lev) / price
            if step > 0:
                qty = math.floor(qty / step) * step
                
            qty = max(qty, step)  # Đảm bảo không nhỏ hơn step size
            qty = round(qty, 8)
            
            if qty < step:
                self.log(f"⚠️ Quantity too small: {qty} < {step}")
                return
                
            # Đặt lệnh
            res = place_order(self.symbol, side, qty)
            if not res:
                self.log("❌ Error placing order")
                return
                
            executed_qty = float(res.get('executedQty', 0))
            if executed_qty < 0:
                self.log(f"❌ Order not filled: {executed_qty}")
                return
                
            # Cập nhật trạng thái
            self.entry = float(res.get('avgPrice', price))
            self.side = side
            self.qty = executed_qty if side == "BUY" else -executed_qty
            self.status = "open"
            self.position_open = True
            self.position_attempt_count = 0

            # Gửi thông báo VÀ IN LOG CHI TIẾT VOLUME
            volume_ratio = current_volume / closed_volume if closed_volume else 0
            message = (f"✅ <b>POSITION OPENED {self.symbol}</b>\n"
                       f"📌 Direction: {side}\n"
                       f"🏷️ Entry Price: {self.entry:.4f}\n"
                       f"📊 Quantity: {executed_qty}\n"
                       f"💵 Value: {executed_qty * self.entry:.2f} USDT\n"
                       f" Leverage: {self.lev}x\n"
                       f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%\n"
                       f"🔥 **Volume Ratio: {volume_ratio:.2f}x** "
                       f"(Current: {current_volume:.2f} | Closed: {closed_volume:.2f})")
            
            # Gửi Telegram (is_critical=True là mặc định)
            self.log(message, is_critical=True)
            
        except Exception as e:
            self.position_open = False
            self.log(f"❌ Error entering position: {str(e)}")

    def close_position(self, reason=""):
        # Lấy logic đóng lệnh từ file 42: Đóng vị thế với số lượng chính xác
        try:
            cancel_all_orders(self.symbol)
            if abs(self.qty) > 0:
                close_side = "SELL" if self.side == "BUY" else "BUY"
                close_qty = abs(self.qty)
                
                # Làm tròn số lượng CHÍNH XÁC
                step = get_step_size(self.symbol)
                if step > 0:
                    # Tính toán chính xác số bước
                    steps = close_qty / step
                    # Làm tròn đến số nguyên gần nhất
                    close_qty = round(steps) * step
                
                close_qty = max(close_qty, 0)
                close_qty = round(close_qty, 8)
                
                res = place_order(self.symbol, close_side, close_qty)
                if res:
                    price = float(res.get('avgPrice', 0))
                    
                    # Tính ROI cho thông báo đóng lệnh (dùng hàm đã có)
                    roi = self.calculate_roi() 

                    message = (f"⛔ <b>POSITION CLOSED {self.symbol}</b>\n"
                              f"📌 Reason: {reason}\n"
                              f"🏷️ Exit Price: {price:.4f}\n"
                              f"📊 Quantity: {close_qty}\n"
                              f"💵 Value: {close_qty * price:.2f} USDT\n"
                              f"🔥 ROI: {roi:.2f}%") # Thêm ROI vào thông báo
                    self.log(message)
                    
                    # Cập nhật trạng thái NGAY LẬP TỨC (quan trọng)
                    self.status = "waiting"
                    self.side = ""
                    self.qty = 0
                    self.entry = 0
                    self.position_open = False
                    self.last_trade_time = time.time()
                    self.last_close_time = time.time()
                else:
                    self.log("❌ Error closing position")
        except Exception as e:
            self.log(f"❌ Error closing position: {str(e)}")

# ========== BOT MANAGER (Giữ nguyên) ==========
class BotManager:
    def __init__(self):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}
        self.admin_chat_id = TELEGRAM_CHAT_ID
        self.log("🟢 BOT SYSTEM STARTED")
        self.status_thread = threading.Thread(target=self._status_monitor, daemon=True)
        self.status_thread.start()
        self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
        self.telegram_thread.start()
        if self.admin_chat_id:
            self.send_main_menu(self.admin_chat_id)

    def log(self, message, is_critical=True):
        """Ghi log và chỉ gửi Telegram nếu là thông báo quan trọng."""
        logger.info(f"[SYSTEM] {message}") 
        if is_critical:
            send_telegram(f"<b>SYSTEM</b>: {message}")

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BINANCE FUTURES TRADING BOT</b>\n\nChoose an option below:"
        send_telegram(welcome, chat_id, create_menu_keyboard())

    def add_bot(self, symbol, lev, percent, tp, sl, initial_weights=None):
        if sl == 0:
            sl = None
        symbol = symbol.upper()
        if symbol in self.bots:
            self.log(f"⚠️ Bot already exists for {symbol}")
            return False
            
        if not API_KEY or not API_SECRET:
            self.log("❌ API Key and Secret Key not configured!")
            return False
            
        try:
            # Kiểm tra symbol có tồn tại
            price = get_current_price(symbol)
            if price <= 0:
                self.log(f"❌ Cannot get price for {symbol}")
                return False
                
            # Tạo bot
            # Không cần truyền initial_weights nữa
            bot = IndicatorBot(symbol, lev, percent, tp, sl, self.ws_manager)
            self.bots[symbol] = bot
            self.log(f"✅ Bot added: {symbol} | Lev: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}%")
            return True
            
        except Exception as e:
            self.log(f"❌ Error creating bot {symbol}: {str(e)}")
            return False

    def stop_bot(self, symbol):
        symbol = symbol.upper()
        bot = self.bots.get(symbol)
        if bot:
            bot.stop()
            # Bot sẽ tự đóng vị thế trong hàm stop
            self.log(f"⛔ Bot stopped for {symbol}")
            del self.bots[symbol]
            return True
        return False

    def stop_all(self):
        self.log("⛔ Stopping all bots...")
        for symbol in list(self.bots.keys()):
            self.stop_bot(symbol)
        self.ws_manager.stop()
        self.running = False
        self.log("🔴 System stopped")

    def _status_monitor(self):
        while self.running:
            try:
                uptime = time.time() - self.start_time
                hours, rem = divmod(uptime, 3600)
                minutes, seconds = divmod(rem, 60)
                uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                active_bots = [s for s, b in self.bots.items() if not b._stop]
                balance = get_balance()
                
                status_msg = (f"📊 <b>SYSTEM STATUS</b>\n"
                             f"⏱ Uptime: {uptime_str}\n"
                             f"🤖 Active Bots: {len(active_bots)}\n"
                             f"📈 Active Pairs: {', '.join(active_bots) if active_bots else 'None'}\n"
                             f"💰 Available Balance: {balance:.2f} USDT")
                send_telegram(status_msg)
                
            except Exception as e:
                logger.error(f"Status report error: {str(e)}")
            time.sleep(6 * 3600)  # 6 hours

    def _telegram_listener(self):
        last_update_id = 0
        while self.running:
            try:
                if not TELEGRAM_BOT_TOKEN:
                    time.sleep(60)
                    continue
                    
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
                            
                            if chat_id != self.admin_chat_id:
                                continue
                                
                            if update_id > last_update_id:
                                last_update_id = update_id
                                self._handle_telegram_message(chat_id, text)
                elif response.status_code == 409:
                    logger.error("Conflict error: Only one bot instance can listen to Telegram")
                    time.sleep(60)
                else:
                    time.sleep(10)
                    
            except Exception as e:
                logger.error(f"Telegram listener error: {str(e)}")
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        if current_step == 'waiting_symbol':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                symbol = text.upper()
                self.user_states[chat_id] = {'step': 'waiting_leverage', 'symbol': symbol}
                send_telegram(f"Choose leverage for {symbol}:", chat_id, create_leverage_keyboard())
                
        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            elif 'x' in text:
                leverage = int(text.replace('', '').replace('x', '').strip())
                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                send_telegram(f"Enter % of balance to use (1-100):", chat_id, create_cancel_keyboard())
                
        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    percent = float(text)
                    if 1 <= percent <= 100:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        send_telegram(f"Enter % Take Profit (e.g., 10):", chat_id, create_cancel_keyboard())
                    else:
                        send_telegram("⚠️ Please enter a % from 1-100", chat_id)
                except Exception:
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)
                    
        elif current_step == 'waiting_tp':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    tp = float(text)
                    if tp > 0:
                        user_state['tp'] = tp
                        user_state['step'] = 'waiting_sl'
                        send_telegram(f"Enter % Stop Loss (e.g., 5, 0 for no SL):", chat_id, create_cancel_keyboard())
                    else:
                        send_telegram("⚠️ TP must be greater than 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)
                    
        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    sl = float(text)
                    if sl >= 0:
                        symbol = user_state['symbol']
                        leverage = user_state['leverage']
                        percent = user_state['percent']
                        tp = user_state['tp']
        
                        # KHÔNG CẦN TRAINING NỮA
                        
                        if self.add_bot(symbol, leverage, percent, tp, sl, initial_weights=None):
                            send_telegram(
                                f"✅ <b>BOT ADDED SUCCESSFULLY</b>\n\n"
                                f"📌 Pair: {symbol}\n"
                                f" Leverage: {leverage}x\n"
                                f"📊 % Balance: {percent}%\n"
                                f"🎯 TP: {tp}%\n"
                                f"🛡️ SL: {sl}%",
                                chat_id,
                                create_menu_keyboard()
                            )
                        else:
                            send_telegram("❌ Could not add bot (API error or invalid symbol)", chat_id, create_menu_keyboard())
                        
                        self.user_states[chat_id] = {}
                    else:
                        send_telegram("⚠️ SL must be greater than or equal to 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)

                    
        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 No bots are currently running", chat_id)
            else:
                message = "🤖 <b>LIST OF RUNNING BOTS</b>\n\n"
                for symbol, bot in self.bots.items():
                    status = "🟢 Open" if bot.status == "open" else "🟡 Waiting"
                    message += f"🔹 {symbol} | {status} | {bot.side} | Lev: {bot.lev}x\n"
                send_telegram(message, chat_id)
                
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_symbol'}
            send_telegram("Choose a coin pair:", chat_id, create_symbols_keyboard())
            
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 No bots are currently running", chat_id)
            else:
                message = "⛔ <b>CHOOSE BOT TO STOP</b>\n\n"
                keyboard = []
                row = []
                for i, symbol in enumerate(self.bots.keys()):
                    message += f"🔹 {symbol}\n"
                    row.append({"text": f"⛔ {symbol}"})
                    if len(row) == 2 or i == len(self.bots) - 1:
                        keyboard.append(row)
                        row = []
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                send_telegram(message, chat_id, {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True})
                
        elif text.startswith("⛔ "):
            symbol = text.replace("⛔ ", "").strip().upper()
            if symbol in self.bots:
                self.stop_bot(symbol)
                send_telegram(f"⛔ Stop command sent for bot {symbol}", chat_id, create_menu_keyboard())
            else:
                send_telegram(f"⚠️ Bot not found {symbol}", chat_id, create_menu_keyboard())
                
        elif text == "💰 Số dư tài khoản":
            try:
                balance = get_balance()
                send_telegram(f"💰 <b>AVAILABLE BALANCE</b>: {balance:.2f} USDT", chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Error getting balance: {str(e)}", chat_id)
                
        elif text == "📈 Vị thế đang mở":
            try:
                positions = get_positions()
                if not positions:
                    send_telegram("📭 No open positions", chat_id)
                    return
                message = "📈 <b>OPEN POSITIONS</b>\n\n"
                for pos in positions:
                    position_amt = float(pos.get('positionAmt', 0))
                    if position_amt != 0:
                        symbol = pos.get('symbol', 'UNKNOWN')
                        entry = float(pos.get('entryPrice', 0))
                        side = "LONG" if position_amt > 0 else "SHORT"
                        pnl = float(pos.get('unRealizedProfit', 0))
                        message += (f"🔹 {symbol} | {side}\n"
                                  f"📊 Quantity: {abs(position_amt):.4f}\n"
                                  f"🏷️ Entry Price: {entry:.4f}\n"
                                  f"💰 PnL: {pnl:.2f} USDT\n\n")
                send_telegram(message, chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Error getting positions: {str(e)}", chat_id)
        elif text:
            self.send_main_menu(chat_id)

# ========== FUNCTIONS FOR INITIAL TRAINING (Bị xóa vì không dùng weights) ==========
def perform_initial_training(manager, bot_configs):
    """ Hàm này bị giữ lại rỗng để tránh lỗi nếu có nơi nào gọi đến """
    manager.log("⚠️ Initial training function is disabled (Volume logic in use).")
    for config in bot_configs:
        if len(config) == 5:
            config.append(None) # Đảm bảo config có 6 phần tử để tránh lỗi index

# ========== MAIN FUNCTION ==========
def main():
    manager = BotManager()

    if BOT_CONFIGS:
        # Gọi hàm training rỗng để đảm bảo BOT_CONFIGS có 6 phần tử (dù không dùng weights)
        perform_initial_training(manager, BOT_CONFIGS) 
        
        for config in BOT_CONFIGS:
            if len(config) >= 5:
                # Lấy 5 tham số chính
                symbol, lev, percent, tp, sl = config[0], config[1], config[2], config[3], config[4]
                
                # initial_weights luôn là None
                if manager.add_bot(symbol, lev, percent, tp, sl, initial_weights=None):
                    manager.log(f"✅ Bot for {symbol} started successfully (Volume Logic)")
                else:
                    manager.log(f"⚠️ Bot for {symbol} failed to start")
    else:
        manager.log("⚠️ No bot configurations found! Please set BOT_CONFIGS environment variable.")

    try:
        balance = get_balance()
        manager.log(f"💰 INITIAL BALANCE: {balance:.2f} USDT")
    except Exception as e:
        manager.log(f"⚠️ Error getting initial balance: {str(e)}")

    try:
        while manager.running:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.log("👋 Received stop signal...")
    except Exception as e:
        manager.log(f"❌ SYSTEM ERROR: {str(e)}")
    finally:
        manager.stop_all()

if __name__ == "__main__":
    main()
