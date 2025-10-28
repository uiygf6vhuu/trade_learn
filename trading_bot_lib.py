# trading_bot_global_market_complete.py - HOÀN CHỈNH VỚI CƠ CHẾ MỞ LỆNH NGƯỢC LẠI
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

def _last_closed_1m_quote_volume(symbol):
    data = binance_api_request(
        "https://fapi.binance.com/fapi/v1/klines",
        params={"symbol": symbol, "interval": "1m", "limit": 2}
    )
    if not data or len(data) < 2:
        return None
    k = data[-2]               # nến 1m đã đóng gần nhất
    return float(k[7])         # quoteVolume (USDT)


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

def get_top_volume_symbols(limit=100):
    """Top {limit} USDT pairs theo quoteVolume của NẾN 1M đã đóng (đa luồng)."""
    try:
        universe = get_all_usdt_pairs(limit=600) or []
        if not universe:
            logger.warning("❌ Không lấy được danh sách coin USDT")
            return []

        scored, failed = [], 0
        max_workers = 16
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
                time.sleep(1)  # nhỏ giọt tránh 429

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
            return None
            
        for asset in data['assets']:
            if asset['asset'] == 'USDT':
                available_balance = float(asset['availableBalance'])
                total_balance = float(asset['walletBalance'])
                
                # Log để debug
                logger.info(f"💰 Số dư - Khả dụng: {available_balance:.2f} USDT, Tổng: {total_balance:.2f} USDT")
                
                return available_balance  # ✅ TRẢ VỀ SỐ DƯ KHẢ DỤNG
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

