# trading_bot_lib_fixed.py
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
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
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
    symbols = get_all_usdt_pairs(limit=20)
    keyboard = []
    row = []
    for symbol in symbols:
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
                cls._instance.managed_coins = {}
                cls._instance.position_coins = set()
        return cls._instance
    
    def register_coin(self, symbol, bot_id):
        with self._lock:
            if symbol not in self.managed_coins:
                self.managed_coins[symbol] = bot_id
                return True
            return False
    
    def unregister_coin(self, symbol):
        with self._lock:
            if symbol in self.managed_coins:
                del self.managed_coins[symbol]
                return True
            return False
    
    def is_coin_managed(self, symbol):
        with self._lock:
            return symbol in self.managed_coins
    
    def get_managed_coins(self):
        with self._lock:
            return self.managed_coins.copy()
    
    def add_position_coin(self, symbol):
        with self._lock:
            self.position_coins.add(symbol)
    
    def remove_position_coin(self, symbol):
        with self._lock:
            if symbol in self.position_coins:
                self.position_coins.remove(symbol)
    
    def get_position_coins(self):
        with self._lock:
            return self.position_coins.copy()

# ========== HÀM TÌM COIN TOÀN BINANCE ==========
def get_all_usdt_pairs(limit=100):
    """Lấy tất cả cặp USDT từ Binance Futures"""
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT"]
        
        usdt_pairs = []
        for symbol_info in data.get('symbols', []):
            symbol = symbol_info.get('symbol', '')
            if symbol.endswith('USDT') and symbol_info.get('status') == 'TRADING':
                usdt_pairs.append(symbol)
        
        return usdt_pairs[:limit] if limit else usdt_pairs
        
    except Exception as e:
        logger.error(f"Lỗi lấy danh sách coin: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT"]

