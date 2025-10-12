# trading_bot_simple.py - HỆ THỐNG BOT TRADING ĐƠN GIẢN HOÀN CHỈNH
import json
import logging
import hmac
import hashlib
import time
import threading
import urllib.request
import urllib.parse
import numpy as np
import requests
import os
import math
import traceback
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ========== CẤU HÌNH LOGGING ==========
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_simple_errors.log')
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

# ========== PHÂN TÍCH VOLUME VÀ NẾN ==========
class VolumeCandleAnalyzer:
    """PHÂN TÍCH XU HƯỚNG DỰA TRÊN VOLUME VÀ NẾN"""
    
    def __init__(self):
        self.volume_threshold = 1.2  # Volume tăng 20%
        self.small_body_ratio = 0.3  # Thân nến nhỏ < 30% range
        
    def analyze_volume_candle(self, symbol):
        """Phân tích volume và nến theo yêu cầu"""
        try:
            # Lấy dữ liệu 3 khung thời gian
            intervals = ['1m', '5m', '15m']
            signals = []
            
            for interval in intervals:
                klines = self.get_klines(symbol, interval, 10)
                if not klines or len(klines) < 5:
                    continue
                    
                # Phân tích nến hiện tại và volume
                current_candle = klines[-1]
                prev_candles = klines[-5:-1]
                
                open_price = float(current_candle[1])
                close_price = float(current_candle[4])
                high = float(current_candle[2])
                low = float(current_candle[3])
                current_volume = float(current_candle[5])
                
                # Tính volume trung bình
                avg_volume = np.mean([float(c[5]) for c in prev_candles])
                
                # Xác định nến xanh/đỏ
                is_green = close_price > open_price
                is_red = close_price < open_price
                
                # Xác định thân nến nhỏ
                body_size = abs(close_price - open_price)
                total_range = high - low
                is_small_body = body_size < total_range * self.small_body_ratio if total_range > 0 else False
                
                # Volume tăng/giảm
                volume_increase = current_volume > avg_volume * self.volume_threshold
                volume_decrease = current_volume < avg_volume * 0.8
                
                # Áp dụng quy tắc
                if volume_increase and is_green:
                    signals.append("BUY")
                elif volume_increase and is_red:
                    signals.append("SELL")
                elif volume_decrease and is_small_body:
                    signals.append("BUY")  # Chỉ mua khi volume giảm + nến thân nhỏ
                else:
                    signals.append("NEUTRAL")
            
            # Quyết định dựa trên đa số
            if signals.count("BUY") >= 2:
                return "BUY"
            elif signals.count("SELL") >= 2:
                return "SELL"
            else:
                return "NEUTRAL"
                
        except Exception as e:
            logger.error(f"Lỗi phân tích volume nến {symbol}: {str(e)}")
            return "NEUTRAL"
    
    def get_klines(self, symbol, interval, limit):
        """Lấy dữ liệu nến từ Binance"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': interval,
                'limit': limit
            }
            return binance_api_request(url, params=params)
        except Exception as e:
            logger.error(f"Lỗi lấy nến {symbol} {interval}: {str(e)}")
            return None

# ========== TÌM COIN THÔNG MINH ==========
class SimpleCoinFinder:
    """TÌM COIN ĐƠN GIẢN THEO YÊU CẦU"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.analyzer = VolumeCandleAnalyzer()
        
    def find_coin_by_direction(self, target_direction, excluded_symbols=None):
        """Tìm coin theo hướng với logic đơn giản"""
        try:
            if excluded_symbols is None:
                excluded_symbols = set()
            
            logger.info(f"🔍 Đang tìm coin {target_direction}...")
            
            all_symbols = get_all_usdt_pairs(limit=600)
            if not all_symbols:
                return None
            
            # Trộn ngẫu nhiên
            random.shuffle(all_symbols)
            
            for symbol in all_symbols:
                try:
                    if symbol in excluded_symbols:
                        continue
                    
                    # Phân tích với hệ thống volume/nến mới
                    signal = self.analyzer.analyze_volume_candle(symbol)
                    
                    if signal == target_direction:
                        logger.info(f"✅ Tìm thấy {symbol} - {target_direction}")
                        return {
                            'symbol': symbol,
                            'direction': target_direction,
                            'qualified': True
                        }
                        
                except Exception as e:
                    continue
            
            logger.warning(f"⚠️ Không tìm thấy coin {target_direction} phù hợp")
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi tìm coin: {str(e)}")
            return None

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

