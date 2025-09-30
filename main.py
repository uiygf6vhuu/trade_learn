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
    BOT_CONFIGS = json.loads(bot_config_json)
except Exception as e:
    logging.error(f"Error parsing BOT_CONFIGS: {e}")
    BOT_CONFIGS = []

API_KEY = BINANCE_API_KEY
API_SECRET = BINANCE_SECRET_KEY

# ========== TELEGRAM FUNCTIONS ==========
def send_telegram(message, chat_id=None, reply_markup=None):
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
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_leverage_keyboard():
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
    """
    General function for Binance API requests with DETAILED ERROR LOGGING.
    """
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
                    error_response = response.read().decode()
                    logger.error(f"API Error ({response.status}): {error_response}")
                    
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            error_response = e.read().decode()
            logger.error(f"HTTP Error ({e.code}): {e.reason}. Detail: {error_response}")
            
            if e.code == 429:
                time.sleep(2 ** attempt)
            elif e.code >= 500:
                time.sleep(1)
            continue
        except Exception as e:
            logger.error(f"API connection error: {str(e)}")
            time.sleep(1)

    logger.error(f"Failed to make API request after {max_retries} attempts")
    return None

def get_max_leverage(symbol):
    """Lấy đòn bẩy tối đa cho một symbol từ API Notional And Leverage Brackets."""
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/leverageBracket?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        
        data = binance_api_request(url, headers=headers)
        if (data and isinstance(data, list) and len(data) > 0 and 
            'brackets' in data[0] and len(data[0]['brackets']) > 0 and
            'initialLeverage' in data[0]['brackets'][0]):
            return int(data[0]['brackets'][0]['initialLeverage'])
        else:
            logger.warning(f"Invalid leverage data structure for {symbol}")
    except Exception as e:
        logger.error(f"Error getting max leverage for {symbol}: {str(e)}")
    return 20

def find_eligible_symbols(min_leverage, min_change_percent=30.0):
    """
    Tìm TẤT CẢ symbol có đòn bẩy tối đa >= min_leverage và biến động 24h (giá trị tuyệt đối) >= min_change_percent.
    """
    url_ticker = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    ticker_data = binance_api_request(url_ticker) 
    
    if not ticker_data:
        logger.error("Could not get 24hr Ticker data.")
        return []

    eligible_symbols = []
    
    for ticker in ticker_data:
        symbol = ticker.get('symbol')
        price_change_percent_str = ticker.get('priceChangePercent')
        
        if not symbol or not price_change_percent_str or not symbol.endswith('USDT'):
            continue
            
        try:
            price_change_percent = float(price_change_percent_str)
            if abs(price_change_percent) >= min_change_percent:
                max_lev = get_max_leverage(symbol)
                if max_lev >= min_leverage:
                     eligible_symbols.append({
                        "symbol": symbol,
                        "change": price_change_percent,
                        "max_leverage": max_lev
                    })
        except ValueError as e:
            logger.debug(f"Invalid price change percent for {symbol}: {price_change_percent_str}")
            continue
            
    # Sắp xếp theo biến động giảm dần
    eligible_symbols.sort(key=lambda x: abs(x['change']), reverse=True)
    
    return eligible_symbols

def get_24h_change(symbol):
    """Lấy phần trăm thay đổi giá 24h cho một symbol cụ thể."""
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'priceChangePercent' in data:
            return float(data['priceChangePercent'])
    except Exception as e:
        logger.error(f"Error getting 24h change for {symbol}: {str(e)}")
    return 0.0

def get_step_size(symbol):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        data = binance_api_request(url)
        if not data: return 0.001
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
        params = {"symbol": symbol.upper(), "leverage": lev, "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/leverage?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        response = binance_api_request(url, method='POST', headers=headers)
        if response and 'leverage' in response: return True
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
        if not data: return 0
        for asset in data['assets']:
            if asset['asset'] == 'USDT': return float(asset['availableBalance'])
    except Exception as e: 
        logger.error(f"Error getting balance: {str(e)}")
        send_telegram(f"⚠️ <b>BALANCE ERROR:</b> {str(e)}")
    return 0

def place_order(symbol, side, qty):
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "side": side, "type": "MARKET", "quantity": qty, "timestamp": ts}
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
        if data and 'price' in data: return float(data['price'])
    except Exception as e: 
        logger.error(f"Error getting price: {str(e)}")
        send_telegram(f"⚠️ <b>PRICE ERROR:</b> {symbol} - {str(e)}")
    return 0