def get_qualified_symbols(api_key, api_secret, strategy_type, leverage, threshold=None, volatility=None, grid_levels=None, max_candidates=50, final_limit=2):
    """Tìm coin phù hợp trên toàn bộ Binance"""
    try:
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE")
            return []
        
        coin_manager = CoinManager()
        managed_coins = coin_manager.get_managed_coins()
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            logger.error("❌ Không lấy được dữ liệu 24h từ Binance")
            return []
        
        qualified_symbols = []
        
        for ticker in data:
            symbol = ticker.get('symbol', '')
            if not symbol.endswith('USDT'):
                continue
                
            # Bỏ qua BTC, ETH để tránh rủi ro cao
            if symbol in ['BTCUSDT', 'ETHUSDT']:
                continue
            
            # Bỏ qua coin đã có bot quản lý
            if symbol in managed_coins:
                continue
            
            try:
                price_change = float(ticker.get('priceChangePercent', 0))
                volume = float(ticker.get('quoteVolume', 0))
                high_price = float(ticker.get('highPrice', 0))
                low_price = float(ticker.get('lowPrice', 0))
                
                if low_price > 0:
                    price_range = ((high_price - low_price) / low_price) * 100
                else:
                    price_range = 0
                
                # TIÊU CHÍ CHO TỪNG CHIẾN LƯỢC
                if strategy_type == "Reverse 24h":
                    if abs(price_change) >= (threshold or 30) and volume > 5000000:
                        qualified_symbols.append((symbol, abs(price_change), volume))
                elif strategy_type == "Scalping":
                    if abs(price_change) >= (volatility or 3) and volume > 10000000 and price_range >= 2.0:
                        qualified_symbols.append((symbol, price_range, volume))
                elif strategy_type == "Safe Grid":
                    if 1.0 <= abs(price_change) <= 5.0 and volume > 2000000 and price_range <= 8.0:
                        qualified_symbols.append((symbol, -abs(price_change - 3.0), volume))
            except (ValueError, TypeError) as e:
                continue
        
        # SẮP XẾP THEO ĐIỂM PHÙ HỢP
        if strategy_type == "Reverse 24h":
            qualified_symbols.sort(key=lambda x: (x[1], x[2]), reverse=True)  # Biến động + volume
        elif strategy_type == "Scalping":
            qualified_symbols.sort(key=lambda x: (x[1], x[2]), reverse=True)  # Price range + volume
        elif strategy_type == "Safe Grid":
            qualified_symbols.sort(key=lambda x: (x[1], x[2]), reverse=True)  # Độ ổn định + volume
        
        # CHỌN COIN TỐT NHẤT
        final_symbols = []
        for symbol, score, volume in qualified_symbols[:max_candidates]:
            if len(final_symbols) >= final_limit:
                break
            try:
                # KIỂM TRA ĐÒN BẨY VÀ LOT SIZE
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                step_size = get_step_size(symbol, api_key, api_secret)
                
                if leverage_success and step_size > 0:
                    final_symbols.append(symbol)
                    logger.info(f"✅ {symbol}: phù hợp {strategy_type} (Score: {score:.2f}, Volume: {volume:.0f})")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ Lỗi kiểm tra {symbol}: {str(e)}")
                continue
        
        # FALLBACK NẾU KHÔNG TÌM ĐỦ COIN
        if len(final_symbols) < final_limit:
            backup_symbols = ["ADAUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT", "ATOMUSDT", "AVAXUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
            for symbol in backup_symbols:
                if len(final_symbols) >= final_limit:
                    break
                if symbol not in final_symbols and symbol not in managed_coins:
                    try:
                        leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                        step_size = get_step_size(symbol, api_key, api_secret)
                        if leverage_success and step_size > 0:
                            final_symbols.append(symbol)
                            logger.info(f"✅ {symbol}: fallback cho {strategy_type}")
                    except Exception as e:
                        continue
        
        logger.info(f"🎯 {strategy_type}: tìm thấy {len(final_symbols)} coin phù hợp")
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
                        return None
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            logger.error(f"Lỗi HTTP ({e.code}): {e.reason}")
            if e.code == 401:
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

def get_min_notional(symbol, api_key, api_secret):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        data = binance_api_request(url)
        if not data:
            return 5.0
        for s in data['symbols']:
            if s['symbol'] == symbol.upper():
                for f in s['filters']:
                    if f['filterType'] == 'MIN_NOTIONAL':
                        return float(f.get('notional', 5.0))
    except Exception as e:
        logger.error(f"Lỗi lấy min notional: {str(e)}")
    return 5.0

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
            change = data['priceChangePercent']
            # ĐẢM BẢO KHÔNG BAO GIỜ TRẢ VỀ None
            if change is None:
                return 0.0
            return float(change)
        return 0.0
    except Exception as e:
        logger.error(f"Lỗi lấy biến động 24h cho {symbol}: {str(e)}")
    return 0.0

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
        rsi_value = 100.0 - (100.0 / (1 + rs))
        
        # KIỂM TRA GIÁ TRỊ HỢP LỆ
        if np.isnan(rsi_value) or np.isinf(rsi_value):
            return None
        return rsi_value
    except Exception as e:
        return None

def calc_ema(prices, period):
    try:
        prices = np.array(prices)
        if len(prices) < period:
            return None
        weights = np.exp(np.linspace(-1., 0., period))
        weights /= weights.sum()
        ema = np.convolve(prices, weights, mode='valid')
        ema_value = float(ema[-1])
        
        # KIỂM TRA GIÁ TRỊ HỢP LỆ
        if np.isnan(ema_value) or np.isinf(ema_value):
            return None
        return ema_value
    except Exception as e:
        return None

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
        self.symbol = symbol.upper() if symbol else "BTCUSDT"
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
        
        # BIẾN TRẠNG THÁI
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []
        self.position_open = False
        self._stop = False
        
        # BIẾN THỜI GIAN
        self.last_trade_time = 0
        self.last_close_time = 0
        self.last_position_check = 0
        self.last_signal_check = 0
        self.last_error_log_time = 0
        
        # CÀI ĐẶT
        self.position_check_interval = 60
        self.cooldown_period = 900
        self.max_position_attempts = 3
        self.position_attempt_count = 0
        
        # ĐĂNG KÝ COIN
        self.coin_manager = CoinManager()
        if symbol:
            self.coin_manager.register_coin(self.symbol, f"{strategy_name}_{id(self)}")
        
        # KHỞI CHẠY
        self.check_position_status()
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot {strategy_name} khởi động cho {self.symbol} | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%")

    def log(self, message):
        logger.info(f"[{self.symbol} - {self.strategy_name}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>{self.symbol}</b> ({self.strategy_name}): {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def _handle_price_update(self, price):
        if self._stop or not price or price <= 0:
            return
        try:
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
                
                # KIỂM TRA VỊ THẾ
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                # LẤY TÍN HIỆU
                signal = self.get_signal()
                
                # MỞ LỆNH NẾU CÓ TÍN HIỆU
                if not self.position_open and signal and current_time - self.last_trade_time > 60:
                    if current_time - self.last_close_time > self.cooldown_period:
                        self.log(f"🎯 Nhận tín hiệu {signal}, đang mở lệnh...")
                        self.open_position(signal)
                        self.last_trade_time = current_time
                
                # KIỂM TRA TP/SL
                if self.position_open:
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    self.log(f"❌ Lỗi hệ thống: {str(e)}")
                    self.last_error_log_time = time.time()
                time.sleep(1)

    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        try:
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
        except Exception as e:
            self.log(f"❌ Lỗi hủy lệnh: {str(e)}")
        self.coin_manager.unregister_coin(self.symbol)
        self.log(f"🔴 Bot dừng cho {self.symbol}")

    def check_position_status(self):
        try:
            positions = get_positions(self.symbol, self.api_key, self.api_secret)
            if not positions:
                self._reset_position()
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
                        self._reset_position()
                        return
            self._reset_position()
            
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")
                self.last_error_log_time = time.time()

    def _reset_position(self):
        self.position_open = False
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.coin_manager.remove_position_coin(self.symbol)

    def open_position(self, side):
        try:
            # KIỂM TRA LẠI VỊ THẾ
            self.check_position_status()
            if self.position_open:
                self.log(f"⚠️ Đã có vị thế {self.side}, bỏ qua")
                return False

            # THIẾT LẬP ĐÒN BẨY
            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x")
                return False

            # TÍNH TOÁN SỐ LƯỢNG
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không đủ số dư")
                return False

            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                self.log("❌ Lỗi lấy giá")
                return False

            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            min_notional = get_min_notional(self.symbol, self.api_key, self.api_secret)

            # TÍNH TOÁN SỐ LƯỢNG
            usdt_amount = balance * (self.percent / 100)
            qty = usdt_amount / current_price
            qty = math.floor(qty / step_size) * step_size

            # KIỂM TRA NOTIONAL TỐI THIỂU
            notional = qty * current_price
            if notional < min_notional:
                qty = math.ceil(min_notional / current_price / step_size) * step_size
                notional = qty * current_price
                if notional > usdt_amount:
                    self.log(f"⚠️ Số dư không đủ để đạt notional tối thiểu {min_notional} USDT")
                    return False

            # ĐẶT LỆNH
            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if result and result.get('status') in ['FILLED', 'NEW']:
                self.position_open = True
                self.side = side
                self.qty = qty
                self.entry = current_price
                self.status = "open"
                self.position_attempt_count = 0
                self.coin_manager.add_position_coin(self.symbol)
                self.log(f"✅ Mở lệnh {side} | SL: {qty} | Giá: {current_price:.4f} | Vốn: {usdt_amount:.2f} USDT")
                return True
            else:
                self.position_attempt_count += 1
                if self.position_attempt_count >= self.max_position_attempts:
                    self.log("❌ Đã thử mở lệnh nhiều lần không thành công, tạm dừng")
                    self.position_attempt_count = 0
                return False

        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False

    def close_position(self):
        try:
            if not self.position_open:
                return True

            side = "SELL" if self.side == "BUY" else "BUY"
            result = place_order(self.symbol, side, abs(self.qty), self.api_key, self.api_secret)
            if result and result.get('status') in ['FILLED', 'NEW']:
                current_price = get_current_price(self.symbol)
                pnl = (current_price - self.entry) * self.qty if self.side == "BUY" else (self.entry - current_price) * self.qty
                pnl_percent = (pnl / (self.entry * abs(self.qty))) * 100
                
                self.log(f"🔒 Đóng lệnh {self.side} | PnL: {pnl:.2f} USDT ({pnl_percent:.2f}%)")
                self._reset_position()
                self.last_close_time = time.time()
                return True
            else:
                self.log("❌ Lỗi đóng lệnh")
                return False
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False

    def check_tp_sl(self):
        try:
            if not self.position_open or self.entry == 0:
                return

            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                return

            # TÍNH LỢI NHUẬN/THUA LỖ
            if self.side == "BUY":
                profit_percent = ((current_price - self.entry) / self.entry) * 100
            else:
                profit_percent = ((self.entry - current_price) / self.entry) * 100

            # KIỂM TRA TP/SL
            if profit_percent >= self.tp:
                self.log(f"🎯 ĐẠT TP {self.tp}% | Lợi nhuận: {profit_percent:.2f}%")
                self.close_position()
            elif profit_percent <= -self.sl:
                self.log(f"🛑 CHẠM SL {self.sl}% | Thua lỗ: {profit_percent:.2f}%")
                self.close_position()

        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra TP/SL: {str(e)}")
                self.last_error_log_time = time.time()

# ========== CHIẾN LƯỢC GIAO DỊCH ==========
class Reverse24hBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, threshold, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Reverse 24h")
        self.threshold = threshold
        self.last_24h_change = 0

    def get_signal(self):
        try:
            # LẤY BIẾN ĐỘNG 24H - ĐÃ SỬA LỖI NONE
            change_24h = get_24h_change(self.symbol)
            self.last_24h_change = change_24h
            
            # KIỂM TRA GIÁ TRỊ HỢP LỆ TRƯỚC KHI SO SÁNH
            if change_24h is None:
                return None
                
            # TÍN HIỆU ĐẢO CHIỀU
            if change_24h <= -self.threshold:
                return "BUY"
            elif change_24h >= self.threshold:
                return "SELL"
            return None
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Reverse 24h: {str(e)}")
                self.last_error_log_time = time.time()
            return None

class ScalpingBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, volatility, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Scalping")
        self.volatility = volatility
        self.rsi_period = 7
        self.ema_fast = 5
        self.ema_slow = 13

    def get_signal(self):
        try:
            if len(self.prices) < 20:
                return None

            # TÍNH TOÁN CÁC CHỈ BÁO
            rsi = calc_rsi(self.prices[-15:], self.rsi_period)
            ema_fast = calc_ema(self.prices[-10:], self.ema_fast)
            ema_slow = calc_ema(self.prices[-15:], self.ema_slow)

            # KIỂM TRA GIÁ TRỊ HỢP LỆ
            if rsi is None or ema_fast is None or ema_slow is None:
                return None

            # TÍN HIỆU SCALPING
            if rsi < 30 and ema_fast > ema_slow:
                return "BUY"
            elif rsi > 70 and ema_fast < ema_slow:
                return "SELL"
            return None
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Scalping: {str(e)}")
                self.last_error_log_time = time.time()
            return None

class SafeGridBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, grid_levels, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Safe Grid")
        self.grid_levels = grid_levels
        self.grid_orders = []
        self.base_price = 0
        self.grid_spacing = 0.02  # 2%

    def get_signal(self):
        try:
            if len(self.prices) < 10:
                return None

            current_price = self.prices[-1]
            
            # KHỞI TẠO GRID
            if not self.grid_orders:
                self._setup_grid(current_price)
                return None

            # KIỂM TRA CÁC MỨC GRID
            for i, (price, side, filled) in enumerate(self.grid_orders):
                if not filled and ((side == "BUY" and current_price <= price) or (side == "SELL" and current_price >= price)):
                    self.grid_orders[i] = (price, side, True)
                    return side

            return None
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Safe Grid: {str(e)}")
                self.last_error_log_time = time.time()
            return None

    def _setup_grid(self, current_price):
        self.base_price = current_price
        self.grid_orders = []
        
        for i in range(self.grid_levels):
            buy_price = current_price * (1 - self.grid_spacing * (i + 1))
            sell_price = current_price * (1 + self.grid_spacing * (i + 1))
            self.grid_orders.append((buy_price, "BUY", False))
            self.grid_orders.append((sell_price, "SELL", False))
        
        self.log(f"🕸️ Thiết lập Grid {self.grid_levels} cấp | Giá cơ sở: {current_price:.4f}")

    def open_position(self, side):
        success = super().open_position(side)
        if success:
            # ĐẶT LỆNH CHỐT LỜI SAU KHI MỞ LỆNH GRID
            self.place_tp_order()
        return success

    def place_tp_order(self):
        try:
            if not self.position_open:
                return
            
            # TÍNH GIÁ CHỐT LỜI CHO GRID
            if self.side == "BUY":
                tp_price = self.entry * (1 + self.tp / 100)
            else:
                tp_price = self.entry * (1 - self.tp / 100)
            
            self.log(f"📊 Grid TP: {tp_price:.4f} từ {self.entry:.4f}")
            
        except Exception as e:
            self.log(f"❌ Lỗi đặt lệnh TP Grid: {str(e)}")

# ========== BOT MANAGER ==========
class BotManager:
    def __init__(self):
        self.bots = {}
        self.ws_manager = WebSocketManager()
        self.api_key = ""
        self.api_secret = ""
        self.telegram_bot_token = ""
        self.telegram_chat_id = ""
        self._lock = threading.Lock()
        self.coin_manager = CoinManager()
        
    def set_api_keys(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def set_telegram_keys(self, bot_token, chat_id):
        self.telegram_bot_token = bot_token
        self.telegram_chat_id = chat_id
        
    def add_bot(self, symbol, strategy, lev, percent, tp, sl, **params):
        with self._lock:
            bot_id = f"{symbol}_{strategy}"
            if bot_id in self.bots:
                return f"❌ Bot {symbol} {strategy} đã tồn tại"
            
            # KIỂM TRA COIN ĐÃ CÓ BOT KHÁC CHƯA
            if self.coin_manager.is_coin_managed(symbol):
                return f"❌ {symbol} đã có bot khác quản lý"
            
            try:
                if strategy == "Reverse 24h":
                    threshold = params.get('threshold', 30)
                    bot = Reverse24hBot(symbol, lev, percent, tp, sl, threshold, 
                                       self.ws_manager, self.api_key, self.api_secret,
                                       self.telegram_bot_token, self.telegram_chat_id)
                elif strategy == "Scalping":
                    volatility = params.get('volatility', 5)
                    bot = ScalpingBot(symbol, lev, percent, tp, sl, volatility,
                                     self.ws_manager, self.api_key, self.api_secret,
                                     self.telegram_bot_token, self.telegram_chat_id)
                elif strategy == "Safe Grid":
                    grid_levels = params.get('grid_levels', 5)
                    bot = SafeGridBot(symbol, lev, percent, tp, sl, grid_levels,
                                     self.ws_manager, self.api_key, self.api_secret,
                                     self.telegram_bot_token, self.telegram_chat_id)
                else:
                    return f"❌ Chiến lược {strategy} không hợp lệ"
                
                self.bots[bot_id] = bot
                return f"✅ Đã thêm bot {symbol} {strategy}"
                
            except Exception as e:
                return f"❌ Lỗi tạo bot: {str(e)}"
    
    def auto_add_bots(self, strategy_type, leverage, percent, tp, sl, **params):
        """Tự động tìm và thêm bot từ toàn bộ Binance"""
        try:
            # TÌM COIN PHÙ HỢP TRÊN TOÀN BỘ BINANCE
            qualified_symbols = get_qualified_symbols(
                self.api_key, self.api_secret, strategy_type, leverage,
                params.get('threshold'), params.get('volatility'), 
                params.get('grid_levels'), max_candidates=50, final_limit=2
            )
            
            if not qualified_symbols:
                return f"❌ Không tìm thấy coin phù hợp cho {strategy_type}"
            
            results = []
            for symbol in qualified_symbols:
                result = self.add_bot(symbol, strategy_type, leverage, percent, tp, sl, **params)
                results.append(f"{symbol}: {result}")
                time.sleep(0.5)  # Tránh rate limit
            
            return f"🤖 Kết quả tìm bot tự động {strategy_type}:\n" + "\n".join(results)
            
        except Exception as e:
            return f"❌ Lỗi tìm bot tự động: {str(e)}"
    
    def remove_bot(self, symbol, strategy):
        with self._lock:
            bot_id = f"{symbol}_{strategy}"
            if bot_id in self.bots:
                bot = self.bots[bot_id]
                bot.stop()
                del self.bots[bot_id]
                return f"✅ Đã xóa bot {symbol} {strategy}"
            return f"❌ Không tìm thấy bot {symbol} {strategy}"
    
    def stop_all_bots(self):
        with self._lock:
            for bot_id, bot in list(self.bots.items()):
                bot.stop()
            self.bots.clear()
            return "✅ Đã dừng tất cả bot"
    
    def get_bot_list(self):
        with self._lock:
            if not self.bots:
                return "📊 Không có bot nào đang chạy"
            
            bot_list = []
            for bot_id, bot in self.bots.items():
                status = "🟢 Mở" if bot.position_open else "🟡 Chờ"
                bot_list.append(f"{bot.symbol} - {bot.strategy_name} | {status} | ĐB: {bot.lev}x")
            
            return "📊 Danh sách Bot:\n" + "\n".join(bot_list)
    
    def get_balance(self):
        if not self.api_key or not self.api_secret:
            return "❌ Chưa thiết lập API Keys"
        
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            return "❌ Lỗi kết nối Binance"
        
        return f"💰 Số dư khả dụng: {balance:.2f} USDT"
    
    def get_positions(self):
        if not self.api_key or not self.api_secret:
            return "❌ Chưa thiết lập API Keys"
        
        positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
        if not positions:
            return "📈 Không có vị thế nào"
        
        position_list = []
        for pos in positions:
            if float(pos.get('positionAmt', 0)) != 0:
                symbol = pos['symbol']
                side = "LONG" if float(pos['positionAmt']) > 0 else "SHORT"
                entry = float(pos['entryPrice'])
                pnl = float(pos['unRealizedProfit'])
                position_list.append(f"{symbol} | {side} | Entry: {entry:.4f} | PnL: {pnl:.2f} USDT")
        
        if not position_list:
            return "📈 Không có vị thế nào"
        
        return "📈 Vị thế hiện tại:\n" + "\n".join(position_list)

# ========== TELEGRAM HANDLER ==========
class TelegramHandler:
    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.user_states = {}
        self.pending_data = {}
        
    def handle_message(self, message, chat_id):
        try:
            text = message.get('text', '').strip()
            if not text:
                return
            
            # XỬ LÝ TRẠNG THÁI NGƯỜI DÙNG
            user_state = self.user_states.get(chat_id, {})
            current_state = user_state.get('state', '')
            pending_data = self.pending_data.get(chat_id, {})
            
            # KIỂM TRA HỦY BỎ
            if text == "❌ Hủy bỏ":
                self.user_states[chat_id] = {}
                self.pending_data[chat_id] = {}
                send_telegram("🔄 Đã hủy thao tác", chat_id=chat_id, 
                             reply_markup=create_main_menu(),
                             bot_token=self.bot_manager.telegram_bot_token)
                return
            
            # XỬ LÝ THEO TRẠNG THÁI
            if current_state:
                self._handle_state(chat_id, text, user_state, pending_data)
                return
            
            # XỬ LÝ LỆNH CHÍNH
            if text == "📊 Danh sách Bot":
                response = self.bot_manager.get_bot_list()
                send_telegram(response, chat_id=chat_id, 
                             bot_token=self.bot_manager.telegram_bot_token)
                
            elif text == "➕ Thêm Bot":
                self.user_states[chat_id] = {'state': 'choosing_strategy'}
                self.pending_data[chat_id] = {}
                send_telegram("🤖 Chọn chiến lược giao dịch:", chat_id=chat_id,
                             reply_markup=create_strategy_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
                
            elif text == "⛔ Dừng Bot":
                self.user_states[chat_id] = {'state': 'stopping_bot'}
                self.pending_data[chat_id] = {}
                bot_list = self.bot_manager.get_bot_list()
                send_telegram(f"{bot_list}\n\nNhập tên bot để dừng (ví dụ: BTCUSDT Reverse 24h):", 
                             chat_id=chat_id, reply_markup=create_cancel_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
                
            elif text == "💰 Số dư":
                response = self.bot_manager.get_balance()
                send_telegram(response, chat_id=chat_id,
                             bot_token=self.bot_manager.telegram_bot_token)
                
            elif text == "📈 Vị thế":
                response = self.bot_manager.get_positions()
                send_telegram(response, chat_id=chat_id,
                             bot_token=self.bot_manager.telegram_bot_token)
                
            elif text == "🎯 Chiến lược":
                send_telegram(
                    "🤖 <b>Chiến lược giao dịch</b>\n\n"
                    "🎯 <b>Reverse 24h</b>: Đảo chiều khi biến động mạnh 24h\n"
                    "⚡ <b>Scalping</b>: Giao dịch nhanh dựa RSI/EMA\n"
                    "🛡️ <b>Safe Grid</b>: Grid an toàn với nhiều mức giá\n\n"
                    "Chọn '➕ Thêm Bot' để bắt đầu!",
                    chat_id=chat_id, reply_markup=create_main_menu(),
                    bot_token=self.bot_manager.telegram_bot_token
                )
                
            elif text == "⚙️ Cấu hình":
                send_telegram(
                    "⚙️ <b>Cấu hình hệ thống</b>\n\n"
                    "Để thiết lập API Keys, vui lòng sử dụng lệnh:\n"
                    "<code>/set_api API_KEY API_SECRET</code>\n\n"
                    "Để thiết lập Telegram:\n"
                    "<code>/set_telegram BOT_TOKEN CHAT_ID</code>",
                    chat_id=chat_id, reply_markup=create_main_menu(),
                    bot_token=self.bot_manager.telegram_bot_token
                )
                
            elif text.startswith('/'):
                self._handle_command(text, chat_id)
                
        except Exception as e:
            logger.error(f"Lỗi xử lý tin nhắn Telegram: {str(e)}")
            send_telegram("❌ Lỗi xử lý yêu cầu", chat_id=chat_id,
                         bot_token=self.bot_manager.telegram_bot_token)
    
    def _handle_state(self, chat_id, text, user_state, pending_data):
        state = user_state.get('state', '')
        
        if state == 'choosing_strategy':
            if text in ["🎯 Reverse 24h", "⚡ Scalping", "🛡️ Safe Grid"]:
                strategy_map = {
                    "🎯 Reverse 24h": "Reverse 24h",
                    "⚡ Scalping": "Scalping", 
                    "🛡️ Safe Grid": "Safe Grid"
                }
                strategy = strategy_map[text]
                self.pending_data[chat_id]['strategy'] = strategy
                self.user_states[chat_id]['state'] = 'choosing_leverage'
                
                send_telegram(f"Đã chọn: {strategy}\n\nChọn đòn bẩy:", 
                             chat_id=chat_id, reply_markup=create_leverage_keyboard(strategy),
                             bot_token=self.bot_manager.telegram_bot_token)
            else:
                send_telegram("❌ Vui lòng chọn chiến lược từ menu", 
                             chat_id=chat_id, reply_markup=create_strategy_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_leverage':
            if text.strip().endswith('x'):
                try:
                    leverage = int(text.strip().replace('x', ''))
                    self.pending_data[chat_id]['leverage'] = leverage
                    self.user_states[chat_id]['state'] = 'choosing_percent'
                    
                    send_telegram(f"Đòn bẩy: {leverage}x\n\nChọn % vốn mỗi lệnh:", 
                                 chat_id=chat_id, reply_markup=create_percent_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
                except ValueError:
                    send_telegram("❌ Đòn bẩy không hợp lệ", 
                                 chat_id=chat_id, reply_markup=create_leverage_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
            else:
                send_telegram("❌ Vui lòng chọn đòn bẩy từ menu", 
                             chat_id=chat_id, reply_markup=create_leverage_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_percent':
            if text.isdigit():
                percent = int(text)
                if 1 <= percent <= 100:
                    self.pending_data[chat_id]['percent'] = percent
                    self.user_states[chat_id]['state'] = 'choosing_tp'
                    
                    send_telegram(f"% vốn: {percent}%\n\nChọn Take Profit (%):", 
                                 chat_id=chat_id, reply_markup=create_tp_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
                else:
                    send_telegram("❌ % vốn phải từ 1-100", 
                                 chat_id=chat_id, reply_markup=create_percent_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
            else:
                send_telegram("❌ Vui lòng nhập số % hợp lệ", 
                             chat_id=chat_id, reply_markup=create_percent_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_tp':
            if text.isdigit():
                tp = int(text)
                if tp > 0:
                    self.pending_data[chat_id]['tp'] = tp
                    self.user_states[chat_id]['state'] = 'choosing_sl'
                    
                    send_telegram(f"Take Profit: {tp}%\n\nChọn Stop Loss (%):", 
                                 chat_id=chat_id, reply_markup=create_sl_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
                else:
                    send_telegram("❌ TP phải > 0", 
                                 chat_id=chat_id, reply_markup=create_tp_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
            else:
                send_telegram("❌ Vui lòng nhập TP hợp lệ", 
                             chat_id=chat_id, reply_markup=create_tp_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_sl':
            if text.isdigit():
                sl = int(text)
                if sl >= 0:
                    self.pending_data[chat_id]['sl'] = sl
                    
                    # THAM SỐ BỔ SUNG THEO CHIẾN LƯỢC
                    strategy = self.pending_data[chat_id].get('strategy')
                    if strategy == "Reverse 24h":
                        self.user_states[chat_id]['state'] = 'choosing_threshold'
                        send_telegram(f"Stop Loss: {sl}%\n\nChọn ngưỡng biến động 24h (%):", 
                                     chat_id=chat_id, reply_markup=create_threshold_keyboard(),
                                     bot_token=self.bot_manager.telegram_bot_token)
                    elif strategy == "Scalping":
                        self.user_states[chat_id]['state'] = 'choosing_volatility'
                        send_telegram(f"Stop Loss: {sl}%\n\nChọn độ biến động tối thiểu (%):", 
                                     chat_id=chat_id, reply_markup=create_volatility_keyboard(),
                                     bot_token=self.bot_manager.telegram_bot_token)
                    elif strategy == "Safe Grid":
                        self.user_states[chat_id]['state'] = 'choosing_grid_levels'
                        send_telegram(f"Stop Loss: {sl}%\n\nChọn số cấp Grid:", 
                                     chat_id=chat_id, reply_markup=create_grid_levels_keyboard(),
                                     bot_token=self.bot_manager.telegram_bot_token)
                    else:
                        self._finalize_bot_creation(chat_id)
                else:
                    send_telegram("❌ SL phải >= 0", 
                                 chat_id=chat_id, reply_markup=create_sl_keyboard(),
                                 bot_token=self.bot_manager.telegram_bot_token)
            else:
                send_telegram("❌ Vui lòng nhập SL hợp lệ", 
                             chat_id=chat_id, reply_markup=create_sl_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_threshold':
            if text.isdigit():
                threshold = int(text)
                self.pending_data[chat_id]['threshold'] = threshold
                self._finalize_bot_creation(chat_id)
            else:
                send_telegram("❌ Vui lòng nhập ngưỡng hợp lệ", 
                             chat_id=chat_id, reply_markup=create_threshold_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_volatility':
            if text.isdigit():
                volatility = int(text)
                self.pending_data[chat_id]['volatility'] = volatility
                self._finalize_bot_creation(chat_id)
            else:
                send_telegram("❌ Vui lòng nhập độ biến động hợp lệ", 
                             chat_id=chat_id, reply_markup=create_volatility_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'choosing_grid_levels':
            if text.isdigit():
                grid_levels = int(text)
                self.pending_data[chat_id]['grid_levels'] = grid_levels
                self._finalize_bot_creation(chat_id)
            else:
                send_telegram("❌ Vui lòng nhập số cấp hợp lệ", 
                             chat_id=chat_id, reply_markup=create_grid_levels_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
        
        elif state == 'stopping_bot':
            parts = text.split()
            if len(parts) >= 2:
                symbol = parts[0].upper()
                strategy = " ".join(parts[1:])
                response = self.bot_manager.remove_bot(symbol, strategy)
                send_telegram(response, chat_id=chat_id, 
                             reply_markup=create_main_menu(),
                             bot_token=self.bot_manager.telegram_bot_token)
                self.user_states[chat_id] = {}
                self.pending_data[chat_id] = {}
            else:
                send_telegram("❌ Định dạng không hợp lệ. Ví dụ: BTCUSDT Reverse 24h", 
                             chat_id=chat_id, reply_markup=create_cancel_keyboard(),
                             bot_token=self.bot_manager.telegram_bot_token)
    
    def _finalize_bot_creation(self, chat_id):
        try:
            data = self.pending_data[chat_id]
            strategy = data.get('strategy')
            
            # TỰ ĐỘNG TÌM COIN PHÙ HỢP
            response = self.bot_manager.auto_add_bots(
                strategy_type=strategy,
                leverage=data.get('leverage', 10),
                percent=data.get('percent', 5),
                tp=data.get('tp', 100),
                sl=data.get('sl', 50),
                threshold=data.get('threshold', 30),
                volatility=data.get('volatility', 5),
                grid_levels=data.get('grid_levels', 5)
            )
            
            send_telegram(response, chat_id=chat_id,
                         reply_markup=create_main_menu(),
                         bot_token=self.bot_manager.telegram_bot_token)
            
        except Exception as e:
            error_msg = f"❌ Lỗi tạo bot: {str(e)}"
            send_telegram(error_msg, chat_id=chat_id,
                         reply_markup=create_main_menu(),
                         bot_token=self.bot_manager.telegram_bot_token)
        
        finally:
            self.user_states[chat_id] = {}
            self.pending_data[chat_id] = {}
    
    def _handle_command(self, text, chat_id):
        parts = text.split()
        command = parts[0].lower()
        
        if command == '/start':
            welcome_msg = (
                "🤖 <b>Binance Futures Trading Bot</b>\n\n"
                "Chào mừng bạn đến với hệ thống giao dịch tự động!\n\n"
                "📊 <b>Chức năng chính:</b>\n"
                "• 🤖 Quản lý bot giao dịch\n"
                "• 📈 Theo dõi vị thế & số dư\n"
                "• ⚡ Đa chiến lược giao dịch\n"
                "• 🎯 Tìm coin tự động toàn Binance\n\n"
                "Sử dụng menu bên dưới để bắt đầu!"
            )
            send_telegram(welcome_msg, chat_id=chat_id,
                         reply_markup=create_main_menu(),
                         bot_token=self.bot_manager.telegram_bot_token)
        
        elif command == '/set_api' and len(parts) == 3:
            api_key = parts[1]
            api_secret = parts[2]
            self.bot_manager.set_api_keys(api_key, api_secret)
            send_telegram("✅ Đã thiết lập API Keys", chat_id=chat_id,
                         bot_token=self.bot_manager.telegram_bot_token)
        
        elif command == '/set_telegram' and len(parts) == 3:
            bot_token = parts[1]
            chat_id_param = parts[2]
            self.bot_manager.set_telegram_keys(bot_token, chat_id_param)
            send_telegram("✅ Đã thiết lập Telegram", chat_id=chat_id,
                         bot_token=self.bot_manager.telegram_bot_token)
        
        elif command == '/stop_all':
            response = self.bot_manager.stop_all_bots()
            send_telegram(response, chat_id=chat_id,
                         bot_token=self.bot_manager.telegram_bot_token)
        
        elif command == '/balance':
            response = self.bot_manager.get_balance()
            send_telegram(response, chat_id=chat_id,
                         bot_token=self.bot_manager.telegram_bot_token)
        
        elif command == '/positions':
            response = self.bot_manager.get_positions()
            send_telegram(response, chat_id=chat_id,
                         bot_token=self.bot_manager.telegram_bot_token)
        
        else:
            send_telegram(
                "❌ Lệnh không hợp lệ. Các lệnh hỗ trợ:\n\n"
                "<code>/start</code> - Khởi động bot\n"
                "<code>/set_api KEY SECRET</code> - Thiết lập API\n"
                "<code>/set_telegram TOKEN CHAT_ID</code> - Thiết lập Telegram\n"
                "<code>/balance</code> - Xem số dư\n"
                "<code>/positions</code> - Xem vị thế\n"
                "<code>/stop_all</code> - Dừng tất cả bot",
                chat_id=chat_id, reply_markup=create_main_menu(),
                bot_token=self.bot_manager.telegram_bot_token
            )

# ========== MAIN APPLICATION ==========
def main():
    # KHỞI TẠO HỆ THỐNG
    bot_manager = BotManager()
    telegram_handler = TelegramHandler(bot_manager)
    
    # CẤU HÌNH TỪ BIẾN MÔI TRƯỜNG (TUỲ CHỌN)
    api_key = os.getenv('BINANCE_API_KEY', '')
    api_secret = os.getenv('BINANCE_API_SECRET', '')
    telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    
    if api_key and api_secret:
        bot_manager.set_api_keys(api_key, api_secret)
        logger.info("✅ Đã thiết lập API Keys từ biến môi trường")
    
    if telegram_bot_token and telegram_chat_id:
        bot_manager.set_telegram_keys(telegram_bot_token, telegram_chat_id)
        logger.info("✅ Đã thiết lập Telegram từ biến môi trường")
    
    logger.info("🤖 Trading Bot System Started")
    
    # GIỮ CHƯƠNG TRÌNH CHẠY
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🔴 Nhận tín hiệu dừng...")
        bot_manager.stop_all_bots()
        bot_manager.ws_manager.stop()
        logger.info("✅ Hệ thống đã dừng an toàn")

if __name__ == "__main__":
    main()
