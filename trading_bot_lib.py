# trading_bot_lib.py
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
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ========== CẤU HÌNH LOGGING ==========
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_errors.log')
        ]
    )
    return logging.getLogger()

logger = setup_logging()

# ========== HÀM TELEGRAM ==========
def send_telegram(message, chat_id=None, reply_markup=None, bot_token=None, default_chat_id=None):
    if not bot_token:
        logger.warning("Telegram Bot Token chưa được thiết lập")
        return
    
    chat_id = chat_id or default_chat_id
    if not chat_id:
        logger.warning("Telegram Chat ID chưa được thiết lập")
        return
    
    clean_message = message
    try:
        clean_message = message
    except:
        pass
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": clean_message,
        "parse_mode": "HTML"
    }
    
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            logger.error(f"Lỗi Telegram ({response.status_code}): {response.text}")
    except Exception as e:
        logger.error(f"Lỗi kết nối Telegram: {str(e)}")

# ========== MENU TELEGRAM NÂNG CAO ==========
def create_main_menu():
    return {
        "keyboard": [
            [{"text": "📊 Danh sách Bot"}],
            [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
            [{"text": "💰 Số dư"}, {"text": "📈 Vị thế"}],
            [{"text": "⚙️ Cấu hình"}, {"text": "🎯 Chiến lược"}]
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

def create_strategy_keyboard():
    return {
        "keyboard": [
            [{"text": "🤖 RSI/EMA Recursive"}, {"text": "📊 EMA Crossover"}],
            [{"text": "🎯 Reverse 24h"}, {"text": "📈 Trend Following"}],
            [{"text": "⚡ Scalping"}, {"text": "🛡️ Safe Grid"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard(strategy=None):
    if strategy == "Reverse 24h":
        volatile_symbols = get_top_volatile_symbols(limit=8, threshold=20)
    else:
        volatile_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT"]
    
    keyboard = []
    row = []
    for symbol in volatile_symbols:
        row.append({"text": symbol})
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

def create_leverage_keyboard(strategy=None):
    if strategy == "Scalping":
        leverages = ["3", "5", "10", "15", "20", "25", "50", "75", "100"]
    elif strategy == "Reverse 24h":
        leverages = ["3", "5", "8", "10", "15", "25", "50", "75", "100"]
    elif strategy == "Safe Grid":
        leverages = ["3", "5", "8", "10", "25", "50", "75", "100"]
    else:
        leverages = ["3", "5", "10", "15", "20", "25", "50", "75", "100"]
    
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

def create_percent_keyboard():
    return {
        "keyboard": [
            [{"text": "1"}, {"text": "3"}, {"text": "5"}, {"text": "10"}],
            [{"text": "15"}, {"text": "20"}, {"text": "25"}, {"text": "50"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_tp_keyboard():
    return {
        "keyboard": [
            [{"text": "50"}, {"text": "100"}, {"text": "200"}],
            [{"text": "300"}, {"text": "500"}, {"text": "1000"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_sl_keyboard():
    return {
        "keyboard": [
            [{"text": "0"}, {"text": "50"}, {"text": "100"}],
            [{"text": "150"}, {"text": "200"}, {"text": "500"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_threshold_keyboard():
    return {
        "keyboard": [
            [{"text": "30"}, {"text": "50"}, {"text": "70"}],
            [{"text": "100"}, {"text": "150"}, {"text": "200"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_volatility_keyboard():
    return {
        "keyboard": [
            [{"text": "2"}, {"text": "3"}, {"text": "5"}],
            [{"text": "8"}, {"text": "10"}, {"text": "15"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_grid_levels_keyboard():
    return {
        "keyboard": [
            [{"text": "3"}, {"text": "5"}, {"text": "8"}],
            [{"text": "10"}, {"text": "15"}, {"text": "20"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

# ========== QUẢN LÝ COIN CHUNG ==========
class CoinManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CoinManager, cls).__new__(cls)
                cls._instance.managed_coins = {}  # {symbol: bot_id}
                cls._instance.position_coins = set()  # Các coin đang có vị thế
        return cls._instance
    
    def register_coin(self, symbol, bot_id):
        """Đăng ký coin được quản lý bởi bot nào"""
        with self._lock:
            if symbol not in self.managed_coins:
                self.managed_coins[symbol] = bot_id
                return True
            return False
    
    def unregister_coin(self, symbol):
        """Hủy đăng ký coin"""
        with self._lock:
            if symbol in self.managed_coins:
                del self.managed_coins[symbol]
                return True
            return False
    
    def is_coin_managed(self, symbol):
        """Kiểm tra coin đã được quản lý chưa"""
        with self._lock:
            return symbol in self.managed_coins
    
    def get_managed_coins(self):
        """Lấy danh sách coin đang được quản lý"""
        with self._lock:
            return self.managed_coins.copy()
    
    def add_position_coin(self, symbol):
        """Thêm coin có vị thế"""
        with self._lock:
            self.position_coins.add(symbol)
    
    def remove_position_coin(self, symbol):
        """Xóa coin có vị thế"""
        with self._lock:
            if symbol in self.position_coins:
                self.position_coins.remove(symbol)
    
    def get_position_coins(self):
        """Lấy danh sách coin có vị thế"""
        with self._lock:
            return self.position_coins.copy()

# ========== HÀM TÌM COIN ==========
def get_top_volatile_symbols(limit=10, threshold=20):
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return ["BTCUSDT", "ETHUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT"]
        
        volatile_pairs = []
        for ticker in data:
            symbol = ticker.get('symbol', '')
            if symbol.endswith('USDT'):
                change = float(ticker.get('priceChangePercent', 0))
                if abs(change) >= threshold:
                    volatile_pairs.append((symbol, abs(change)))
        
        volatile_pairs.sort(key=lambda x: x[1], reverse=True)
        
        top_symbols = [pair[0] for pair in volatile_pairs[:limit]]
        
        default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "SOLUSDT", "MATICUSDT"]
        for symbol in default_symbols:
            if len(top_symbols) < limit and symbol not in top_symbols:
                top_symbols.append(symbol)
        
        return top_symbols[:limit]
        
    except Exception as e:
        logger.error(f"Lỗi lấy danh sách coin biến động: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT"]

def get_qualified_symbols(api_key, api_secret, strategy_type, leverage, threshold=None, volatility=None, grid_levels=None, max_candidates=8, final_limit=2):
    try:
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE")
            return []
        
        coin_manager = CoinManager()
        managed_coins = coin_manager.get_managed_coins()
        position_coins = coin_manager.get_position_coins()
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return ["ADAUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT"]
        
        qualified_symbols = []
        
        for ticker in data:
            symbol = ticker.get('symbol', '')
            if symbol.endswith('USDT'):
                # LOẠI BỎ BTC VÀ ETH
                if symbol in ['BTCUSDT', 'ETHUSDT']:
                    continue
                
                # KIỂM TRA COIN ĐÃ ĐƯỢC QUẢN LÝ CHƯA
                if symbol in managed_coins:
                    continue
                
                price_change = abs(float(ticker.get('priceChangePercent', 0)))
                volume = float(ticker.get('quoteVolume', 0))
                high_price = float(ticker.get('highPrice', 0))
                low_price = float(ticker.get('lowPrice', 0))
                price_range = ((high_price - low_price) / low_price) * 100 if low_price > 0 else 0
                
                # TIÊU CHÍ THEO CHIẾN LƯỢC
                if strategy_type == "Reverse 24h":
                    if price_change >= threshold and volume > 5000000:
                        qualified_symbols.append((symbol, price_change))
                        
                elif strategy_type == "Scalping":
                    if price_change >= volatility and volume > 10000000 and price_range >= 2.0:
                        qualified_symbols.append((symbol, price_range))
                        
                elif strategy_type == "Safe Grid":
                    if 1.0 <= price_change <= 5.0 and volume > 2000000 and price_range <= 3.0:
                        qualified_symbols.append((symbol, -abs(price_change - 3.0)))
        
        # SẮP XẾP
        if strategy_type == "Reverse 24h":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Scalping":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Safe Grid":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        
        # THÊM COIN CÓ VỊ THẾ NHƯNG CHƯA ĐƯỢC QUẢN LÝ
        for symbol in position_coins:
            if symbol not in managed_coins and len(qualified_symbols) < final_limit:
                qualified_symbols.insert(0, (symbol, 999))  # Ưu tiên cao nhất
        
        # KIỂM TRA ĐÒN BẨY
        final_symbols = []
        for symbol, score in qualified_symbols[:max_candidates]:
            if len(final_symbols) >= final_limit:
                break
                
            try:
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                if leverage_success:
                    final_symbols.append(symbol)
                    logger.info(f"✅ {symbol}: phù hợp {strategy_type}")
                time.sleep(0.1)
            except:
                continue
        
        # COIN DỰ PHÒNG
        backup_symbols = ["ADAUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT", "ATOMUSDT", "AVAXUSDT", "SOLUSDT", "BNBUSDT"]
        for symbol in backup_symbols:
            if len(final_symbols) < final_limit and symbol not in final_symbols and symbol not in managed_coins:
                try:
                    leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                    if leverage_success:
                        final_symbols.append(symbol)
                except:
                    continue
        
        logger.info(f"🎯 {strategy_type}: {len(final_symbols)} coin")
        return final_symbols[:final_limit]
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin {strategy_type}: {str(e)}")
        return []

# ========== API BINANCE ==========
def sign(query, api_secret):
    try:
        return hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"Lỗi tạo chữ ký: {str(e)}")
        return ""

def binance_api_request(url, method='GET', params=None, headers=None):
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
                    error_content = response.read().decode()
                    logger.error(f"Lỗi API ({response.status}): {error_content}")
                    
                    if response.status == 401:
                        logger.error("❌ LỖI 401 UNAUTHORIZED")
                        return None
                    
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            logger.error(f"Lỗi HTTP ({e.code}): {e.reason}")
            
            if e.code == 401:
                logger.error("❌ LỖI 401 UNAUTHORIZED")
                return None
                
            if e.code == 429:
                time.sleep(2 ** attempt)
            elif e.code >= 500:
                time.sleep(1)
            continue
        except Exception as e:
            logger.error(f"Lỗi kết nối API: {str(e)}")
            time.sleep(1)
    
    logger.error(f"Không thể thực hiện yêu cầu API sau {max_retries} lần thử")
    return None

def get_step_size(symbol, api_key, api_secret):
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
    return 0.001

def set_leverage(symbol, lev, api_key, api_secret):
    try:
        ts = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "leverage": lev,
            "timestamp": ts
        }
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v1/leverage?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        response = binance_api_request(url, method='POST', headers=headers)
        
        if response is None:
            logger.error(f"❌ Không thể đặt đòn bẩy cho {symbol}")
            return False
            
        if response and 'leverage' in response:
            return True
        return False
    except Exception as e:
        logger.error(f"Lỗi thiết lập đòn bẩy: {str(e)}")
        return False

def get_balance(api_key, api_secret):
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        data = binance_api_request(url, headers=headers)
        if not data:
            return None
            
        for asset in data['assets']:
            if asset['asset'] == 'USDT':
                return float(asset['availableBalance'])
        return 0
    except Exception as e:
        logger.error(f"Lỗi lấy số dư: {str(e)}")
        return None

def place_order(symbol, side, qty, api_key, api_secret):
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
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v1/order?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        return binance_api_request(url, method='POST', headers=headers)
    except Exception as e:
        logger.error(f"Lỗi đặt lệnh: {str(e)}")
    return None

def cancel_all_orders(symbol, api_key, api_secret):
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v1/allOpenOrders?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        binance_api_request(url, method='DELETE', headers=headers)
        return True
    except Exception as e:
        logger.error(f"Lỗi hủy lệnh: {str(e)}")
    return False

def get_current_price(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            return float(data['price'])
    except Exception as e:
        logger.error(f"Lỗi lấy giá: {str(e)}")
    return 0

def get_positions(symbol=None, api_key=None, api_secret=None):
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        if symbol:
            params["symbol"] = symbol.upper()
            
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v2/positionRisk?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
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
    return []

def get_24h_change(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'priceChangePercent' in data:
            return float(data['priceChangePercent'])
    except Exception as e:
        logger.error(f"Lỗi lấy biến động 24h cho {symbol}: {str(e)}")
    return 0

# ========== CHỈ BÁO KỸ THUẬT ==========
def calc_rsi(prices, period=14):
    try:
        if len(prices) < period + 1:
            return None
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1 + rs))
    except Exception as e:
        logger.error(f"Lỗi tính RSI: {str(e)}")
        return None

def calc_ema(prices, period):
    prices = np.array(prices)
    if len(prices) < period:
        return None
    weights = np.exp(np.linspace(-1., 0., period))
    weights /= weights.sum()
    ema = np.convolve(prices, weights, mode='valid')
    return float(ema[-1])

# ========== WEBSOCKET MANAGER ==========
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

# ========== BASE BOT CLASS ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, strategy_name):
        # XỬ LÝ SYMBOL = None CHO CHẾ ĐỘ TỰ ĐỘNG
        if symbol is None:
            self.symbol = "BTCUSDT"
            self.auto_symbol_mode = True
        else:
            self.symbol = symbol.upper()
            self.auto_symbol_mode = False
            
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.ws_manager = ws_manager
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.strategy_name = strategy_name
        self.bot_id = f"{self.strategy_name}_{id(self)}"
        
        # KHỞI TẠO BIẾN QUAN TRỌNG
        self.last_signal_check = 0
        self.last_price = 0
        self.previous_price = 0
        self.price_change_24h = 0
        self.price_history = []
        self.max_history_size = 100
        
        self.check_position_status()
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []

        self._stop = False
        self.position_open = False
        self.last_trade_time = 0
        self.position_check_interval = 60
        self.last_position_check = 0
        self.last_error_log_time = 0
        self.last_close_time = 0
        self.cooldown_period = 900
        self.max_position_attempts = 3
        self.position_attempt_count = 0
        
        # ĐĂNG KÝ COIN VỚI COIN MANAGER
        self.coin_manager = CoinManager()
        if not self.auto_symbol_mode:
            self.coin_manager.register_coin(self.symbol, self.bot_id)
        
        # CHỈ THÊM WEBSOCKET NẾU KHÔNG PHẢI CHẾ ĐỘ TỰ ĐỘNG HOÀN TOÀN
        if not self.auto_symbol_mode:
            self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot {strategy_name} khởi động cho {self.symbol}")

    def _ensure_required_attributes(self):
        required_attrs = {
            'last_signal_check': 0,
            'last_price': 0,
            'previous_price': 0,
            'price_change_24h': 0,
            'price_history': [],
            'max_history_size': 100,
            'status': "waiting",
            'side': "",
            'qty': 0,
            'entry': 0,
            'prices': [],
            '_stop': False,
            'position_open': False,
            'last_trade_time': 0,
            'position_check_interval': 60,
            'last_position_check': 0,
            'last_error_log_time': 0,
            'last_close_time': 0,
            'cooldown_period': 900,
            'max_position_attempts': 3,
            'position_attempt_count': 0
        }
        
        for attr, default_value in required_attrs.items():
            if not hasattr(self, attr):
                setattr(self, attr, default_value)

    def log(self, message):
        logger.info(f"[{self.symbol} - {self.strategy_name}] {message}")
        send_telegram(f"<b>{self.symbol}</b> ({self.strategy_name}): {message}", 
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def _handle_price_update(self, price):
        if self._stop: 
            return
            
        try:
            if price and price > 0:
                self.prices.append(float(price))
                if len(self.prices) > 100:
                    self.prices = self.prices[-100:]
        except Exception as e:
            self.log(f"❌ Lỗi xử lý giá: {str(e)}")

    def get_signal(self):
        raise NotImplementedError("Phương thức get_signal cần được triển khai")

    def _run(self):
        while not self._stop:
            try:
                current_time = time.time()
                
                # KIỂM TRA VỊ THẾ HIỆN TẠI ĐỊNH KỲ
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                    
                signal = self.get_signal()
                
                # CHỈ VÀO LỆNH NẾU KHÔNG CÓ VỊ THẾ HIỆN TẠI
                if not self.position_open and self.status == "waiting":
                    if current_time - self.last_close_time < self.cooldown_period:
                        time.sleep(1)
                        continue

                    if signal and current_time - self.last_trade_time > 60:
                        # KIỂM TRA LẠI VỊ THẾ TRƯỚC KHI VÀO LỆNH
                        self.check_position_status()
                        if not self.position_open:
                            self.log(f"🎯 Nhận tín hiệu {signal}, đang mở lệnh...")
                            self.open_position(signal)
                            self.last_trade_time = current_time
                            
                # KIỂM TRA TP/SL NẾU CÓ VỊ THẾ
                if self.position_open and self.status == "open":
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    error_msg = f"❌ Lỗi hệ thống: {str(e)}"
                    self.log(error_msg)
                    self.last_error_log_time = time.time()
                time.sleep(1)

    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        try:
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi hủy lệnh: {str(e)}")
                self.last_error_log_time = time.time()
        self.coin_manager.unregister_coin(self.symbol)
        self.log(f"🔴 Bot dừng cho {self.symbol}")

    def check_position_status(self):
        try:
            positions = get_positions(self.symbol, self.api_key, self.api_secret)
            
            if not positions or len(positions) == 0:
                self.position_open = False
                self.status = "waiting"
                self.side = ""
                self.qty = 0
                self.entry = 0
                self.coin_manager.remove_position_coin(self.symbol)
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
                        self.coin_manager.add_position_coin(self.symbol)
                        return
                    else:
                        self.position_open = False
                        self.status = "waiting"
                        self.side = ""
                        self.qty = 0
                        self.entry = 0
                        self.coin_manager.remove_position_coin(self.symbol)
                        return
                        
            self.position_open = False
            self.status = "waiting"
            self.side = ""
            self.qty = 0
            self.entry = 0
            self.coin_manager.remove_position_coin(self.symbol)
            
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side):
        try:
            self.check_position_status()
            if self.position_open:
                self.log(f"⚠️ Đã có vị thế {self.side}, bỏ qua tín hiệu mới")
                return False

            # KIỂM TRA ĐÒN BẨY
            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể thiết lập đòn bẩy {self.lev}x")
                return False

            # LẤY SỐ DƯ
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không thể lấy số dư")
                return False

            # TÍNH TOÁN SỐ LƯỢNG
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                self.log("❌ Không thể lấy giá hiện tại")
                return False

            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            usd_amount = balance * self.percent / 100
            qty = usd_amount / current_price
            qty = math.floor(qty / step_size) * step_size

            if qty <= 0:
                self.log("❌ Số lượng không hợp lệ")
                return False

            # ĐẶT LỆNH
            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                self.log(f"✅ Mở lệnh {side} {qty} {self.symbol} giá {current_price:.4f}")
                
                # ĐỢI VÀ KIỂM TRA VỊ THẾ
                time.sleep(2)
                self.check_position_status()
                
                if self.position_open:
                    self.position_attempt_count = 0
                    return True
                else:
                    self.position_attempt_count += 1
                    if self.position_attempt_count >= self.max_position_attempts:
                        self.log("❌ Không thể mở vị thế sau nhiều lần thử")
                        self.position_attempt_count = 0
                    return False
            else:
                self.log(f"❌ Lỗi mở lệnh {side}")
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False

    def close_position(self):
        try:
            if not self.position_open or not self.side:
                return False

            # ĐẢO NGƯỢC SIDE ĐỂ ĐÓNG LỆNH
            close_side = "SELL" if self.side == "BUY" else "BUY"
            result = place_order(self.symbol, close_side, abs(self.qty), self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                current_price = get_current_price(self.symbol)
                pnl = 0
                if self.entry > 0 and current_price > 0:
                    if self.side == "BUY":
                        pnl = (current_price - self.entry) * abs(self.qty)
                    else:
                        pnl = (self.entry - current_price) * abs(self.qty)
                
                self.log(f"🔒 Đóng lệnh {self.side} {abs(self.qty)} {self.symbol} giá {current_price:.4f} (PNL: {pnl:.2f} USDT)")
                
                # CẬP NHẬT TRẠNG THÁI
                self.position_open = False
                self.status = "waiting"
                self.side = ""
                self.qty = 0
                self.entry = 0
                self.last_close_time = time.time()
                self.coin_manager.remove_position_coin(self.symbol)
                return True
            else:
                self.log(f"❌ Lỗi đóng lệnh {self.side}")
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False

    def check_tp_sl(self):
        if not self.position_open or self.entry <= 0:
            return

        current_price = get_current_price(self.symbol)
        if current_price <= 0:
            return

        # TÍNH TOÁN LỢI NHUẬN/THUA LỖ
        if self.side == "BUY":
            profit_percent = ((current_price - self.entry) / self.entry) * 100 * self.lev
        else:
            profit_percent = ((self.entry - current_price) / self.entry) * 100 * self.lev

        # KIỂM TRA TP/SL
        if profit_percent >= self.tp:
            self.log(f"🎯 ĐẠT TP {self.tp}% (Lợi nhuận: {profit_percent:.2f}%)")
            self.close_position()
        elif profit_percent <= -self.sl:
            self.log(f"🛑 ĐẠT SL {self.sl}% (Thua lỗ: {profit_percent:.2f}%)")
            self.close_position()

# ========== CHIẾN LƯỢC GIAO DỊCH ==========
class RSI_EMA_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "RSI/EMA Recursive")
        self.rsi_period = 14
        self.ema_fast = 9
        self.ema_slow = 21
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.min_price_movement = 0.002

    def get_signal(self):
        try:
            if len(self.prices) < 50:
                return None

            current_price = self.prices[-1] if self.prices else get_current_price(self.symbol)
            if current_price <= 0:
                return None

            # TÍNH TOÁN CHỈ BÁO
            rsi = calc_rsi(self.prices, self.rsi_period)
            ema_fast = calc_ema(self.prices, self.ema_fast)
            ema_slow = calc_ema(self.prices, self.ema_slow)

            if rsi is None or ema_fast is None or ema_slow is None:
                return None

            # TÍN HIỆU GIAO DỊCH
            signal = None
            if rsi < self.rsi_oversold and ema_fast > ema_slow:
                signal = "BUY"
            elif rsi > self.rsi_overbought and ema_fast < ema_slow:
                signal = "SELL"

            return signal

        except Exception as e:
            self.log(f"❌ Lỗi tính tín hiệu RSI/EMA: {str(e)}")
            return None

class EMA_Crossover_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "EMA Crossover")
        self.ema_fast = 9
        self.ema_slow = 21
        self.ema_signal = 5
        self.prev_ema_fast = None
        self.prev_ema_slow = None

    def get_signal(self):
        try:
            if len(self.prices) < 50:
                return None

            # TÍNH TOÁN EMA
            ema_fast = calc_ema(self.prices, self.ema_fast)
            ema_slow = calc_ema(self.prices, self.ema_slow)

            if ema_fast is None or ema_slow is None:
                return None

            # TÍN HIỆU GIAO CẮT
            signal = None
            if self.prev_ema_fast is not None and self.prev_ema_slow is not None:
                if (self.prev_ema_fast <= self.prev_ema_slow and ema_fast > ema_slow):
                    signal = "BUY"
                elif (self.prev_ema_fast >= self.prev_ema_slow and ema_fast < ema_slow):
                    signal = "SELL"

            self.prev_ema_fast = ema_fast
            self.prev_ema_slow = ema_slow

            return signal

        except Exception as e:
            self.log(f"❌ Lỗi tính tín hiệu EMA Crossover: {str(e)}")
            return None

class Reverse_24h_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, threshold=50):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Reverse 24h")
        self.threshold = threshold
        self.last_24h_check = 0
        self.checked_24h_change = False

    def get_signal(self):
        try:
            current_time = time.time()
            
            # KIỂM TRA BIẾN ĐỘNG 24H MỖI 5 PHÚT
            if current_time - self.last_24h_check > 300 or not self.checked_24h_change:
                self.price_change_24h = get_24h_change(self.symbol)
                self.last_24h_check = current_time
                self.checked_24h_change = True
                
                # LOG BIẾN ĐỘNG
                if abs(self.price_change_24h) >= self.threshold:
                    self.log(f"📊 Biến động 24h: {self.price_change_24h:.2f}% (Ngưỡng: {self.threshold}%)")

            # TÍN HIỆU ĐẢO CHIỀU
            signal = None
            if self.price_change_24h >= self.threshold:
                signal = "SELL"  # ĐẢO CHIỀU GIẢM
            elif self.price_change_24h <= -self.threshold:
                signal = "BUY"   # ĐẢO CHIỀU TĂNG

            return signal

        except Exception as e:
            self.log(f"❌ Lỗi tính tín hiệu Reverse 24h: {str(e)}")
            return None

class Trend_Following_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Following")
        self.trend_period = 20
        self.trend_threshold = 0.001

    def get_signal(self):
        try:
            if len(self.prices) < self.trend_period + 1:
                return None

            # XÁC ĐỊNH XU HƯỚNG
            recent_prices = self.prices[-self.trend_period:]
            price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]

            signal = None
            if price_change > self.trend_threshold:
                signal = "BUY"   # XU HƯỚNG TĂNG
            elif price_change < -self.trend_threshold:
                signal = "SELL"  # XU HƯỚNG GIẢM

            return signal

        except Exception as e:
            self.log(f"❌ Lỗi tính tín hiệu Trend Following: {str(e)}")
            return None

class Scalping_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, volatility=5):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Scalping")
        self.volatility = volatility
        self.rsi_period = 7
        self.min_movement = 0.001

    def get_signal(self):
        try:
            if len(self.prices) < 20:
                return None

            current_price = self.prices[-1]
            if len(self.prices) >= 2:
                price_change = (current_price - self.prices[-2]) / self.prices[-2]
            else:
                price_change = 0

            # TÍNH RSI NGẮN
            rsi = calc_rsi(self.prices, self.rsi_period)

            signal = None
            if rsi is not None:
                if rsi < 25 and price_change < -self.min_movement:
                    signal = "BUY"
                elif rsi > 75 and price_change > self.min_movement:
                    signal = "SELL"

            return signal

        except Exception as e:
            self.log(f"❌ Lỗi tính tín hiệu Scalping: {str(e)}")
            return None

class Safe_Grid_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, grid_levels=5):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Safe Grid")
        self.grid_levels = grid_levels
        self.grid_orders = []
        self.base_price = 0
        self.grid_spacing = 0.01  # 1%

    def get_signal(self):
        try:
            if not self.position_open:
                # KHỞI TẠO LƯỚI
                current_price = get_current_price(self.symbol)
                if current_price > 0:
                    self._setup_grid(current_price)
                    return "BUY"  # BẮT ĐẦU VỚI LỆNH MUA ĐẦU TIÊN
            else:
                # QUẢN LÝ LỆNH LƯỚI
                self._manage_grid()
            
            return None

        except Exception as e:
            self.log(f"❌ Lỗi tính tín hiệu Safe Grid: {str(e)}")
            return None

    def _setup_grid(self, current_price):
        self.base_price = current_price
        self.grid_orders = []
        
        # TẠO CÁC MỨC LỆNH
        for i in range(self.grid_levels):
            buy_price = current_price * (1 - (i + 1) * self.grid_spacing)
            sell_price = current_price * (1 + (i + 1) * self.grid_spacing)
            
            self.grid_orders.append({
                'buy_price': buy_price,
                'sell_price': sell_price,
                'buy_filled': False,
                'sell_filled': False
            })
        
        self.log(f"🎯 Thiết lập lưới {self.grid_levels} mức quanh giá {current_price:.4f}")

    def _manage_grid(self):
        current_price = get_current_price(self.symbol)
        if current_price <= 0:
            return

        for i, order in enumerate(self.grid_orders):
            # KIỂM TRA LỆNH MUA
            if not order['buy_filled'] and current_price <= order['buy_price']:
                self.log(f"🔼 Lệnh mua lưới #{i+1} kích hoạt tại {current_price:.4f}")
                order['buy_filled'] = True
                
            # KIỂM TRA LỆNH BÁN
            if not order['sell_filled'] and current_price >= order['sell_price']:
                self.log(f"🔽 Lệnh bán lưới #{i+1} kích hoạt tại {current_price:.4f}")
                order['sell_filled'] = True

# ========== BOT MANAGER ==========
class BotManager:
    def __init__(self):
        self.bots = {}
        self.ws_manager = WebSocketManager()
        self._lock = threading.Lock()
        self.auto_bots = {}  # Bot tự động
        
    def create_bot(self, strategy, symbol, lev, percent, tp, sl, api_key, api_secret, telegram_bot_token, telegram_chat_id, **kwargs):
        bot_id = f"{strategy}_{symbol}_{int(time.time())}"
        
        with self._lock:
            if bot_id in self.bots:
                return f"❌ Bot {bot_id} đã tồn tại"
            
            try:
                # TẠO BOT THEO CHIẾN LƯỢC
                if strategy == "RSI/EMA Recursive":
                    bot = RSI_EMA_Bot(symbol, lev, percent, tp, sl, self.ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id)
                elif strategy == "EMA Crossover":
                    bot = EMA_Crossover_Bot(symbol, lev, percent, tp, sl, self.ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id)
                elif strategy == "Reverse 24h":
                    threshold = kwargs.get('threshold', 50)
                    bot = Reverse_24h_Bot(symbol, lev, percent, tp, sl, self.ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, threshold)
                elif strategy == "Trend Following":
                    bot = Trend_Following_Bot(symbol, lev, percent, tp, sl, self.ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id)
                elif strategy == "Scalping":
                    volatility = kwargs.get('volatility', 5)
                    bot = Scalping_Bot(symbol, lev, percent, tp, sl, self.ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, volatility)
                elif strategy == "Safe Grid":
                    grid_levels = kwargs.get('grid_levels', 5)
                    bot = Safe_Grid_Bot(symbol, lev, percent, tp, sl, self.ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, grid_levels)
                else:
                    return f"❌ Chiến lược {strategy} không hợp lệ"
                
                self.bots[bot_id] = bot
                
                message = f"""✅ <b>ĐÃ TẠO BOT THÀNH CÔNG</b>

🎯 <b>Chiến lược:</b> {strategy}
💰 <b>Cặp coin:</b> {symbol}
📈 <b>Đòn bẩy:</b> {lev}x
💵 <b>Vốn:</b> {percent}%
🎯 <b>TP:</b> {tp}%
🛑 <b>SL:</b> {sl}%

⚡ <b>Bot ID:</b> <code>{bot_id}</code>"""
                
                send_telegram(message, bot_token=telegram_bot_token, default_chat_id=telegram_chat_id)
                return f"✅ Đã tạo bot {bot_id}"
                
            except Exception as e:
                error_msg = f"❌ Lỗi tạo bot {strategy}: {str(e)}"
                logger.error(error_msg)
                send_telegram(error_msg, bot_token=telegram_bot_token, default_chat_id=telegram_chat_id)
                return error_msg
    
    def create_auto_bot(self, strategy, lev, percent, tp, sl, api_key, api_secret, telegram_bot_token, telegram_chat_id, **kwargs):
        """Tạo bot tự động tìm coin"""
        bot_id = f"AUTO_{strategy}_{int(time.time())}"
        
        with self._lock:
            if bot_id in self.auto_bots:
                return f"❌ Bot tự động {bot_id} đã tồn tại"
            
            try:
                # TÌM COIN PHÙ HỢP
                threshold = kwargs.get('threshold', 50)
                volatility = kwargs.get('volatility', 5)
                grid_levels = kwargs.get('grid_levels', 5)
                
                qualified_symbols = get_qualified_symbols(
                    api_key, api_secret, strategy, lev, 
                    threshold, volatility, grid_levels
                )
                
                if not qualified_symbols:
                    return "❌ Không tìm thấy coin phù hợp"
                
                # TẠO BOT CHO MỖI COIN
                created_bots = []
                for symbol in qualified_symbols:
                    try:
                        # KIỂM TRA COIN ĐÃ CÓ BOT CHƯA
                        coin_manager = CoinManager()
                        if coin_manager.is_coin_managed(symbol):
                            continue
                            
                        bot_result = self.create_bot(
                            strategy, symbol, lev, percent, tp, sl,
                            api_key, api_secret, telegram_bot_token, telegram_chat_id,
                            **kwargs
                        )
                        
                        if "✅" in bot_result:
                            created_bots.append(symbol)
                            
                    except Exception as e:
                        logger.error(f"Lỗi tạo bot cho {symbol}: {str(e)}")
                        continue
                
                if created_bots:
                    self.auto_bots[bot_id] = {
                        'strategy': strategy,
                        'symbols': created_bots,
                        'params': {'lev': lev, 'percent': percent, 'tp': tp, 'sl': sl, **kwargs}
                    }
                    
                    message = f"""🤖 <b>BOT TỰ ĐỘNG ĐÃ KHỞI CHẠY</b>

🎯 <b>Chiến lược:</b> {strategy}
📈 <b>Đòn bẩy:</b> {lev}x
💵 <b>Vốn:</b> {percent}%
🎯 <b>TP:</b> {tp}%
🛑 <b>SL:</b> {sl}%

💰 <b>Coin đã chọn:</b> {', '.join(created_bots)}
⚡ <b>Bot ID:</b> <code>{bot_id}</code>"""
                    
                    send_telegram(message, bot_token=telegram_bot_token, default_chat_id=telegram_chat_id)
                    return f"✅ Đã tạo {len(created_bots)} bot tự động: {', '.join(created_bots)}"
                else:
                    return "❌ Không thể tạo bot tự động nào"
                    
            except Exception as e:
                error_msg = f"❌ Lỗi tạo bot tự động {strategy}: {str(e)}"
                logger.error(error_msg)
                send_telegram(error_msg, bot_token=telegram_bot_token, default_chat_id=telegram_chat_id)
                return error_msg
    
    def stop_bot(self, bot_id):
        with self._lock:
            if bot_id in self.bots:
                self.bots[bot_id].stop()
                del self.bots[bot_id]
                return f"✅ Đã dừng bot {bot_id}"
            elif bot_id in self.auto_bots:
                # DỪNG TẤT CẢ BOT TRONG AUTO BOT
                auto_bot = self.auto_bots[bot_id]
                symbols_to_remove = []
                
                for symbol in auto_bot['symbols']:
                    for bid, bot in list(self.bots.items()):
                        if bot.symbol == symbol and bot.strategy_name == auto_bot['strategy']:
                            bot.stop()
                            del self.bots[bid]
                            symbols_to_remove.append(symbol)
                
                del self.auto_bots[bot_id]
                return f"✅ Đã dừng bot tự động {bot_id} ({len(symbols_to_remove)} bot con)"
            else:
                return f"❌ Không tìm thấy bot {bot_id}"
    
    def stop_all_bots(self):
        with self._lock:
            # DỪNG TẤT CẢ BOT THƯỜNG
            for bot_id in list(self.bots.keys()):
                self.bots[bot_id].stop()
                del self.bots[bot_id]
            
            # DỪNG TẤT CẢ BOT TỰ ĐỘNG
            for bot_id in list(self.auto_bots.keys()):
                del self.auto_bots[bot_id]
            
            self.ws_manager.stop()
            return "✅ Đã dừng tất cả bot"
    
    def get_bot_status(self):
        with self._lock:
            status = {
                'total_bots': len(self.bots),
                'total_auto_bots': len(self.auto_bots),
                'bots': {},
                'auto_bots': {}
            }
            
            for bot_id, bot in self.bots.items():
                status['bots'][bot_id] = {
                    'symbol': bot.symbol,
                    'strategy': bot.strategy_name,
                    'status': bot.status,
                    'side': bot.side,
                    'qty': bot.qty,
                    'entry': bot.entry
                }
            
            for bot_id, auto_bot in self.auto_bots.items():
                status['auto_bots'][bot_id] = {
                    'strategy': auto_bot['strategy'],
                    'symbols': auto_bot['symbols'],
                    'params': auto_bot['params']
                }
            
            return status
    
    def get_active_symbols(self):
        with self._lock:
            symbols = set()
            for bot in self.bots.values():
                symbols.add(bot.symbol)
            return list(symbols)

# ========== HÀM TIỆN ÍCH ==========
def format_bot_status(status_data):
    if not status_data:
        return "❌ Không có dữ liệu trạng thái"
    
    try:
        total_bots = status_data.get('total_bots', 0)
        total_auto_bots = status_data.get('total_auto_bots', 0)
        
        message = f"""🤖 <b>TỔNG QUAN BOT</b>

📊 <b>Tổng số bot:</b> {total_bots}
🤖 <b>Bot tự động:</b> {total_auto_bots}

"""
        
        # THÔNG TIN BOT CHI TIẾT
        if status_data.get('bots'):
            message += "\n<b>📈 BOT ĐANG HOẠT ĐỘNG:</b>\n"
            for bot_id, bot_info in status_data['bots'].items():
                symbol = bot_info.get('symbol', 'N/A')
                strategy = bot_info.get('strategy', 'N/A')
                bot_status = bot_info.get('status', 'N/A')
                side = bot_info.get('side', '')
                qty = bot_info.get('qty', 0)
                entry = bot_info.get('entry', 0)
                
                status_emoji = "🟢" if bot_status == "open" else "🟡" if bot_status == "waiting" else "🔴"
                position_info = f" | {side} {qty}" if side and qty else ""
                
                message += f"{status_emoji} <b>{symbol}</b> ({strategy}) - {bot_status}{position_info}\n"
        
        # THÔNG TIN BOT TỰ ĐỘNG
        if status_data.get('auto_bots'):
            message += "\n<b>🤖 BOT TỰ ĐỘNG:</b>\n"
            for bot_id, auto_info in status_data['auto_bots'].items():
                strategy = auto_info.get('strategy', 'N/A')
                symbols = auto_info.get('symbols', [])
                message += f"🔧 <b>{strategy}</b>: {', '.join(symbols)}\n"
        
        return message
        
    except Exception as e:
        logger.error(f"Lỗi định dạng trạng thái bot: {str(e)}")
        return "❌ Lỗi hiển thị trạng thái"

def get_balance_info(api_key, api_secret):
    try:
        balance = get_balance(api_key, api_secret)
        if balance is None:
            return "❌ Không thể kết nối Binance"
        
        positions = get_positions(api_key=api_key, api_secret=api_secret)
        if positions is None:
            return "❌ Lỗi lấy vị thế"
        
        total_pnl = 0
        open_positions = []
        
        for pos in positions:
            position_amt = float(pos.get('positionAmt', 0))
            if abs(position_amt) > 0:
                entry_price = float(pos.get('entryPrice', 0))
                current_price = get_current_price(pos['symbol'])
                if current_price > 0:
                    if position_amt > 0:  # LONG
                        pnl = (current_price - entry_price) * abs(position_amt)
                    else:  # SHORT
                        pnl = (entry_price - current_price) * abs(position_amt)
                    
                    total_pnl += pnl
                    open_positions.append({
                        'symbol': pos['symbol'],
                        'side': 'LONG' if position_amt > 0 else 'SHORT',
                        'qty': abs(position_amt),
                        'entry': entry_price,
                        'current': current_price,
                        'pnl': pnl
                    })
        
        message = f"""💰 <b>THÔNG TIN TÀI KHOẢN</b>

💵 <b>Số dư khả dụng:</b> {balance:.2f} USDT
📈 <b>Tổng PnL:</b> {total_pnl:.2f} USDT
🏦 <b>Tổng tài sản:</b> {balance + total_pnl:.2f} USDT

"""
        
        if open_positions:
            message += "<b>📊 VỊ THẾ MỞ:</b>\n"
            for pos in open_positions:
                pnl_emoji = "🟢" if pos['pnl'] >= 0 else "🔴"
                message += f"{pnl_emoji} <b>{pos['symbol']}</b> {pos['side']} {pos['qty']} | PnL: {pos['pnl']:.2f} USDT\n"
        
        return message
        
    except Exception as e:
        logger.error(f"Lỗi lấy thông tin số dư: {str(e)}")
        return f"❌ Lỗi lấy thông tin: {str(e)}"

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
bot_manager = BotManager()
coin_manager = CoinManager()