def get_positions(symbol=None):
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        if symbol: params["symbol"] = symbol.upper()
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v2/positionRisk?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}
        positions = binance_api_request(url, headers=headers)
        if not positions: return []
        if symbol:
            for pos in positions:
                if pos['symbol'] == symbol.upper(): return [pos]
        return positions
    except Exception as e: 
        logger.error(f"Error getting positions: {str(e)}")
        send_telegram(f"⚠️ <b>POSITIONS ERROR:</b> {symbol if symbol else ''} - {str(e)}")
    return []

def update_weights_and_stats(*args):
    """Hàm này được giữ lại ở dạng tối giản để tránh lỗi gọi hàm."""
    return {}, {}

# ========== WEBSOCKET MANAGER (ĐÃ CẢI THIỆN) ==========
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
        if self._stop_event.is_set(): return
        stream = f"{symbol.lower()}@aggTrade"
        url = f"wss://fstream.binance.com/ws/{stream}"

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if 'p' in data:
                    price = float(data['p'])
                    # Thêm rate limiting để tránh xử lý quá nhiều message
                    current_time = time.time()
                    if hasattr(ws, 'last_processed') and current_time - ws.last_processed < 0.1:
                        return
                    ws.last_processed = current_time
                    self.executor.submit(callback, price)
            except Exception as e: 
                logger.error(f"WebSocket message processing error {symbol}: {str(e)}")

        def on_error(ws, error):
            logger.error(f"WebSocket error {symbol}: {str(error)}")
            if not self._stop_event.is_set(): 
                time.sleep(5)
                # Thêm kiểm tra số lần reconnect
                if hasattr(ws, 'reconnect_count'):
                    ws.reconnect_count += 1
                    if ws.reconnect_count > 5:
                        logger.error(f"Max reconnection attempts reached for {symbol}")
                        return
                else:
                    ws.reconnect_count = 1
                self._reconnect(symbol, callback)

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed {symbol}: {close_status_code} - {close_msg}")
            if not self._stop_event.is_set() and symbol in self.connections: 
                time.sleep(5)
                self._reconnect(symbol, callback)

        def on_open(ws): 
            logger.info(f"WebSocket connected for {symbol}")
            ws.last_processed = 0

        ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()
        self.connections[symbol] = {'ws': ws, 'thread': thread, 'callback': callback}
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