# ========== GLOBAL MARKET ANALYZER ==========
class GlobalMarketAnalyzer:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.last_analysis_time = 0
        self.analysis_interval = 10  # 10 giây
        self.current_market_signal = "NEUTRAL"
        self.last_green_count = 0
        self.last_red_count = 0
        self.last_neutral_count = 0
        self.previous_green_count = 0
        self.previous_red_count = 0
        self.previous_neutral_count = 0
        
    def analyze_global_market(self):
        """Phân tích toàn thị trường theo 2 phút liên tiếp:
           - Đếm màu nến của phút TRƯỚC (prev) và phút HIỆN TẠI (curr) trên 100 cặp top 1m quoteVolume
           - Nếu nến xanh curr tăng >= 10% so với prev => BUY
           - Nếu nến đỏ  curr tăng >= 10% so với prev => SELL
        """
        try:
            current_time = time.time()
            if current_time - self.last_analysis_time < self.analysis_interval:
                return self.current_market_signal
    
            # 1) Lấy danh sách 100 cặp theo 1m quoteVolume (đã đóng)
            top_symbols = get_top_volume_symbols(limit=100)
            if not top_symbols or len(top_symbols) < 80:
                logger.warning(f"⚠️ Không đủ ứng viên 1m: {len(top_symbols) if top_symbols else 0}/100")
                return "NEUTRAL"
    
            # 2) Biến đếm cho 2 phút liên tiếp
            prev_green = prev_red = prev_neutral = 0
            curr_green = curr_red = curr_neutral = 0
            failed_symbols = 0
            sample_count = 0
    
            # 3) Duyệt từng symbol, lấy 3 nến để có 2 nến đã đóng: [-3] và [-2]
            for symbol in top_symbols:
                try:
                    klines = self.get_klines(symbol, '1m', limit=3)
                    if not klines or len(klines) < 3:
                        failed_symbols += 1
                        continue
    
                    prev_candle = klines[-3]  # nến đã đóng của phút trước
                    curr_candle = klines[-2]  # nến đã đóng của phút hiện tại
    
                    po, pc = float(prev_candle[1]), float(prev_candle[4])
                    co, cc = float(curr_candle[1]), float(curr_candle[4])
    
                    # Đếm màu phút TRƯỚC
                    if pc > po:      prev_green += 1
                    elif pc < po:    prev_red   += 1
                    else:            prev_neutral += 1
    
                    # Đếm màu phút HIỆN TẠI
                    if cc > co:      curr_green += 1
                    elif cc < co:    curr_red   += 1
                    else:            curr_neutral += 1
    
                    sample_count += 1
    
                except Exception:
                    failed_symbols += 1
                    continue
    
            # 4) Kiểm tra đủ dữ liệu
            if sample_count < 80:
                logger.warning(f"⚠️ Phân tích không đủ sâu: {sample_count}/100 coin (lỗi: {failed_symbols})")
                return "NEUTRAL"
    
            # 5) Tính % thay đổi giữa 2 phút
            #    Tránh chia cho 0: dùng "Laplace smoothing" nhỏ (+1 ở mẫu số)
            green_change = ((curr_green - prev_green) / max(1, prev_green)) * 100.0
            red_change   = ((curr_red   - prev_red)   / max(1, prev_red))   * 100.0
    
            logger.info(
                f"📊 2-PHÚT | "
                f"Prev 🟢{prev_green} 🔴{prev_red} ⚪{prev_neutral}  →  "
                f"Curr 🟢{curr_green} 🔴{curr_red} ⚪{curr_neutral} | "
                f"Δ🟢 {green_change:+.1f}% | Δ🔴 {red_change:+.1f}% | "
                f"Số mẫu: {sample_count}, Lỗi: {failed_symbols}"
            )
    
            # 6) Ra tín hiệu theo ngưỡng 10%
            signal = "NEUTRAL"
            if green_change >= 10:
                signal = "BUY"
                logger.info(f"🎯 TÍN HIỆU BUY: Nến xanh tăng {green_change:.1f}% (2 phút liên tiếp)")
            elif red_change >= 10:
                signal = "SELL"
                logger.info(f"🎯 TÍN HIỆU SELL: Nến đỏ tăng {red_change:.1f}% (2 phút liên tiếp)")
            else:
                # nếu không đủ mạnh, giữ nguyên tín hiệu cũ
                signal = self.current_market_signal
    
            # 7) Cập nhật state (nếu bạn vẫn muốn lưu lại để hiển thị chỗ khác)
            self.previous_green_count = prev_green
            self.previous_red_count = prev_red
            self.previous_neutral_count = prev_neutral
    
            self.current_market_signal = signal
            self.last_analysis_time = current_time
            self.last_green_count = curr_green
            self.last_red_count = curr_red
            self.last_neutral_count = curr_neutral
    
            # 8) Log tổng hợp
            logger.info(
                f"📊 TOÀN THỊ TRƯỜNG (2P): {signal} | "
                f"HIỆN TẠI: 🟢 {curr_green}/{sample_count} | 🔴 {curr_red}/{sample_count} | ⚪ {curr_neutral}/{sample_count} | "
                f"TRƯỚC ĐÓ: 🟢 {prev_green}/{sample_count} | 🔴 {prev_red}/{sample_count} | ⚪ {prev_neutral}/{sample_count} | "
                f"❌ Lỗi: {failed_symbols}"
            )
    
            return signal
    
        except Exception as e:
            logger.error(f"❌ Lỗi phân tích toàn thị trường: {str(e)}")
            return "NEUTRAL"

    
    def get_klines(self, symbol, interval, limit=2):
        """Lấy dữ liệu nến từ Binance - THÊM RETRY"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                url = "https://fapi.binance.com/fapi/v1/klines"
                params = {
                    'symbol': symbol.upper(),
                    'interval': interval,
                    'limit': limit
                }
                data = binance_api_request(url, params=params)
                if data and len(data) >= limit:
                    return data
                elif attempt < max_retries - 1:
                    time.sleep(0.1)
                    continue
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.1)
                    continue
        return None

# ========== SMART COIN FINDER ĐÃ SỬA ==========
class SmartCoinFinder:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.global_analyzer = GlobalMarketAnalyzer(api_key, api_secret)
        
    def get_global_market_signal(self):
        """Chỉ sử dụng tín hiệu từ phân tích toàn thị trường"""
        return self.global_analyzer.analyze_global_market()
    
    def get_symbol_leverage(self, symbol):
        """Lấy đòn bẩy tối đa của symbol"""
        return get_max_leverage(symbol, self.api_key, self.api_secret)
    
    def find_best_coin(self, target_direction, excluded_coins=None):
        """Tìm coin tốt nhất theo hướng mong muốn - RANDOM TỪ 600 COIN"""
        try:
            all_symbols = get_all_usdt_pairs(limit=600)
            if not all_symbols:
                return None
            
            # Trộn ngẫu nhiên danh sách coin
            random.shuffle(all_symbols)
            
            for symbol in all_symbols:
                # Kiểm tra coin không trong danh sách loại trừ
                if excluded_coins and symbol in excluded_coins:
                    continue
                
                # Kiểm tra đòn bẩy
                max_lev = self.get_symbol_leverage(symbol)
                if max_lev < 10:
                    continue
                
                # Kiểm tra giá hiện tại
                current_price = get_current_price(symbol)
                if current_price <= 0:
                    continue
                    
                logger.info(f"✅ Tìm thấy coin phù hợp: {symbol} - Đòn bẩy: {max_lev}x")
                return symbol
            
            return None
            
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

# ========== BASE BOT ĐÃ SỬA ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, strategy_name, config_key=None, bot_id=None):
        
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
        
        self.cooldown_period = 3
        self.position_check_interval = 30
        
        self._close_attempted = False
        self._last_close_attempt = 0
        
        self.should_be_removed = False
        
        self.coin_manager = CoinManager()
        self.coin_finder = SmartCoinFinder(api_key, api_secret)
        
        self.current_target_direction = None
        self.last_find_time = 0
        self.find_interval = 30
        
        # Biến quản lý nhồi lệnh Fibonacci
        self.entry_base = 0
        self.average_down_count = 0
        self.last_average_down_time = 0
        self.average_down_cooldown = 60
        self.max_average_down_count = 7
        
        # Biến theo dõi nến và ROI
        self.entry_green_count = 0
        self.entry_red_count = 0
        self.high_water_mark_roi = 0
        self.roi_check_activated = False
        
        # BIẾN MỚI: Hướng cho lệnh tiếp theo (ngược với lệnh vừa đóng)
        self.next_side = None
        
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

    def _reset_position(self):
        """Reset trạng thái vị thế nhưng giữ nguyên symbol"""
        self.position_open = False
        self.status = "waiting"  # Thay vì "searching" để chờ mở lệnh ngược lại
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
        # KHÔNG reset symbol: self.symbol = None

    def find_and_set_coin(self):
        """Tìm và thiết lập coin mới cho bot - CHỈ DÙNG TÍN HIỆU TOÀN THỊ TRƯỜNG"""
        try:
            current_time = time.time()
            if current_time - self.last_find_time < self.find_interval:
                return False
            
            self.last_find_time = current_time
            
            # Bước 1: Xác định hướng ưu tiên từ TÍN HIỆU TOÀN THỊ TRƯỜNG
            target_direction = self.coin_finder.get_global_market_signal()
            if target_direction == "NEUTRAL":
                # Nếu thị trường cân bằng, chọn ngẫu nhiên
                target_direction = random.choice(["BUY", "SELL"])
            
            # Lấy danh sách coin đang active để tránh trùng lặp
            active_coins = self.coin_manager.get_active_coins()
            
            # Bước 2: Tìm coin phù hợp (RANDOM TỪ 600 COIN)
            new_symbol = self.coin_finder.find_best_coin(
                target_direction, 
                excluded_coins=active_coins
            )
            
            if new_symbol:
                # Kiểm tra đòn bẩy một lần nữa
                max_lev = self.coin_finder.get_symbol_leverage(new_symbol)
                if max_lev >= self.lev:
                    # Đăng ký coin mới
                    self.coin_manager.register_coin(new_symbol)
                    
                    # Cập nhật symbol cho bot
                    if self.symbol:
                        self.ws_manager.remove_symbol(self.symbol)
                        self.coin_manager.unregister_coin(self.symbol)
                    
                    self.symbol = new_symbol
                    self.ws_manager.add_symbol(new_symbol, self._handle_price_update)
                    self.status = "waiting"
                    
                    # Đặt hướng cho lệnh đầu tiên
                    self.next_side = target_direction
                    
                    self.log(f"🎯 Đã tìm thấy coin: {new_symbol} - Hướng ưu tiên: {target_direction}")
                    return True
            
            return False
            
        except Exception as e:
            self.log(f"❌ Lỗi tìm coin: {str(e)}")
            return False

    def verify_leverage_and_switch(self):
        """Kiểm tra và chuyển đổi đòn bẩy nếu cần"""
        if not self.symbol:
            return True
            
        try:
            current_leverage = self.coin_finder.get_symbol_leverage(self.symbol)
            if current_leverage >= self.lev:
                # Thiết lập đòn bẩy mong muốn
                if set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                    return True
            return False
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
                
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                # KIỂM TRA NHỒI LỆNH KHI CÓ VỊ THẾ
                if self.position_open and self.entry_base > 0:
                    self.check_averaging_down()
                              
                if not self.position_open:
                    # QUAN TRỌNG: Nếu không có symbol, tìm coin mới NGAY
                    if not self.symbol:
                        if self.find_and_set_coin():
                            self.log("✅ Đã tìm thấy coin mới, chờ tín hiệu...")
                        time.sleep(1)
                        continue
                    
                    # NẾU CÓ SYMBOL VÀ CÓ HƯỚNG CHO LỆNH TIẾP THEO - MỞ LỆNH NGAY
                    if self.symbol and self.next_side:
                        if current_time - self.last_trade_time > 3 and current_time - self.last_close_time > self.cooldown_period:
                            if self.open_position(self.next_side):
                                self.last_trade_time = current_time
                                self.next_side = None  # Reset sau khi mở lệnh thành công
                            else:
                                time.sleep(1)
                        else:
                            time.sleep(1)
                    else:
                        # Phân tích tín hiệu cho lệnh đầu tiên
                        signal = self.get_signal()
                        
                        if signal and signal != "NEUTRAL":
                            if current_time - self.last_trade_time > 3 and current_time - self.last_close_time > self.cooldown_period:
                                if self.open_position(signal):
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

    def get_signal(self):
        """Phương thức này sẽ được override bởi các bot chiến lược cụ thể"""
        return "NEUTRAL"

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
            self.ws_manager.remove_symbol(self.symbol)
        if self.symbol:
            self.coin_manager.unregister_coin(self.symbol)
        if self.symbol:
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
        self.log(f"🔴 Bot dừng")

    def open_position(self, side):
        if side not in ["BUY", "SELL"]:
            self.log(f"❌ Side không hợp lệ: {side}")
            self._cleanup_symbol()
            return False
            
        try:
            # Kiểm tra vị thế hiện tại
            self.check_position_status()
            
            if self.position_open:
                self.log(f"⚠️ Đã có vị thế {self.side}, bỏ qua tín hiệu {side}")
                return False
    
            if self.should_be_removed:
                self.log("⚠️ Bot đã được đánh dấu xóa, không mở lệnh mới")
                return False
    
            # KIỂM TRA LẠI ĐÒN BẨY TRƯỚC KHI MỞ LỆNH
            current_leverage = self.coin_finder.get_symbol_leverage(self.symbol)
            if current_leverage < self.lev:
                self.log(f"❌ Coin {self.symbol} chỉ hỗ trợ đòn bẩy {current_leverage}x < {self.lev}x -> TÌM COIN KHÁC")
                self._cleanup_symbol()
                return False
    
            # Thiết lập đòn bẩy
            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x -> TÌM COIN KHÁC")
                self._cleanup_symbol()
                return False
    
            # Kiểm tra số dư
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không đủ số dư")
                return False
    
            # Lấy giá hiện tại - THÊM KIỂM TRA LỖI
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                self.log(f"❌ Lỗi lấy giá {self.symbol}: {current_price} -> TÌM COIN KHÁC")
                self._cleanup_symbol()
                return False
    
            # Tính toán khối lượng
            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
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
            
            # Hủy mọi lệnh chờ trước đó
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            time.sleep(0.2)
            
            # Đặt lệnh
            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty >= 0:
                    self.entry = avg_price
                    self.entry_base = avg_price
                    self.average_down_count = 0
                    self.side = side
                    self.qty = executed_qty if side == "BUY" else -executed_qty
                    self.position_open = True
                    self.status = "open"
                    
                    # LƯU SỐ NẾN TẠI THỜI ĐIỂM VÀO LỆNH
                    self.entry_green_count = self.coin_finder.global_analyzer.last_green_count
                    self.entry_red_count = self.coin_finder.global_analyzer.last_red_count
                    self.high_water_mark_roi = 0
                    self.roi_check_activated = False
                    
                    roi_trigger_info = f" | 🎯 ROI Trigger: {self.roi_trigger}%" if self.roi_trigger else ""
                    
                    message = (
                        f"✅ <b>ĐÃ MỞ VỊ THẾ {self.symbol}</b>\n"
                        f"🤖 Chiến lược: {self.strategy_name}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {self.entry:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💵 Giá trị: {executed_qty * self.entry:.2f} USDT\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%{roi_trigger_info}\n"
                        f"📊 Nến tại entry: 🟢 {self.entry_green_count} | 🔴 {self.entry_red_count}"
                    )
                    
                    if self.roi_trigger:
                        message += f"\n🎯 <b>Cơ chế chốt lệnh ROI {self.roi_trigger}% đã kích hoạt</b>"
                    
                    self.log(message)
                    return True
                else:
                    self.log(f"❌ Lệnh không khớp - Số lượng: {qty} -> TÌM COIN KHÁC")
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
        self.entry_green_count = 0
        self.entry_red_count = 0
        self.high_water_mark_roi = 0
        self.roi_check_activated = False
        self.next_side = None  # Reset hướng tiếp theo
        
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
                
                # THÊM THÔNG TIN NẾN VÀO MESSAGE
                current_green = self.coin_finder.global_analyzer.last_green_count
                current_red = self.coin_finder.global_analyzer.last_red_count
                
                message = (
                    f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ {self.symbol}</b>\n"
                    f"🤖 Chiến lược: {self.strategy_name}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDT\n"
                    f"📈 Số lần nhồi: {self.average_down_count}\n"
                    f"📊 Nến tại entry: 🟢 {self.entry_green_count} | 🔴 {self.entry_red_count}\n"
                    f"📊 Nến tại close: 🟢 {current_green} | 🔴 {current_red}"
                )
                self.log(message)
                
                # QUAN TRỌNG: ĐẶT HƯỚNG CHO LỆNH TIẾP THEO LÀ NGƯỢC LẠI
                self.next_side = "BUY" if self.side == "SELL" else "SELL"
                
                # Reset position nhưng GIỮ NGUYÊN SYMBOL
                self._reset_position()
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

        # KIỂM TRA ĐIỀU KIỆN ROI TRIGGER (do người dùng nhập) - LOGIC CHỐT LỆNH MỚI
        if self.roi_trigger is not None and self.high_water_mark_roi >= self.roi_trigger and not self.roi_check_activated:
            self.roi_check_activated = True
            self.log(f"🎯 ĐÃ ĐẠT ROI {self.roi_trigger}% - KÍCH HOẠT CƠ CHẾ CHỐT LỆNH THEO NẾN")
        
        # NẾU ĐÃ KÍCH HOẠT KIỂM TRA ROI TRIGGER, THÌ KIỂM TRA ĐIỀU KIỆN CHỐT LỆNH
        if self.roi_check_activated:
            current_green = self.coin_finder.global_analyzer.last_green_count
            current_red = self.coin_finder.global_analyzer.last_red_count
            
            if self.side == "BUY":
                # Nếu số nến xanh hiện tại GIẢM 30% so với lúc vào lệnh
                if current_green <= self.entry_green_count * 0.7:
                    self.close_position(f"✅ ROI đạt {roi:.2f}% và nến xanh giảm 30% (từ {self.entry_green_count} xuống {current_green})")
                    return
            elif self.side == "SELL":
                # Nếu số nến đỏ hiện tại GIẢM 30% so với lúc vào lệnh
                if current_red <= self.entry_red_count * 0.7:
                    self.close_position(f"✅ ROI đạt {roi:.2f}% và nến đỏ giảm 30% (từ {self.entry_red_count} xuống {current_red})")
                    return

        # TP/SL TRUYỀN THỐNG (vẫn hoạt động bình thường)
        if self.tp is not None and roi >= self.tp:
            self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
        elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
            self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")

    def check_averaging_down(self):
        """Bước 4: Kiểm tra và thực hiện nhồi lệnh Fibonacci khi lỗ"""
        if not self.position_open or not self.entry_base or self.average_down_count >= self.max_average_down_count:
            return
            
        try:
            current_time = time.time()
            if current_time - self.last_average_down_time < self.average_down_cooldown:
                return
                
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                return
                
            # Tính % lỗ so với giá vào gốc
            if self.side == "BUY":
                drawdown_pct = (self.entry_base - current_price) / self.entry_base * 100
            else:
                drawdown_pct = (current_price - self.entry_base) / self.entry_base * 100
                
            # Các mốc Fibonacci để nhồi lệnh
            fib_levels = [2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0]
            
            if self.average_down_count < len(fib_levels):
                current_fib_level = fib_levels[self.average_down_count]
                
                if drawdown_pct >= current_fib_level:
                    # Thực hiện nhồi lệnh
                    if self.execute_average_down_order():
                        self.last_average_down_time = current_time
                        self.average_down_count += 1
                        
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra nhồi lệnh: {str(e)}")

    def execute_average_down_order(self):
        """Thực hiện lệnh nhồi theo Fibonacci"""
        try:
            # Tính khối lượng nhồi lệnh (có thể điều chỉnh %)
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                return False
                
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
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
                    
                    message = (
                        f"📈 <b>ĐÃ NHỒI LỆNH FIBONACCI {self.symbol}</b>\n"
                        f"🔢 Lần nhồi: {self.average_down_count + 1}\n"
                        f"📊 Khối lượng thêm: {executed_qty:.4f}\n"
                        f"🏷️ Giá nhồi: {avg_price:.4f}\n"
                        f"📈 Giá trung bình mới: {self.entry:.4f}\n"
                        f"💰 Tổng khối lượng: {total_qty:.4f}"
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

# ========== BOT GLOBAL MARKET VỚI NHỒI LỆNH ==========
class GlobalMarketBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, bot_id=None):
        super().__init__(symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret,
                        telegram_bot_token, telegram_chat_id, "Global-Market", bot_id=bot_id)
    
    def get_signal(self):
        """Sử dụng tín hiệu từ phân tích toàn thị trường"""
        return self.coin_finder.get_global_market_signal()

# ========== BOT MANAGER HOÀN CHỈNH ==========
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
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT TOÀN THỊ TRƯỜNG VỚI CƠ CHẾ MỞ LỆNH NGƯỢC LẠI ĐÃ KHỞI ĐỘNG")
            
            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()
            
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

    def get_position_summary(self):
        """Lấy thống kê tổng quan - CHI TIẾT THEO YÊU CẦU"""
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            binance_buy_count = 0
            binance_sell_count = 0
            binance_positions = []
            
            # Đếm vị thế từ Binance
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry_price = float(pos.get('entryPrice', 0))
                    leverage = float(pos.get('leverage', 1))
                    position_value = abs(position_amt) * entry_price / leverage
                    
                    if position_amt > 0:
                        binance_buy_count += 1
                        binance_positions.append({
                            'symbol': symbol,
                            'side': 'LONG',
                            'leverage': leverage,
                            'size': abs(position_amt),
                            'entry': entry_price,
                            'value': position_value
                        })
                    else:
                        binance_sell_count += 1
                        binance_positions.append({
                            'symbol': symbol, 
                            'side': 'SHORT',
                            'leverage': leverage,
                            'size': abs(position_amt),
                            'entry': entry_price,
                            'value': position_value
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
                    'roi_trigger': bot.roi_trigger
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
            summary += f"💰 **SỐ DƯ**: {balance:.2f} USDT\n\n"
            
            # Phần 2: Bot hệ thống
            summary += f"🤖 **BOT HỆ THỐNG**: {len(self.bots)} bots\n"
            summary += f"   🔍 Đang tìm coin: {searching_bots}\n"
            summary += f"   🟡 Đang chờ: {waiting_bots}\n" 
            summary += f"   📈 Đang trade: {trading_bots}\n\n"
            
            # Phần 3: Chi tiết từng bot
            if bot_details:
                summary += "📋 **CHI TIẾT TỪNG BOT**:\n"
                for bot in bot_details[:8]:  # Giới hạn hiển thị
                    symbol_info = bot['symbol'] if bot['symbol'] != 'Đang tìm...' else '🔍 Đang tìm'
                    status_map = {
                        "searching": "🔍 Tìm coin",
                        "waiting": "🟡 Chờ tín hiệu", 
                        "open": "🟢 Đang trade"
                    }
                    status = status_map.get(bot['status'], bot['status'])
                    
                    roi_info = f" | 🎯 ROI: {bot['roi_trigger']}%" if bot['roi_trigger'] else ""
                    
                    summary += f"   🔹 {bot['bot_id'][:15]}...\n"
                    summary += f"      📊 {symbol_info} | {status}\n"
                    summary += f"      💰 ĐB: {bot['leverage']}x | Vốn: {bot['percent']}%{roi_info}\n"
                    if bot['tp'] is not None and bot['sl'] is not None:
                        summary += f"      🎯 TP: {bot['tp']}% | 🛡️ SL: {bot['sl']}%\n"
                    summary += "\n"
                
                if len(bot_details) > 8:
                    summary += f"   ... và {len(bot_details) - 8} bot khác\n\n"
            
            # Phần 4: Tất cả vị thế Binance
            total_binance = binance_buy_count + binance_sell_count
            if total_binance > 0:
                summary += f"💰 **TẤT CẢ VỊ THẾ BINANCE**: {total_binance} vị thế\n"
                summary += f"   🟢 LONG: {binance_buy_count}\n"
                summary += f"   🔴 SHORT: {binance_sell_count}\n\n"
                
                # Hiển thị chi tiết 5 vị thế đầu
                summary += "📈 **CHI TIẾT VỊ THẾ**:\n"
                for pos in binance_positions[:5]:
                    summary += f"   🔹 {pos['symbol']} | {pos['side']}\n"
                    summary += f"      📊 KL: {pos['size']:.4f} | Giá: {pos['entry']:.4f}\n"
                    summary += f"      💰 ĐB: {pos['leverage']}x | GT: ${pos['value']:.0f}\n\n"
                
                if len(binance_positions) > 5:
                    summary += f"   ... và {len(binance_positions) - 5} vị thế khác\n"
                    
                # Đề xuất hướng
                if binance_buy_count > binance_sell_count:
                    summary += f"\n⚖️ **ĐỀ XUẤT**: Nhiều LONG hơn → ƯU TIÊN TÌM SHORT"
                elif binance_sell_count > binance_buy_count:
                    summary += f"\n⚖️ **ĐỀ XUẤT**: Nhiều SHORT hơn → ƯU TIÊN TÌM LONG"
                else:
                    summary += f"\n⚖️ **TRẠNG THÁI**: Cân bằng tốt"
                        
            else:
                summary += f"💰 **TẤT CẢ VỊ THẾ BINANCE**: Không có vị thế nào\n"
                    
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
            "🎯 <b>HỆ THỐNG TOÀN THỊ TRƯỜNG VỚI CƠ CHẾ MỞ LỆNH NGƯỢC LẠI</b>\n\n"
            "📈 <b>CƠ CHẾ TÍN HIỆU TOÀN THỊ TRƯỜNG:</b>\n"
            "• Phân tích 100 coin volume cao nhất\n"
            "• So sánh 2 nến 1 PHÚT liên tiếp\n"
            "• Nến xanh tăng ≥10% → Tín hiệu BUY\n"
            "• Nến đỏ tăng ≥10% → Tín hiệu SELL\n\n"
            "🔄 <b>CƠ CHẾ MỞ LỆNH NGƯỢC LẠI:</b>\n"
            "• Sau khi đóng lệnh, bot tự động mở lệnh ngược lại\n"
            "• Giữ nguyên coin, giữ nguyên số tiền đầu tư\n"
            "• Tiếp tục luân phiên BUY/SELL trên cùng coin\n"
            "• Chỉ tìm coin mới khi có lỗi hoặc dừng bot\n\n"
            "🎯 <b>CƠ CHẾ CHỐT LỆNH ROI THÔNG MINH:</b>\n"
            "• Khi ROI đạt ngưỡng (do bạn đặt)\n"
            "• Theo dõi số nến xanh/đỏ toàn thị trường\n"
            "• Chốt lệnh nếu nến giảm 30% so với lúc vào\n"
            "• Kết hợp TP/SL truyền thống\n\n"
            "📊 <b>CƠ CHẾ NHỒI LỆNH FIBONACCI:</b>\n"
            "• Mốc 1: Giá biến động 2%\n"
            "• Mốc 2: Giá biến động 3%\n" 
            "• Mốc 3: Giá biến động 5%\n"
            "• Mốc 4: Giá biến động 8%\n"
            "• Mốc 5: Giá biến động 13%\n"
            "• Mốc 6: Giá biến động 21%\n"
            "• Mốc 7: Giá biến động 34%"
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
        
        test_balance = get_balance(self.api_key, self.api_secret)
        if test_balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance")
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
                    
                    bot = bot_class(symbol, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                                  self.api_key, self.api_secret, self.telegram_bot_token, 
                                  self.telegram_chat_id, bot_id=bot_id)
                    
                else:
                    bot_id = f"DYNAMIC_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = GlobalMarketBot
                    
                    if not bot_class:
                        continue
                    
                    bot = bot_class(None, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                                  self.api_key, self.api_secret, self.telegram_bot_token,
                                  self.telegram_chat_id, bot_id=bot_id)
                
                bot._bot_manager = self
                self.bots[bot_id] = bot
                created_count += 1
                
            except Exception as e:
                self.log(f"❌ Lỗi tạo bot {i}: {str(e)}")
                continue
        
        if created_count > 0:
            roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else " | 🎯 ROI Trigger: Tắt"
            
            success_msg = (
                f"✅ <b>ĐÃ TẠO {created_count}/{bot_count} BOT TOÀN THỊ TRƯỜNG</b>\n\n"
                f"🎯 Hệ thống: Global Market Analysis\n"
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
            
            success_msg += f"\n🎯 <b>TÍN HIỆU TOÀN THỊ TRƯỜNG ĐÃ KÍCH HOẠT</b>\n"
            success_msg += f"📊 Phân tích 100 coin volume cao\n"
            success_msg += f"⏰ So sánh 2 nến 1 phút\n"
            success_msg += f"🔄 Mỗi bot là 1 vòng lặp độc lập\n\n"
            success_msg += f"🔄 <b>CƠ CHẾ MỞ LỆNH NGƯỢC LẠI ĐÃ KÍCH HOẠT</b>\n"
            success_msg += f"📈 Sau khi đóng lệnh, bot tự mở lệnh ngược lại\n"
            success_msg += f"💵 Giữ nguyên số tiền đầu tư: {percent}%\n"
            success_msg += f"🔗 Giữ nguyên coin (chỉ tìm mới khi lỗi)"
            
            if roi_trigger:
                success_msg += f"\n\n🎯 <b>CƠ CHẾ ROI {roi_trigger}% ĐÃ KÍCH HOẠT</b>\n"
                success_msg += f"📈 Khi ROI đạt {roi_trigger}%, bot sẽ theo dõi nến\n"
                success_msg += f"⏰ Chốt lệnh nếu nến giảm 30% so với lúc vào"
            
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
                    user_state['step'] = 'waiting_strategy'
                    send_telegram(
                        "🎯 <b>ĐÃ CHỌN: BOT TĨNH</b>\n\n"
                        "🤖 Bot sẽ giao dịch coin CỐ ĐỊNH\n"
                        "📊 Bạn cần chọn coin cụ thể\n\n"
                        "Chọn chiến lược:",
                        chat_id,
                        create_strategy_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                else:
                    user_state['bot_mode'] = 'dynamic'
                    user_state['step'] = 'waiting_strategy'
                    send_telegram(
                        "🎯 <b>ĐÃ CHỌN: BOT ĐỘNG</b>\n\n"
                        f"🤖 Hệ thống sẽ tạo <b>{user_state.get('bot_count', 1)} bot độc lập</b>\n"
                        f"🔄 Mỗi bot tự tìm coin & trade độc lập\n"
                        f"🎯 Tự reset hoàn toàn sau mỗi lệnh\n"
                        f"📊 Mỗi bot là 1 vòng lặp hoàn chỉnh\n\n"
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
            elif text in ["📊 Global Market System"]:
                
                strategy_map = {
                    "📊 Global Market System": "Global-Market"
                }
                
                strategy = strategy_map[text]
                user_state['strategy'] = strategy
                user_state['step'] = 'waiting_exit_strategy'
                
                strategy_descriptions = {
                    "Global-Market": "Phân tích toàn thị trường - 100 coin volume cao"
                }
                
                description = strategy_descriptions.get(strategy, "")
                bot_count = user_state.get('bot_count', 1)
                
                send_telegram(
                    f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n"
                    f"🤖 Số lượng: {bot_count} bot độc lập\n\n"
                    f"{description}\n\n"
                    f"Chọn chiến lược thoát lệnh:",
                    chat_id,
                    create_exit_strategy_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

        elif current_step == 'waiting_exit_strategy':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text == "🎯 Chỉ TP/SL cố định":
                user_state['exit_strategy'] = 'traditional'
                user_state['step'] = 'waiting_roi_trigger'
                
                send_telegram(
                    f"🎯 <b>CHỌN NGƯỠNG ROI ĐỂ KÍCH HOẠT CƠ CHẾ CHỐT LỆNH THÔNG MINH</b>\n\n"
                    f"📊 <b>Cơ chế hoạt động:</b>\n"
                    f"• Khi ROI đạt ngưỡng bạn chọn\n"
                    f"• Bot sẽ theo dõi số nến toàn thị trường\n"
                    f"• Chốt lệnh nếu nến giảm 30% so với lúc vào\n"
                    f"• Kết hợp với TP/SL truyền thống\n\n"
                    f"Chọn ngưỡng ROI trigger (%):",
                    chat_id,
                    create_roi_trigger_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

        elif current_step == 'waiting_roi_trigger':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text == '❌ Tắt tính năng':
                user_state['roi_trigger'] = None
                self._continue_bot_creation(chat_id, user_state)
            else:
                try:
                    roi_trigger = float(text)
                    if roi_trigger <= 0:
                        send_telegram("⚠️ ROI Trigger phải lớn hơn 0. Vui lòng chọn lại:",
                                    chat_id, create_roi_trigger_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['roi_trigger'] = roi_trigger
                    self._continue_bot_creation(chat_id, user_state)
                    
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho ROI Trigger:",
                                chat_id, create_roi_trigger_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

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

                    # THÊM CẢNH BÁO VỀ ĐÒN BẨY CAO
                    warning_msg = ""
                    if leverage > 50:
                        warning_msg = f"\n\n⚠️ <b>CẢNH BÁO RỦI RO CAO</b>\nĐòn bẩy {leverage}x rất nguy hiểm!"
                    elif leverage > 20:
                        warning_msg = f"\n\n⚠️ <b>CẢNH BÁO RỦI RO</b>\nĐòn bẩy {leverage}x có rủi ro cao!"

                    user_state['leverage'] = leverage
                    user_state['step'] = 'waiting_percent'
                    
                    balance = get_balance(self.api_key, self.api_secret)
                    balance_info = f"\n💰 Số dư hiện có: {balance:.2f} USDT" if balance else ""
                    
                    send_telegram(
                        f"💰 Đòn bẩy: {leverage}x{balance_info}{warning_msg}\n\n"
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
                    
                    # Lấy tất cả thông tin từ user_state
                    strategy = user_state.get('strategy')
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
                        strategy_type=strategy,
                        bot_mode=bot_mode,
                        bot_count=bot_count
                    )
                    
                    if success:
                        roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else ""
                        
                        success_msg = (
                            f"✅ <b>ĐÃ TẠO {bot_count} BOT THÀNH CÔNG</b>\n\n"
                            f"🤖 Chiến lược: {strategy}\n"
                            f"🔧 Chế độ: {bot_mode}\n"
                            f"🔢 Số lượng: {bot_count} bot độc lập\n"
                            f"💰 Đòn bẩy: {leverage}x\n"
                            f"📊 % Số dư: {percent}%\n"
                            f"🎯 TP: {tp}%\n"
                            f"🛡️ SL: {sl}%{roi_info}"
                        )
                        if bot_mode == 'static' and symbol:
                            success_msg += f"\n🔗 Coin: {symbol}"
                        
                        success_msg += f"\n\n🎯 <b>TÍN HIỆU TOÀN THỊ TRƯỜNG ĐÃ KÍCH HOẠT</b>\n"
                        success_msg += f"📊 Phân tích 100 coin volume cao\n"
                        success_msg += f"⏰ So sánh 2 nến 1 phút\n"
                        success_msg += f"🔄 Mỗi bot là 1 vòng lặp độc lập\n\n"
                        success_msg += f"🔄 <b>CƠ CHẾ MỞ LỆNH NGƯỢC LẠI ĐÃ KÍCH HOẠT</b>\n"
                        success_msg += f"📈 Sau khi đóng lệnh, bot tự mở lệnh ngược lại\n"
                        success_msg += f"💵 Giữ nguyên số tiền đầu tư: {percent}%\n"
                        success_msg += f"🔗 Giữ nguyên coin (chỉ tìm mới khi lỗi)"
                        
                        if roi_trigger:
                            success_msg += f"\n\n🎯 <b>CƠ CHẾ ROI {roi_trigger}% ĐÃ KÍCH HOẠT</b>\n"
                            success_msg += f"📈 Khi ROI đạt {roi_trigger}%, bot sẽ theo dõi nến\n"
                            success_msg += f"⏰ Chốt lệnh nếu nến giảm 30% so với lúc vào"
                        
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
                
                active_bots = 0
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
                    message += f"🔹 {bot_id}\n"
                    message += f"   📊 {symbol_info} | {status}\n"
                    message += f"   💰 ĐB: {bot.lev}x | Vốn: {bot.percent}%{roi_info}\n\n"
                
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
                "🎯 <b>HỆ THỐNG PHÂN TÍCH TOÀN THỊ TRƯỜNG VỚI CƠ CHẾ MỞ LỆNH NGƯỢC LẠI</b>\n\n"
                
                "📊 <b>Nguyên tắc giao dịch:</b>\n"
                "• Phân tích 100 coin volume cao nhất\n"
                "• So sánh 2 nến 1 PHÚT liên tiếp\n"
                "• Nến xanh tăng ≥10% → Tín hiệu BUY\n"
                "• Nến đỏ tăng ≥10% → Tín hiệu SELL\n"
                "• Còn lại → BỎ QUA\n\n"
                
                "🔄 <b>Cơ chế mở lệnh ngược lại:</b>\n"
                "• Sau khi đóng lệnh, bot tự động mở lệnh ngược lại\n"
                "• Giữ nguyên coin, giữ nguyên số tiền đầu tư\n"
                "• Tiếp tục luân phiên BUY/SELL trên cùng coin\n"
                "• Chỉ tìm coin mới khi có lỗi hoặc dừng bot\n\n"
                
                "🎯 <b>Cơ chế chốt lệnh ROI thông minh:</b>\n"
                "• Khi ROI đạt ngưỡng (do bạn đặt)\n"
                "• Theo dõi số nến xanh/đỏ toàn thị trường\n"
                "• Chốt lệnh nếu nến giảm 30% so với lúc vào\n"
                "• Kết hợp TP/SL truyền thống\n\n"
                
                "🔍 <b>Lọc coin thông minh:</b>\n"
                "• Tự động chọn ngẫu nhiên từ 600 coin\n"
                "• Kiểm tra đòn bẩy tối đa của coin\n"
                "• Tránh trùng lặp với các bot khác\n\n"
                
                "🔄 <b>Quy trình tìm coin:</b>\n"
                "1. Phân tích toàn thị trường (100 coin volume cao)\n"
                "2. Xác định hướng ưu tiên (BUY/SELL)\n"
                "3. Quét ngẫu nhiên 600 coin\n"
                "4. Kiểm tra đòn bẩy hỗ trợ\n"
                "5. Chọn coin không trùng lặp\n"
                "6. Vào lệnh và quản lý TP/SL + Nhồi lệnh Fibonacci\n"
                "7. Sau khi đóng lệnh → Tự động mở lệnh ngược lại"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            
            searching_bots = sum(1 for bot in self.bots.values() if bot.status == "searching")
            trading_bots = sum(1 for bot in self.bots.values() if bot.status in ["waiting", "open"])
            
            roi_bots = sum(1 for bot in self.bots.values() if bot.roi_trigger is not None)
            
            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG ĐA LUỒNG</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Tổng số bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots} bot\n"
                f"📊 Đang trade: {trading_bots} bot\n"
                f"🎯 Bot có ROI Trigger: {roi_bots} bot\n"
                f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối\n\n"
                f"🔄 <b>CƠ CHẾ MỞ LỆNH NGƯỢC LẠI ĐANG HOẠT ĐỘNG</b>"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

    def _continue_bot_creation(self, chat_id, user_state):
        strategy = user_state.get('strategy')
        bot_mode = user_state.get('bot_mode', 'static')
        bot_count = user_state.get('bot_count', 1)
        roi_trigger = user_state.get('roi_trigger')
        
        roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else ""
        
        if bot_mode == 'static':
            user_state['step'] = 'waiting_symbol'
            send_telegram(
                f"🎯 <b>BOT TĨNH: {strategy}</b>\n"
                f"🤖 Số lượng: {bot_count} bot độc lập{roi_info}\n\n"
                f"🤖 Mỗi bot sẽ trade coin CỐ ĐỊNH\n\n"
                f"Chọn cặp coin:",
                chat_id,
                create_symbols_keyboard(strategy),
                self.telegram_bot_token, self.telegram_chat_id
            )
        else:
            user_state['step'] = 'waiting_leverage'
            send_telegram(
                f"🎯 <b>BOT ĐỘNG ĐA LUỒNG</b>\n"
                f"🤖 Số lượng: {bot_count} bot độc lập{roi_info}\n\n"
                f"🤖 Mỗi bot sẽ tự tìm coin & trade độc lập\n"
                f"🔄 Tự reset hoàn toàn sau mỗi lệnh\n"
                f"📊 Mỗi bot là 1 vòng lặp hoàn chỉnh\n"
                f"⚖️ Tự cân bằng với các bot khác\n\n"
                f"Chọn đòn bẩy:",
                chat_id,
                create_leverage_keyboard(strategy),
                self.telegram_bot_token, self.telegram_chat_id
            )

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()
