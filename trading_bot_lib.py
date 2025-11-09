# trading_bot_lib.py - HOÀN CHỈNH VỚI CƠ CHẾ TÍNH TOÀN DIỆN LỜI/LỖ VÀ ĐẾM COIN
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
from collections import defaultdict
import time
import ssl

# ========== BYPASS SSL VERIFICATION ==========
ssl._create_default_https_context = ssl._create_unverified_context

def _last_closed_1m_quote_volume(symbol):
    data = binance_api_request(
        "https://fapi.binance.com/fapi/v1/klines",
        params={"symbol": symbol, "interval": "1m", "limit": 2}
    )
    if not data or len(data) < 2:
        return None
    k = data[-2]               # nến 1m đã đóng gần nhất
    return float(k[7])         # quoteVolume (USDC)


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

# ========== MENU TELEGRAM HOÀN CHỈNH ==========
def create_cancel_keyboard():
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_strategy_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Global Market System"}],
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
        symbols = get_all_usdc_pairs(limit=12)
        if not symbols:
            symbols = ["BTCUSDC", "ETHUSDC", "BNBUSDC", "ADAUSDC", "DOGEUSDC", "XRPUSDC", "DOTUSDC", "LINKUSDC"]
    except:
        symbols = ["BTCUSDC", "ETHUSDC", "BNBUSDC", "ADAUSDC", "DOGEUSDC", "XRPUSDC", "DOTUSDC", "LINKUSDC"]
    
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

# ========== API BINANCE - ĐÃ SỬA LỖI 451 ==========
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
            # Thêm User-Agent để tránh bị chặn
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
            
            # Tăng timeout và thêm retry logic
            with urllib.request.urlopen(req, timeout=30) as response:
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
            if e.code == 451:
                logger.error(f"❌ Lỗi 451: Truy cập bị chặn - Có thể do hạn chế địa lý. Vui lòng kiểm tra VPN/proxy.")
                # Thử sử dụng endpoint thay thế
                if "fapi.binance.com" in url:
                    new_url = url.replace("fapi.binance.com", "fapi.binance.com")
                    logger.info(f"Thử URL thay thế: {new_url}")
                    # Không retry lại ngay mà để lần sau
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

def get_all_usdc_pairs(limit=100):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            logger.warning("Không lấy được dữ liệu từ Binance, trả về danh sách rỗng")
            return []
        
        usdc_pairs = []
        for symbol_info in data.get('symbols', []):
            symbol = symbol_info.get('symbol', '')
            if symbol.endswith('USDC') and symbol_info.get('status') == 'TRADING':
                usdc_pairs.append(symbol)
        
        logger.info(f"✅ Lấy được {len(usdc_pairs)} coin USDC từ Binance")
        return usdc_pairs[:limit] if limit else usdc_pairs
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy danh sách coin từ Binance: {str(e)}")
        return []

def get_top_volume_symbols(limit=100):
    """Top {limit} USDC pairs theo quoteVolume của NẾN 1M đã đóng (đa luồng)."""
    try:
        universe = get_all_usdc_pairs(limit=100) or []
        if not universe:
            logger.warning("❌ Không lấy được danh sách coin USDC")
            return []

        scored, failed = [], 0
        max_workers = 8  # Giảm workers để tránh bị chặn
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futmap = {ex.submit(_last_closed_1m_quote_volume, s): s for s in universe}
            for fut in as_completed(futmap):
                sym = futmap[fut]
                try:
                    qv = fut.result()
                    if qv is not None:
                        scored.append((sym, qv))
                except Exception:
                    failed += 1
                time.sleep(0.5)  # Tăng thời gian chờ để tránh 429

        scored.sort(key=lambda x: x[1], reverse=True)
        top_syms = [s for s, _ in scored[:limit]]
        logger.info(f"✅ Top {len(top_syms)} theo 1m quoteVolume (phân tích: {len(scored)}, lỗi: {failed})")
        return top_syms

    except Exception as e:
        logger.error(f"❌ Lỗi lấy top volume 1 phút (đa luồng): {str(e)}")
        return []

def get_max_leverage(symbol, api_key, api_secret):
    """Lấy đòn bẩy tối đa cho một symbol"""
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            return 100  # Mặc định nếu không lấy được
        
        for s in data['symbols']:
            if s['symbol'] == symbol.upper():
                # Tìm thông tin đòn bẩy từ filters
                for f in s['filters']:
                    if f['filterType'] == 'LEVERAGE':
                        if 'maxLeverage' in f:
                            return int(f['maxLeverage'])
                break
        return 100  # Mặc định
    except Exception as e:
        logger.error(f"Lỗi lấy đòn bẩy tối đa {symbol}: {str(e)}")
        return 100

def get_step_size(symbol, api_key, api_secret):
    if not symbol:
        logger.error("❌ Lỗi: Symbol là None khi lấy step size")
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
        logger.error("❌ Lỗi: Symbol là None khi set leverage")
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
        if response is None:
            return False
        if response and 'leverage' in response:
            return True
        return False
    except Exception as e:
        logger.error(f"Lỗi thiết lập đòn bẩy: {str(e)}")
        return False

def get_balance(api_key, api_secret):
    """Lấy số dư KHẢ DỤNG (availableBalance) để tính toán khối lượng"""
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        data = binance_api_request(url, headers=headers)
        if not data:
            logger.error("❌ Không lấy được số dư từ Binance")
            return None
            
        for asset in data['assets']:
            if asset['asset'] == 'USDC':
                available_balance = float(asset['availableBalance'])
                total_balance = float(asset['walletBalance'])
                
                logger.info(f"💰 Số dư - Khả dụng: {available_balance:.2f} USDC, Tổng: {total_balance:.2f} USDC")
                return available_balance
        return 0
    except Exception as e:
        logger.error(f"Lỗi lấy số dư: {str(e)}")
        return None

def place_order(symbol, side, qty, api_key, api_secret):
    if not symbol:
        logger.error("❌ Không thể đặt lệnh: symbol là None")
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
        logger.error("❌ Không thể hủy lệnh: symbol là None")
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
        logger.error("💰 Lỗi: Symbol là None khi lấy giá")
        return 0
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            price = float(data['price'])
            if price > 0:
                return price
            else:
                logger.error(f"💰 Giá {symbol} = 0")
        return 0
    except Exception as e:
        logger.error(f"💰 Lỗi lấy giá {symbol}: {str(e)}")
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

# ========== COIN MANAGER ==========
class CoinManager:
    def __init__(self):
        self.active_coins = set()
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