# ========== MAIN BOT CLASS (Logic Dynamic Hunter - ĐÃ SỬA LỖI) ==========
class IndicatorBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, change_24h, max_leverage, min_volatility):
        self.symbol = symbol.upper()
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.ws_manager = ws_manager
        
        self.initial_lev = lev
        self.initial_symbol = symbol.upper()
        self.current_max_leverage = max_leverage
        self.min_volatility = min_volatility
        
        self.target_side = self._determine_target_side(change_24h) 
        self.current_change_24h = change_24h

        # Kiểm tra vị thế đang mở
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
        self.cooldown_period = 60
        self.last_symbol_search = 0
        self.symbol_search_interval = 30
        
        self.log(f"🟢 Bot started | Current: {self.symbol} | Target: {self.target_side} | Lev: {self.lev}x | Min Vol: {self.min_volatility}%")

        # Bắt đầu WebSocket cho symbol hiện tại
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _determine_target_side(self, change_24h):
        """Xác định chiều vào lệnh ngược xu hướng 24h (>= Min Volatility)."""
        if change_24h <= -self.min_volatility:
            return "BUY" 
        elif change_24h >= self.min_volatility:
            return "SELL" 
        else:
            # Nếu biến động không đủ, vẫn trả về hướng dựa trên trend
            return "BUY" if change_24h < 0 else "SELL"

    def calculate_roi(self):
        if not self.position_open or self.entry == 0 or self.entry is None: 
            return 0.0
        try:
            current_price = self.prices[-1] if self.prices else self.entry
            if self.entry == 0:
                return 0.0
            if self.side == "BUY": 
                roi = ((current_price - self.entry) / self.entry) * self.lev * 100
            else: 
                roi = ((self.entry - current_price) / self.entry) * self.lev * 100
            return roi
        except Exception as e:
            logger.error(f"ROI calculation error: {str(e)}")
            return 0.0

    def log(self, message, is_critical=True):
        logger.info(f"[{self.initial_symbol}/{self.symbol}] {message}") 
        if is_critical: 
            send_telegram(f"<b>{self.initial_symbol} ({self.symbol})</b>: {message}")

    def _handle_price_update(self, price):
        if self._stop: return
        if not self.prices or price != self.prices[-1]:
            self.prices.append(price)
            if len(self.prices) > 100: 
                self.prices = self.prices[-100:]
            if self.position_open: 
                self.check_tp_sl()

    def _update_symbol_and_stream(self, new_symbol, new_change_24h, new_max_leverage):
        """Cập nhật symbol và WebSocket stream khi tìm thấy symbol mới."""
        
        self.log(f"🔄 Switching monitoring from {self.symbol} to {new_symbol} (Target: {new_change_24h:.2f}%)")
        
        # 1. Dừng stream cũ
        self.ws_manager.remove_symbol(self.symbol) 
        
        # 2. Cập nhật symbol và trạng thái
        self.symbol = new_symbol 
        self.current_change_24h = new_change_24h
        self.current_max_leverage = new_max_leverage
        self.target_side = self._determine_target_side(new_change_24h)
        self.prices = [] # Reset giá
        
        # 3. Bắt đầu stream mới
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)

    def _run(self):
        """Main loop: Kiểm tra vị thế. Nếu chưa có, tìm symbol mới và vào lệnh trên symbol đó."""
        self.log("🔍 Starting main trade loop (Dynamic Hunter).")
        
        while not self._stop:
            try:
                current_time = time.time()
                
                # 1. Kiểm tra vị trí
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                    
                if self.position_open:
                    self.check_tp_sl()
                else:
                    # 2. Logic: Nếu bot chưa có lệnh, tìm symbol mới và vào lệnh
                    if (current_time - self.last_trade_time > self.cooldown_period and 
                        current_time - self.last_symbol_search > self.symbol_search_interval):
                        
                        self.log("🔄 Position closed. Starting search from scratch...")
                        
                        # Tự động tìm symbol tốt nhất
                        eligible_list = find_eligible_symbols(
                            min_leverage=self.initial_lev, 
                            min_change_percent=self.min_volatility
                        )
                        
                        if eligible_list:
                            best_entry = eligible_list[0]
                            symbol = best_entry['symbol']
                            change_24h = best_entry['change']
                            max_leverage = best_entry['max_leverage']
                            new_target_side = self._determine_target_side(change_24h)
                            
                            if new_target_side:
                                # Chuyển đổi symbol chỉ khi symbol tốt nhất khác symbol bot đang theo dõi
                                if symbol != self.symbol:
                                    self._update_symbol_and_stream(symbol, change_24h, max_leverage)
                                else:
                                    # Nếu symbol vẫn là tốt nhất, chỉ cập nhật trạng thái
                                    self.current_change_24h = change_24h
                                    self.current_max_leverage = max_leverage
                                
                                # Mở lệnh trên symbol hiện tại
                                self.log(f"🚀 Attempting to open {new_target_side} position on {self.symbol}...")
                                self.open_position(new_target_side, change_24h=self.current_change_24h)
                                self.last_trade_time = current_time
                            else:
                                self.log(f"⚠️ Found {symbol} but 24h change ({change_24h:.2f}%) does not meet the {self.min_volatility}% threshold for entry.")
                        else:
                            self.log("⏳ No suitable high volatility symbol found. Waiting 60 seconds...")
                            time.sleep(60)
                        
                        self.last_symbol_search = current_time
                        
                time.sleep(5) 
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 30:
                    self.log(f"❌ Main loop error: {str(e)}", is_critical=False)
                    self.last_error_log_time = time.time()
                time.sleep(10)

    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        try: 
            cancel_all_orders(self.symbol)
        except Exception as e: 
            self.log(f"Order cancellation error: {str(e)}")
        self.log(f"🔴 Bot stopped for {self.initial_symbol}") 

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
            else: 
                profit = (self.entry - current_price) * abs(self.qty)
                
            invested = self.entry * abs(self.qty) / self.lev
            if invested <= 0: 
                return
                
            roi = (profit / invested) * 100
            if roi >= self.tp: 
                self.close_position(f"✅ TP hit at {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl is not None and self.sl > 0 and roi <= -self.sl: 
                self.close_position(f"❌ SL hit at {self.sl}% (ROI: {roi:.2f}%)")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 30: 
                self.log(f"TP/SL check error: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side, current_volume=0, closed_volume=0):
        self.check_position_status()
        if self.position_open:
            self.log("⚠️ Position already open, skipping")
            return
            
        try:
            cancel_all_orders(self.symbol)
            if not set_leverage(self.symbol, self.lev): 
                self.log(f"❌ Could not set leverage to {self.lev}")
                return
                
            balance = get_balance()
            if balance <= 0: 
                self.log("❌ Insufficient USDT balance")
                return
                
            # 1. XÁC ĐỊNH SỐ VỐN KÝ QUỸ (MARGIN)
            usdt_amount = balance * (min(max(self.percent, 1), 100) / 100)
            
            price = get_current_price(self.symbol)
            if price <= 0: 
                self.log("❌ Error getting price")
                return
                
            step = get_step_size(self.symbol)
            if step <= 0: 
                step = 0.001
                
            # 2. TÍNH TOÁN GIÁ TRỊ DANH NGHĨA (NOTIONAL VALUE)
            notional_value = usdt_amount * self.lev

            # 3. TÍNH TOÁN SỐ LƯỢNG THÔ
            qty_raw = notional_value / price
            
            # 4. LÀM TRÒN CHÍNH XÁC THEO LOT_SIZE (STEP SIZE)
            steps = qty_raw / step
            qty = round(steps) * step
            qty = max(qty, step)
            qty = round(qty, 8)
            
            # 5. KIỂM TRA MIN NOTIONAL
            MIN_NOTIONAL_SAFE = 5.0

            if qty * price < MIN_NOTIONAL_SAFE:
                 self.log(f"⚠️ Notional Value ({qty * price:.2f} USDT) too low (Min > {MIN_NOTIONAL_SAFE} USDT). Skipping trade.", is_critical=True)
                 return
            
            if qty < step: 
                self.log(f"⚠️ Quantity too small: {qty} < {step}")
                return
                
            # 6. ĐẶT LỆNH
            res = place_order(self.symbol, side, qty)
            if not res: 
                self.log("❌ Error placing order")
                return
                
            executed_qty = float(res.get('executedQty', 0))
            if executed_qty < step: 
                self.log(f"❌ Order not filled: {executed_qty}")
                return

            # 7. CẬP NHẬT TRẠNG THÁI
            self.entry = float(res.get('avgPrice', price))
            self.side = side
            self.qty = executed_qty if side == "BUY" else -executed_qty
            self.status = "open"
            self.position_open = True

            # Xử lý volume ratio an toàn
            try:
                volume_ratio = current_volume / closed_volume if closed_volume and closed_volume > 0 else 0
            except (ZeroDivisionError, TypeError):
                volume_ratio = 0

            message = (f"✅ <b>POSITION OPENED {self.symbol}</b>\n"
                       f"📌 Direction: {side}\n"
                       f"🏷️ Entry Price: {self.entry:.4f}\n"
                       f"📊 Quantity: {executed_qty}\n"
                       f"💵 Value (Notional): {executed_qty * self.entry:.2f} USDT\n"
                       f" Leverage: {self.lev}x\n"
                       f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%\n"
                       f"🔥 Volume Ratio: {volume_ratio:.2f}x")
            
            self.log(message, is_critical=True)
            
        except Exception as e:
            self.position_open = False
            self.log(f"❌ Error entering position: {str(e)}")

    def close_position(self, reason=""):
        try:
            cancel_all_orders(self.symbol)
            if abs(self.qty) > 0:
                close_side = "SELL" if self.side == "BUY" else "BUY"
                close_qty = abs(self.qty)
                step = get_step_size(self.symbol)
                
                if step > 0: 
                    steps = close_qty / step
                    close_qty = round(steps) * step
                
                close_qty = max(close_qty, 0)
                close_qty = round(close_qty, 8)
                
                res = place_order(self.symbol, close_side, close_qty)
                if res:
                    price = float(res.get('avgPrice', 0))
                    roi = self.calculate_roi() 

                    message = (f"⛔ <b>POSITION CLOSED {self.symbol}</b>\n"
                              f"📌 Reason: {reason}\n"
                              f"🏷️ Exit Price: {price:.4f}\n"
                              f"📊 Quantity: {close_qty}\n"
                              f"💵 Value: {close_qty * price:.2f} USDT\n"
                              f"🔥 ROI: {roi:.2f}%")
                    self.log(message)
                    
                    self.status = "waiting"
                    self.side = ""
                    self.qty = 0
                    self.entry = 0
                    self.position_open = False
                    self.last_trade_time = time.time()
                else: 
                    self.log("❌ Error closing position")
        except Exception as e: 
            self.log(f"❌ Error closing position: {str(e)}")

# ========== BOT MANAGER (ĐÃ THÊM RATE LIMITING) ==========
class BotManager:
    def __init__(self):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}
        self.admin_chat_id = TELEGRAM_CHAT_ID
        self.last_api_call = 0
        self.min_api_interval = 0.2  # 200ms giữa các lần gọi API
        
        self.log("🟢 BOT SYSTEM STARTED")
        self.status_thread = threading.Thread(target=self._status_monitor, daemon=True)
        self.status_thread.start()
        self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
        self.telegram_thread.start()
        if self.admin_chat_id: 
            self.send_main_menu(self.admin_chat_id)

    def rate_limited_api_call(self):
        """Rate limiting cho API calls để tránh bị ban"""
        current_time = time.time()
        elapsed = current_time - self.last_api_call
        if elapsed < self.min_api_interval:
            time.sleep(self.min_api_interval - elapsed)
        self.last_api_call = time.time()

    def log(self, message, is_critical=True):
        logger.info(f"[SYSTEM] {message}") 
        if is_critical: 
            send_telegram(f"<b>SYSTEM</b>: {message}")

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BINANCE FUTURES TRADING BOT (Dynamic Contrarian 24h)</b>\n\nChoose an option below:"
        send_telegram(welcome, chat_id, create_menu_keyboard())

    def add_bot(self, symbol, lev, percent, tp, sl, change_24h, max_leverage, min_volatility):
        if sl == 0: 
            sl = None
        symbol = symbol.upper()
        
        bot_id = f"BOT_{len(self.bots) + 1}"
            
        if not API_KEY or not API_SECRET:
            self.log("❌ API Key and Secret Key not configured!")
            return False
            
        try:
            self.rate_limited_api_call()
            price = get_current_price(symbol)
            if price <= 0:
                self.log(f"❌ Cannot get price for {symbol}")
                return False
                
            bot = IndicatorBot(symbol, lev, percent, tp, sl, self.ws_manager, change_24h, max_leverage, min_volatility)
            self.bots[bot_id] = bot
            self.log(f"✅ Bot added: {bot_id} | Pair: {symbol} | Vol: {min_volatility}% | Lev: {lev}x (Max {max_leverage}x) | %: {percent} | TP/SL: {tp}%/{sl}%")
            return True
            
        except Exception as e:
            self.log(f"❌ Error creating bot {symbol}: {str(e)}")
            return False

    def stop_bot(self, bot_id):
        bot = self.bots.get(bot_id)
        if bot:
            bot.stop()
            self.log(f"⛔ Bot {bot_id} stopped for {bot.initial_symbol}")
            del self.bots[bot_id]
            return True
        return False

    def stop_all(self):
        self.log("⛔ Stopping all bots...")
        for bot_id in list(self.bots.keys()): 
            self.stop_bot(bot_id)
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
                active_bots_count = len(self.bots)
                
                self.rate_limited_api_call()
                balance = get_balance()
                
                status_msg = (f"📊 <b>SYSTEM STATUS</b>\n"
                             f"⏱ Uptime: {uptime_str}\n"
                             f"🤖 Active Bots: {active_bots_count}\n"
                             f"💰 Available Balance: {balance:.2f} USDT")
                send_telegram(status_msg)
                
            except Exception as e: 
                logger.error(f"Status report error: {str(e)}")
            time.sleep(6 * 3600)

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
        
        if current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ': 
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            elif 'x' in text:
                leverage = int(text.replace('', '').replace('x', '').strip())
                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                send_telegram(f"Bước 2/5: Enter % of balance to use (1-100):", chat_id, create_cancel_keyboard())
                
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
                        send_telegram(f"Bước 3/5: Enter % Take Profit (e.g., 10):", chat_id, create_cancel_keyboard())
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
                        send_telegram(f"Bước 4/5: Enter % Stop Loss (e.g., 5, 0 for no SL):", chat_id, create_cancel_keyboard())
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
                        user_state['sl'] = sl
                        user_state['step'] = 'waiting_min_volatility'
                        send_telegram("Bước 5/5: Enter Min Volatility % (e.g., 30):", chat_id, create_cancel_keyboard())
                    else: 
                        send_telegram("⚠️ SL must be greater than or equal to 0", chat_id)
                except Exception: 
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)

        elif current_step == 'waiting_min_volatility':
            if text == '❌ Hủy bỏ': 
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    min_volatility = float(text)
                    if min_volatility > 0:
                        leverage = user_state['leverage']
                        percent = user_state['percent']
                        tp = user_state['tp']
                        sl = user_state['sl']
                        
                        # ========= LOGIC TẠO HÀNG LOẠT BOT ==========
                        send_telegram(f"🔍 Đang tìm kiếm TẤT CẢ đồng coin phù hợp (Leverage {leverage}x, Biến động > {min_volatility}%)...", chat_id)
                        
                        eligible_symbols = find_eligible_symbols(min_leverage=leverage, min_change_percent=min_volatility)
                        
                        if not eligible_symbols:
                            send_telegram("❌ Không tìm thấy đồng coin nào phù hợp với đòn bẩy và biến động yêu cầu.", chat_id, create_menu_keyboard())
                            self.user_states[chat_id] = {}
                            return
                        
                        success_count = 0
                        
                        for entry in eligible_symbols:
                            symbol = entry['symbol']
                            change_24h = entry['change']
                            max_leverage = entry['max_leverage']
                            
                            if self.add_bot(symbol, leverage, percent, tp, sl, change_24h, max_leverage, min_volatility): 
                                success_count += 1
                        
                        send_telegram(
                            f"✅ <b>TẠO HÀNG LOẠT BOT HOÀN TẤT</b>\n\n"
                            f"Đã tạo thành công **{success_count}** bot. Mỗi bot là một thợ săn độc lập.\n"
                            f"Ngưỡng Volatility: **{min_volatility}%**",
                            chat_id,
                            create_menu_keyboard()
                        )
                        self.user_states[chat_id] = {}
                    else: 
                        send_telegram("⚠️ Min Volatility must be greater than 0", chat_id)
                except Exception as e:
                    self.log(f"Mass creation error: {str(e)}", is_critical=True)
                    send_telegram("⚠️ Invalid value or API error during mass creation.", chat_id, create_menu_keyboard())
                    self.user_states[chat_id] = {}

                    
        elif text == "📊 Danh sách Bot":
            if not self.bots: 
                send_telegram("🤖 No bots are currently running", chat_id)
            else:
                message = "🤖 <b>LIST OF RUNNING BOTS</b>\n\n"
                for bot_id, bot in self.bots.items():
                    status = "🟢 Open" if bot.status == "open" else "🟡 Waiting"
                    message += f"🔹 {bot_id} (Initial: {bot.initial_symbol}) | Current: {bot.symbol} | {status} | Lev: {bot.lev}x\n"
                send_telegram(message, chat_id)
                
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_leverage'}
            send_telegram("Bước 1/5: Choose leverage for the new bot:", chat_id, create_leverage_keyboard())
            
        elif text == "⛔ Dừng Bot":
            if not self.bots: 
                send_telegram("🤖 No bots are currently running", chat_id)
            else:
                message = "⛔ <b>CHOOSE BOT TO STOP</b>\n\n"
                keyboard = []
                row = []
                for bot_id, bot in self.bots.items():
                    message += f"🔹 {bot_id} ({bot.initial_symbol})\n"
                    row.append({"text": f"⛔ {bot_id}"})
                    if len(row) == 2: 
                        keyboard.append(row)
                        row = []
                if row: 
                    keyboard.append(row)
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                send_telegram(message, chat_id, {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True})
                
        elif text.startswith("⛔ BOT_"):
            bot_id = text.replace("⛔ ", "").strip().upper()
            if bot_id in self.bots: 
                self.stop_bot(bot_id)
                send_telegram(f"⛔ Stop command sent for bot {bot_id}", chat_id, create_menu_keyboard())
            else: 
                send_telegram(f"⚠️ Bot not found {bot_id}", chat_id, create_menu_keyboard())
                
        elif text == "💰 Số dư tài khoản":
            try: 
                self.rate_limited_api_call()
                balance = get_balance()
                send_telegram(f"💰 <b>AVAILABLE BALANCE</b>: {balance:.2f} USDT", chat_id)
            except Exception as e: 
                send_telegram(f"⚠️ Error getting balance: {str(e)}", chat_id)
                
        elif text == "📈 Vị thế đang mở":
            try:
                self.rate_limited_api_call()
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

# ========== MAIN FUNCTION ==========
def perform_initial_training(manager, bot_configs):
    manager.log("⚠️ Bot configurations from environment variables are ignored because the current strategy requires dynamic symbol selection.")

def main():
    manager = BotManager()

    if BOT_CONFIGS: 
        perform_initial_training(manager, BOT_CONFIGS) 

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
