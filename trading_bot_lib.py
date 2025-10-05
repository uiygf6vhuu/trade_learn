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

# ========== MENU TELEGRAM ==========
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
    """Bàn phím chọn coin"""
    try:
        # Lấy danh sách coin từ Binance thực tế
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

def create_leverage_keyboard(strategy=None):
    """Bàn phím chọn đòn bẩy"""
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
    """Bàn phím chọn % số dư"""
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
    """Bàn phím chọn Take Profit"""
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
    """Bàn phím chọn Stop Loss"""
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
    """Bàn phím chọn ngưỡng biến động cho Reverse 24h"""
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
    """Bàn phím chọn biến động cho Scalping"""
    return {
        "keyboard": [
            [{"text": "2"}, {"text": "3"}, {"text": "5"}],
            [{"text": "7"}, {"text": "10"}, {"text": "15"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_grid_levels_keyboard():
    """Bàn phím chọn số lệnh grid cho Safe Grid"""
    return {
        "keyboard": [
            [{"text": "3"}, {"text": "5"}, {"text": "7"}],
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
                cls._instance.managed_coins = {}  # Format: {symbol: {"strategy": strategy, "bot_id": bot_id, "config_key": config_key}}
                cls._instance.position_coins = set()
        return cls._instance
    
    def register_coin(self, symbol, bot_id, strategy, config_key=None):
        with self._lock:
            if symbol not in self.managed_coins:
                self.managed_coins[symbol] = {
                    "strategy": strategy, 
                    "bot_id": bot_id,
                    "config_key": config_key
                }
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

    # THÊM: Kiểm tra coin đã có bot CÙNG CẤU HÌNH chưa
    def has_same_config_bot(self, symbol, config_key):
        with self._lock:
            if symbol in self.managed_coins:
                existing_config = self.managed_coins[symbol].get("config_key")
                return existing_config == config_key
            return False
    
    # THÊM: Đếm số bot theo cấu hình
    def count_bots_by_config(self, config_key):
        with self._lock:
            count = 0
            for coin_info in self.managed_coins.values():
                if coin_info.get("config_key") == config_key:
                    count += 1
            return count
    
    def get_managed_coins(self):
        with self._lock:
            return self.managed_coins.copy()

# ========== HÀM TÌM COIN TOÀN BINANCE ==========
def get_all_usdt_pairs(limit=100):
    """Lấy toàn bộ coin USDT từ Binance, không dùng danh sách cố định"""
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            logger.warning("Không lấy được dữ liệu từ Binance, trả về danh sách rỗng")
            return []
        
        usdt_pairs = []
        for symbol_info in data.get('symbols', []):
            symbol = symbol_info.get('symbol', '')
            if symbol.endswith('USDT') and symbol_info.get('status') == 'TRADING':
                usdt_pairs.append(symbol)
        
        logger.info(f"✅ Lấy được {len(usdt_pairs)} coin USDT từ Binance")
        return usdt_pairs[:limit] if limit else usdt_pairs
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy danh sách coin từ Binance: {str(e)}")
        return []

def get_top_volatile_symbols(limit=10, threshold=20):
    """Lấy danh sách coin có biến động 24h cao nhất từ toàn bộ Binance"""
    try:
        all_symbols = get_all_usdt_pairs(limit=200)  # Lấy nhiều hơn để lọc
        if not all_symbols:
            logger.warning("Không lấy được coin từ Binance")
            return []
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return []
        
        # Tạo dict để tra cứu nhanh
        ticker_dict = {ticker['symbol']: ticker for ticker in data if 'symbol' in ticker}
        
        volatile_pairs = []
        for symbol in all_symbols:
            if symbol in ticker_dict:
                ticker = ticker_dict[symbol]
                try:
                    change = float(ticker.get('priceChangePercent', 0))
                    volume = float(ticker.get('quoteVolume', 0))
                    
                    # Lọc theo ngưỡng biến động và volume
                    if abs(change) >= threshold and volume > 1000000:  # Volume > 1M USDT
                        volatile_pairs.append((symbol, abs(change)))
                except (ValueError, TypeError):
                    continue
        
        # Sắp xếp theo biến động giảm dần
        volatile_pairs.sort(key=lambda x: x[1], reverse=True)
        
        top_symbols = [pair[0] for pair in volatile_pairs[:limit]]
        logger.info(f"✅ Tìm thấy {len(top_symbols)} coin biến động ≥{threshold}%")
        return top_symbols
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy danh sách coin biến động: {str(e)}")
        return []

def get_qualified_symbols(api_key, api_secret, strategy_type, leverage, threshold=None, volatility=None, grid_levels=None, max_candidates=20, final_limit=2, strategy_key=None):
    """Tìm coin phù hợp từ TOÀN BỘ Binance - PHÂN BIỆT THEO CẤU HÌNH"""
    try:
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE")
            return []
        
        coin_manager = CoinManager()
        
        # LẤY TOÀN BỘ COIN TỪ BINANCE
        all_symbols = get_all_usdt_pairs(limit=200)
        if not all_symbols:
            logger.error("❌ Không lấy được danh sách coin từ Binance")
            return []
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return []
        
        # Tạo dict để tra cứu nhanh
        ticker_dict = {ticker['symbol']: ticker for ticker in data if 'symbol' in ticker}
        
        qualified_symbols = []
        
        for symbol in all_symbols:
            if symbol not in ticker_dict:
                continue
                
            # Bỏ qua BTC và ETH để tránh rủi ro cao
            if symbol in ['BTCUSDT', 'ETHUSDT']:
                continue
            
            # QUAN TRỌNG: Kiểm tra coin đã có bot CÙNG CẤU HÌNH chưa
            if strategy_key and coin_manager.has_same_config_bot(symbol, strategy_key):
                continue
            
            ticker = ticker_dict[symbol]
            
            try:
                price_change = float(ticker.get('priceChangePercent', 0))
                abs_price_change = abs(price_change)
                volume = float(ticker.get('quoteVolume', 0))
                high_price = float(ticker.get('highPrice', 0))
                low_price = float(ticker.get('lowPrice', 0))
                
                if low_price > 0:
                    price_range = ((high_price - low_price) / low_price) * 100
                else:
                    price_range = 0
                
                # KIỂM TRA ĐIỀU KIỆN CHO TỪNG CHIẾN LƯỢC
                if strategy_type == "Reverse 24h":
                    if abs_price_change >= threshold and volume > 3000000:
                        score = abs_price_change * (volume / 1000000)
                        qualified_symbols.append((symbol, score, price_change))
                elif strategy_type == "Scalping":
                    if abs_price_change >= volatility and volume > 5000000 and price_range >= 1.5:
                        qualified_symbols.append((symbol, price_range))
                elif strategy_type == "Safe Grid":
                    if 1.0 <= abs_price_change <= 5.0 and volume > 1000000 and price_range <= 4.0:
                        qualified_symbols.append((symbol, -abs(price_change - 3.0)))
                elif strategy_type == "Trend Following":
                    if 2.0 <= abs_price_change <= 10.0 and volume > 3000000 and price_range >= 1.0:
                        qualified_symbols.append((symbol, abs_price_change))
                        
            except (ValueError, TypeError) as e:
                continue
        
        # Sắp xếp theo điểm số
        if strategy_type == "Reverse 24h":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Scalping":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Safe Grid":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Trend Following":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        
        # KIỂM TRA ĐÒN BẨY VÀ STEP SIZE
        final_symbols = []
        for item in qualified_symbols[:max_candidates]:
            if len(final_symbols) >= final_limit:
                break
                
            if strategy_type == "Reverse 24h":
                symbol, score, original_change = item
            else:
                symbol, score = item
                
            try:
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                step_size = get_step_size(symbol, api_key, api_secret)
                
                if leverage_success and step_size > 0:
                    final_symbols.append(symbol)
                    if strategy_type == "Reverse 24h":
                        logger.info(f"✅ {symbol}: phù hợp {strategy_type} (Biến động: {original_change:.2f}%, Điểm: {score:.2f}, Config: {strategy_key})")
                    else:
                        logger.info(f"✅ {symbol}: phù hợp {strategy_type} (Score: {score:.2f}, Config: {strategy_key})")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ Lỗi kiểm tra {symbol}: {str(e)}")
                continue
        
        if not final_symbols:
            logger.warning(f"⚠️ {strategy_type}: không tìm thấy coin phù hợp cho config {strategy_key}")
        
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
            if change is None:
                return 0.0
            return float(change) if change is not None else 0.0
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
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, strategy_name, config_key=None):
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
        self.config_key = config_key  # LƯU CONFIG KEY
        
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []
        self.position_open = False
        self._stop = False
        
        # THÊM: Biến theo dõi thời gian cho vòng lặp vô hạn
        self.last_trade_time = 0
        self.last_close_time = 0
        self.last_position_check = 0
        self.last_error_log_time = 0
        
        # THÊM: Cooldown period (giây) - thời gian chờ sau khi đóng lệnh
        self.cooldown_period = 300  # 5 phút
        
        # THÊM: Khoảng thời gian kiểm tra vị thế
        self.position_check_interval = 30  # 30 giây
        
        # BẢO VỆ CHỐNG LẶP ĐÓNG LỆNH
        self._close_attempted = False
        self._last_close_attempt = 0
        
        # THÊM: Cờ đánh dấu cần xóa bot
        self.should_be_removed = False
        
        self.coin_manager = CoinManager()
        if symbol:
            success = self.coin_manager.register_coin(self.symbol, f"{strategy_name}_{id(self)}", strategy_name, config_key)
            if not success:
                self.log(f"⚠️ Cảnh báo: {self.symbol} đã được quản lý bởi bot khác")
        
        self.check_position_status()
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot {strategy_name} khởi động cho {self.symbol} | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}% | Config: {config_key}")

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
        """VÒNG LẶP VÔ HẠN - Bot chạy liên tục tìm kiếm cơ hội"""
        while not self._stop:
            try:
                current_time = time.time()
                
                # Kiểm tra trạng thái vị thế định kỳ
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                # CHỈ TÌM TÍN HIỆU KHI KHÔNG CÓ VỊ THẾ ĐANG MỞ
                if not self.position_open:
                    signal = self.get_signal()
                    
                    # KIỂM TRA ĐIỀU KIỆN VÀO LỆNH
                    if (signal and 
                        current_time - self.last_trade_time > 60 and  # Tránh vào lệnh quá nhanh
                        current_time - self.last_close_time > self.cooldown_period):  # Chờ sau khi đóng lệnh
                        
                        self.log(f"🎯 Nhận tín hiệu {signal}, đang mở lệnh...")
                        if self.open_position(signal):
                            self.last_trade_time = current_time
                        else:
                            # Nếu mở lệnh thất bại, đợi 30s trước khi thử lại
                            time.sleep(30)
                
                # KIỂM TRA TP/SL KHI CÓ VỊ THẾ
                if self.position_open and not self._close_attempted:
                    self.check_tp_sl()
                    
                time.sleep(1)  # Giảm tải CPU
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    self.log(f"❌ Lỗi hệ thống: {str(e)}")
                    self.last_error_log_time = time.time()
                time.sleep(1)

    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        self.coin_manager.unregister_coin(self.symbol)
        cancel_all_orders(self.symbol, self.api_key, self.api_secret)
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
        """Reset hoàn toàn trạng thái để sẵn sàng cho lệnh tiếp theo"""
        self.position_open = False
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self._close_attempted = False
        self._last_close_attempt = 0

    def open_position(self, side):
        try:
            self.check_position_status()
            if self.position_open:
                self.log(f"⚠️ Đã có vị thế {self.side}, bỏ qua")
                return False

            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x")
                return False

            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không đủ số dư")
                return False

            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                self.log("❌ Lỗi lấy giá")
                return False

            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            usd_amount = balance * (self.percent / 100)
            qty = (usd_amount * self.lev) / current_price
            
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)

            if qty <= step_size:
                self.log(f"❌ Số lượng quá nhỏ: {qty}")
                return False

            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty > 0:
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
                        f"💵 Giá trị: {executed_qty * self.entry:.2f} USDT\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    self.log(message)
                    return True
                else:
                    self.log(f"❌ Lệnh không khớp - Số lượng: {qty}")
                    return False
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đặt lệnh {side}: {error_msg}")
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False

    def close_position(self, reason=""):
        try:
            if not self.position_open or abs(self.qty) <= 0:
                return False

            # CHỈ ĐƯỢC ĐÓNG 1 LẦN
            current_time = time.time()
            if self._close_attempted and current_time - self._last_close_attempt < 10:
                return False
            
            self._close_attempted = True
            self._last_close_attempt = current_time

            close_side = "SELL" if self.side == "BUY" else "BUY"
            close_qty = abs(self.qty)
            
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
                    f"🤖 Chiến lược: {self.strategy_name}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDT"
                )
                self.log(message)
                
                # QUAN TRỌNG: ĐÁNH DẤU ĐỂ BOT MANAGER XÓA BOT NÀY
                self.should_be_removed = True
                
                self._reset_position()
                self.last_close_time = time.time()
                return True
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đóng lệnh: {error_msg}")
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False

    def check_tp_sl(self):
        if not self.position_open or self.entry <= 0 or self._close_attempted:
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

# ========== CÁC CHIẾN LƯỢC GIAO DỊCH ==========
class RSI_EMA_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "RSI/EMA Recursive")
        self.rsi_period = 14
        self.ema_fast = 9
        self.ema_slow = 21
        self.rsi_oversold = 30
        self.rsi_overbought = 70

    def get_signal(self):
        try:
            if len(self.prices) < 50:
                return None

            rsi = calc_rsi(self.prices, self.rsi_period)
            ema_fast = calc_ema(self.prices, self.ema_fast)
            ema_slow = calc_ema(self.prices, self.ema_slow)

            if rsi is None or ema_fast is None or ema_slow is None:
                return None

            signal = None
            if rsi < self.rsi_oversold and ema_fast > ema_slow:
                signal = "BUY"
            elif rsi > self.rsi_overbought and ema_fast < ema_slow:
                signal = "SELL"

            return signal

        except Exception as e:
            return None

class EMA_Crossover_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "EMA Crossover")
        self.ema_fast = 9
        self.ema_slow = 21
        self.prev_ema_fast = None
        self.prev_ema_slow = None

    def get_signal(self):
        try:
            if len(self.prices) < 50:
                return None

            ema_fast = calc_ema(self.prices, self.ema_fast)
            ema_slow = calc_ema(self.prices, self.ema_slow)

            if ema_fast is None or ema_slow is None:
                return None

            signal = None
            if self.prev_ema_fast is not None and self.prev_ema_slow is not None:
                if self.prev_ema_fast <= self.prev_ema_slow and ema_fast > ema_slow:
                    signal = "BUY"
                elif self.prev_ema_fast >= self.prev_ema_slow and ema_fast < ema_slow:
                    signal = "SELL"

            self.prev_ema_fast = ema_fast
            self.prev_ema_slow = ema_slow

            return signal

        except Exception as e:
            return None