def get_all_usdt_pairs(limit=600):
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

# ========== BOT TRADING ĐƠN GIẢN ==========
class SimpleTrendBot:
    """BOT ĐƠN GIẢN THEO YÊU CẦU"""
    
    def __init__(self, lev, percent, tp, sl, api_key, api_secret, telegram_bot_token=None, telegram_chat_id=None, bot_id=None):
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.bot_id = bot_id or f"SimpleBot_{int(time.time())}_{random.randint(1000, 9999)}"
        
        self.symbol = None
        self.status = "searching"  # searching, open, closed
        self.side = ""
        self.entry_price = 0
        self.position_size = 0
        
        self.coin_finder = SimpleCoinFinder(api_key, api_secret)
        self.analyzer = VolumeCandleAnalyzer()
        
        self._stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        self.log(f"🟢 Bot khởi động - ĐB: {lev}x, Vốn: {percent}%, TP: {tp}%, SL: {sl}%")
    
    def log(self, message):
        """Ghi log và gửi Telegram"""
        logger.info(f"[Bot {self.bot_id}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            symbol_info = f"<b>{self.symbol}</b>" if self.symbol else "<i>Đang tìm coin...</i>"
            send_telegram(f"{symbol_info} (Bot {self.bot_id}): {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def _run(self):
        """Vòng lặp chính của bot - THỰC HIỆN 5 BƯỚC"""
        while not self._stop:
            try:
                # BƯỚC 1 & 2 & 3 & 4: Tìm và mở vị thế nếu đang tìm kiếm
                if self.status == "searching":
                    self._find_and_open_position()
                
                # BƯỚC 4: Kiểm tra TP/SL nếu đang có vị thế
                elif self.status == "open":
                    self._check_tp_sl()
                
                time.sleep(5)  # Kiểm tra mỗi 5 giây
                
            except Exception as e:
                self.log(f"❌ Lỗi hệ thống: {str(e)}")
                time.sleep(10)
    
    def _find_and_open_position(self):
        """BƯỚC 1, 2, 3, 4: Tìm và mở vị thế"""
        try:
            # BƯỚC 1: Xác định hướng giao dịch dựa trên vị thế hiện có
            target_direction = self._get_market_direction()
            if not target_direction:
                return
            
            self.log(f"🎯 Hướng giao dịch: {target_direction}")
            
            # BƯỚC 2 & 3: Tìm coin phù hợp
            coin_data = self.coin_finder.find_coin_by_direction(target_direction)
            if not coin_data:
                return
            
            symbol = coin_data['symbol']
            direction = coin_data['direction']
            
            # BƯỚC 4: Kiểm tra và vào lệnh
            if self._open_position(symbol, direction):
                self.status = "open"
                self.log(f"✅ Đã vào lệnh {direction} {symbol}")
                
        except Exception as e:
            self.log(f"❌ Lỗi tìm và mở vị thế: {str(e)}")
    
    def _get_market_direction(self):
        """BƯỚC 1: Kiểm tra và xác định hướng giao dịch"""
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
            
            # Quyết định hướng ngược lại với bên nhiều hơn
            if long_count > short_count:
                return "SELL"
            elif short_count > long_count:
                return "BUY"
            else:
                # Nếu cân bằng, chọn ngẫu nhiên
                return random.choice(["BUY", "SELL"])
                
        except Exception as e:
            self.log(f"❌ Lỗi xác định hướng: {str(e)}")
            return random.choice(["BUY", "SELL"])
    
    def _open_position(self, symbol, direction):
        """BƯỚC 4: Mở vị thế"""
        try:
            # Kiểm tra số dư
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không đủ số dư")
                return False
            
            # Kiểm tra đã có vị thế với coin này chưa
            existing_positions = get_positions(symbol, self.api_key, self.api_secret)
            for pos in existing_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    self.log(f"⚠️ Đã có vị thế với {symbol}, bỏ qua")
                    return False
            
            # Đặt đòn bẩy
            if not set_leverage(symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x")
                return False
            
            # Tính số lượng theo công thức: số dư khả dụng * % số dư * đòn bẩy / 100
            current_price = get_current_price(symbol)
            if current_price <= 0:
                self.log("❌ Lỗi lấy giá")
                return False
            
            # Tính toán số lượng
            usd_amount = balance * (self.percent / 100)
            position_value = usd_amount * self.lev
            qty = position_value / current_price
            
            # Làm tròn theo step size
            step_size = get_step_size(symbol, self.api_key, self.api_secret)
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
            
            if qty < step_size:
                self.log(f"❌ Số lượng quá nhỏ: {qty}")
                return False
            
            self.log(f"📊 Đang đặt lệnh {direction} - SL: {step_size}, Qty: {qty}, Giá: {current_price}")
            
            # Đặt lệnh
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
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    self.log(message)
                    return True
                else:
                    self.log(f"❌ Lệnh không khớp - Số lượng: {qty}")
                    return False
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đặt lệnh {direction}: {error_msg}")
                return False
                    
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False
    
    def _check_tp_sl(self):
        """BƯỚC 4: Kiểm tra TP/SL"""
        if not self.symbol or self.entry_price <= 0:
            return
        
        current_price = get_current_price(self.symbol)
        if current_price <= 0:
            return
        
        # Tính PnL %
        if self.side == "BUY":
            pnl_percent = ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            pnl_percent = ((self.entry_price - current_price) / self.entry_price) * 100
        
        # Kiểm tra TP/SL
        if self.tp and pnl_percent >= self.tp:
            self._close_position(f"✅ Đạt TP {self.tp}% (ROI: {pnl_percent:.2f}%)")
        elif self.sl and pnl_percent <= -self.sl:
            self._close_position(f"❌ Đạt SL {self.sl}% (ROI: {pnl_percent:.2f}%)")
    
    def _close_position(self, reason=""):
        """BƯỚC 4: Đóng vị thế"""
        try:
            if not self.symbol:
                return False

            close_side = "SELL" if self.side == "BUY" else "BUY"
            
            # Hủy tất cả lệnh chờ
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            time.sleep(0.5)
            
            # Đóng lệnh
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
                
                # BƯỚC 4: Reset trạng thái về chưa vào lệnh
                self._reset_position()
                return True
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đóng lệnh: {error_msg}")
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False
    
    def _reset_position(self):
        """Reset trạng thái bot về ban đầu"""
        self.symbol = None
        self.status = "searching"
        self.side = ""
        self.entry_price = 0
        self.position_size = 0
    
    def stop(self):
        """Dừng bot"""
        self._stop = True
        if self.status == "open":
            self._close_position("Dừng bot")
        self.log("🔴 Bot đã dừng")
    
    def get_info(self):
        """Lấy thông tin bot"""
        return {
            'bot_id': self.bot_id,
            'symbol': self.symbol,
            'status': self.status,
            'side': self.side,
            'lev': self.lev,
            'percent': self.percent,
            'tp': self.tp,
            'sl': self.sl,
            'entry_price': self.entry_price,
            'position_size': self.position_size
        }

# ========== QUẢN LÝ BOT ĐƠN GIẢN ==========
class BotManager:
    """QUẢN LÝ BOT ĐƠN GIẢN"""
    
    def __init__(self, api_key=None, api_secret=None, telegram_bot_token=None, telegram_chat_id=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        
        self.bots = []
        self.running = True
        self.user_states = {}
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT ĐƠN GIẢN ĐÃ KHỞI ĐỘNG")
            
            if self.telegram_bot_token and self.telegram_chat_id:
                self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
                self.telegram_thread.start()
                
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
        welcome = "🤖 <b>BOT GIAO DỊCH FUTURES ĐƠN GIẢN</b>\n\n🎯 <b>HỆ THỐNG DỰA TRÊN VOLUME VÀ NẾN</b>"
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bots(self, bot_count, lev, percent, tp, sl):
        """Thêm nhiều bot - Mỗi bot chạy thread riêng"""
        created_count = 0
        
        for i in range(bot_count):
            try:
                bot_id = f"Bot_{i+1}_{int(time.time())}"
                bot = SimpleTrendBot(lev, percent, tp, sl, self.api_key, self.api_secret,
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
                f"📊 <b>Tự reset sau mỗi lệnh</b>"
            )
            
            self.log(success_msg)
            return True
        else:
            self.log("❌ Không thể tạo bot nào")
            return False

    def get_statistics(self):
        """BƯỚC 5: Thống kê hệ thống"""
        try:
            # Số dư
            balance = get_balance(self.api_key, self.api_secret)
            
            # Thống kê bot
            searching_bots = sum(1 for bot in self.bots if bot.status == "searching")
            open_bots = sum(1 for bot in self.bots if bot.status == "open")
            
            # Vị thế trên Binance (bao gồm cả ngoài hệ thống)
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
                        f"   💰 ĐB: {info['lev']}x | Vốn: {info['percent']}%\n"
                        f"   🎯 TP: {info['tp']}% | 🛡️ SL: {info['sl']}%\n\n"
                    )
            
            # Vị thế Binance
            if binance_positions:
                stats += f"\n💰 **VỊ THẾ BINANCE**:\n"
                for pos in binance_positions:
                    stats += (
                        f"🔹 {pos['symbol']} | {pos['side']}\n"
                        f"   🏷️ Giá vào: {pos['entry']:.4f}\n"
                        f"   💰 ĐB: {pos['leverage']}x | PnL: {pos['pnl']:.2f} USDT\n\n"
                    )
            
            return stats
                    
        except Exception as e:
            return f"❌ Lỗi thống kê: {str(e)}"

    def stop_all(self):
        """Dừng tất cả bot"""
        self.log("⛔ Đang dừng tất cả bot...")
        for bot in self.bots:
            bot.stop()
        self.bots.clear()
        self.running = False
        self.log("🔴 Đã dừng tất cả bot")

    def stop_bot(self, bot_id):
        """Dừng bot cụ thể"""
        for bot in self.bots:
            if bot.bot_id == bot_id:
                bot.stop()
                self.bots.remove(bot)
                self.log(f"⛔ Đã dừng bot {bot_id}")
                return True
        return False

    def _telegram_listener(self):
        """Lắng nghe tin nhắn Telegram"""
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
        """Xử lý tin nhắn Telegram"""
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        # Xử lý các bước thêm bot
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
                    user_state['step'] = 'waiting_leverage'
                    
                    send_telegram(
                        f"🤖 Số lượng bot: {bot_count}\n\n"
                        f"Chọn đòn bẩy:",
                        chat_id,
                        create_leverage_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho số lượng bot:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

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
                    
                    # Lấy thông tin từ user_state
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
                            f"🎯 <b>Mỗi bot là 1 thread độc lập</b>\n"
                            f"🔄 <b>Tự động tìm coin & trade</b>\n"
                            f"📊 <b>Tự reset sau mỗi lệnh</b>"
                        )

                        send_telegram(success_msg, chat_id, create_main_menu(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        send_telegram("❌ Có lỗi khi tạo bot. Vui lòng thử lại.",
                                    chat_id, create_main_menu(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    
                    self.user_states[chat_id] = {}
                    
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho Stop Loss:",
                                chat_id, create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        # Xử lý menu chính
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_bot_count'}
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key!", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"🎯 <b>CHỌN SỐ LƯỢNG BOT ĐỘC LẬP</b>\n\n"
                f"💰 Số dư hiện có: <b>{balance:.2f} USDT</b>\n\n"
                f"Chọn số lượng bot độc lập bạn muốn tạo:\n"
                f"<i>Mỗi bot sẽ tự tìm coin & trade độc lập</i>",
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
                
                for bot in self.bots:
                    info = bot.get_info()
                    symbol_info = info['symbol'] if info['symbol'] else "Đang tìm..."
                    status_map = {"searching": "🔍 Đang tìm coin", "open": "📈 Đang trade"}
                    status = status_map.get(info['status'], info['status'])
                    
                    message += f"🔹 {info['bot_id']}\n"
                    message += f"   📊 {symbol_info} | {status}\n"
                    message += f"   💰 ĐB: {info['lev']}x | Vốn: {info['percent']}%\n\n"
                
                message += f"📈 Tổng số: {len(self.bots)} bot"
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📊 Thống kê":
            summary = self.get_statistics()
            send_telegram(summary, chat_id,
                         bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                self.stop_all()
                send_telegram("⛔ Đã dừng tất cả bot", chat_id, create_main_menu(),
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
                
                message = "📈 <b>VỊ THẾ ĐANG MỞ TRÊN BINANCE</b>\n\n"
                for pos in positions:
                    position_amt = float(pos.get('positionAmt', 0))
                    if position_amt != 0:
                        symbol = pos.get('symbol', 'UNKNOWN')
                        entry = float(pos.get('entryPrice', 0))
                        side = "LONG" if position_amt > 0 else "SHORT"
                        pnl = float(pos.get('unRealizedProfit', 0))
                        leverage = float(pos.get('leverage', 1))
                        
                        message += (
                            f"🔹 {symbol} | {side}\n"
                            f"📊 Khối lượng: {abs(position_amt):.4f}\n"
                            f"🏷️ Giá vào: {entry:.4f}\n"
                            f"💰 ĐB: {leverage}x | PnL: {pnl:.2f} USDT\n\n"
                        )
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy vị thế: {str(e)}", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>HỆ THỐNG BOT ĐƠN GIẢN</b>\n\n"
                "🤖 <b>5 BƯỚC HOẠT ĐỘNG</b>\n"
                "1. 📊 Kiểm tra vị thế Binance\n"
                "2. 🎯 Xác định hướng ngược lại\n"  
                "3. 🔍 Tìm coin phù hợp\n"
                "4. 📈 Vào lệnh & quản lý TP/SL\n"
                "5. 🔄 Reset và lặp lại\n\n"
                
                "📈 <b>PHÂN TÍCH KỸ THUẬT</b>\n"
                "• Volume tăng + nến xanh → MUA\n"
                "• Volume tăng + nến đỏ → BÁN\n"
                "• Volume giảm + nến thân nhỏ → MUA\n"
                "• Đa khung: 1m, 5m, 15m\n\n"
                
                "⚖️ <b>QUẢN LÝ RỦI RO</b>\n"
                "• Tự động cân bằng vị thế\n"
                "• Mỗi bot độc lập thread\n"
                "• Tự reset sau mỗi lệnh"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"

            searching_bots = sum(1 for bot in self.bots if bot.status == "searching")
            trading_bots = sum(1 for bot in self.bots if bot.status == "open")

            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Tổng số bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots} bot\n"
                f"📊 Đang trade: {trading_bots} bot\n"
                f"💰 Số dư: {balance:.2f} USDT\n\n"
                f"🎯 <b>Mỗi bot độc lập - Tự reset hoàn toàn</b>"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text.startswith("⛔ "):
            bot_id = text.replace("⛔ ", "").strip()
            if self.stop_bot(bot_id):
                send_telegram(f"⛔ Đã dừng bot {bot_id}", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                send_telegram(f"⚠️ Không tìm thấy bot {bot_id}", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)