# ========== SMART COIN FINDER ĐÃ SỬA - TÌM COIN BIẾN ĐỘNG MẠNH ==========
class SmartCoinFinder:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def get_symbol_leverage(self, symbol):
        """Lấy đòn bẩy tối đa của symbol"""
        return get_max_leverage(symbol, self.api_key, self.api_secret)
    
    def find_best_coin(self, target_direction, excluded_coins=None, required_leverage=10):
        """Tìm coin tốt nhất - TÌM COIN BIẾN ĐỘNG MẠNH VÀ ĐỦ ĐÒN BẨY"""
        try:
            # Lấy tất cả coin USDC
            all_symbols = get_all_usdc_pairs(limit=100)
            if not all_symbols:
                return None
            
            # Lọc coin theo đòn bẩy và loại bỏ coin đã active
            valid_symbols = []
            for symbol in all_symbols:
                if excluded_coins and symbol in excluded_coins:
                    continue
                
                # Kiểm tra đòn bẩy
                max_lev = self.get_symbol_leverage(symbol)
                if max_lev < required_leverage:
                    continue
                
                valid_symbols.append(symbol)
            
            if not valid_symbols:
                logger.warning("❌ Không tìm thấy coin nào đáp ứng đòn bẩy")
                return None
            
            # Chọn ngẫu nhiên từ các coin hợp lệ
            selected_symbol = random.choice(valid_symbols)
            max_lev = self.get_symbol_leverage(selected_symbol)
            
            logger.info(f"✅ Đã chọn coin: {selected_symbol} - Đòn bẩy: {max_lev}x")
            return selected_symbol
            
        except Exception as e:
            logger.error(f"Lỗi tìm coin: {str(e)}")
            return None

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
        if not symbol:
            return
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