class Reverse_24h_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, threshold=30, config_key=None):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Reverse 24h", config_key)
        self.threshold = threshold
        self.last_24h_check = 0
        self.last_reported_change = 0

    def get_signal(self):
        try:
            current_time = time.time()
            if current_time - self.last_24h_check < 60:
                return None

            change_24h = get_24h_change(self.symbol)
            self.last_24h_check = current_time

            if change_24h is None:
                return None
                
            # DEBUG: Log biến động để kiểm tra
            if abs(change_24h - self.last_reported_change) > 5:
                self.log(f"📊 Biến động 24h: {change_24h:.2f}% | Ngưỡng: {self.threshold}%")
                self.last_reported_change = change_24h

            signal = None
            if abs(change_24h) >= self.threshold:
                if change_24h > 0:
                    signal = "SELL"
                    self.log(f"🎯 Tín hiệu SELL - Biến động 24h: +{change_24h:.2f}% (≥ {self.threshold}%)")
                else:
                    signal = "BUY" 
                    self.log(f"🎯 Tín hiệu BUY - Biến động 24h: {change_24h:.2f}% (≤ -{self.threshold}%)")

            return signal

        except Exception as e:
            self.log(f"❌ Lỗi tín hiệu Reverse 24h: {str(e)}")
            return None

