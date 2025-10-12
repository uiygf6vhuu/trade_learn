# trading_bot_complete.py - HỆ THỐNG BOT TRADING HOÀN CHỈNH VỚI ROTATION COIN
import json
import hmac
import hashlib
import time
import threading
import urllib.request
import urllib.parse
import numpy as np
import requests
import math
import random
import logging
from datetime import datetime

# ========== CẤU HÌNH LOGGING ==========
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_trading.log')
        ]
    )
    return logging.getLogger()

logger = setup_logging()

# ========== HÀM TELEGRAM ==========
def send_telegram(message, chat_id=None, reply_markup=None, bot_token=None, default_chat_id=None):
    if not bot_token:
        return
    
    chat_id = chat_id or default_chat_id
    if not chat_id:
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
    except Exception as e:
        logger.error(f"Lỗi kết nối Telegram: {str(e)}")

# ========== MENU TELEGRAM ==========
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

def create_leverage_keyboard():
    leverages = ["3", "5", "10", "15", "20", "25"]
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
    return {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True}

def create_percent_keyboard():
    return {
        "keyboard": [
            [{"text": "1"}, {"text": "3"}, {"text": "5"}, {"text": "10"}],
            [{"text": "15"}, {"text": "20"}, {"text": "25"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_tp_keyboard():
    return {
        "keyboard": [
            [{"text": "50"}, {"text": "100"}, {"text": "200"}],
            [{"text": "300"}, {"text": "500"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_sl_keyboard():
    return {
        "keyboard": [
            [{"text": "50"}, {"text": "100"}, {"text": "150"}],
            [{"text": "200"}, {"text": "500"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_bot_count_keyboard():
    return {
        "keyboard": [
            [{"text": "1"}, {"text": "2"}, {"text": "3"}],
            [{"text": "5"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

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
        except Exception as e:
            logger.error(f"Lỗi kết nối API: {str(e)}")
            time.sleep(1)
    return None

def get_all_usdt_pairs(limit=100):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT"]
        
        usdt_pairs = []
        for symbol_info in data.get('symbols', []):
            symbol = symbol_info.get('symbol', '')
            if symbol.endswith('USDT') and symbol_info.get('status') == 'TRADING':
                usdt_pairs.append(symbol)
        
        return usdt_pairs[:limit] if limit else usdt_pairs
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy danh sách coin: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT"]

def get_step_size(symbol, api_key, api_secret):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
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
        return response is not None
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

# ========== PHÂN TÍCH VOLUME VÀ NẾN ==========
class VolumeCandleAnalyzer:
    def __init__(self):
        self.volume_threshold = 1.2
        self.small_body_ratio = 0.3
        
    def analyze_volume_candle(self, symbol):
        try:
            intervals = ['5m', '15m']
            signals = []
            
            for interval in intervals:
                klines = self.get_klines(symbol, interval, 10)
                if not klines or len(klines) < 5:
                    continue
                    
                current_candle = klines[-1]
                prev_candles = klines[-5:-1]
                
                open_price = float(current_candle[1])
                close_price = float(current_candle[4])
                high = float(current_candle[2])
                low = float(current_candle[3])
                current_volume = float(current_candle[5])
                
                avg_volume = np.mean([float(c[5]) for c in prev_candles])
                
                is_green = close_price > open_price
                is_red = close_price < open_price
                
                body_size = abs(close_price - open_price)
                total_range = high - low
                is_small_body = body_size < total_range * self.small_body_ratio if total_range > 0 else False
                
                volume_increase = current_volume > avg_volume * self.volume_threshold
                volume_decrease = current_volume < avg_volume * 0.8
                
                if volume_increase and is_green:
                    signals.append("BUY")
                elif volume_increase and is_red:
                    signals.append("SELL")
                elif volume_decrease and is_small_body:
                    signals.append("BUY")
                else:
                    signals.append("NEUTRAL")
            
            if signals.count("BUY") >= 1:
                return "BUY"
            elif signals.count("SELL") >= 1:
                return "SELL"
            else:
                return "NEUTRAL"
                
        except Exception as e:
            logger.error(f"Lỗi phân tích volume nến {symbol}: {str(e)}")
            return "NEUTRAL"
    
    def get_klines(self, symbol, interval, limit):
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': interval,
                'limit': limit
            }
            return binance_api_request(url, params=params)
        except Exception as e:
            return None

# ========== QUẢN LÝ COIN CHUNG ==========
class CoinManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CoinManager, cls).__new__(cls)
                cls._instance.managed_coins = {}  # {symbol: bot_id}
                cls._instance.recently_closed = {}  # {symbol: close_time}
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
                # Thêm vào danh sách vừa đóng
                self.recently_closed[symbol] = time.time()
                return True
            return False
    
    def is_coin_managed(self, symbol):
        with self._lock:
            return symbol in self.managed_coins
    
    def get_managed_coins(self):
        with self._lock:
            return list(self.managed_coins.keys())
    
    def cleanup_old_closed(self):
        with self._lock:
            current_time = time.time()
            expired_coins = []
            for symbol, close_time in self.recently_closed.items():
                if current_time - close_time > 3600:  # 1 giờ
                    expired_coins.append(symbol)
            
            for symbol in expired_coins:
                del self.recently_closed[symbol]

# ========== BOT TRADING HOÀN CHỈNH ==========
class TradingBot:
    def __init__(self, lev, percent, tp, sl, api_key, api_secret, telegram_bot_token=None, telegram_chat_id=None, bot_id=None):
        self.lev = lev
        self.percent = percent
        self.tp = tp / 100  # Chuyển thành decimal
        self.sl = sl / 100  # Chuyển thành decimal
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.bot_id = bot_id or f"Bot_{int(time.time())}_{random.randint(1000, 9999)}"
        
        self.symbol = None
        self.status = "searching"  # searching, open
        self.side = ""
        self.entry_price = 0
        self.position_size = 0
        
        self.coin_manager = CoinManager()
        self.analyzer = VolumeCandleAnalyzer()
        
        self._stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        self.log(f"🟢 Bot khởi động - ĐB: {lev}x, Vốn: {percent}%, TP: {tp}%, SL: {sl}%")
    
    def log(self, message):
        logger.info(f"[Bot {self.bot_id}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            symbol_info = f"<b>{self.symbol}</b>" if self.symbol else "<i>Đang tìm coin...</i>"
            send_telegram(f"{symbol_info} (Bot {self.bot_id}): {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def _run(self):
        while not self._stop:
            try:
                if self.status == "searching":
                    self._find_and_open_position()
                elif self.status == "open":
                    self._check_tp_sl()
                
                time.sleep(10)
                
            except Exception as e:
                self.log(f"❌ Lỗi hệ thống: {str(e)}")
                time.sleep(30)
    
    def _find_and_open_position(self):
        try:
            # BƯỚC 1: Xác định hướng dựa trên vị thế hiện có
            target_direction = self._get_market_direction()
            if not target_direction:
                return
            
            # BƯỚC 2 & 3: Tìm coin phù hợp
            coin_data = self._find_qualified_coin(target_direction)
            if not coin_data:
                return
            
            symbol = coin_data['symbol']
            direction = coin_data['direction']
            
            # BƯỚC 4: Vào lệnh
            if self._open_position(symbol, direction):
                self.status = "open"
                self.log(f"✅ Đã vào lệnh {direction} {symbol}")
                
        except Exception as e:
            self.log(f"❌ Lỗi tìm và mở vị thế: {str(e)}")
    
    def _get_market_direction(self):
        try:
            positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            long_count = 0
            short_count = 0
            
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt > 0:
                    long_count += 1
                elif position_amt < 0:
                    short_count += 1
            
            self.log(f"📊 Vị thế hiện tại: {long_count} LONG, {short_count} SHORT")
            
            if long_count > short_count:
                return "SELL"
            elif short_count > long_count:
                return "BUY"
            else:
                return random.choice(["BUY", "SELL"])
                
        except Exception as e:
            self.log(f"❌ Lỗi xác định hướng: {str(e)}")
            return random.choice(["BUY", "SELL"])
    
    def _find_qualified_coin(self, target_direction):
        try:
            all_symbols = get_all_usdt_pairs(limit=100)
            if not all_symbols:
                return None
            
            # Lọc coin đang được quản lý và vừa đóng
            managed_coins = self.coin_manager.get_managed_coins()
            excluded_symbols = set(managed_coins)
            
            # Thêm coin vừa đóng gần đây
            current_time = time.time()
            for symbol, close_time in self.coin_manager.recently_closed.items():
                if current_time - close_time < 300:  # 5 phút
                    excluded_symbols.add(symbol)
            
            random.shuffle(all_symbols)
            
            for symbol in all_symbols:
                if symbol in excluded_symbols:
                    continue
                
                # Kiểm tra coin đã có vị thế chưa
                existing_positions = get_positions(symbol, self.api_key, self.api_secret)
                has_position = False
                for pos in existing_positions:
                    if float(pos.get('positionAmt', 0)) != 0:
                        has_position = True
                        break
                
                if has_position:
                    continue
                
                # Phân tích tín hiệu
                signal = self.analyzer.analyze_volume_candle(symbol)
                
                if signal == target_direction:
                    # Đăng ký coin với hệ thống
                    if self.coin_manager.register_coin(symbol, self.bot_id):
                        self.log(f"🎯 Tìm thấy {symbol} - {target_direction}")
                        return {
                            'symbol': symbol,
                            'direction': target_direction,
                            'qualified': True
                        }
                    else:
                        self.log(f"⚠️ Coin {symbol} đã có bot khác trade")
            
            return None
            
        except Exception as e:
            self.log(f"❌ Lỗi tìm coin: {str(e)}")
            return None
    
    def _open_position(self, symbol, direction):
        try:
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không đủ số dư")
                return False
            
            if not set_leverage(symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x")
                return False
            
            current_price = get_current_price(symbol)
            if current_price <= 0:
                self.log("❌ Lỗi lấy giá")
                return False
            
            # Tính số lượng: số dư * % số dư * đòn bẩy / giá
            usd_amount = balance * (self.percent / 100)
            position_value = usd_amount * self.lev
            qty = position_value / current_price
            
            step_size = get_step_size(symbol, self.api_key, self.api_secret)
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
            
            if qty < step_size:
                self.log(f"❌ Số lượng quá nhỏ: {qty}")
                return False
            
            self.log(f"📊 Đang đặt lệnh {direction} - SL: {step_size}, Qty: {qty}, Giá: {current_price}")
            
            result = place_order(symbol, direction, qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty > 0:
                    self.symbol = symbol
                    self.side = direction
                    self.entry_price = avg_price
                    self.position_size = executed_qty
                    
                    message = (
                        f"✅ <b>ĐÃ MỞ VỊ THẾ</b>\n"
                        f"🔗 Coin: {symbol}\n"
                        f"📌 Hướng: {direction}\n"
                        f"🏷️ Giá vào: {self.entry_price:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💵 Giá trị: {executed_qty * self.entry_price:.2f} USDT\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp*100}% | 🛡️ SL: {self.sl*100}%"
                    )
                    self.log(message)
                    return True
            
            self.log("❌ Không thể mở vị thế")
            return False
                    
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False
    
    def _check_tp_sl(self):
        if not self.symbol or self.entry_price <= 0:
            return
        
        current_price = get_current_price(self.symbol)
        if current_price <= 0:
            return
        
        # Tính PnL %
        if self.side == "BUY":
            pnl_ratio = (current_price - self.entry_price) / self.entry_price
        else:
            pnl_ratio = (self.entry_price - current_price) / self.entry_price
        
        # Kiểm tra TP/SL
        if pnl_ratio >= self.tp:
            self._close_position(f"✅ Đạt TP {self.tp*100:.1f}% (Lợi nhuận: {pnl_ratio*100:.2f}%)")
        elif pnl_ratio <= -self.sl:
            self._close_position(f"❌ Đạt SL {self.sl*100:.1f}% (Lỗ: {pnl_ratio*100:.2f}%)")
    
    def _close_position(self, reason=""):
        try:
            if not self.symbol:
                return False

            close_side = "SELL" if self.side == "BUY" else "BUY"
            
            result = place_order(self.symbol, close_side, self.position_size, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                current_price = get_current_price(self.symbol)
                
                message = (
                    f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ</b>\n"
                    f"🔗 Coin: {self.symbol}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {self.position_size:.4f}"
                )
                self.log(message)
                
                # QUAN TRỌNG: Xóa coin khỏi danh sách đang trade
                self.coin_manager.unregister_coin(self.symbol)
                
                # Reset trạng thái bot
                self._reset_position()
                return True
            
            self.log("❌ Không thể đóng vị thế")
            return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False
    
    def _reset_position(self):
        """Reset trạng thái bot và tìm coin mới"""
        old_symbol = self.symbol
        self.symbol = None
        self.status = "searching"
        self.side = ""
        self.entry_price = 0
        self.position_size = 0
        
        self.log(f"🔄 Đã reset bot, tìm coin mới thay thế {old_symbol}")
    
    def stop(self):
        self._stop = True
        if self.status == "open":
            self._close_position("Dừng bot")
        self.log("🔴 Bot đã dừng")
    
    def get_info(self):
        return {
            'bot_id': self.bot_id,
            'symbol': self.symbol,
            'status': self.status,
            'side': self.side,
            'lev': self.lev,
            'percent': self.percent,
            'tp': self.tp * 100,
            'sl': self.sl * 100,
            'entry_price': self.entry_price,
            'position_size': self.position_size
        }

# ========== BOT MANAGER HOÀN CHỈNH ==========
class BotManager:
    def __init__(self, api_key=None, api_secret=None, telegram_bot_token=None, telegram_chat_id=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        
        self.bots = []
        self.running = True
        self.user_states = {}
        self.coin_manager = CoinManager()
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT TRADING ĐÃ KHỞI ĐỘNG")
            
            if self.telegram_bot_token and self.telegram_chat_id:
                self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
                self.telegram_thread.start()
                self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
                self.cleanup_thread.start()
                
                self.send_main_menu(self.telegram_chat_id)

    def _verify_api_connection(self):
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance API.")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def _cleanup_loop(self):
        while self.running:
            try:
                self.coin_manager.cleanup_old_closed()
                time.sleep(300)  # 5 phút
            except Exception as e:
                logger.error(f"Lỗi cleanup: {str(e)}")

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>SYSTEM</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BOT GIAO DỊCH FUTURES HOÀN CHỈNH</b>\n\n🎯 <b>HỆ THỐNG ROTATION COIN TỰ ĐỘNG</b>"
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bots(self, bot_count, lev, percent, tp, sl):
        created_count = 0
        
        for i in range(bot_count):
            try:
                bot_id = f"Bot_{i+1}_{int(time.time())}"
                bot = TradingBot(lev, percent, tp, sl, self.api_key, self.api_secret,
                               self.telegram_bot_token, self.telegram_chat_id, bot_id)
                self.bots.append(bot)
                created_count += 1
                
            except Exception as e:
                self.log(f"❌ Lỗi tạo bot {i}: {str(e)}")
                continue
        
        if created_count > 0:
            success_msg = (
                f"✅ <b>ĐÃ TẠO {created_count} BOT ĐỘC LẬP</b>\n\n"
                f"🤖 Số lượng: {created_count} bot\n"
                f"💰 Đòn bẩy: {lev}x\n"
                f"📊 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl}%\n\n"
                f"🎯 <b>Mỗi bot là 1 thread độc lập</b>\n"
                f"🔄 <b>Tự động tìm coin & trade</b>\n"
                f"📊 <b>Tự reset sau mỗi lệnh</b>\n"
                f"🔄 <b>Rotation coin tự động</b>"
            )
            
            self.log(success_msg)
            return True
        else:
            self.log("❌ Không thể tạo bot nào")
            return False

    def get_statistics(self):
        try:
            balance = get_balance(self.api_key, self.api_secret)
            
            searching_bots = sum(1 for bot in self.bots if bot.status == "searching")
            open_bots = sum(1 for bot in self.bots if bot.status == "open")
            
            positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            binance_positions = []
            
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry = float(pos.get('entryPrice', 0))
                    side = "LONG" if position_amt > 0 else "SHORT"
                    pnl = float(pos.get('unRealizedProfit', 0))
                    leverage = float(pos.get('leverage', 1))
                    
                    binance_positions.append({
                        'symbol': symbol,
                        'side': side,
                        'entry': entry,
                        'leverage': leverage,
                        'pnl': pnl
                    })
            
            stats = (
                f"📊 **THỐNG KÊ TOÀN HỆ THỐNG**\n\n"
                f"💰 Số dư: {balance:.2f} USDT\n"
                f"🤖 Tổng bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots}\n"
                f"📈 Đang trade: {open_bots}\n"
            )
            
            # Coin đang được quản lý
            managed_coins = self.coin_manager.get_managed_coins()
            if managed_coins:
                stats += f"\n🔗 **Coin đang trade**: {', '.join(managed_coins)}\n"
            
            # Thông tin bot chi tiết
            if self.bots:
                stats += f"\n🤖 **CHI TIẾT BOT**:\n"
                for bot in self.bots:
                    info = bot.get_info()
                    symbol_info = info['symbol'] if info['symbol'] else "Đang tìm..."
                    status_map = {"searching": "🔍 Tìm coin", "open": "📈 Đang trade"}
                    status = status_map.get(info['status'], info['status'])
                    
                    stats += (
                        f"🔹 {info['bot_id']}\n"
                        f"   📊 {symbol_info} | {status}\n"
                        f"   💰 ĐB: {info['lev']}x | Vốn: {info['percent']}%\n\n"
                    )
            
            # Vị thế Binance
            if binance_positions:
                stats += f"\n💰 **VỊ THẾ BINANCE**:\n"
                for pos in binance_positions[:3]:  # Hiển thị tối đa 3
                    stats += (
                        f"🔹 {pos['symbol']} | {pos['side']}\n"
                        f"   🏷️ Giá vào: {pos['entry']:.4f}\n"
                        f"   💰 ĐB: {pos['leverage']}x | PnL: {pos['pnl']:.2f} USDT\n\n"
                    )
            
            return stats
                    
        except Exception as e:
            return f"❌ Lỗi thống kê: {str(e)}"

    def stop_all(self):
        self.log("⛔ Đang dừng tất cả bot...")
        for bot in self.bots:
            bot.stop()
        self.bots.clear()
        self.running = False
        self.log("🔴 Đã dừng tất cả bot")

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
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Lỗi Telegram listener: {str(e)}")
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
                        user_state['step'] = 'waiting_leverage'
                        send_telegram(f"🤖 Số lượng bot: {bot_count}\n\nChọn đòn bẩy:", chat_id, create_leverage_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        send_telegram("⚠️ Số lượng bot phải từ 1 đến 10.", chat_id, create_bot_count_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ.", chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    leverage = int(text.replace('x', ''))
                    if 1 <= leverage <= 25:
                        user_state['leverage'] = leverage
                        user_state['step'] = 'waiting_percent'
                        send_telegram(f"💰 Đòn bẩy: {leverage}x\n\nChọn % số dư:", chat_id, create_percent_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        send_telegram("⚠️ Đòn bẩy phải từ 1 đến 25.", chat_id, create_leverage_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ.", chat_id, create_leverage_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    percent = float(text)
                    if 0 < percent <= 50:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        send_telegram(f"📊 % Số dư: {percent}%\n\nChọn Take Profit (%):", chat_id, create_tp_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        send_telegram("⚠️ % số dư phải từ 0.1 đến 50.", chat_id, create_percent_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ.", chat_id, create_percent_keyboard(),
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
                        send_telegram(f"🎯 Take Profit: {tp}%\n\nChọn Stop Loss (%):", chat_id, create_sl_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        send_telegram("⚠️ Take Profit phải lớn hơn 0.", chat_id, create_tp_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ.", chat_id, create_tp_keyboard(),
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
                        
                        bot_count = user_state.get('bot_count', 1)
                        leverage = user_state.get('leverage')
                        percent = user_state.get('percent')
                        tp = user_state.get('tp')
                        sl = user_state.get('sl')
                        
                        success = self.add_bots(bot_count, leverage, percent, tp, sl)

                        if success:
                            success_msg = (
                                f"✅ <b>ĐÃ TẠO {bot_count} BOT THÀNH CÔNG</b>\n\n"
                                f"🤖 Số lượng: {bot_count} bot độc lập\n"
                                f"💰 Đòn bẩy: {leverage}x\n"
                                f"📊 % Số dư: {percent}%\n"
                                f"🎯 TP: {tp}%\n"
                                f"🛡️ SL: {sl}%\n\n"
                                f"🎯 <b>Hệ thống rotation coin tự động</b>\n"
                                f"🔄 <b>Mỗi bot tự tìm coin mới sau khi đóng lệnh</b>"
                            )
                            send_telegram(success_msg, chat_id, create_main_menu(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                        else:
                            send_telegram("❌ Có lỗi khi tạo bot.", chat_id, create_main_menu(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                        
                        self.user_states[chat_id] = {}
                    else:
                        send_telegram("⚠️ Stop Loss phải lớn hơn hoặc bằng 0.", chat_id, create_sl_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ.", chat_id, create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_bot_count'}
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ LỖI KẾT NỐI BINANCE", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"🎯 <b>CHỌN SỐ LƯỢNG BOT</b>\n\n"
                f"💰 Số dư: {balance:.2f} USDT\n\n"
                f"Chọn số lượng bot (1-10):",
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
                for bot in self.bots:
                    info = bot.get_info()
                    symbol_info = info['symbol'] if info['symbol'] else "Đang tìm..."
                    status = "🔍 Tìm coin" if info['status'] == "searching" else "📈 Đang trade"
                    message += f"🔹 {info['bot_id']}\n📊 {symbol_info} | {status}\n💰 ĐB: {info['lev']}x | Vốn: {info['percent']}%\n\n"
                send_telegram(message, chat_id, bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📊 Thống kê":
            summary = self.get_statistics()
            send_telegram(summary, chat_id, bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                self.stop_all()
                send_telegram("⛔ Đã dừng tất cả bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
        
        elif text == "💰 Số dư":
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ LỖI KẾT NỐI BINANCE", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                send_telegram(f"💰 <b>SỐ DƯ KHẢ DỤNG</b>: {balance:.2f} USDT", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📈 Vị thế":
            positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            if not positions:
                send_telegram("📭 Không có vị thế nào đang mở", chat_id,
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
                        message += f"🔹 {symbol} | {side}\n🏷️ Giá vào: {entry:.4f}\n💰 PnL: {pnl:.2f} USDT\n\n"
                send_telegram(message, chat_id, bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>HỆ THỐNG BOT ROTATION COIN</b>\n\n"
                "🤖 <b>5 BƯỚC HOẠT ĐỘNG</b>\n"
                "1. 📊 Kiểm tra vị thế Binance\n"
                "2. 🎯 Xác định hướng ngược lại\n"  
                "3. 🔍 Tìm coin phù hợp\n"
                "4. 📈 Vào lệnh & quản lý TP/SL\n"
                "5. 🔄 Đóng lệnh → Tìm coin mới\n\n"
                
                "🔄 <b>ROTATION COIN TỰ ĐỘNG</b>\n"
                "• Mỗi bot có coin riêng\n"
                "• Khi đóng lệnh → Xóa coin cũ\n"
                "• Tự động tìm coin mới\n"
                "• Luôn có coin mới để trade\n\n"
                
                "⚖️ <b>QUẢN LÝ RỦI RO</b>\n"
                "• Tự động cân bằng vị thế\n"
                "• Mỗi bot độc lập thread\n"
                "• TP/SL linh hoạt"
            )
            send_telegram(strategy_info, chat_id, bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            searching_bots = sum(1 for bot in self.bots if bot.status == "searching")
            trading_bots = sum(1 for bot in self.bots if bot.status == "open")
            managed_coins = self.coin_manager.get_managed_coins()

            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Tổng bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots}\n"
                f"📊 Đang trade: {trading_bots}\n"
                f"🔗 Coin đang quản lý: {len(managed_coins)}\n"
                f"💰 Số dư: {balance:.2f} USDT\n\n"
                f"🎯 <b>Hệ thống rotation coin tự động</b>"
            )
            send_telegram(config_info, chat_id, bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)