# ========== BASE BOT VỚI CƠ CHẾ TÍNH TOÀN DIỆN LỜI/LỖ VÀ ĐẾM COIN ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret,
                 telegram_bot_token, telegram_chat_id, strategy_name, config_key=None, bot_id=None,
                 coin_manager=None, symbol_locks=None):

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
        self.config_key = config_key
        self.bot_id = bot_id or f"{strategy_name}_{int(time.time())}_{random.randint(1000, 9999)}"

        self.status = "searching"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []
        self.current_price = 0
        self.position_open = False
        self._stop = False

        self.last_trade_time = 0
        self.last_close_time = 0
        self.last_position_check = 0
        self.last_error_log_time = 0

        self.cooldown_period = 3600
        self.position_check_interval = 30

        self._close_attempted = False
        self._last_close_attempt = 0

        self.should_be_removed = False

        # ✅ dùng chung
        self.coin_manager = coin_manager or CoinManager()
        self.symbol_locks = symbol_locks  # có thể None, sẽ fallback lock tạm thời khi cần

        self.coin_finder = SmartCoinFinder(api_key, api_secret)

        self.last_side = None
        self.is_first_trade = True

        self.entry_base = 0
        self.average_down_count = 0
        self.last_average_down_time = 0
        self.average_down_cooldown = 60
        self.max_average_down_count = 7

        self.entry_green_count = 0
        self.entry_red_count = 0
        self.high_water_mark_roi = 0
        self.roi_check_activated = False

        self.global_long_count = 0
        self.global_short_count = 0
        self.global_long_pnl = 0
        self.global_short_pnl = 0
        self.last_global_position_check = 0
        self.global_position_check_interval = 10

        self.find_new_bot_after_close = True
        self.bot_creation_time = time.time()

        self.check_position_status()
        if self.symbol:
            self.ws_manager.add_symbol(self.symbol, self._handle_price_update)

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else " | 🎯 ROI Trigger: Tắt"
        if self.symbol:
            self.log(f"🟢 Bot {strategy_name} khởi động | {self.symbol} | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%{roi_info}")
        else:
            self.log(f"🟢 Bot {strategy_name} khởi động | Đang tìm coin... | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%{roi_info}")

    def check_position_status(self):
        if not self.symbol:
            return
            
        try:
            positions = get_positions(self.symbol, self.api_key, self.api_secret)
            if not positions:
                self._reset_position()
                return
            
            position_found = False
            for pos in positions:
                if pos['symbol'] == self.symbol:
                    position_amt = float(pos.get('positionAmt', 0))
                    if abs(position_amt) > 0:
                        position_found = True
                        self.position_open = True
                        self.status = "open"
                        self.side = "BUY" if position_amt > 0 else "SELL"
                        self.qty = position_amt
                        self.entry = float(pos.get('entryPrice', 0))
                        
                        # CẬP NHẬT QUAN TRỌNG: Lưu hướng lệnh hiện tại
                        self.last_side = self.side
                        self.is_first_trade = False
                        break
                    else:
                        position_found = True
                        self._reset_position()
                        break
            
            if not position_found:
                self._reset_position()
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")
                self.last_error_log_time = time.time()

    def check_global_positions(self):
        """Kiểm tra vị thế toàn tài khoản - tính cả số lượng và tổng PnL (cả âm và dương)"""
        try:
            positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            if not positions:
                self.global_long_count = 0
                self.global_short_count = 0
                self.global_long_pnl = 0
                self.global_short_pnl = 0
                self.global_long_value = 0
                self.global_short_value = 0
                return
            
            long_count = 0
            short_count = 0
            long_pnl_total = 0
            short_pnl_total = 0
            long_value_total = 0
            short_value_total = 0
            
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                entry_price = float(pos.get('entryPrice', 0))
                leverage = float(pos.get('leverage', 1))
                
                # Tính giá trị vị thế (position value)
                position_value = abs(position_amt) * entry_price / leverage
                
                if position_amt > 0:  # LONG position
                    long_count += 1
                    long_pnl_total += unrealized_pnl
                    long_value_total += position_value
                elif position_amt < 0:  # SHORT position
                    short_count += 1
                    short_pnl_total += unrealized_pnl
                    short_value_total += position_value
            
            self.global_long_count = long_count
            self.global_short_count = short_count
            self.global_long_pnl = long_pnl_total
            self.global_short_pnl = short_pnl_total
            self.global_long_value = long_value_total
            self.global_short_value = short_value_total
            
            # Log thống kê định kỳ
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"❌ Lỗi kiểm tra vị thế toàn tài khoản: {str(e)}")
                self.last_error_log_time = time.time()
    
    def get_next_side_based_on_comprehensive_analysis(self):
        """Xác định hướng lệnh tiếp theo dựa trên phân tích toàn diện: tổng giá trị và PnL"""
        # Cập nhật thống kê toàn tài khoản
        self.check_global_positions()
        
        # QUY TẮC MỚI: Ưu tiên tổng giá trị vị thế trước, sau đó đến PnL, cuối cùng là số lượng
        
        # 1. Điểm số dựa trên TỔNG GIÁ TRỊ vị thế
        long_score = 0
        short_score = 0
        
        if self.global_long_pnl > self.global_short_pnl:
            # LONG đang có PnL thấp hơn SHORT -> ưu tiên SEll để cân bằng
            long_score += 2
        elif self.global_short_pnl > self.global_long_pnl:
            # SHORT đang có PnL thấp hơn LONG -> ưu tiên SELL để cân bằng
            short_score += 2
        
        # 3. Điểm số dựa trên số lượng vị thế (nếu vẫn không quyết định được)
        if long_score == short_score:
            if self.global_long_count > self.global_short_count:
                # Nhiều LONG hơn -> ưu tiên SELL để cân bằng
                short_score += 1
            elif self.global_short_count > self.global_long_count:
                # Nhiều SHORT hơn -> ưu tiên BUY để cân bằng
                long_score += 1
        
        # 4. Quyết định dựa trên điểm số
        if long_score > short_score:
            return "BUY"
        elif short_score > long_score:
            return "SELL"
        else:
            # Bằng nhau -> Chọn ngẫu nhiên
            return random.choice(["BUY", "SELL"])

    def _reset_position(self):
        """Reset trạng thái vị thế"""
        self.position_open = False
        self.status = "waiting"  # Chờ mở lệnh tiếp theo
        self.side = ""
        self.qty = 0
        self.entry = 0
        self._close_attempted = False
        self._last_close_attempt = 0
        # Reset thông tin nhồi lệnh
        self.entry_base = 0
        self.average_down_count = 0
        # Reset thông tin theo dõi nến và ROI
        self.entry_green_count = 0
        self.entry_red_count = 0
        self.high_water_mark_roi = 0
        self.roi_check_activated = False

    def find_and_set_coin(self):
        """Tìm và thiết lập coin mới cho bot"""
        try:
            # Lấy danh sách coin đang active để tránh trùng lặp
            active_coins = self.coin_manager.get_active_coins()
            
            # Tìm coin phù hợp
            new_symbol = self.coin_finder.find_best_coin(
                target_direction="BUY",  # Không quan trọng vì sẽ đi theo phân tích toàn diện
                excluded_coins=active_coins,
                required_leverage=self.lev
            )
            
            if new_symbol:
                # Đăng ký coin mới
                self.coin_manager.register_coin(new_symbol)
                
                # Cập nhật symbol cho bot
                if self.symbol:
                    self.ws_manager.remove_symbol(self.symbol)
                    self.coin_manager.unregister_coin(self.symbol)
                
                self.symbol = new_symbol
                self.ws_manager.add_symbol(new_symbol, self._handle_price_update)
                self.status = "waiting"
                
                self.log(f"🎯 Đã tìm thấy coin mới: {new_symbol}")
                return True
            
            return False
            
        except Exception as e:
            self.log(f"❌ Lỗi tìm coin: {str(e)}")
            return False

    def verify_leverage_and_switch(self):
        if not self.symbol:
            return True
        try:
            current_leverage = self.coin_finder.get_symbol_leverage(self.symbol)
            if current_leverage >= self.lev:
                return set_leverage(self.symbol, self.lev, self.api_key, self.api_secret)
            else:
                # thử đặt về mức tối đa coin hỗ trợ thay vì bỏ ngay
                ok = set_leverage(self.symbol, current_leverage, self.api_key, self.api_secret)
                if not ok:
                    self.log(f"❌ Không thể set leverage {current_leverage}x cho {self.symbol}")
                return ok
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra đòn bẩy: {str(e)}")
            return False


    def _run(self):
        while not self._stop:
            try:
                current_time = time.time()
                
                # KIỂM TRA ĐÒN BẨY ĐỊNH KỲ
                if current_time - getattr(self, '_last_leverage_check', 0) > 60:
                    if not self.verify_leverage_and_switch():
                        if self.symbol:
                            self.ws_manager.remove_symbol(self.symbol)
                            self.coin_manager.unregister_coin(self.symbol)
                            self.symbol = None
                        time.sleep(1)
                        continue
                    self._last_leverage_check = current_time
                
                # KIỂM TRA VỊ THẾ TOÀN TÀI KHOẢN ĐỊNH KỲ
                if current_time - self.last_global_position_check > self.global_position_check_interval:
                    self.check_global_positions()
                    self.last_global_position_check = current_time
                
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                # KIỂM TRA NHỒI LỆNH KHI CÓ VỊ THẾ
                if self.position_open:
                    self.check_averaging_down()
                              
                if not self.position_open:
                    # QUAN TRỌNG: Nếu không có symbol, tìm coin mới NGAY
                    if not self.symbol:
                        if self.find_and_set_coin():
                            self.log("✅ Đã tìm thấy coin mới, chờ tín hiệu...")
                        time.sleep(1)
                        continue
                    
                    # CƠ CHẾ MỚI: VÀO LỆNH DỰA TRÊN PHÂN TÍCH TOÀN DIỆN
                    target_side = self.get_next_side_based_on_comprehensive_analysis()
                    
                    if target_side:
                        if current_time - self.last_trade_time > 60 and current_time - self.last_close_time > self.cooldown_period:
                            if self.open_position(target_side):
                                self.last_trade_time = current_time
                            else:
                                time.sleep(1)
                        else:
                            time.sleep(1)
                    else:
                        time.sleep(1)
                
                if self.position_open and not self._close_attempted:
                    self.check_tp_sl()
                    
                time.sleep(1)
            
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    self.log(f"❌ Lỗi hệ thống: {str(e)}")
                    self.last_error_log_time = time.time()
                time.sleep(1)

    def _handle_price_update(self, price):
        """Xử lý cập nhật giá realtime"""
        self.current_price = price
        self.prices.append(price)
        
        # Giữ lịch sử giá trong giới hạn
        if len(self.prices) > 100:
            self.prices.pop(0)

    def stop(self):
        self._stop = True
        if self.symbol:
            try:
                self.ws_manager.remove_symbol(self.symbol)
            except Exception:
                pass
            try:
                self.coin_manager.unregister_coin(self.symbol)
            except Exception:
                pass
            try:
                cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            except Exception:
                pass
        self.log("🔴 Bot dừng")


    def open_position(self, side):
        if side not in ["BUY", "SELL"]:
            self.log(f"❌ Side không hợp lệ: {side}")
            return False

        # ✅ lock theo symbol để tránh race
        if self.symbol_locks and self.symbol:
            lock = self.symbol_locks[self.symbol]
        else:
            lock = threading.Lock()  # fallback nếu thiếu dict hoặc symbol

        with lock:
            try:
                # luôn kiểm tra lại trước khi đặt lệnh
                self.check_position_status()
                if self.position_open:
                    self.log(f"⚠️ Đã có vị thế {self.side}, bỏ qua tín hiệu {side}")
                    return False

                if self.should_be_removed:
                    self.log("⚠️ Bot đã được đánh dấu xóa, không mở lệnh mới")
                    return False

                # kiểm tra & đặt leverage
                current_leverage = self.coin_finder.get_symbol_leverage(self.symbol)
                if current_leverage < self.lev:
                    self.log(f"❌ Coin {self.symbol} chỉ hỗ trợ đòn bẩy {current_leverage}x < {self.lev}x -> TÌM COIN KHÁC")
                    self._cleanup_symbol()
                    return False

                if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                    self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x -> TÌM COIN KHÁC")
                    self._cleanup_symbol()
                    return False

                # số dư
                balance = get_balance(self.api_key, self.api_secret)
                if balance is None or balance <= 0:
                    self.log("❌ Không đủ số dư")
                    return False

                # giá & step
                current_price = get_current_price(self.symbol)
                if current_price <= 0:
                    self.log(f"❌ Lỗi lấy giá {self.symbol}: {current_price} -> TÌM COIN KHÁC")
                    self._cleanup_symbol()
                    return False

                step_size = get_step_size(self.symbol, self.api_key, self.api_secret)

                # tính khối lượng
                usd_amount = balance * (self.percent / 100)
                qty = (usd_amount * self.lev) / current_price
                if step_size > 0:
                    qty = math.floor(qty / step_size) * step_size
                    qty = round(qty, 8)

                if qty <= 0 or qty < step_size:
                    self.log(f"❌ Khối lượng không hợp lệ: {qty} (step: {step_size}) -> TÌM COIN KHÁC")
                    self._cleanup_symbol()
                    return False

                self.log(f"📊 Đang đặt lệnh {side} - SL: {step_size}, Qty: {qty}, Giá: {current_price}")

                cancel_all_orders(self.symbol, self.api_key, self.api_secret)
                time.sleep(0.2)

                result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
                if result and 'orderId' in result:
                    executed_qty = float(result.get('executedQty', 0))
                    avg_price = float(result.get('avgPrice', current_price))

                    # ✅ chỉ xác nhận mở khi thực sự có khối lượng khớp
                    if executed_qty >= 0:
                        self.entry = avg_price
                        self.entry_base = avg_price
                        self.average_down_count = 0
                        self.side = side
                        self.qty = executed_qty if side == "BUY" else -executed_qty
                        self.position_open = True
                        self.status = "open"

                        self.last_side = side
                        self.is_first_trade = False

                        self.high_water_mark_roi = 0
                        self.roi_check_activated = False

                        roi_trigger_info = f" | 🎯 ROI Trigger: {self.roi_trigger}%" if self.roi_trigger else ""
                        analysis_info = f" | 📊 Phân tích: LONG={self.global_long_count} vị thế, PnL={self.global_long_pnl:.2f} USDC | SHORT={self.global_short_count} vị thế, PnL={self.global_short_pnl:.2f} USDC"

                        message = (
                            f"✅ <b>ĐÃ MỞ VỊ THẾ {self.symbol}</b>\n"
                            f"🤖 Chiến lược: {self.strategy_name}\n"
                            f"📌 Hướng: {side}\n"
                            f"🏷️ Giá vào: {self.entry:.4f}\n"
                            f"📊 Khối lượng: {abs(self.qty):.4f}\n"
                            f"💵 Giá trị: {abs(self.qty) * self.entry:.2f} USDC\n"
                            f"💰 Đòn bẩy: {self.lev}x\n"
                            f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%{roi_trigger_info}{analysis_info}"
                        )
                        self.log(message)
                        return True
                    else:
                        self.log(f"❌ Lệnh không khớp (executed_qty={executed_qty}) -> TÌM COIN KHÁC")
                        self._cleanup_symbol()
                        return False
                else:
                    error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                    self.log(f"❌ Lỗi đặt lệnh {side}: {error_msg} -> TÌM COIN KHÁC")
                    if result and 'code' in result:
                        self.log(f"📋 Mã lỗi Binance: {result['code']} - {result.get('msg', '')}")
                    self._cleanup_symbol()
                    return False

            except Exception as e:
                self.log(f"❌ Lỗi mở lệnh: {str(e)} -> TÌM COIN KHÁC")
                self._cleanup_symbol()
                return False

    
    def _cleanup_symbol(self):
        """Dọn dẹp symbol hiện tại và chuyển về trạng thái tìm kiếm"""
        if self.symbol:
            try:
                self.ws_manager.remove_symbol(self.symbol)
                self.coin_manager.unregister_coin(self.symbol)
                self.log(f"🧹 Đã dọn dẹp symbol {self.symbol}")
            except Exception as e:
                self.log(f"⚠️ Lỗi khi dọn dẹp symbol: {str(e)}")
            
            self.symbol = None
        
        # Reset hoàn toàn trạng thái
        self.status = "searching"
        self.position_open = False
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.entry_base = 0
        self.average_down_count = 0
        self.high_water_mark_roi = 0
        self.roi_check_activated = False
        
        self.log("🔄 Đã reset bot, sẵn sàng tìm coin mới")

    def close_position(self, reason=""):
        try:
            self.check_position_status()
            
            if not self.position_open or abs(self.qty) <= 0:
                self.log(f"⚠️ Không có vị thế để đóng: {reason}")
                return False

            current_time = time.time()
            if self._close_attempted and current_time - self._last_close_attempt < 30:
                self.log(f"⚠️ Đang thử đóng lệnh lần trước, chờ...")
                return False
            
            self._close_attempted = True
            self._last_close_attempt = current_time

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
                    f"🤖 Chiến lược: {self.strategy_name}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDC\n"
                    f"📈 Số lần nhồi: {self.average_down_count}\n"
                    f"🔄 Tự động tìm bot mới sau khi đóng lệnh"
                )
                self.log(message)
                
                # CƠ CHẾ MỚI: Tìm bot mới sau khi đóng lệnh
                if self.find_new_bot_after_close:
                    self.log("🔄 Đang tìm bot mới sau khi đóng lệnh...")
                    self._cleanup_symbol()  # Reset hoàn toàn để tìm bot mới
                
                self.last_close_time = time.time()
                
                time.sleep(2)
                self.check_position_status()
                
                return True
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đóng lệnh: {error_msg}")
                self._close_attempted = False
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            self._close_attempted = False
            return False

    def check_tp_sl(self):
        if not self.symbol or not self.position_open or self.entry <= 0 or self._close_attempted:
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

        # CẬP NHẬT ROI CAO NHẤT
        if roi > self.high_water_mark_roi:
            self.high_water_mark_roi = roi

        # KIỂM TRA ĐIỀU KIỆN ROI TRIGGER
        if self.roi_trigger is not None and self.high_water_mark_roi >= self.roi_trigger and not self.roi_check_activated:
            self.roi_check_activated = True
            self.log(f"🎯 ĐÃ ĐẠT ROI {self.roi_trigger}% - KÍCH HOẠT CƠ CHẾ CHỐT LỆNH")

        # TP/SL TRUYỀN THỐNG
        if self.tp is not None and roi >= self.tp:
            self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
        elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
            self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")

    def check_averaging_down(self):
        """Kiểm tra và thực hiện nhồi lệnh Fibonacci khi lỗ THEO ROI ÂM"""
        if not self.position_open or not self.entry_base or self.average_down_count >= self.max_average_down_count:
            return
            
        try:
            current_time = time.time()
            if current_time - self.last_average_down_time < self.average_down_cooldown:
                return
                
            current_price = get_current_price(self.symbol)
            if current_price < 0:
                return
                
            # Tính ROI ÂM hiện tại (lỗ)
            if self.side == "BUY":
                profit = (current_price - self.entry_base) * abs(self.qty)
            else:
                profit = (self.entry_base - current_price) * abs(self.qty)
                
            invested = self.entry_base * abs(self.qty) / self.lev
            if invested < 0:
                return
                
            current_roi = (profit / invested) * 100
            
            # Chỉ xét khi ROI ÂM (đang lỗ)
            if current_roi >= 0:
                return
                
            # Chuyển ROI âm thành số dương để so sánh
            roi_negative = abs(current_roi)
            
            # Các mốc Fibonacci NHÂN 100 để nhồi lệnh (200%, 300%, 500%, ...)
            fib_levels = [200, 300, 500, 800, 1300, 2100, 3400]
            
            if self.average_down_count < len(fib_levels):
                current_fib_level = fib_levels[self.average_down_count]
                
                # Kiểm tra nếu ROI âm đạt mốc Fibonacci
                if roi_negative >= current_fib_level:
                    # Thực hiện nhồi lệnh
                    if self.execute_average_down_order():
                        self.last_average_down_time = current_time
                        self.average_down_count += 1
                        
                        # Log thông tin nhồi lệnh
                        self.log(f"📈 Đã kích hoạt nhồi lệnh Fibonacci ở mốc {current_fib_level}% lỗ (ROI: {current_roi:.2f}%)")
                        
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra nhồi lệnh: {str(e)}")

    def execute_average_down_order(self):
        """Thực hiện lệnh nhồi theo Fibonacci"""
        try:
            # Tính khối lượng nhồi lệnh
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                return False
                
            current_price = get_current_price(self.symbol)
            if current_price < 0:
                return False
                
            # Khối lượng nhồi = % số dư * (số lần nhồi + 1) để tăng dần
            additional_percent = self.percent * (self.average_down_count + 1)
            usd_amount = balance * (additional_percent / 100)
            qty = (usd_amount * self.lev) / current_price
            
            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
            
            if qty < step_size:
                return False
                
            # Đặt lệnh cùng hướng với vị thế hiện tại
            result = place_order(self.symbol, self.side, qty, self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty >= 0:
                    # Cập nhật giá trung bình và khối lượng
                    total_qty = abs(self.qty) + executed_qty
                    self.entry = (abs(self.qty) * self.entry + executed_qty * avg_price) / total_qty
                    self.qty = total_qty if self.side == "BUY" else -total_qty
                    
                    # Tính ROI mới sau khi nhồi
                    if self.side == "BUY":
                        new_profit = (current_price - self.entry) * abs(self.qty)
                    else:
                        new_profit = (self.entry - current_price) * abs(self.qty)
                        
                    new_invested = self.entry * abs(self.qty) / self.lev
                    new_roi = (new_profit / new_invested) * 100 if new_invested > 0 else 0
                    
                    message = (
                        f"📈 <b>ĐÃ NHỒI LỆNH FIBONACCI {self.symbol}</b>\n"
                        f"🔢 Lần nhồi: {self.average_down_count + 1}\n"
                        f"📊 Khối lượng thêm: {executed_qty:.4f}\n"
                        f"🏷️ Giá nhồi: {avg_price:.4f}\n"
                        f"📈 Giá trung bình mới: {self.entry:.4f}\n"
                        f"💰 Tổng khối lượng: {total_qty:.4f}\n"
                        f"📉 ROI sau nhồi: {new_roi:.2f}%"
                    )
                    self.log(message)
                    return True
                    
            return False
            
        except Exception as e:
            self.log(f"❌ Lỗi nhồi lệnh: {str(e)}")
            return False

    def log(self, message):
        logger.info(f"[{self.bot_id}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>{self.bot_id}</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

# ========== BOT GLOBAL MARKET VỚI CƠ CHẾ PHÂN TÍCH TOÀN DIỆN ==========
class GlobalMarketBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager,
                 api_key, api_secret, telegram_bot_token, telegram_chat_id, bot_id=None, **kwargs):
        super().__init__(symbol, lev, percent, tp, sl, roi_trigger, ws_manager,
                         api_key, api_secret, telegram_bot_token, telegram_chat_id,
                         "Global-Market-Toàn-Diện", bot_id=bot_id, **kwargs)
# ========== BOT MANAGER HOÀN CHỈNH VỚI CƠ CHẾ PHÂN TÍCH TOÀN DIỆN ==========
class BotManager:
    def __init__(self, api_key=None, api_secret=None, telegram_bot_token=None, telegram_chat_id=None):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}

        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id

        # ✅ tài nguyên dùng chung cho tất cả bot
        self.coin_manager = CoinManager()
        self.symbol_locks = defaultdict(threading.Lock)

        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT VỚI CƠ CHẾ PHÂN TÍCH TOÀN DIỆN ĐÃ KHỞI ĐỘNG")

            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()

            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)
        else:
            self.log("⚡ BotManager khởi động ở chế độ không config")

    def _verify_api_connection(self):
        """Kiểm tra kết nối API"""
        try:
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                self.log("❌ LỖI: Không thể kết nối Binance API. Kiểm tra:")
                self.log("   - API Key và Secret có đúng không?")
                self.log("   - Có thể bị chặn IP (lỗi 451), thử dùng VPN")
                self.log("   - Kiểm tra kết nối internet")
                return False
            else:
                self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDC")
                return True
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra kết nối: {str(e)}")
            return False

    def get_position_summary(self):
        """Lấy thống kê tổng quan"""
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            total_long_count = 0
            total_short_count = 0
            total_long_pnl = 0
            total_short_pnl = 0
            total_unrealized_pnl = 0
            binance_positions = []
            
            # Tính toán toàn diện từ Binance
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry_price = float(pos.get('entryPrice', 0))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    leverage = float(pos.get('leverage', 1))
                    position_value = abs(position_amt) * entry_price / leverage
                    
                    total_unrealized_pnl += unrealized_pnl
                    
                    if position_amt > 0:
                        total_long_count += 1
                        total_long_pnl += unrealized_pnl
                        binance_positions.append({
                            'symbol': symbol,
                            'side': 'LONG',
                            'leverage': leverage,
                            'size': abs(position_amt),
                            'entry': entry_price,
                            'value': position_value,
                            'pnl': unrealized_pnl
                        })
                    else:
                        total_short_count += 1
                        total_short_pnl += unrealized_pnl
                        binance_positions.append({
                            'symbol': symbol, 
                            'side': 'SHORT',
                            'leverage': leverage,
                            'size': abs(position_amt),
                            'entry': entry_price,
                            'value': position_value,
                            'pnl': unrealized_pnl
                        })
        
            # Thống kê bot
            bot_details = []
            searching_bots = 0
            waiting_bots = 0
            trading_bots = 0
            
            for bot_id, bot in self.bots.items():
                bot_info = {
                    'bot_id': bot_id,
                    'symbol': bot.symbol or 'Đang tìm...',
                    'status': bot.status,
                    'side': bot.side,
                    'leverage': bot.lev,
                    'percent': bot.percent,
                    'tp': bot.tp,
                    'sl': bot.sl,
                    'roi_trigger': bot.roi_trigger,
                    'last_side': bot.last_side,
                    'is_first_trade': bot.is_first_trade,
                    'global_long_count': bot.global_long_count,
                    'global_short_count': bot.global_short_count,
                    'global_long_pnl': bot.global_long_pnl,
                    'global_short_pnl': bot.global_short_pnl,
                    'average_down_count': bot.average_down_count
                }
                bot_details.append(bot_info)
                
                if bot.status == "searching":
                    searching_bots += 1
                elif bot.status == "waiting":
                    waiting_bots += 1
                elif bot.status == "open":
                    trading_bots += 1
            
            # Tạo báo cáo chi tiết
            summary = "📊 **THỐNG KÊ CHI TIẾT HỆ THỐNG**\n\n"
            
            # Phần 1: Số dư
            balance = get_balance(self.api_key, self.api_secret)
            if balance is not None:
                summary += f"💰 **SỐ DƯ**: {balance:.2f} USDC\n"
                summary += f"📈 **Tổng PnL**: {total_unrealized_pnl:.2f} USDC\n\n"
            else:
                summary += f"💰 **SỐ DƯ**: ❌ Lỗi kết nối\n\n"
            
            # Phần 2: Bot hệ thống
            summary += f"🤖 **BOT HỆ THỐNG**: {len(self.bots)} bots\n"
            summary += f"   🔍 Đang tìm coin: {searching_bots}\n"
            summary += f"   🟡 Đang chờ: {waiting_bots}\n" 
            summary += f"   📈 Đang trade: {trading_bots}\n\n"
            
            # Phần 3: Phân tích toàn diện
            summary += f"📈 **PHÂN TÍCH TOÀN DIỆN**:\n"
            summary += f"   📊 Số lượng: LONG={total_long_count} | SHORT={total_short_count}\n"
            summary += f"   💰 PnL: LONG={total_long_pnl:.2f} USDC | SHORT={total_short_pnl:.2f} USDC\n"
            summary += f"   ⚖️ Chênh lệch: {abs(total_long_pnl - total_short_pnl):.2f} USDC\n\n"
            
            # Phần 4: Chi tiết từng bot
            if bot_details:
                summary += "📋 **CHI TIẾT TỪNG BOT**:\n"
                for bot in bot_details[:8]:
                    symbol_info = bot['symbol'] if bot['symbol'] != 'Đang tìm...' else '🔍 Đang tìm'
                    status_map = {
                        "searching": "🔍 Tìm coin",
                        "waiting": "🟡 Chờ tín hiệu", 
                        "open": "🟢 Đang trade"
                    }
                    status = status_map.get(bot['status'], bot['status'])
                    
                    roi_info = f" | 🎯 ROI: {bot['roi_trigger']}%" if bot['roi_trigger'] else ""
                    trade_info = f" | Lệnh đầu" if bot['is_first_trade'] else f" | Tiếp theo dựa trên phân tích toàn diện"
                    
                    summary += f"   🔹 {bot['bot_id'][:15]}...\n"
                    summary += f"      📊 {symbol_info} | {status}{trade_info}\n"
                    summary += f"      💰 ĐB: {bot['leverage']}x | Vốn: {bot['percent']}%{roi_info}\n"
                    if bot['tp'] is not None and bot['sl'] is not None:
                        summary += f"      🎯 TP: {bot['tp']}% | 🛡️ SL: {bot['sl']}%\n"
                    summary += f"      📊 Phân tích: LONG={bot['global_long_count']} vị thế, PnL={bot['global_long_pnl']:.2f} | SHORT={bot['global_short_count']} vị thế, PnL={bot['global_short_pnl']:.2f}\n"
                    if bot['average_down_count'] > 0:
                        summary += f"      📈 Số lần nhồi: {bot['average_down_count']}\n"
                    summary += "\n"
                
                if len(bot_details) > 8:
                    summary += f"   ... và {len(bot_details) - 8} bot khác\n\n"
            
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
            "🤖 <b>BOT GIAO DỊCH FUTURES ĐA LUỒNG</b>\n\n"
            "🎯 <b>HỆ THỐNG VỚI CƠ CHẾ PHÂN TÍCH TOÀN DIỆN</b>\n\n"
            "📊 <b>Phân tích toàn diện:</b>\n"
            "• Kết hợp cả SỐ LƯỢNG vị thế và TỔNG LỢI NHUẬN (cả âm và dương)\n"
            "• Xem xét cả số lượng LONG/SHORT và PnL của từng loại\n"
            "• Quyết định dựa trên phân tích đa chiều\n\n"
            "📈 <b>Quy tắc quyết định:</b>\n"
            "• Nhiều LONG hơn -> Ưu tiên SELL\n"
            "• Nhiều SHORT hơn -> Ưu tiên BUY\n"
            "• PnL LONG thấp hơn -> Ưu tiên BUY\n"
            "• PnL SHORT thấp hơn -> Ưu tiên SELL\n"
            "• Bằng nhau -> Chọn ngẫu nhiên\n\n"
            "📈 <b>Nhồi lệnh Fibonacci theo ROI:</b>\n"
            "• Khi ROI ÂM đạt các mốc Fibonacci (200%, 300%, 500%, ...)\n"
            "• Tự động nhồi lệnh để giảm giá trung bình\n"
            "• Các mốc: 200%, 300%, 500%, 800%, 1300%, 2100%, 3400%\n\n"
            "🔄 <b>Tìm bot mới sau đóng lệnh:</b>\n"
            "• Mỗi khi đóng lệnh -> Tự động tìm coin mới\n"
            "• Luôn thay đổi coin giao dịch\n"
            "• Đa dạng hóa rủi ro"
        )
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bot(self, symbol, lev, percent, tp, sl, roi_trigger, strategy_type, bot_count=1, **kwargs):
        if sl == 0:
            sl = None
            
        if not self.api_key or not self.api_secret:
            self.log("❌ Chưa thiết lập API Key trong BotManager")
            return False
        
        # Kiểm tra kết nối trước khi tạo bot
        if not self._verify_api_connection():
            self.log("❌ KHÔNG THỂ KẾT NỐI BINANCE - KHÔNG THỂ TẠO BOT")
            return False
        
        bot_mode = kwargs.get('bot_mode', 'static')
        created_count = 0
        
        for i in range(bot_count):
            try:
                if bot_mode == 'static' and symbol:
                    bot_id = f"{symbol}_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = GlobalMarketBot
                    
                    if not bot_class:
                        continue
                    
                    bot = bot_class(
                        symbol, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                        self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id,
                        coin_manager=self.coin_manager,          # ✅ thêm
                        symbol_locks=self.symbol_locks,          # ✅ thêm
                        bot_id=bot_id
                    )


                    
                else:
                    bot_id = f"DYNAMIC_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = GlobalMarketBot
                    
                    if not bot_class:
                        continue
                    
                    bot = bot_class(
                        None, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                        self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id,
                        coin_manager=self.coin_manager,          # ✅ thêm
                        symbol_locks=self.symbol_locks,          # ✅ thêm
                        bot_id=bot_id
                    )

                
                bot._bot_manager = self
                self.bots[bot_id] = bot
                created_count += 1
                
            except Exception as e:
                self.log(f"❌ Lỗi tạo bot {i}: {str(e)}")
                continue
        
        if created_count > 0:
            roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else " | 🎯 ROI Trigger: Tắt"
            
            success_msg = (
                f"✅ <b>ĐÃ TẠO {created_count}/{bot_count} BOT PHÂN TÍCH TOÀN DIỆN</b>\n\n"
                f"🎯 Hệ thống: Phân tích toàn diện (số lượng + PnL)\n"
                f"💰 Đòn bẩy: {lev}x\n"
                f"📈 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl if sl is not None else 'Tắt'}%{roi_info}\n"
                f"🔧 Chế độ: {bot_mode}\n"
            )
            
            if bot_mode == 'static' and symbol:
                success_msg += f"🔗 Coin: {symbol}\n"
            else:
                success_msg += f"🔗 Coin: Tự động tìm kiếm\n"
            
            success_msg += f"\n📊 <b>CƠ CHẾ PHÂN TÍCH TOÀN DIỆN ĐÃ KÍCH HOẠT</b>\n"
            success_msg += f"📈 Xem xét cả số lượng và PnL (cả âm và dương)\n"
            success_msg += f"⚖️ Quyết định dựa trên phân tích đa chiều\n"
            success_msg += f"🔄 Kết hợp: Số lượng + Lợi nhuận = Quyết định tối ưu\n\n"
            success_msg += f"📈 <b>NHỒI LỆNH FIBONACCI THEO ROI</b>\n"
            success_msg += f"🔢 Các mốc: 200%, 300%, 500%, 800%, 1300%, 2100%, 3400%\n"
            success_msg += f"⏰ Kiểm tra 10 giây/lần"
            
            self.log(success_msg)
            return True
        else:
            self.log("❌ Không thể tạo bot nào")
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
        
        # Xử lý các bước tạo bot
        if current_step == 'waiting_bot_count':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    bot_count = int(text)
                    if bot_count <= 0 or bot_count > 10:
                        send_telegram("⚠️ Số lượng bot phải từ 1 đến 10. Vui lòng chọn lại:",
                                    chat_id, create_bot_count_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['bot_count'] = bot_count
                    user_state['step'] = 'waiting_bot_mode'
                    
                    send_telegram(
                        f"🤖 Số lượng bot: {bot_count}\n\n"
                        f"Chọn chế độ bot:",
                        chat_id,
                        create_bot_mode_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho số lượng bot:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_bot_mode':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text in ["🤖 Bot Tĩnh - Coin cụ thể", "🔄 Bot Động - Tự tìm coin"]:
                if text == "🤖 Bot Tĩnh - Coin cụ thể":
                    user_state['bot_mode'] = 'static'
                    user_state['step'] = 'waiting_symbol'
                    send_telegram(
                        "🎯 <b>ĐÃ CHỌN: BOT TĨNH</b>\n\n"
                        "🤖 Bot sẽ giao dịch coin CỐ ĐỊNH\n"
                        "📊 Bạn cần chọn coin cụ thể\n\n"
                        "Chọn coin:",
                        chat_id,
                        create_symbols_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                else:
                    user_state['bot_mode'] = 'dynamic'
                    user_state['step'] = 'waiting_leverage'
                    send_telegram(
                        "🎯 <b>ĐÃ CHỌN: BOT ĐỘNG</b>\n\n"
                        f"🤖 Hệ thống sẽ tạo <b>{user_state.get('bot_count', 1)} bot độc lập</b>\n"
                        f"🔄 Mỗi bot tự tìm coin & trade độc lập\n\n"
                        "Chọn đòn bẩy:",
                        chat_id,
                        create_leverage_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )

        elif current_step == 'waiting_symbol':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                user_state['symbol'] = text
                user_state['step'] = 'waiting_leverage'
                send_telegram(
                    f"🔗 Coin: {text}\n\n"
                    f"Chọn đòn bẩy:",
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
                if text.endswith('x'):
                    lev_text = text[:-1]
                else:
                    lev_text = text

                try:
                    leverage = int(lev_text)
                    if leverage <= 0 or leverage > 100:
                        send_telegram("⚠️ Đòn bẩy phải từ 1 đến 100. Vui lòng chọn lại:",
                                    chat_id, create_leverage_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['leverage'] = leverage
                    user_state['step'] = 'waiting_percent'
                    
                    balance = get_balance(self.api_key, self.api_secret)
                    balance_info = f"\n💰 Số dư hiện có: {balance:.2f} USDT" if balance else ""
                    
                    send_telegram(
                        f"💰 Đòn bẩy: {leverage}x{balance_info}\n\n"
                        f"Chọn % số dư cho mỗi lệnh:",
                        chat_id,
                        create_percent_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho đòn bẩy:",
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
                    if percent <= 0 or percent > 100:
                        send_telegram("⚠️ % số dư phải từ 0.1 đến 100. Vui lòng chọn lại:",
                                    chat_id, create_percent_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['percent'] = percent
                    user_state['step'] = 'waiting_tp'
                    
                    balance = get_balance(self.api_key, self.api_secret)
                    actual_amount = balance * (percent / 100) if balance else 0
                    
                    send_telegram(
                        f"📊 % Số dư: {percent}%\n"
                        f"💵 Số tiền mỗi lệnh: ~{actual_amount:.2f} USDT\n\n"
                        f"Chọn Take Profit (%):",
                        chat_id,
                        create_tp_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho % số dư:",
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
                    if tp <= 0:
                        send_telegram("⚠️ Take Profit phải lớn hơn 0. Vui lòng chọn lại:",
                                    chat_id, create_tp_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['tp'] = tp
                    user_state['step'] = 'waiting_sl'
                    
                    send_telegram(
                        f"🎯 Take Profit: {tp}%\n\n"
                        f"Chọn Stop Loss (%):",
                        chat_id,
                        create_sl_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho Take Profit:",
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
                    if sl < 0:
                        send_telegram("⚠️ Stop Loss phải lớn hơn hoặc bằng 0. Vui lòng chọn lại:",
                                    chat_id, create_sl_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['sl'] = sl
                    user_state['step'] = 'waiting_roi_trigger'
                    
                    send_telegram(
                        f"🛡️ Stop Loss: {sl}%\n\n"
                        f"🎯 <b>CHỌN NGƯỠNG ROI ĐỂ KÍCH HOẠT CƠ CHẾ CHỐT LỆNH THÔNG MINH</b>\n\n"
                        f"Chọn ngưỡng ROI trigger (%):",
                        chat_id,
                        create_roi_trigger_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho Stop Loss:",
                                chat_id, create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_roi_trigger':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text == '❌ Tắt tính năng':
                user_state['roi_trigger'] = None
                self._finish_bot_creation(chat_id, user_state)
            else:
                try:
                    roi_trigger = float(text)
                    if roi_trigger <= 0:
                        send_telegram("⚠️ ROI Trigger phải lớn hơn 0. Vui lòng chọn lại:",
                                    chat_id, create_roi_trigger_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['roi_trigger'] = roi_trigger
                    self._finish_bot_creation(chat_id, user_state)
                    
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho ROI Trigger:",
                                chat_id, create_roi_trigger_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_bot_count'}
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key và kết nối mạng!", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"🎯 <b>CHỌN SỐ LƯỢNG BOT ĐỘC LẬP</b>\n\n"
                f"💰 Số dư hiện có: <b>{balance:.2f} USDT</b>\n\n"
                f"Chọn số lượng bot độc lập bạn muốn tạo:",
                chat_id,
                create_bot_count_keyboard(),
                self.telegram_bot_token, self.telegram_chat_id
            )
        
        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                message = "🤖 <b>DANH SÁCH BOT ĐỘC LẬP ĐANG CHẠY</b>\n\n"
                
                searching_bots = 0
                trading_bots = 0
                
                for bot_id, bot in self.bots.items():
                    if bot.status == "searching":
                        status = "🔍 Đang tìm coin"
                        searching_bots += 1
                    elif bot.status == "waiting":
                        status = "🟡 Chờ tín hiệu"
                        trading_bots += 1
                    elif bot.status == "open":
                        status = "🟢 Đang trade"
                        trading_bots += 1
                    else:
                        status = "⚪ Unknown"
                    
                    roi_info = f" | 🎯 ROI: {bot.roi_trigger}%" if bot.roi_trigger else ""
                    symbol_info = bot.symbol if bot.symbol else "Đang tìm..."
                    next_trade = "Lệnh đầu" if bot.is_first_trade else f"Tiếp: {'SELL' if bot.last_side == 'BUY' else 'BUY'}"
                    
                    message += f"🔹 {bot_id}\n"
                    message += f"   📊 {symbol_info} | {status}\n"
                    message += f"   💰 ĐB: {bot.lev}x | Vốn: {bot.percent}%{roi_info}\n"
                    message += f"   🔄 {next_trade}\n\n"
                
                message += f"📈 Tổng số: {len(self.bots)} bot\n"
                message += f"🔍 Đang tìm coin: {searching_bots} bot\n"
                message += f"📊 Đang trade: {trading_bots} bot"
                
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
                message = "⛔ <b>CHỌN BOT ĐỂ DỪNG</b>\n\n"
                keyboard = []
                row = []
                
                for i, bot_id in enumerate(self.bots.keys()):
                    bot = self.bots[bot_id]
                    symbol_info = bot.symbol if bot.symbol else "No Coin"
                    message += f"🔹 {bot_id} - {symbol_info}\n"
                    row.append({"text": f"⛔ {bot_id}"})
                    if len(row) == 1 or i == len(self.bots) - 1:
                        keyboard.append(row)
                        row = []
                
                keyboard.append([{"text": "⛔ DỪNG TẤT CẢ"}])
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                
                send_telegram(
                    message, 
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
            try:
                balance = get_balance(self.api_key, self.api_secret)
                if balance is None:
                    send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key và kết nối mạng!", chat_id,
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
                "🎯 <b>HỆ THỐNG VỚI CƠ CHẾ LUÔN NGƯỢC HƯỚNG</b>\n\n"
                
                "🔄 <b>Cơ chế luôn ngược hướng:</b>\n"
                "• Lần đầu: Chọn ngẫu nhiên BUY/SELL\n"
                "• Các lần sau: LUÔN vào lệnh ngược với lệnh trước\n"
                "• Áp dụng cho cả đóng lệnh thủ công trên Binance\n"
                "• Giữ nguyên coin, chỉ tìm mới khi có lỗi\n\n"
                
                "🔍 <b>Tìm coin thông minh:</b>\n"
                "• Tự động chọn từ 300 coin USDT\n"
                "• Kiểm tra đòn bẩy tối đa của coin\n"
                "• Tránh trùng lặp với các bot khác\n\n"
                
                "💰 <b>Quản lý rủi ro:</b>\n"
                "• TP/SL cố định theo %\n"
                "• Cơ chế ROI Trigger thông minh\n"
                "• Nhồi lệnh Fibonacci khi drawdown"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            
            searching_bots = sum(1 for bot in self.bots.values() if bot.status == "searching")
            trading_bots = sum(1 for bot in self.bots.values() if bot.status in ["waiting", "open"])
            
            roi_bots = sum(1 for bot in self.bots.values() if bot.roi_trigger is not None)
            first_trade_bots = sum(1 for bot in self.bots.values() if bot.is_first_trade)
            
            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG ĐA LUỒNG</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Tổng số bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots} bot\n"
                f"📊 Đang trade: {trading_bots} bot\n"
                f"🎯 Bot có ROI Trigger: {roi_bots} bot\n"
                f"🔄 Bot chờ lệnh đầu: {first_trade_bots} bot\n"
                f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối\n\n"
                f"🔄 <b>CƠ CHẾ LUÔN NGƯỢC HƯỚNG ĐANG HOẠT ĐỘNG</b>"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

    def _finish_bot_creation(self, chat_id, user_state):
        """Hoàn tất quá trình tạo bot"""
        try:
            # Lấy tất cả thông tin từ user_state
            bot_mode = user_state.get('bot_mode', 'static')
            leverage = user_state.get('leverage')
            percent = user_state.get('percent')
            tp = user_state.get('tp')
            sl = user_state.get('sl')
            roi_trigger = user_state.get('roi_trigger')
            symbol = user_state.get('symbol')
            bot_count = user_state.get('bot_count', 1)
            
            success = self.add_bot(
                symbol=symbol,
                lev=leverage,
                percent=percent,
                tp=tp,
                sl=sl,
                roi_trigger=roi_trigger,
                strategy_type="Global-Market-Tổng-Lỗ",
                bot_mode=bot_mode,
                bot_count=bot_count
            )
            
            if success:
                roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else ""
                
                success_msg = (
                    f"✅ <b>ĐÃ TẠO {bot_count} BOT THÀNH CÔNG</b>\n\n"
                    f"🤖 Chiến lược: Tính tổng lỗ toàn tài khoản\n"
                    f"🔧 Chế độ: {bot_mode}\n"
                    f"🔢 Số lượng: {bot_count} bot độc lập\n"
                    f"💰 Đòn bẩy: {leverage}x\n"
                    f"📊 % Số dư: {percent}%\n"
                    f"🎯 TP: {tp}%\n"
                    f"🛡️ SL: {sl}%{roi_info}"
                )
                if bot_mode == 'static' and symbol:
                    success_msg += f"\n🔗 Coin: {symbol}"
                
                success_msg += f"\n\n📉 <b>CƠ CHẾ TÍNH TỔNG LỖ ĐÃ KÍCH HOẠT</b>\n"
                success_msg += f"📈 Lỗ LONG nhiều -> Ưu tiên SELL\n"
                success_msg += f"📉 Lỗ SHORT nhiều -> Ưu tiên BUY\n"
                success_msg += f"⚖️ Bằng nhau -> Chọn ngẫu nhiên\n\n"
                success_msg += f"📈 <b>NHỒI LỆNH FIBONACCI THEO ROI</b>\n"
                success_msg += f"🔢 Các mốc: 200%, 300%, 500%, 800%, 1300%, 2100%, 3400%\n"
                success_msg += f"⏰ Kiểm tra 10 giây/lần"
                
                send_telegram(success_msg, chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                send_telegram("❌ Có lỗi khi tạo bot. Vui lòng thử lại.",
                            chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            
            self.user_states[chat_id] = {}
            
        except Exception as e:
            send_telegram(f"❌ Lỗi tạo bot: {str(e)}", chat_id, create_main_menu(),
                        self.telegram_bot_token, self.telegram_chat_id)
            self.user_states[chat_id] = {}

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()