class Trend_Following_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, config_key=None):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Following", config_key)
        self.trend_period = 20
        self.trend_threshold = 0.001

    def get_signal(self):
        try:
            if len(self.prices) < self.trend_period + 1:
                return None

            recent_prices = self.prices[-self.trend_period:]
            if len(recent_prices) < 2:
                return None
                
            price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]

            signal = None
            if price_change > self.trend_threshold:
                signal = "BUY"
            elif price_change < -self.trend_threshold:
                signal = "SELL"

            return signal

        except Exception as e:
            return None

class Scalping_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, config_key=None):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Scalping", config_key)
        self.rsi_period = 7
        self.min_movement = 0.001

    def get_signal(self):
        try:
            if len(self.prices) < 20:
                return None

            current_price = self.prices[-1]
            price_change = 0
            if len(self.prices) >= 2:
                price_change = (current_price - self.prices[-2]) / self.prices[-2]

            rsi = calc_rsi(self.prices, self.rsi_period)

            if rsi is None:
                return None

            signal = None
            if rsi < 25 and price_change < -self.min_movement:
                signal = "BUY"
            elif rsi > 75 and price_change > self.min_movement:
                signal = "SELL"

            return signal

        except Exception as e:
            return None

class Safe_Grid_Bot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, grid_levels=5, config_key=None):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Safe Grid", config_key)
        self.grid_levels = grid_levels
        self.orders_placed = 0

    def get_signal(self):
        try:
            if self.orders_placed < self.grid_levels:
                self.orders_placed += 1
                if self.orders_placed % 2 == 1:
                    return "BUY"
                else:
                    return "SELL"
            return None
        except Exception as e:
            return None

