# trading_bot_manager_complete.py - BOT MANAGER HOÀN CHỈNH ĐÃ SỬA LỖI
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
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import ssl

# ========== BYPASS SSL VERIFICATION ==========
ssl._create_default_https_context = ssl._create_unverified_context

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

# ========== MENU TELEGRAM ==========
def create_cancel_keyboard():
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_strategy_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Volatility System"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_exit_strategy_keyboard():
    return {
        "keyboard": [
            [{"text": "🎯 Chỉ TP/SL cố định"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_bot_mode_keyboard():
    return {
        "keyboard": [
            [{"text": "🤖 Bot Tĩnh - Coin cụ thể"}, {"text": "🔄 Bot Động - Tự tìm coin"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard(strategy=None):
    try:
        symbols = get_all_usdt_pairs(limit=12)
        if not symbols:
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT"]
    except:
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT"]
    
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

def create_main_menu():
    return {
        "keyboard": [
            [{"text": "📊 Danh sách Bot"}, {"text": "📊 Thống kê"}],
            [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
            [{"text": "💰 Số dư"}, {"text": "📈 Vị thế"}],
            [{"text": "⚙️ Cấu hình"}, {"text": "🎯 Chiến lược"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def create_leverage_keyboard(strategy=None):
    leverages = ["3", "5", "10", "15", "20", "25", "50", "75", "100"]
    
    keyboard = []
    row = []
    for lev in leverages:
        row.append({"text": f"{lev}x"})
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

def create_bot_count_keyboard():
    return {
        "keyboard": [
            [{"text": "1"}, {"text": "2"}, {"text": "3"}],
            [{"text": "5"}, {"text": "10"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_roi_trigger_keyboard():
    return {
        "keyboard": [
            [{"text": "30"}, {"text": "50"}, {"text": "100"}],
            [{"text": "150"}, {"text": "200"}, {"text": "300"}],
            [{"text": "❌ Tắt tính năng"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

# ========== API BINANCE ĐÃ SỬA LỖI ==========
def sign(query, api_secret):
    try:
        return hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"Lỗi tạo chữ ký: {str(e)}")
        return ""

def binance_api_request(url, method='GET', params=None, headers=None):
    max_retries = 2
    for attempt in range(max_retries):
        try:
            if headers is None:
                headers = {}
            
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            
            if method.upper() == 'GET':
                if params:
                    query = urllib.parse.urlencode(params)
                    url = f"{url}?{query}"
                req = urllib.request.Request(url, headers=headers)
            else:
                data = urllib.parse.urlencode(params).encode() if params else None
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    return json.loads(response.read().decode())
                else:
                    error_content = response.read().decode()
                    logger.error(f"Lỗi API ({response.status}): {error_content}")
                    if response.status in [400, 401]:
                        return None
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
                    
        except urllib.error.HTTPError as e:
            error_content = e.read().decode()
            if e.code in [400, 451]:
                logger.error(f"Lỗi {e.code}: {error_content}")
                return None
            else:
                logger.error(f"Lỗi HTTP ({e.code}): {e.reason}")
            
            if e.code == 401:
                return None
            if e.code == 429:
                time.sleep(2 ** attempt)
            elif e.code >= 500:
                time.sleep(1)
            continue
                
        except Exception as e:
            logger.error(f"Lỗi kết nối API (lần {attempt + 1}): {str(e)}")
            time.sleep(1)
    
    logger.error(f"Không thể thực hiện yêu cầu API sau {max_retries} lần thử")
    return None

def get_all_usdt_pairs(limit=300):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            return []
        
        usdt_pairs = []
        for symbol_info in data.get('symbols', []):
            symbol = symbol_info.get('symbol', '')
            if symbol.endswith('USDT') and symbol_info.get('status') == 'TRADING':
                usdt_pairs.append(symbol)
        
        return usdt_pairs[:limit] if limit else usdt_pairs
        
    except Exception as e:
        logger.error(f"Lỗi lấy danh sách coin: {str(e)}")
        return []

def get_max_leverage(symbol, api_key, api_secret):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            return 0
        
        for s in data['symbols']:
            if s['symbol'] == symbol.upper():
                for f in s['filters']:
                    if f['filterType'] == 'LEVERAGE' and 'maxLeverage' in f:
                        return int(f['maxLeverage'])
                break
        return 0
    except Exception as e:
        logger.error(f"Lỗi lấy đòn bẩy {symbol}: {str(e)}")
        return 0

def get_step_size(symbol, api_key, api_secret):
    if not symbol:
        return 0.001
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
    if not symbol:
        return False
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
        return response is not None and 'leverage' in response
    except Exception as e:
        logger.error(f"Lỗi set đòn bẩy: {str(e)}")
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
    if not symbol:
        return None
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
    if not symbol:
        return False
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
    if not symbol:
        return 0
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            return float(data['price'])
        return 0
    except Exception as e:
        logger.error(f"Lỗi lấy giá {symbol}: {str(e)}")
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
        return positions if positions else []
    except Exception as e:
        logger.error(f"Lỗi lấy vị thế: {str(e)}")
    return []

def get_1h_volatility(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': symbol.upper(),
            'interval': '1h',
            'limit': 2
        }
        data = binance_api_request(url, params=params)
        if not data or len(data) < 2:
            return 0
            
        prev_candle = data[0]
        current_candle = data[1]
        
        prev_close = float(prev_candle[4])
        current_close = float(current_candle[4])
        
        volatility = ((current_close - prev_close) / prev_close) * 100
        return volatility
        
    except Exception as e:
        logger.error(f"Lỗi tính biến động {symbol}: {str(e)}")
        return 0

# ========== COIN MANAGER MỚI ==========
class CoinManager:
    def __init__(self):
        self.active_coins = set()
        self.failed_coins = {}
        self._lock = threading.Lock()
    
    def register_coin(self, symbol):
        if not symbol:
            return
        with self._lock:
            self.active_coins.add(symbol.upper())
    
    def unregister_coin(self, symbol):
        if not symbol:
            return
        with self._lock:
            self.active_coins.discard(symbol.upper())
    
    def is_coin_active(self, symbol):
        if not symbol:
            return False
        with self._lock:
            return symbol.upper() in self.active_coins
    
    def get_active_coins(self):
        with self._lock:
            return list(self.active_coins)
    
    def add_failed_coin(self, symbol, duration=600):
        if not symbol:
            return
        with self._lock:
            self.failed_coins[symbol.upper()] = time.time() + duration
    
    def is_coin_failed(self, symbol):
        if not symbol:
            return True
        with self._lock:
            if symbol.upper() in self.failed_coins:
                if time.time() < self.failed_coins[symbol.upper()]:
                    return True
                else:
                    del self.failed_coins[symbol.upper()]
            return False
    
    def cleanup_expired_failed_coins(self):
        current_time = time.time()
        with self._lock:
            expired = [symbol for symbol, expire_time in self.failed_coins.items() if current_time > expire_time]
            for symbol in expired:
                del self.failed_coins[symbol]

# ========== VOLATILITY COIN FINDER MỚI ==========
class VolatilityCoinFinder:
    def __init__(self, api_key, api_secret, leverage):
        self.api_key = api_key
        self.api_secret = api_secret
        self.leverage = leverage
        self.eligible_coins = []
        self.last_update_time = 0
        self.update_interval = 300
        self._lock = threading.Lock()
        
    def update_eligible_coins(self):
        try:
            current_time = time.time()
            if current_time - self.last_update_time < self.update_interval and self.eligible_coins:
                return self.eligible_coins
                
            logger.info(f"🔄 Đang cập nhật danh sách coin với đòn bẩy {self.leverage}x...")
            
            all_symbols = get_all_usdt_pairs(limit=300)
            if not all_symbols:
                return []
            
            eligible = []
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_symbol = {
                    executor.submit(get_max_leverage, symbol, self.api_key, self.api_secret): symbol 
                    for symbol in all_symbols
                }
                
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        max_lev = future.result()
                        if max_lev >= self.leverage:
                            eligible.append(symbol)
                    except Exception:
                        pass
                    time.sleep(0.1)
                    
            with self._lock:
                self.eligible_coins = eligible
                self.last_update_time = current_time
                
            logger.info(f"✅ Đã cập nhật {len(eligible)} coin với đòn bẩy >= {self.leverage}x")
            return eligible
            
        except Exception as e:
            logger.error(f"❌ Lỗi cập nhật danh sách coin: {str(e)}")
            return []
    
    def find_most_volatile_coin(self, coin_manager, excluded_coins=None):
        try:
            eligible_coins = self.update_eligible_coins()
            if not eligible_coins:
                return None, None
                
            coin_manager.cleanup_expired_failed_coins()
                
            filtered_coins = []
            for coin in eligible_coins:
                if coin_manager.is_coin_active(coin):
                    continue
                if coin_manager.is_coin_failed(coin):
                    continue
                if excluded_coins and coin in excluded_coins:
                    continue
                filtered_coins.append(coin)
                
            if not filtered_coins:
                return None, None
                
            volatilities = []
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_coin = {
                    executor.submit(get_1h_volatility, coin): coin 
                    for coin in filtered_coins[:20]
                }
                
                for future in as_completed(future_to_coin):
                    coin = future_to_coin[future]
                    try:
                        volatility = future.result()
                        if volatility != 0:
                            volatilities.append((coin, abs(volatility), volatility))
                        time.sleep(0.3)
                    except Exception:
                        continue
            
            if not volatilities:
                return None, None
                
            volatilities.sort(key=lambda x: x[1], reverse=True)
            best_coin, best_volatility, raw_volatility = volatilities[0]
            
            direction = "SELL" if raw_volatility > 0 else "BUY"
            
            logger.info(f"🎯 Coin biến động nhất: {best_coin} - Biến động: {raw_volatility:.2f}% - Hướng: {direction}")
            return best_coin, direction
            
        except Exception as e:
            logger.error(f"❌ Lỗi tìm coin biến động: {str(e)}")
            return None, None

# ========== WEBSOCKET MANAGER ==========
class WebSocketManager:
    def __init__(self):
        self.connections = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
    def add_symbol(self, symbol, callback):
        if not symbol:
            return
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
                logger.error(f"Lỗi WebSocket {symbol}: {str(e)}")
                
        def on_error(ws, error):
            logger.error(f"Lỗi WebSocket {symbol}: {str(error)}")
            
        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket đóng {symbol}")
            
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
        
    def remove_symbol(self, symbol):
        if not symbol:
            return
        symbol = symbol.upper()
        with self._lock:
            if symbol in self.connections:
                try:
                    self.connections[symbol]['ws'].close()
                except:
                    pass
                del self.connections[symbol]
                
    def stop(self):
        self._stop_event.set()
        for symbol in list(self.connections.keys()):
            self.remove_symbol(symbol)

# ========== BASE BOT ĐÃ SỬA ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, strategy_name, bot_id=None):
        
        self.symbol = symbol.upper() if symbol else None
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.roi_trigger = roi_trigger
        self.ws_manager = ws_manager
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.strategy_name = strategy_name
        self.bot_id = bot_id or f"{strategy_name}_{int(time.time())}_{random.randint(1000, 9999)}"
        
        self.status = "searching"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.current_price = 0
        self.position_open = False
        self._stop = False
        
        self.last_trade_time = 0
        self.last_close_time = 0
        
        self.coin_manager = CoinManager()
        self.coin_finder = VolatilityCoinFinder(api_key, api_secret, lev)
        
        self.next_side = None
        self.last_find_time = 0
        self.find_interval = 30
        
        self.check_position_status()
        if self.symbol:
            self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        if self.symbol:
            self.log(f"🟢 Bot {strategy_name} khởi động | {self.symbol} | ĐB: {lev}x | Vốn: {percent}%")
        else:
            self.log(f"🟢 Bot {strategy_name} khởi động | Đang tìm coin... | ĐB: {lev}x | Vốn: {percent}%")

    def check_position_status(self):
        if not self.symbol:
            return
            
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
                        return
                    else:
                        self._reset_position()
                        return
                        
            self._reset_position()
                
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")

    def _reset_position(self):
        self.position_open = False
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0

    def find_and_set_coin(self):
        try:
            current_time = time.time()
            if current_time - self.last_find_time < self.find_interval:
                return False
            
            self.last_find_time = current_time
            
            active_coins = self.coin_manager.get_active_coins()
            
            new_symbol, new_direction = self.coin_finder.find_most_volatile_coin(
                coin_manager=self.coin_manager,
                excluded_coins=active_coins
            )
            
            if new_symbol and new_direction:
                max_lev = get_max_leverage(new_symbol, self.api_key, self.api_secret)
                if max_lev >= self.lev:
                    self.coin_manager.register_coin(new_symbol)
                    
                    if self.symbol:
                        self.ws_manager.remove_symbol(self.symbol)
                        self.coin_manager.unregister_coin(self.symbol)
                    
                    self.symbol = new_symbol
                    self.ws_manager.add_symbol(new_symbol, self._handle_price_update)
                    self.status = "waiting"
                    self.next_side = new_direction
                    
                    self.log(f"🎯 Đã tìm thấy coin: {new_symbol} - Hướng: {new_direction}")
                    return True
                else:
                    self.coin_manager.add_failed_coin(new_symbol, duration=600)
            
            return False
            
        except Exception as e:
            self.log(f"❌ Lỗi tìm coin: {str(e)}")
            return False

    def verify_leverage_and_switch(self):
        if not self.symbol:
            return True
            
        try:
            current_leverage = get_max_leverage(self.symbol, self.api_key, self.api_secret)
            if current_leverage < self.lev:
                self.coin_manager.add_failed_coin(self.symbol, duration=600)
                return False

            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.coin_manager.add_failed_coin(self.symbol, duration=600)
                return False
                
            return True
            
        except Exception as e:
            self.coin_manager.add_failed_coin(self.symbol, duration=600)
            return False

    def _run(self):
        while not self._stop:
            try:
                current_time = time.time()
                
                if current_time - getattr(self, '_last_leverage_check', 0) > 60:
                    if not self.verify_leverage_and_switch():
                        if self.symbol:
                            self._cleanup_symbol()
                        time.sleep(1)
                        continue
                    self._last_leverage_check = current_time
                
                if not self.position_open:
                    if not self.symbol:
                        if self.find_and_set_coin():
                            self.log("✅ Đã tìm thấy coin mới")
                        time.sleep(2)
                        continue
                    
                    if self.symbol and self.next_side:
                        if current_time - self.last_trade_time > 3 and current_time - self.last_close_time > 3:
                            if self.open_position(self.next_side):
                                self.last_trade_time = current_time
                                self.next_side = None
                            else:
                                time.sleep(1)
                        else:
                            time.sleep(1)
                    else:
                        time.sleep(1)
                
                self.check_tp_sl()
                time.sleep(1)
            
            except Exception as e:
                self.log(f"❌ Lỗi hệ thống: {str(e)}")
                time.sleep(1)

    def _handle_price_update(self, price):
        self.current_price = price

    def stop(self):
        self._stop = True
        if self.symbol:
            self.ws_manager.remove_symbol(self.symbol)
        if self.symbol:
            self.coin_manager.unregister_coin(self.symbol)
        self.log(f"🔴 Bot dừng")

    def open_position(self, side):
        if side not in ["BUY", "SELL"]:
            self._cleanup_symbol()
            return False
            
        try:
            self.check_position_status()
            
            if self.position_open:
                return False
    
            if not self.verify_leverage_and_switch():
                self._cleanup_symbol()
                return False
    
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                return False
    
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                self._cleanup_symbol()
                return False
    
            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            usd_amount = balance * (self.percent / 100)
            qty = (usd_amount * self.lev) / current_price
            
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
    
            if qty <= 0:
                self._cleanup_symbol()
                return False
    
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            time.sleep(0.2)
            
            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty >= 0:
                    self.entry = avg_price
                    self.side = side
                    self.qty = executed_qty if side == "BUY" else -executed_qty
                    self.position_open = True
                    self.status = "open"
                    
                    message = (
                        f"✅ <b>ĐÃ MỞ VỊ THẾ {self.symbol}</b>\n"
                        f"🤖 Chiến lược: {self.strategy_name}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {self.entry:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    
                    self.log(message)
                    return True
                else:
                    self._cleanup_symbol()
                    return False
            else:
                self._cleanup_symbol()
                return False
                        
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            self._cleanup_symbol()
            return False
    
    def _cleanup_symbol(self):
        if self.symbol:
            try:
                self.ws_manager.remove_symbol(self.symbol)
                self.coin_manager.unregister_coin(self.symbol)
            except:
                pass
            
            self.symbol = None
        
        self.status = "searching"
        self.position_open = False
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.next_side = None

    def close_position(self, reason=""):
        try:
            self.check_position_status()
            
            if not self.position_open or abs(self.qty) <= 0:
                return False

            close_side = "SELL" if self.side == "BUY" else "BUY"
            close_qty = abs(self.qty)
            
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            time.sleep(0.5)
            
            result = place_order(self.symbol, close_side, close_qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                current_price = get_current_price(self.symbol)
                pnl = 0
                if self.entry > 0:
                    if self.side == "BUY":
                        pnl = (current_price - self.entry) * abs(self.qty)
                    else:
                        pnl = (self.entry - current_price) * abs(self.qty)
                
                message = (
                    f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ {self.symbol}</b>\n"
                    f"📌 Lý do: {reason}\n"
                    f"💰 PnL: {pnl:.2f} USDT"
                )
                self.log(message)
                
                self.next_side = "BUY" if self.side == "SELL" else "SELL"
                self._reset_position()
                self.last_close_time = time.time()
                
                return True
            else:
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False

    def check_tp_sl(self):
        if not self.symbol or not self.position_open or self.entry <= 0:
            return

        current_price = get_current_price(self.symbol)
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

        if self.tp is not None and roi >= self.tp:
            self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
        elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
            self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")

    def log(self, message):
        logger.info(f"[{self.bot_id}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>{self.bot_id}</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

# ========== VOLATILITY BOT ==========
class VolatilityBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, bot_id=None):
        super().__init__(symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret,
                        telegram_bot_token, telegram_chat_id, "Volatility-Reversal", bot_id=bot_id)

# ========== BOT MANAGER MỚI HOÀN TOÀN ==========
class BotManager:
    def __init__(self, api_key=None, api_secret=None, telegram_bot_token=None, telegram_chat_id=None):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.user_states = {}
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT BIẾN ĐỘNG ĐÃ KHỞI ĐỘNG")
            
            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()
            
            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)

    def _verify_api_connection(self):
        try:
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                self.log("❌ LỖI: Không thể kết nối Binance API")
                return False
            else:
                self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")
                return True
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra kết nối: {str(e)}")
            return False

    def get_position_summary(self):
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            binance_positions = []
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry_price = float(pos.get('entryPrice', 0))
                    side = "LONG" if position_amt > 0 else "SHORT"
                    pnl = float(pos.get('unRealizedProfit', 0))
                    
                    binance_positions.append({
                        'symbol': symbol,
                        'side': side,
                        'size': abs(position_amt),
                        'entry': entry_price,
                        'pnl': pnl
                    })
        
            bot_details = []
            searching_bots = 0
            trading_bots = 0
            
            for bot_id, bot in self.bots.items():
                bot_info = {
                    'bot_id': bot_id,
                    'symbol': bot.symbol or 'Đang tìm...',
                    'status': bot.status,
                    'side': bot.side,
                    'leverage': bot.lev,
                    'percent': bot.percent
                }
                bot_details.append(bot_info)
                
                if bot.status == "searching":
                    searching_bots += 1
                elif bot.status == "open":
                    trading_bots += 1
            
            summary = "📊 **THỐNG KÊ HỆ THỐNG**\n\n"
            
            balance = get_balance(self.api_key, self.api_secret)
            if balance is not None:
                summary += f"💰 **SỐ DƯ**: {balance:.2f} USDT\n\n"
            
            summary += f"🤖 **BOT HỆ THỐNG**: {len(self.bots)} bots\n"
            summary += f"   🔍 Đang tìm coin: {searching_bots}\n"
            summary += f"   📈 Đang trade: {trading_bots}\n\n"
            
            if bot_details:
                summary += "📋 **CHI TIẾT BOT**:\n"
                for bot in bot_details[:6]:
                    symbol_info = bot['symbol'] if bot['symbol'] != 'Đang tìm...' else '🔍 Đang tìm'
                    status = "🔍 Tìm coin" if bot['status'] == "searching" else "🟢 Đang trade"
                    
                    summary += f"   🔹 {bot['bot_id'][:12]}...\n"
                    summary += f"      📊 {symbol_info} | {status}\n"
                    summary += f"      💰 ĐB: {bot['leverage']}x | Vốn: {bot['percent']}%\n\n"
            
            return summary
                    
        except Exception as e:
            return f"❌ Lỗi thống kê: {str(e)}"

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>SYSTEM</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = (
            "🤖 <b>BOT GIAO DỊCH FUTURES - PHIÊN BẢN BIẾN ĐỘNG</b>\n\n"
            "🎯 <b>CHIẾN THUẬT ĐẢO CHIỀU BIẾN ĐỘNG</b>\n\n"
            "📊 <b>Nguyên tắc hoạt động:</b>\n"
            "• Tự động lọc coin có đòn bẩy phù hợp\n"
            "• Phân tích biến động giá 1 giờ\n"
            "• Chọn coin biến động mạnh nhất\n"
            "• ĐI NGƯỢC HƯỚNG biến động\n\n"
            "🔄 <b>Cơ chế thông minh:</b>\n"
            "• Tự động tìm coin mới khi có lỗi\n"
            "• Tránh trùng lặp giữa các bot\n"
            "• Quản lý rủi ro với TP/SL"
        )
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bot(self, symbol, lev, percent, tp, sl, roi_trigger, strategy_type, bot_count=1, **kwargs):
        if sl == 0:
            sl = None
            
        if not self.api_key or not self.api_secret:
            return False
        
        if not self._verify_api_connection():
            return False
        
        bot_mode = kwargs.get('bot_mode', 'static')
        created_count = 0
        
        for i in range(bot_count):
            try:
                if bot_mode == 'static' and symbol:
                    bot_id = f"{symbol}_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot = VolatilityBot(symbol, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                                      self.api_key, self.api_secret, self.telegram_bot_token, 
                                      self.telegram_chat_id, bot_id=bot_id)
                    
                else:
                    bot_id = f"DYNAMIC_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot = VolatilityBot(None, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                                      self.api_key, self.api_secret, self.telegram_bot_token,
                                      self.telegram_chat_id, bot_id=bot_id)
                
                self.bots[bot_id] = bot
                created_count += 1
                
            except Exception as e:
                continue
        
        if created_count > 0:
            roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else ""
            
            success_msg = (
                f"✅ <b>ĐÃ TẠO {created_count} BOT BIẾN ĐỘNG</b>\n\n"
                f"💰 Đòn bẩy: {lev}x\n"
                f"📈 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl if sl is not None else 'Tắt'}%{roi_info}"
            )
            
            if bot_mode == 'static' and symbol:
                success_msg += f"\n🔗 Coin: {symbol}"
            else:
                success_msg += f"\n🔗 Coin: Tự động tìm kiếm"
            
            self.log(success_msg)
            return True
        else:
            return False

    def stop_bot(self, bot_id):
        bot = self.bots.get(bot_id)
        if bot:
            bot.stop()
            del self.bots[bot_id]
            self.log(f"⛔ Đã dừng bot {bot_id}")
            return True
        return False

    def stop_all(self):
        self.log("⛔ Đang dừng tất cả bot...")
        for bot_id in list(self.bots.keys()):
            self.stop_bot(bot_id)
        self.ws_manager.stop()
        self.running = False
        self.log("🔴 Hệ thống đã dừng")

    def _telegram_listener(self):
        last_update_id = 0
        
        while self.running and self.telegram_bot_token:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getUpdates?offset={last_update_id+1}&timeout=30"
                response = requests.get(url, timeout=35)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        for update in data['result']:
                            update_id = update['update_id']
                            message = update.get('message', {})
                            chat_id = str(message.get('chat', {}).get('id'))
                            text = message.get('text', '').strip()
                            
                            if chat_id != self.telegram_chat_id:
                                continue
                            
                            if update_id > last_update_id:
                                last_update_id = update_id
                            
                            self._handle_telegram_message(chat_id, text)
                time.sleep(10)
                
            except Exception as e:
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        if current_step == 'waiting_bot_count':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    bot_count = int(text)
                    if 1 <= bot_count <= 10:
                        user_state['bot_count'] = bot_count
                        user_state['step'] = 'waiting_bot_mode'
                        
                        send_telegram(
                            f"🤖 Số lượng bot: {bot_count}\n\nChọn chế độ bot:",
                            chat_id,
                            create_bot_mode_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Số lượng bot phải từ 1 đến 10:",
                                    chat_id, create_bot_count_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_bot_mode':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text in ["🤖 Bot Tĩnh - Coin cụ thể", "🔄 Bot Động - Tự tìm coin"]:
                user_state['bot_mode'] = 'static' if text == "🤖 Bot Tĩnh - Coin cụ thể" else 'dynamic'
                user_state['step'] = 'waiting_strategy'
                send_telegram(
                    "Chọn chiến lược:",
                    chat_id,
                    create_strategy_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

        elif current_step == 'waiting_strategy':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text == "📊 Volatility System":
                user_state['strategy'] = "Volatility-Reversal"
                user_state['step'] = 'waiting_leverage'
                
                send_telegram(
                    "Chọn đòn bẩy:",
                    chat_id,
                    create_leverage_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    if text.endswith('x'):
                        lev_text = text[:-1]
                    else:
                        lev_text = text

                    leverage = int(lev_text)
                    if 1 <= leverage <= 100:
                        user_state['leverage'] = leverage
                        user_state['step'] = 'waiting_percent'
                        
                        send_telegram(
                            f"💰 Đòn bẩy: {leverage}x\n\nChọn % số dư:",
                            chat_id,
                            create_percent_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Đòn bẩy phải từ 1 đến 100:",
                                    chat_id, create_leverage_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_leverage_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    percent = float(text)
                    if 0 < percent <= 100:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        
                        send_telegram(
                            f"📊 % Số dư: {percent}%\n\nChọn Take Profit (%):",
                            chat_id,
                            create_tp_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ % số dư phải từ 0.1 đến 100:",
                                    chat_id, create_percent_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_percent_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_tp':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    tp = float(text)
                    if tp > 0:
                        user_state['tp'] = tp
                        user_state['step'] = 'waiting_sl'
                        
                        send_telegram(
                            f"🎯 Take Profit: {tp}%\n\nChọn Stop Loss (%):",
                            chat_id,
                            create_sl_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Take Profit phải lớn hơn 0:",
                                    chat_id, create_tp_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_tp_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    sl = float(text)
                    if sl >= 0:
                        user_state['sl'] = sl
                        
                        strategy = user_state.get('strategy')
                        bot_mode = user_state.get('bot_mode', 'static')
                        leverage = user_state.get('leverage')
                        percent = user_state.get('percent')
                        tp = user_state.get('tp')
                        sl = user_state.get('sl')
                        symbol = user_state.get('symbol')
                        bot_count = user_state.get('bot_count', 1)
                        
                        success = self.add_bot(
                            symbol=symbol,
                            lev=leverage,
                            percent=percent,
                            tp=tp,
                            sl=sl,
                            roi_trigger=None,
                            strategy_type=strategy,
                            bot_mode=bot_mode,
                            bot_count=bot_count
                        )
                        
                        if success:
                            send_telegram("✅ Đã tạo bot thành công!", chat_id, create_main_menu(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                        else:
                            send_telegram("❌ Có lỗi khi tạo bot", chat_id, create_main_menu(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                        
                        self.user_states[chat_id] = {}
                        
                    else:
                        send_telegram("⚠️ Stop Loss phải >= 0:",
                                    chat_id, create_sl_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_bot_count'}
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ LỖI KẾT NỐI BINANCE", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"💰 Số dư: {balance:.2f} USDT\n\nChọn số lượng bot:",
                chat_id,
                create_bot_count_keyboard(),
                self.telegram_bot_token, self.telegram_chat_id
            )
        
        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                message = "🤖 <b>DANH SÁCH BOT ĐANG CHẠY</b>\n\n"
                
                for bot_id, bot in self.bots.items():
                    status = "🔍 Đang tìm coin" if bot.status == "searching" else "🟢 Đang trade"
                    symbol_info = bot.symbol if bot.symbol else "Đang tìm..."
                    message += f"🔹 {bot_id}\n"
                    message += f"   📊 {symbol_info} | {status}\n"
                    message += f"   💰 ĐB: {bot.lev}x | Vốn: {bot.percent}%\n\n"
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📊 Thống kê":
            summary = self.get_position_summary()
            send_telegram(summary, chat_id,
                         bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                keyboard = []
                for bot_id in self.bots.keys():
                    keyboard.append([{"text": f"⛔ {bot_id}"}])
                
                keyboard.append([{"text": "⛔ DỪNG TẤT CẢ"}])
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                
                send_telegram(
                    "Chọn bot để dừng:", 
                    chat_id, 
                    {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True},
                    self.telegram_bot_token, self.telegram_chat_id
                )
        
        elif text.startswith("⛔ "):
            bot_id = text.replace("⛔ ", "").strip()
            if bot_id == "DỪNG TẤT CẢ":
                self.stop_all()
                send_telegram("⛔ Đã dừng tất cả bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif self.stop_bot(bot_id):
                send_telegram(f"⛔ Đã dừng bot {bot_id}", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                send_telegram(f"⚠️ Không tìm thấy bot {bot_id}", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
        
        elif text == "💰 Số dư":
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ Lỗi kết nối Binance", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                send_telegram(f"💰 Số dư: {balance:.2f} USDT", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📈 Vị thế":
            positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            if not positions:
                send_telegram("📭 Không có vị thế nào", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
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
                            f"💰 PnL: {pnl:.2f} USDT\n\n"
                        )
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>CHIẾN THUẬT ĐẢO CHIỀU BIẾN ĐỘNG</b>\n\n"
                "📊 Tự động lọc coin có đòn bẩy phù hợp\n"
                "📈 Phân tích biến động giá 1 giờ\n"
                "🔄 Đi ngược hướng biến động\n"
                "⚡ Tự động tìm coin mới khi có lỗi"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            
            searching_bots = sum(1 for bot in self.bots.values() if bot.status == "searching")
            trading_bots = sum(1 for bot in self.bots.values() if bot.status == "open")
            
            config_info = (
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Tổng số bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots}\n"
                f"📊 Đang trade: {trading_bots}"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)