# ========== BOT MANAGER ==========
class BotManager:
    def __init__(self, api_key=None, api_secret=None, telegram_bot_token=None, telegram_chat_id=None):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}
        
        # SỬA: Dictionary lưu theo KEY duy nhất cho mỗi cấu hình
        self.auto_strategies = {}
        self.last_auto_scan = 0
        self.auto_scan_interval = 600  # 10 phút
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT ĐA CHIẾN LƯỢC ĐÃ KHỞI ĐỘNG")
            
            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()
            
            self.auto_scan_thread = threading.Thread(target=self._auto_scan_loop, daemon=True)
            self.auto_scan_thread.start()
            
            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)
        else:
            self.log("⚡ BotManager khởi động ở chế độ không config")

    def _verify_api_connection(self):
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance API.")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>SYSTEM</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BOT GIAO DỊCH FUTURES BINANCE</b>\n\n🎯 <b>HỆ THỐNG ĐA CHIẾN LƯỢC</b>"
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def _auto_scan_loop(self):
        """VÒNG LẶP TỰ ĐỘNG QUÉT COIN CHO CÁC CHIẾN THUẬT TỰ ĐỘNG"""
        while self.running:
            try:
                current_time = time.time()
                
                # BƯỚC 1: DỌN DẸP BOT ĐÃ ĐÓNG LỆNH (ưu tiên cao)
                removed_count = 0
                for bot_id in list(self.bots.keys()):
                    bot = self.bots[bot_id]
                    if (hasattr(bot, 'should_be_removed') and bot.should_be_removed and
                        bot.strategy_name in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]):
                        
                        self.log(f"🔄 Tự động xóa bot {bot_id} (đã đóng lệnh)")
                        self.stop_bot(bot_id)
                        removed_count += 1
                
                if removed_count > 0:
                    self.log(f"🗑️ Đã xóa {removed_count} bot đóng lệnh, chuẩn bị tìm coin mới")
                
                # BƯỚC 2: Quét tìm coin mới mỗi 10 phút HOẶC ngay sau khi xóa bot
                if (removed_count > 0 or 
                    current_time - self.last_auto_scan > self.auto_scan_interval):
                    
                    self._scan_auto_strategies()
                    self.last_auto_scan = current_time
                
                time.sleep(30)
                
            except Exception as e:
                self.log(f"❌ Lỗi auto scan: {str(e)}")
                time.sleep(30)

    def _scan_auto_strategies(self):
        """Quét và bổ sung coin cho các chiến thuật tự động - PHÂN BIỆT CẤU HÌNH"""
        if not self.auto_strategies:
            return
            
        self.log("🔄 Đang quét coin cho các cấu hình tự động...")
        
        for strategy_key, strategy_config in self.auto_strategies.items():
            try:
                strategy_type = strategy_config['strategy_type']
                leverage = strategy_config['leverage']
                percent = strategy_config['percent']
                tp = strategy_config['tp']
                sl = strategy_config['sl']
                
                # Đếm số bot hiện có cho CẤU HÌNH NÀY
                coin_manager = CoinManager()
                current_bots_count = coin_manager.count_bots_by_config(strategy_key)
                
                # Nếu chưa đủ 2 bot, tìm thêm coin RIÊNG cho cấu hình này
                if current_bots_count < 2:
                    self.log(f"🔄 {strategy_type} (Config: {strategy_key}): đang có {current_bots_count}/2 bot, tìm thêm coin...")
                    
                    # Gọi hàm tìm coin với strategy_key để phân biệt
                    if strategy_type == "Reverse 24h":
                        threshold = strategy_config.get('threshold', 30)
                        qualified_symbols = get_qualified_symbols(
                            self.api_key, self.api_secret, strategy_type, leverage,
                            threshold=threshold, max_candidates=10, final_limit=2,
                            strategy_key=strategy_key
                        )
                    elif strategy_type == "Scalping":
                        volatility = strategy_config.get('volatility', 3)
                        qualified_symbols = get_qualified_symbols(
                            self.api_key, self.api_secret, strategy_type, leverage,
                            volatility=volatility, max_candidates=10, final_limit=2,
                            strategy_key=strategy_key
                        )
                    elif strategy_type == "Safe Grid":
                        grid_levels = strategy_config.get('grid_levels', 5)
                        qualified_symbols = get_qualified_symbols(
                            self.api_key, self.api_secret, strategy_type, leverage,
                            grid_levels=grid_levels, max_candidates=10, final_limit=2,
                            strategy_key=strategy_key
                        )
                    elif strategy_type == "Trend Following":
                        qualified_symbols = get_qualified_symbols(
                            self.api_key, self.api_secret, strategy_type, leverage,
                            max_candidates=10, final_limit=2,
                            strategy_key=strategy_key
                        )
                    else:
                        qualified_symbols = []
                    
                    # Thêm bot cho các coin mới tìm được
                    added_count = 0
                    for symbol in qualified_symbols:
                        bot_id = f"{symbol}_{strategy_key}"
                        if bot_id not in self.bots and added_count < (2 - current_bots_count):
                            success = self._create_auto_bot(symbol, strategy_type, strategy_config)
                            if success:
                                added_count += 1
                                self.log(f"✅ Đã thêm {symbol} cho {strategy_type} (Config: {strategy_key})")
                    
                    if added_count > 0:
                        self.log(f"🎯 {strategy_type}: đã thêm {added_count} bot mới cho config {strategy_key}")
                    else:
                        self.log(f"⚠️ {strategy_type}: không tìm thấy coin mới phù hợp cho config {strategy_key}")
                        
            except Exception as e:
                self.log(f"❌ Lỗi quét {strategy_type}: {str(e)}")

    def _create_auto_bot(self, symbol, strategy_type, config):
        """Tạo bot tự động từ config - TRUYỀN CONFIG_KEY"""
        try:
            leverage = config['leverage']
            percent = config['percent']
            tp = config['tp']
            sl = config['sl']
            strategy_key = config['strategy_key']
            
            if strategy_type == "Reverse 24h":
                threshold = config.get('threshold', 30)
                bot = Reverse_24h_Bot(symbol, leverage, percent, tp, sl, self.ws_manager,
                                   self.api_key, self.api_secret, self.telegram_bot_token, 
                                   self.telegram_chat_id, threshold, strategy_key)
            elif strategy_type == "Scalping":
                bot = Scalping_Bot(symbol, leverage, percent, tp, sl, self.ws_manager,
                                 self.api_key, self.api_secret, self.telegram_bot_token, 
                                 self.telegram_chat_id, strategy_key)
            elif strategy_type == "Safe Grid":
                grid_levels = config.get('grid_levels', 5)
                bot = Safe_Grid_Bot(symbol, leverage, percent, tp, sl, self.ws_manager,
                                 self.api_key, self.api_secret, self.telegram_bot_token, 
                                 self.telegram_chat_id, grid_levels, strategy_key)
            elif strategy_type == "Trend Following":
                bot = Trend_Following_Bot(symbol, leverage, percent, tp, sl, self.ws_manager,
                                       self.api_key, self.api_secret, self.telegram_bot_token, 
                                       self.telegram_chat_id, strategy_key)
            else:
                return False
            
            bot_id = f"{symbol}_{strategy_key}"
            self.bots[bot_id] = bot
            return True
            
        except Exception as e:
            self.log(f"❌ Lỗi tạo bot {symbol}: {str(e)}")
            return False

    def add_bot(self, symbol, lev, percent, tp, sl, strategy_type, **kwargs):
        if sl == 0:
            sl = None
            
        if not self.api_key or not self.api_secret:
            self.log("❌ Chưa thiết lập API Key trong BotManager")
            return False
        
        test_balance = get_balance(self.api_key, self.api_secret)
        if test_balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance")
            return False
            
        # CHIẾN LƯỢC TỰ ĐỘNG - 4 CHIẾN LƯỢC
        if strategy_type in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]:
            # TẠO KEY DUY NHẤT cho mỗi cấu hình
            strategy_key = f"{strategy_type}_{lev}_{percent}_{tp}_{sl}"
            
            # Thêm tham số đặc biệt vào key để phân biệt
            if strategy_type == "Reverse 24h":
                threshold = kwargs.get('threshold', 30)
                strategy_key += f"_th{threshold}"
            elif strategy_type == "Scalping":
                volatility = kwargs.get('volatility', 3)
                strategy_key += f"_vol{volatility}"
            elif strategy_type == "Safe Grid":
                grid_levels = kwargs.get('grid_levels', 5)
                strategy_key += f"_grid{grid_levels}"
            
            # LƯU CẤU HÌNH RIÊNG
            self.auto_strategies[strategy_key] = {
                'strategy_type': strategy_type,
                'leverage': lev,
                'percent': percent,
                'tp': tp,
                'sl': sl,
                'strategy_key': strategy_key,
                **kwargs
            }
            
            # TÌM COIN RIÊNG cho cấu hình này
            threshold = kwargs.get('threshold', 30)
            volatility = kwargs.get('volatility', 3)
            grid_levels = kwargs.get('grid_levels', 5)
            
            qualified_symbols = get_qualified_symbols(
                self.api_key, self.api_secret, strategy_type, lev,
                threshold, volatility, grid_levels, 
                max_candidates=20, 
                final_limit=2,
                strategy_key=strategy_key
            )
            
            success_count = 0
            for symbol in qualified_symbols:
                bot_id = f"{symbol}_{strategy_key}"
                if bot_id in self.bots:
                    continue
                    
                success = self._create_auto_bot(symbol, strategy_type, self.auto_strategies[strategy_key])
                if success:
                    success_count += 1
            
            if success_count > 0:
                success_msg = (
                    f"✅ <b>ĐÃ TẠO {success_count} BOT {strategy_type}</b>\n\n"
                    f"🎯 Chiến lược: {strategy_type}\n"
                    f"💰 Đòn bẩy: {lev}x\n"
                    f"📊 % Số dư: {percent}%\n"
                    f"🎯 TP: {tp}%\n"
                    f"🛡️ SL: {sl}%\n"
                )
                if strategy_type == "Reverse 24h":
                    success_msg += f"📈 Ngưỡng: {threshold}%\n"
                elif strategy_type == "Scalping":
                    success_msg += f"⚡ Biến động: {volatility}%\n"
                elif strategy_type == "Safe Grid":
                    success_msg += f"🛡️ Số lệnh: {grid_levels}\n"
                    
                success_msg += f"🤖 Coin: {', '.join(qualified_symbols[:success_count])}\n\n"
                success_msg += f"🔑 <b>Config Key:</b> {strategy_key}\n"
                success_msg += f"🔄 <i>Hệ thống sẽ tự động quét RIÊNG cho cấu hình này</i>"
                
                self.log(success_msg)
                return True
            else:
                self.log(f"⚠️ {strategy_type}: chưa tìm thấy coin phù hợp, sẽ thử lại sau")
                return True
        
        # CHIẾN LƯỢC THỦ CÔNG - 2 CHIẾN LƯỢC
        else:
            symbol = symbol.upper()
            bot_id = f"{symbol}_{strategy_type}"
            
            if bot_id in self.bots:
                self.log(f"⚠️ Đã có bot {strategy_type} cho {symbol}")
                return False
                
            try:
                if strategy_type == "RSI/EMA Recursive":
                    bot = RSI_EMA_Bot(symbol, lev, percent, tp, sl, self.ws_manager, 
                                   self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                elif strategy_type == "EMA Crossover":
                    bot = EMA_Crossover_Bot(symbol, lev, percent, tp, sl, self.ws_manager,
                                         self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                else:
                    self.log(f"❌ Chiến lược {strategy_type} không được hỗ trợ")
                    return False
                
                self.bots[bot_id] = bot
                self.log(f"✅ Đã thêm bot {strategy_type}: {symbol} | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%")
                return True
                
            except Exception as e:
                error_msg = f"❌ Lỗi tạo bot {symbol}: {str(e)}"
                self.log(error_msg)
                return False

    def stop_bot(self, bot_id):
        bot = self.bots.get(bot_id)
        if bot:
            bot.stop()
            self.log(f"⛔ Đã dừng bot {bot_id}")
            del self.bots[bot_id]
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
                elif response.status_code == 409:
                    logger.error("Lỗi xung đột Telegram")
                    time.sleep(60)
                else:
                    time.sleep(10)
                
            except Exception as e:
                logger.error(f"Lỗi Telegram listener: {str(e)}")
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        # Xử lý theo bước hiện tại
        if current_step == 'waiting_strategy':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text in ["🤖 RSI/EMA Recursive", "📊 EMA Crossover", "🎯 Reverse 24h", 
                         "📈 Trend Following", "⚡ Scalping", "🛡️ Safe Grid"]:
                strategy_map = {
                    "🤖 RSI/EMA Recursive": "RSI/EMA Recursive",
                    "📊 EMA Crossover": "EMA Crossover", 
                    "🎯 Reverse 24h": "Reverse 24h",
                    "📈 Trend Following": "Trend Following",
                    "⚡ Scalping": "Scalping",
                    "🛡️ Safe Grid": "Safe Grid"
                }
                strategy = strategy_map[text]
                user_state['strategy'] = strategy
                
                if strategy in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]:
                    if strategy == "Reverse 24h":
                        user_state['step'] = 'waiting_threshold'
                        send_telegram(
                            f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                            f"🤖 Bot sẽ tự động tìm coin phù hợp từ TOÀN BỘ Binance\n"
                            f"🔄 Sẽ quét lại mỗi 10 phút nếu chưa đủ 2 coin\n\n"
                            f"Chọn ngưỡng biến động (%):",
                            chat_id,
                            create_threshold_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    elif strategy == "Scalping":
                        user_state['step'] = 'waiting_volatility'
                        send_telegram(
                            f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                            f"🤖 Bot sẽ tự động tìm coin biến động nhanh từ TOÀN BỘ Binance\n"
                            f"🔄 Sẽ quét lại mỗi 10 phút nếu chưa đủ 2 coin\n\n"
                            f"Chọn biến động tối thiểu (%):",
                            chat_id,
                            create_volatility_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    elif strategy == "Safe Grid":
                        user_state['step'] = 'waiting_grid_levels'
                        send_telegram(
                            f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                            f"🤖 Bot sẽ tự động tìm coin ổn định từ TOÀN BỘ Binance\n"
                            f"🔄 Sẽ quét lại mỗi 10 phút nếu chưa đủ 2 coin\n\n"
                            f"Chọn số lệnh grid:",
                            chat_id,
                            create_grid_levels_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    elif strategy == "Trend Following":
                        user_state['step'] = 'waiting_leverage'
                        send_telegram(
                            f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                            f"🤖 Bot sẽ tự động tìm coin theo xu hướng từ TOÀN BỘ Binance\n"
                            f"🔄 Sẽ quét lại mỗi 10 phút nếu chưa đủ 2 coin\n\n"
                            f"Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard(strategy),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                else:
                    user_state['step'] = 'waiting_symbol'
                    send_telegram(
                        f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                        f"Chọn cặp coin:",
                        chat_id,
                        create_symbols_keyboard(strategy),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
        
        elif current_step == 'waiting_threshold':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    threshold = float(text)
                    if threshold > 0:
                        user_state['threshold'] = threshold
                        user_state['step'] = 'waiting_leverage'
                        send_telegram(
                            f"🎯 Chiến lược: {user_state['strategy']}\n"
                            f"📊 Ngưỡng: {threshold}%\n\n"
                            f"Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard(user_state.get('strategy')),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Ngưỡng phải lớn hơn 0", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif current_step == 'waiting_volatility':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    volatility = float(text)
                    if volatility > 0:
                        user_state['volatility'] = volatility
                        user_state['step'] = 'waiting_leverage'
                        send_telegram(
                            f"🎯 Chiến lược: {user_state['strategy']}\n"
                            f"⚡ Biến động: {volatility}%\n\n"
                            f"Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard(user_state.get('strategy')),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Biến động phải lớn hơn 0", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif current_step == 'waiting_grid_levels':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    grid_levels = int(text)
                    if grid_levels > 0:
                        user_state['grid_levels'] = grid_levels
                        user_state['step'] = 'waiting_leverage'
                        send_telegram(
                            f"🎯 Chiến lược: {user_state['strategy']}\n"
                            f"🛡️ Số lệnh: {grid_levels}\n\n"
                            f"Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard(user_state.get('strategy')),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Số lệnh phải lớn hơn 0", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif current_step == 'waiting_symbol':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                symbol = text.upper()
                user_state['symbol'] = symbol
                user_state['step'] = 'waiting_leverage'
                send_telegram(
                    f"📌 <b>ĐÃ CHỌN: {symbol}</b>\n"
                    f"🎯 Chiến lược: {user_state['strategy']}\n\n"
                    f"Chọn đòn bẩy:",
                    chat_id,
                    create_leverage_keyboard(user_state.get('strategy')),
                    self.telegram_bot_token, self.telegram_chat_id
                )
        
        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif 'x' in text:
                leverage = int(text.replace('', '').replace('x', '').strip())
                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                
                if user_state.get('strategy') in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]:
                    send_telegram(
                        f"🎯 Chiến lược: {user_state['strategy']}\n"
                        f"💰 Đòn bẩy: {leverage}x\n\n"
                        f"Nhập % số dư muốn sử dụng:\n"
                        f"💡 <i>Gợi ý: 1%, 3%, 5%, 10%</i>",
                        chat_id,
                        create_percent_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                else:
                    send_telegram(
                        f"📌 Cặp: {user_state['symbol']}\n"
                        f"🎯 Chiến lược: {user_state['strategy']}\n"
                        f"💰 Đòn bẩy: {leverage}x\n\n"
                        f"Nhập % số dư muốn sử dụng:\n"
                        f"💡 <i>Gợi ý: 1%, 3%, 5%, 10%</i>",
                        chat_id,
                        create_percent_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
        
        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    percent = float(text)
                    if 1 <= percent <= 100:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        
                        if user_state.get('strategy') in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]:
                            send_telegram(
                                f"🎯 Chiến lược: {user_state['strategy']}\n"
                                f"💰 ĐB: {user_state['leverage']}x\n"
                                f"📊 %: {percent}%\n\n"
                                f"Nhập % Take Profit:\n"
                                f"💡 <i>Gợi ý: 50%, 100%, 200%</i>",
                                chat_id,
                                create_tp_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id
                            )
                        else:
                            send_telegram(
                                f"📌 Cặp: {user_state['symbol']}\n"
                                f"🎯 Chiến lược: {user_state['strategy']}\n"
                                f"💰 ĐB: {user_state['leverage']}x\n"
                                f"📊 %: {percent}%\n\n"
                                f"Nhập % Take Profit:\n"
                                f"💡 <i>Gợi ý: 50%, 100%, 200%</i>",
                                chat_id,
                                create_tp_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id
                            )
                    else:
                        send_telegram("⚠️ Vui lòng nhập % từ 1-100", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
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
                        
                        if user_state.get('strategy') in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]:
                            send_telegram(
                                f"🎯 Chiến lược: {user_state['strategy']}\n"
                                f"💰 ĐB: {user_state['leverage']}x\n"
                                f"📊 %: {user_state['percent']}%\n"
                                f"🎯 TP: {tp}%\n\n"
                                f"Nhập % Stop Loss:\n"
                                f"💡 <i>Gợi ý: 0 (tắt SL), 150%, 500%</i>",
                                chat_id,
                                create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id
                            )
                        else:
                            send_telegram(
                                f"📌 Cặp: {user_state['symbol']}\n"
                                f"🎯 Chiến lược: {user_state['strategy']}\n"
                                f"💰 ĐB: {user_state['leverage']}x\n"
                                f"📊 %: {user_state['percent']}%\n"
                                f"🎯 TP: {tp}%\n\n"
                                f"Nhập % Stop Loss:\n"
                                f"💡 <i>Gợi ý: 0 (tắt SL), 150%, 500%</i>",
                                chat_id,
                                create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id
                            )
                    else:
                        send_telegram("⚠️ TP phải lớn hơn 0", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    sl = float(text)
                    if sl >= 0:
                        strategy = user_state['strategy']
                        leverage = user_state['leverage']
                        percent = user_state['percent']
                        tp = user_state['tp']
                        
                        if strategy in ["Reverse 24h", "Scalping", "Safe Grid", "Trend Following"]:
                            if strategy == "Reverse 24h":
                                threshold = user_state.get('threshold', 30)
                                success = self.add_bot(symbol=None, lev=leverage, percent=percent, tp=tp, sl=sl, 
                                                     strategy_type=strategy, threshold=threshold)
                            elif strategy == "Scalping":
                                volatility = user_state.get('volatility', 3)
                                success = self.add_bot(symbol=None, lev=leverage, percent=percent, tp=tp, sl=sl, 
                                                     strategy_type=strategy, volatility=volatility)
                            elif strategy == "Safe Grid":
                                grid_levels = user_state.get('grid_levels', 5)
                                success = self.add_bot(symbol=None, lev=leverage, percent=percent, tp=tp, sl=sl, 
                                                     strategy_type=strategy, grid_levels=grid_levels)
                            elif strategy == "Trend Following":
                                success = self.add_bot(symbol=None, lev=leverage, percent=percent, tp=tp, sl=sl, 
                                                     strategy_type=strategy)
                        else:
                            symbol = user_state['symbol']
                            success = self.add_bot(symbol, leverage, percent, tp, sl, strategy)
                        
                        if success:
                            send_telegram("✅ Đã thêm bot thành công!", chat_id, create_main_menu(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                        else:
                            send_telegram("❌ Không thể thêm bot, vui lòng kiểm tra log", chat_id, create_main_menu(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                        
                        self.user_states[chat_id] = {}
                    else:
                        send_telegram("⚠️ SL phải lớn hơn hoặc bằng 0", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        # Xử lý các lệnh chính
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_strategy'}
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key!", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"🎯 <b>CHỌN CHIẾN LƯỢC GIAO DỊCH</b>\n\n"
                f"💡 <b>Chiến lược tự động (Tìm coin từ TOÀN BỘ Binance):</b>\n• Reverse 24h\n• Scalping  \n• Safe Grid\n• Trend Following\n\n"
                f"💡 <b>Chiến lược thủ công:</b>\n• RSI/EMA Recursive\n• EMA Crossover",
                chat_id,
                create_strategy_keyboard(),
                self.telegram_bot_token, self.telegram_chat_id
            )
        
        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                message = "🤖 <b>DANH SÁCH BOT ĐANG CHẠY</b>\n\n"
                for bot_id, bot in self.bots.items():
                    status = "🟢 Mở" if bot.status == "open" else "🟡 Chờ"
                    message += f"🔹 {bot_id} | {status} | {bot.side} | ĐB: {bot.lev}x\n"
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                message = "⛔ <b>CHỌN BOT ĐỂ DỪNG</b>\n\n"
                keyboard = []
                row = []
                
                for i, bot_id in enumerate(self.bots.keys()):
                    message += f"🔹 {bot_id}\n"
                    row.append({"text": f"⛔ {bot_id}"})
                    if len(row) == 2 or i == len(self.bots) - 1:
                        keyboard.append(row)
                        row = []
                
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                
                send_telegram(
                    message, 
                    chat_id, 
                    {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True},
                    self.telegram_bot_token, self.telegram_chat_id
                )
        
        elif text.startswith("⛔ "):
            bot_id = text.replace("⛔ ", "").strip()
            if self.stop_bot(bot_id):
                send_telegram(f"⛔ Đã dừng bot {bot_id}", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                send_telegram(f"⚠️ Không tìm thấy bot {bot_id}", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
        
        elif text == "💰 Số dư":
            try:
                balance = get_balance(self.api_key, self.api_secret)
                if balance is None:
                    send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key!", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                else:
                    send_telegram(f"💰 <b>SỐ DƯ KHẢ DỤNG</b>: {balance:.2f} USDT", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy số dư: {str(e)}", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📈 Vị thế":
            try:
                positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
                if not positions:
                    send_telegram("📭 Không có vị thế nào đang mở", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
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
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy vị thế: {str(e)}", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>DANH SÁCH CHIẾN LƯỢC</b>\n\n"
                "🎯 <b>Reverse 24h</b> - TỰ ĐỘNG\n"
                "• Đảo chiều biến động 24h\n"
                "• Tự tìm coin từ TOÀN BỘ Binance\n"
                "• Ngưỡng biến động: 30-200%\n"
                "• 🔄 Tự quét mỗi 10 phút\n\n"
                "⚡ <b>Scalping</b> - TỰ ĐỘNG\n"
                "• Giao dịch tốc độ cao\n"
                "• Tự tìm coin từ TOÀN BỘ Binance\n"
                "• Biến động tối thiểu: 2-15%\n"
                "• 🔄 Tự quét mỗi 10 phút\n\n"
                "🛡️ <b>Safe Grid</b> - TỰ ĐỘNG\n"
                "• Grid an toàn\n"
                "• Tự tìm coin từ TOÀN BỘ Binance\n"
                "• Số lệnh grid: 3-20\n"
                "• 🔄 Tự quét mỗi 10 phút\n\n"
                "📈 <b>Trend Following</b> - TỰ ĐỘNG\n"
                "• Theo xu hướng giá\n"
                "• Tự tìm coin từ TOÀN BỘ Binance\n"
                "• Biến động vừa phải: 2-8%\n"
                "• 🔄 Tự quét mỗi 10 phút\n\n"
                "🤖 <b>RSI/EMA Recursive</b> - THỦ CÔNG\n"
                "• Phân tích RSI + EMA đệ quy\n\n"
                "📊 <b>EMA Crossover</b> - THỦ CÔNG\n"
                "• Giao cắt EMA nhanh/chậm"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            
            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Số bot: {len(self.bots)}\n"
                f"📊 Chiến lược: {len(set(bot.strategy_name for bot in self.bots.values()))}\n"
                f"🔄 Auto scan: {len(self.auto_strategies)} cấu hình\n"
                f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()
