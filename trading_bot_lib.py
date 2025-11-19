# trading_bot_lib_complete.py - HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH
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
        level=logging.WARNING,  # CHỈ HIỂN THỊ WARNING VÀ ERROR
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_errors.log')
        ]
    )
    return logging.getLogger()

logger = setup_logging()

# ========== HÀM TELEGRAM ĐÃ SỬA LỖI ==========
def escape_html(text):
    """Escape các ký tự đặc biệt trong HTML để tránh lỗi Telegram"""
    if not text:
        return text
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

def send_telegram(message, chat_id=None, reply_markup=None, bot_token=None, default_chat_id=None):
    """Hàm gửi Telegram đã sửa lỗi - LUÔN TRUYỀN ĐỦ THAM SỐ"""
    if not bot_token:
        logger.warning("Telegram Bot Token chưa được thiết lập")
        return False
    
    chat_id = chat_id or default_chat_id
    if not chat_id:
        logger.warning("Telegram Chat ID chưa được thiết lập")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # ESCAPE MESSAGE ĐỂ TRÁNH LỐI HTML
    safe_message = escape_html(message)
    
    payload = {
        "chat_id": chat_id,
        "text": safe_message,
        "parse_mode": "HTML"
    }
    
    # 🔴 SỬA LỖI: CHỈ THÊM REPLY_MARKUP NẾU CÓ
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Lỗi Telegram ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        logger.error(f"Lỗi kết nối Telegram: {str(e)}")
        return False


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
            [{"text": "📊 Hệ thống RSI + Khối lượng"}],
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
        max_workers = 8
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
                time.sleep(0.5)

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
            return 100
        
        for s in data['symbols']:
            if s['symbol'] == symbol.upper():
                for f in s['filters']:
                    if f['filterType'] == 'LEVERAGE':
                        if 'maxLeverage' in f:
                            return int(f['maxLeverage'])
                break
        return 100
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

# ========== SMART COIN FINDER VỚI HỆ THỐNG RSI + KHỐI LƯỢNG ==========
class SmartCoinFinder:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def get_symbol_leverage(self, symbol):
        """Lấy đòn bẩy tối đa của symbol"""
        return get_max_leverage(symbol, self.api_key, self.api_secret)
    
    def calculate_rsi(self, prices, period=14):
        """Tính RSI từ danh sách giá"""
        if len(prices) < period + 1:
            return 50  # Giá trị trung bình nếu không đủ dữ liệu
            
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = np.mean(gains[:period])
        avg_losses = np.mean(losses[:period])
        
        if avg_losses == 0:
            return 100
            
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def get_rsi_signal(self, symbol, volume_threshold=20):
        """Phân tích tín hiệu RSI và khối lượng - DÙNG CHUNG CHO CẢ VÀO VÀ ĐÓNG LỆNH"""
        try:
            # Lấy dữ liệu kline 5 phút
            data = binance_api_request(
                "https://fapi.binance.com/fapi/v1/klines",
                params={"symbol": symbol, "interval": "5m", "limit": 15}
            )
            if not data or len(data) < 15:
                return None
            
            # Lấy 2 nến gần nhất đã đóng
            prev_candle = data[-3]  # Nến trước
            current_candle = data[-2]  # Nến hiện tại (đã đóng)
            
            # Giá đóng cửa cho RSI
            closes = [float(k[4]) for k in data]
            
            # Tính RSI cho 2 nến
            rsi_prev = self.calculate_rsi(closes[:-1])  # RSI nến trước
            rsi_current = self.calculate_rsi(closes)    # RSI nến hiện tại
            
            # Khối lượng
            prev_volume = float(prev_candle[5])
            current_volume = float(current_candle[5])
            volume_change = (current_volume - prev_volume) / prev_volume * 100

            # PHÂN TÍCH TÍN HIỆU - LOGIC CHUNG
            # TH1: RSI ở vùng cực (>80 hoặc <20) và đang hồi về trung tâm
            if (rsi_prev > 80 and rsi_current < rsi_prev and volume_change < -volume_threshold):
                return "SELL"  # Từ vùng quá mua hồi về
            elif (rsi_prev < 20 and rsi_current > rsi_prev and volume_change < -volume_threshold):
                return "BUY"   # Từ vùng quá bán hồi về
            
            # TH2: RSI trong vùng 30-70 và khối lượng tăng
            elif (30 <= rsi_current <= 70 and volume_change > volume_threshold):
                if rsi_current > 55:
                    return "BUY"
                elif rsi_current < 45:
                    return "SELL"
            return None
            
        except Exception as e:
            logger.error(f"Lỗi phân tích RSI {symbol}: {str(e)}")
            return None
    
    def get_entry_signal(self, symbol):
        """Tín hiệu vào lệnh - khối lượng 20%"""
        return self.get_rsi_signal(symbol, volume_threshold=20)
    
    def get_exit_signal(self, symbol):
        """Tín hiệu đóng lệnh - khối lượng 40%"""
        return self.get_rsi_signal(symbol, volume_threshold=40)
    
    def has_existing_position(self, symbol):
        """Kiểm tra xem coin đã có vị thế trên Binance chưa"""
        try:
            positions = get_positions(symbol, self.api_key, self.api_secret)
            if positions:
                for pos in positions:
                    position_amt = float(pos.get('positionAmt', 0))
                    if abs(position_amt) > 0:
                        logger.info(f"⚠️ Phát hiện vị thế trên {symbol}: {position_amt}")
                        return True
            return False
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra vị thế {symbol}: {str(e)}")
            return True
    
    def find_best_coin(self, target_direction, excluded_coins=None, required_leverage=10):
        """Tìm coin tốt nhất - MỖI COIN ĐỘC LẬP"""
        try:
            all_symbols = get_all_usdc_pairs(limit=50)
            if not all_symbols:
                return None
            
            valid_symbols = []
            
            for symbol in all_symbols:
                # Kiểm tra coin đã bị loại trừ
                if excluded_coins and symbol in excluded_coins:
                    continue
                
                # 🔴 QUAN TRỌNG: Kiểm tra coin đã có vị thế trên Binance
                if self.has_existing_position(symbol):
                    logger.info(f"🚫 Bỏ qua {symbol} - đã có vị thế trên Binance")
                    continue
                
                # Kiểm tra đòn bẩy
                max_lev = self.get_symbol_leverage(symbol)
                if max_lev < required_leverage:
                    continue
                
                # 🔴 SỬ DỤNG TÍN HIỆU VÀO LỆNH (20% khối lượng)
                entry_signal = self.get_entry_signal(symbol)
                if entry_signal == target_direction:
                    valid_symbols.append(symbol)
                    logger.info(f"✅ Tìm thấy coin phù hợp: {symbol} - Tín hiệu: {entry_signal}")
                else:
                    logger.info(f"🔄 Bỏ qua {symbol} - Tín hiệu: {entry_signal} (không trùng với {target_direction})")
            
            if not valid_symbols:
                logger.info(f"❌ Không tìm thấy coin nào có tín hiệu trùng với {target_direction}")
                return None
            
            # Chọn ngẫu nhiên từ danh sách hợp lệ
            selected_symbol = random.choice(valid_symbols)
            max_lev = self.get_symbol_leverage(selected_symbol)
            
            # 🔴 KIỂM TRA LẦN CUỐI: Đảm bảo coin được chọn không có vị thế
            if self.has_existing_position(selected_symbol):
                logger.info(f"🚫 {selected_symbol} - Coin được chọn đã có vị thế, bỏ qua")
                return None
            
            logger.info(f"✅ Đã chọn coin: {selected_symbol} - Tín hiệu: {target_direction} - Đòn bẩy: {max_lev}x")
            return selected_symbol
            
        except Exception as e:
            logger.error(f"❌ Lỗi tìm coin: {str(e)}")
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
        logger.info(f"🔗 WebSocket bắt đầu cho {symbol}")
        
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

# ========== BASE BOT VỚI HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH ==========
# ========== BASE BOT VỚI HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager, api_key, api_secret,
                 telegram_bot_token, telegram_chat_id, strategy_name, config_key=None, bot_id=None,
                 coin_manager=None, symbol_locks=None, max_coins=1):

        self.max_coins = max_coins
        self.active_symbols = []
        self.symbol_data = {}
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

        # 🔴 LUÔN Ở TRẠNG THÁI TÌM KIẾM
        self.status = "searching"
        self._stop = False

        # 🔴 BIẾN QUẢN LÝ - GIẢM THỜI GIAN CHỜ ĐỢI
        self.current_processing_symbol = None
        self.last_trade_completion_time = 0
        self.trade_cooldown = 1  # 🔴 GIẢM từ 3s xuống 1s để vào lệnh nhanh hơn

        # Quản lý thời gian
        self.last_global_position_check = 0
        self.last_error_log_time = 0
        self.global_position_check_interval = 10

        # Thống kê
        self.global_long_count = 0
        self.global_short_count = 0
        self.global_long_pnl = 0
        self.global_short_pnl = 0

        self.coin_manager = coin_manager or CoinManager()
        self.symbol_locks = symbol_locks
        self.coin_finder = SmartCoinFinder(api_key, api_secret)

        self.find_new_bot_after_close = True
        self.bot_creation_time = time.time()

        # 🔴 LOCK ĐẢM BẢO THREAD-SAFE
        self.symbol_management_lock = threading.Lock()

        # Khởi tạo symbol đầu tiên nếu có
        if symbol and not self.coin_finder.has_existing_position(symbol):
            self._add_symbol(symbol)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else " | 🎯 ROI Trigger: Tắt"
        self.log(f"🟢 Bot {strategy_name} khởi động | Tối đa: {max_coins} coin | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%{roi_info}")

    def _run(self):
        """VÒNG LẶP CHÍNH - XỬ LÝ TỪNG COIN ĐỘC LẬP"""
        while not self._stop:
            try:
                current_time = time.time()
                
                # KIỂM TRA VỊ THẾ TOÀN TÀI KHOẢN ĐỊNH KỲ
                if current_time - self.last_global_position_check > self.global_position_check_interval:
                    self.check_global_positions()
                    self.last_global_position_check = current_time
                
                # 🔴 LUÔN TÌM COIN MỚI NẾU CHƯA ĐẠT GIỚI HẠN
                if len(self.active_symbols) < self.max_coins:
                    if self._find_and_add_new_coin():
                        # 🔴 KHÔNG CHỜ ĐỢI - TIẾP TỤC XỬ LÝ NGAY
                        time.sleep(0.5)
                        continue
                
                # 🔴 XỬ LÝ TẤT CẢ COIN ĐANG HOẠT ĐỘNG - MỖI COIN ĐỘC LẬP
                processed_any = False
                for symbol in self.active_symbols[:]:  # Dùng bản copy để tránh thay đổi trong khi lặp
                    if self._process_single_symbol_independent(symbol):
                        processed_any = True
                        # 🔴 CHỈ CHỜ 1s SAU KHI XỬ LÝ THÀNH CÔNG MỘT COIN
                        time.sleep(1)
                
                # 🔴 NẾU KHÔNG XỬ LÝ ĐƯỢC COIN NÀO, NGHỈ NGẮN
                if not processed_any:
                    time.sleep(2)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    self.log(f"❌ Lỗi hệ thống: {str(e)}")
                    self.last_error_log_time = time.time()
                time.sleep(1)

    def _process_single_symbol_independent(self, symbol):
        """XỬ LÝ MỘT SYMBOL ĐỘC LẬP - VÀO LỆNH NGAY KHI CÓ TÍN HIỆU"""
        try:
            symbol_info = self.symbol_data[symbol]
            current_time = time.time()
            
            # Kiểm tra vị thế định kỳ
            if current_time - symbol_info.get('last_position_check', 0) > 30:
                self._check_symbol_position(symbol)
                symbol_info['last_position_check'] = current_time
            
            # 🔴 KIỂM TRA VỊ THẾ TRÊN BINANCE
            if self.coin_finder.has_existing_position(symbol) and not symbol_info['position_open']:
                self.log(f"⚠️ {symbol} - PHÁT HIỆN CÓ VỊ THẾ TRÊN BINANCE, DỪNG THEO DÕI")
                self.stop_symbol(symbol)
                return False
            
            # Xử lý theo trạng thái
            if symbol_info['position_open']:
                # 🔴 KIỂM TRA ĐÓNG LỆNH THÔNG MINH
                if self._check_smart_exit_condition(symbol):
                    return True
                
                # 🔴 KIỂM TRA TP/SL TRUYỀN THỐNG
                if self._check_symbol_tp_sl(symbol):
                    return True
                
                # 🔴 KIỂM TRA NHỒI LỆNH
                if self._check_symbol_averaging_down(symbol):
                    return True
            else:
                # 🔴 VÀO LỆNH NGAY KHI CÓ TÍN HIỆU - KHÔNG CHỜ ĐỢI
                if (current_time - symbol_info['last_trade_time'] > 30 and  # 🔴 GIẢM THỜI GIAN CHỜ TỪ 60s xuống 30s
                    current_time - symbol_info['last_close_time'] > 1800):  # 🔴 GIẢM THỜI GIAN CHỜ TỪ 3600s xuống 1800s
                    
                    target_side = self.get_next_side_based_on_comprehensive_analysis()
                    
                    # 🔴 SỬ DỤNG TÍN HIỆU VÀO LỆNH
                    entry_signal = self.coin_finder.get_entry_signal(symbol)
                    
                    if entry_signal == target_side:
                        # 🔴 KIỂM TRA CUỐI CÙNG TRƯỚC KHI VÀO LỆNH
                        if self.coin_finder.has_existing_position(symbol):
                            self.log(f"🚫 {symbol} - ĐÃ CÓ VỊ THẾ TRÊN BINANCE, BỎ QUA")
                            self.stop_symbol(symbol)
                            return False
                        
                        if self._open_symbol_position(symbol, target_side):
                            symbol_info['last_trade_time'] = current_time
                            return True
            
            return False
            
        except Exception as e:
            self.log(f"❌ Lỗi xử lý {symbol}: {str(e)}")
            return False

    def _find_and_add_new_coin(self):
        """TÌM VÀ THÊM COIN MỚI - THREAD-SAFE"""
        with self.symbol_management_lock:
            try:
                if len(self.active_symbols) >= self.max_coins:
                    return False
                    
                active_coins = self.coin_manager.get_active_coins()
                target_direction = self.get_next_side_based_on_comprehensive_analysis()
                
                new_symbol = self.coin_finder.find_best_coin(
                    target_direction=target_direction,
                    excluded_coins=active_coins,
                    required_leverage=self.lev
                )
                
                if new_symbol:
                    if self.coin_finder.has_existing_position(new_symbol):
                        return False
                        
                    success = self._add_symbol(new_symbol)
                    if success:
                        self.log(f"✅ Đã thêm coin thứ {len(self.active_symbols)}: {new_symbol}")
                        # 🔴 XỬ LÝ COIN MỚI NGAY LẬP TỨC
                        threading.Thread(target=self._process_new_symbol_immediately, args=(new_symbol,), daemon=True).start()
                        return True
                    
                return False
                
            except Exception as e:
                self.log(f"❌ Lỗi tìm coin mới: {str(e)}")
                return False

    def _process_new_symbol_immediately(self, symbol):
        """XỬ LÝ COIN MỚI NGAY SAU KHI THÊM"""
        try:
            time.sleep(0.5)  # Chờ ngắn để dữ liệu khởi tạo
            self._process_single_symbol_independent(symbol)
        except Exception as e:
            self.log(f"❌ Lỗi xử lý coin mới {symbol}: {str(e)}")

    def _add_symbol(self, symbol):
        """THÊM SYMBOL - THREAD-SAFE"""
        with self.symbol_management_lock:
            if symbol in self.active_symbols:
                return False
                
            if len(self.active_symbols) >= self.max_coins:
                return False
            
            if self.coin_finder.has_existing_position(symbol):
                return False
            
            # Khởi tạo dữ liệu cho symbol
            self.symbol_data[symbol] = {
                'status': 'waiting',
                'side': '',
                'qty': 0,
                'entry': 0,
                'current_price': 0,
                'position_open': False,
                'last_trade_time': 0,
                'last_close_time': 0,
                'entry_base': 0,
                'average_down_count': 0,
                'last_average_down_time': 0,
                'high_water_mark_roi': 0,
                'roi_check_activated': False,
                'close_attempted': False,
                'last_close_attempt': 0,
                'last_position_check': 0
            }
            
            self.active_symbols.append(symbol)
            self.coin_manager.register_coin(symbol)
            self.ws_manager.add_symbol(symbol, lambda price, sym=symbol: self._handle_price_update(price, sym))
            
            self._check_symbol_position(symbol)
            
            if self.symbol_data[symbol]['position_open']:
                self.stop_symbol(symbol)
                return False
            
            return True

    def _check_smart_exit_condition(self, symbol):
        """KIỂM TRA ĐÓNG LỆNH THÔNG MINH - HOÀN CHỈNH"""
        try:
            if not self.symbol_data[symbol]['position_open']:
                return False
            
            if not self.symbol_data[symbol]['roi_check_activated']:
                return False
            
            current_price = get_current_price(symbol)
            if current_price <= 0:
                return False
            
            # Tính ROI hiện tại
            if self.symbol_data[symbol]['side'] == "BUY":
                profit = (current_price - self.symbol_data[symbol]['entry']) * abs(self.symbol_data[symbol]['qty'])
            else:
                profit = (self.symbol_data[symbol]['entry'] - current_price) * abs(self.symbol_data[symbol]['qty'])
                
            invested = self.symbol_data[symbol]['entry'] * abs(self.symbol_data[symbol]['qty']) / self.lev
            if invested <= 0:
                return False
                
            current_roi = (profit / invested) * 100
            
            # Kiểm tra nếu đạt ROI trigger
            if current_roi >= self.roi_trigger:
                # 🔴 SỬ DỤNG TÍN HIỆU ĐÓNG LỆNH
                exit_signal = self.coin_finder.get_exit_signal(symbol)
                
                if exit_signal:
                    reason = f"🎯 Đạt ROI {self.roi_trigger}% + Tín hiệu đóng lệnh (ROI: {current_roi:.2f}%)"
                    self._close_symbol_position(symbol, reason)
                    return True
            
            return False
            
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra đóng lệnh thông minh {symbol}: {str(e)}")
            return False

    def _handle_price_update(self, price, symbol):
        """XỬ LÝ CẬP NHẬT GIÁ"""
        if symbol in self.symbol_data:
            self.symbol_data[symbol]['current_price'] = price

    def _check_symbol_position(self, symbol):
        """KIỂM TRA VỊ THẾ CHO SYMBOL"""
        try:
            positions = get_positions(symbol, self.api_key, self.api_secret)
            if not positions:
                self._reset_symbol_position(symbol)
                return
            
            position_found = False
            for pos in positions:
                if pos['symbol'] == symbol:
                    position_amt = float(pos.get('positionAmt', 0))
                    if abs(position_amt) > 0:
                        position_found = True
                        self.symbol_data[symbol]['position_open'] = True
                        self.symbol_data[symbol]['status'] = "open"
                        self.symbol_data[symbol]['side'] = "BUY" if position_amt > 0 else "SELL"
                        self.symbol_data[symbol]['qty'] = position_amt
                        self.symbol_data[symbol]['entry'] = float(pos.get('entryPrice', 0))
                        
                        # Kích hoạt ROI check nếu đang có lợi nhuận
                        current_price = get_current_price(symbol)
                        if current_price > 0:
                            if self.symbol_data[symbol]['side'] == "BUY":
                                profit = (current_price - self.symbol_data[symbol]['entry']) * abs(self.symbol_data[symbol]['qty'])
                            else:
                                profit = (self.symbol_data[symbol]['entry'] - current_price) * abs(self.symbol_data[symbol]['qty'])
                                
                            invested = self.symbol_data[symbol]['entry'] * abs(self.symbol_data[symbol]['qty']) / self.lev
                            if invested > 0:
                                current_roi = (profit / invested) * 100
                                if current_roi >= self.roi_trigger:
                                    self.symbol_data[symbol]['roi_check_activated'] = True
                        break
                    else:
                        position_found = True
                        self._reset_symbol_position(symbol)
                        break
            
            if not position_found:
                self._reset_symbol_position(symbol)
                
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra vị thế {symbol}: {str(e)}")

    def _reset_symbol_position(self, symbol):
        """RESET TRẠNG THÁI VỊ THẾ"""
        if symbol in self.symbol_data:
            self.symbol_data[symbol]['position_open'] = False
            self.symbol_data[symbol]['status'] = "waiting"
            self.symbol_data[symbol]['side'] = ""
            self.symbol_data[symbol]['qty'] = 0
            self.symbol_data[symbol]['entry'] = 0
            self.symbol_data[symbol]['close_attempted'] = False
            self.symbol_data[symbol]['last_close_attempt'] = 0
            self.symbol_data[symbol]['entry_base'] = 0
            self.symbol_data[symbol]['average_down_count'] = 0
            self.symbol_data[symbol]['high_water_mark_roi'] = 0
            self.symbol_data[symbol]['roi_check_activated'] = False

    def _open_symbol_position(self, symbol, side):
        """MỞ VỊ THẾ - KIỂM TRA KỸ TRƯỚC KHI VÀO LỆNH"""
        try:
            # 🔴 KIỂM TRA QUAN TRỌNG
            if self.coin_finder.has_existing_position(symbol):
                self.log(f"⚠️ {symbol} - ĐÃ CÓ VỊ THẾ TRÊN BINANCE, BỎ QUA")
                self.stop_symbol(symbol)
                return False

            # Kiểm tra lại trạng thái trong bot
            self._check_symbol_position(symbol)
            if self.symbol_data[symbol]['position_open']:
                return False

            # Kiểm tra đòn bẩy
            current_leverage = self.coin_finder.get_symbol_leverage(symbol)
            if current_leverage < self.lev:
                self.log(f"❌ {symbol} - Đòn bẩy không đủ: {current_leverage}x < {self.lev}x")
                self.stop_symbol(symbol)
                return False

            if not set_leverage(symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ {symbol} - Không thể đặt đòn bẩy")
                self.stop_symbol(symbol)
                return False

            # Số dư
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log(f"❌ {symbol} - Không đủ số dư")
                return False

            # Giá & step size
            current_price = get_current_price(symbol)
            if current_price <= 0:
                self.log(f"❌ {symbol} - Lỗi lấy giá")
                self.stop_symbol(symbol)
                return False

            step_size = get_step_size(symbol, self.api_key, self.api_secret)

            # Tính khối lượng
            usd_amount = balance * (self.percent / 100)
            qty = (usd_amount * self.lev) / current_price
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)

            if qty <= 0 or qty < step_size:
                self.log(f"❌ {symbol} - Khối lượng không hợp lệ")
                self.stop_symbol(symbol)
                return False

            cancel_all_orders(symbol, self.api_key, self.api_secret)
            time.sleep(0.2)

            result = place_order(symbol, side, qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))

                if executed_qty >= 0:
                    # 🔴 KIỂM TRA LẦN CUỐI
                    time.sleep(1)
                    self._check_symbol_position(symbol)
                    
                    if not self.symbol_data[symbol]['position_open']:
                        self.log(f"❌ {symbol} - Lệnh đã khớp nhưng không tạo được vị thế")
                        self.stop_symbol(symbol)
                        return False
                    
                    # Cập nhật thông tin vị thế
                    self.symbol_data[symbol]['entry'] = avg_price
                    self.symbol_data[symbol]['entry_base'] = avg_price
                    self.symbol_data[symbol]['average_down_count'] = 0
                    self.symbol_data[symbol]['side'] = side
                    self.symbol_data[symbol]['qty'] = executed_qty if side == "BUY" else -executed_qty
                    self.symbol_data[symbol]['position_open'] = True
                    self.symbol_data[symbol]['status'] = "open"
                    self.symbol_data[symbol]['high_water_mark_roi'] = 0
                    self.symbol_data[symbol]['roi_check_activated'] = False

                    message = (
                        f"✅ <b>ĐÃ MỞ VỊ THẾ {symbol}</b>\n"
                        f"🤖 Bot: {self.bot_id}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {avg_price:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    if self.roi_trigger:
                        message += f" | 🎯 ROI Trigger: {self.roi_trigger}%"
                    
                    self.log(message)
                    return True
                else:
                    self.log(f"❌ {symbol} - Lệnh không khớp")
                    self.stop_symbol(symbol)
                    return False
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ {symbol} - Lỗi đặt lệnh: {error_msg}")
                self.stop_symbol(symbol)
                return False

        except Exception as e:
            self.log(f"❌ {symbol} - Lỗi mở lệnh: {str(e)}")
            self.stop_symbol(symbol)
            return False

    def _close_symbol_position(self, symbol, reason=""):
        """ĐÓNG VỊ THẾ"""
        try:
            self._check_symbol_position(symbol)
            
            if not self.symbol_data[symbol]['position_open'] or abs(self.symbol_data[symbol]['qty']) <= 0:
                return True

            current_time = time.time()
            if (self.symbol_data[symbol]['close_attempted'] and 
                current_time - self.symbol_data[symbol]['last_close_attempt'] < 30):
                return False
            
            self.symbol_data[symbol]['close_attempted'] = True
            self.symbol_data[symbol]['last_close_attempt'] = current_time

            close_side = "SELL" if self.symbol_data[symbol]['side'] == "BUY" else "BUY"
            close_qty = abs(self.symbol_data[symbol]['qty'])
            
            cancel_all_orders(symbol, self.api_key, self.api_secret)
            time.sleep(0.5)
            
            result = place_order(symbol, close_side, close_qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                current_price = get_current_price(symbol)
                pnl = 0
                if self.symbol_data[symbol]['entry'] > 0:
                    if self.symbol_data[symbol]['side'] == "BUY":
                        pnl = (current_price - self.symbol_data[symbol]['entry']) * abs(self.symbol_data[symbol]['qty'])
                    else:
                        pnl = (self.symbol_data[symbol]['entry'] - current_price) * abs(self.symbol_data[symbol]['qty'])
                
                message = (
                    f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ {symbol}</b>\n"
                    f"🤖 Bot: {self.bot_id}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDC\n"
                    f"📈 Số lần nhồi: {self.symbol_data[symbol]['average_down_count']}"
                )
                self.log(message)
                
                self.symbol_data[symbol]['last_close_time'] = time.time()
                self._reset_symbol_position(symbol)
                
                return True
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ {symbol} - Lỗi đóng lệnh: {error_msg}")
                self.symbol_data[symbol]['close_attempted'] = False
                return False
                
        except Exception as e:
            self.log(f"❌ {symbol} - Lỗi đóng lệnh: {str(e)}")
            self.symbol_data[symbol]['close_attempted'] = False
            return False

    def _check_symbol_tp_sl(self, symbol):
        """KIỂM TRA TP/SL"""
        if (not self.symbol_data[symbol]['position_open'] or 
            self.symbol_data[symbol]['entry'] <= 0 or 
            self.symbol_data[symbol]['close_attempted']):
            return False

        current_price = get_current_price(symbol)
        if current_price <= 0:
            return False

        if self.symbol_data[symbol]['side'] == "BUY":
            profit = (current_price - self.symbol_data[symbol]['entry']) * abs(self.symbol_data[symbol]['qty'])
        else:
            profit = (self.symbol_data[symbol]['entry'] - current_price) * abs(self.symbol_data[symbol]['qty'])
            
        invested = self.symbol_data[symbol]['entry'] * abs(self.symbol_data[symbol]['qty']) / self.lev
        if invested <= 0:
            return False
            
        roi = (profit / invested) * 100

        # CẬP NHẬT ROI CAO NHẤT
        if roi > self.symbol_data[symbol]['high_water_mark_roi']:
            self.symbol_data[symbol]['high_water_mark_roi'] = roi

        # KIỂM TRA ĐIỀU KIỆN ROI TRIGGER
        if (self.roi_trigger is not None and 
            self.symbol_data[symbol]['high_water_mark_roi'] >= self.roi_trigger and 
            not self.symbol_data[symbol]['roi_check_activated']):
            self.symbol_data[symbol]['roi_check_activated'] = True

        # TP/SL TRUYỀN THỐNG
        position_closed = False
        if self.tp is not None and roi >= self.tp:
            self._close_symbol_position(symbol, f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
            position_closed = True
        elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
            self._close_symbol_position(symbol, f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")
            position_closed = True
            
        return position_closed

    def _check_symbol_averaging_down(self, symbol):
        """KIỂM TRA NHỒI LỆNH"""
        if (not self.symbol_data[symbol]['position_open'] or 
            not self.symbol_data[symbol]['entry_base'] or 
            self.symbol_data[symbol]['average_down_count'] >= 7):
            return False
            
        try:
            current_time = time.time()
            if current_time - self.symbol_data[symbol]['last_average_down_time'] < 60:
                return False
                
            current_price = get_current_price(symbol)
            if current_price <= 0:
                return False
                
            # Tính ROI ÂM hiện tại (lỗ)
            if self.symbol_data[symbol]['side'] == "BUY":
                profit = (current_price - self.symbol_data[symbol]['entry_base']) * abs(self.symbol_data[symbol]['qty'])
            else:
                profit = (self.symbol_data[symbol]['entry_base'] - current_price) * abs(self.symbol_data[symbol]['qty'])
                
            invested = self.symbol_data[symbol]['entry_base'] * abs(self.symbol_data[symbol]['qty']) / self.lev
            if invested <= 0:
                return False
                
            current_roi = (profit / invested) * 100
            
            # Chỉ xét khi ROI ÂM (đang lỗ)
            if current_roi >= 0:
                return False
                
            # Chuyển ROI âm thành số dương để so sánh
            roi_negative = abs(current_roi)
            
            # Các mốc Fibonacci
            fib_levels = [200, 300, 500, 800, 1300, 2100, 3400]
            
            if self.symbol_data[symbol]['average_down_count'] < len(fib_levels):
                current_fib_level = fib_levels[self.symbol_data[symbol]['average_down_count']]
                
                if roi_negative >= current_fib_level:
                    if self._execute_symbol_average_down(symbol):
                        self.symbol_data[symbol]['last_average_down_time'] = current_time
                        self.symbol_data[symbol]['average_down_count'] += 1
                        self.log(f"📈 {symbol} - Đã nhồi lệnh Fibonacci ở mốc {current_fib_level}% lỗ")
                        return True
                        
            return False
            
        except Exception as e:
            self.log(f"❌ {symbol} - Lỗi kiểm tra nhồi lệnh: {str(e)}")
            return False

    def _execute_symbol_average_down(self, symbol):
        """THỰC HIỆN NHỒI LỆNH"""
        try:
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                return False
                
            current_price = get_current_price(symbol)
            if current_price <= 0:
                return False
                
            # Khối lượng nhồi = % số dư * (số lần nhồi + 1)
            additional_percent = self.percent * (self.symbol_data[symbol]['average_down_count'] + 1)
            usd_amount = balance * (additional_percent / 100)
            qty = (usd_amount * self.lev) / current_price
            
            step_size = get_step_size(symbol, self.api_key, self.api_secret)
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
            
            if qty < step_size:
                return False
                
            # Đặt lệnh cùng hướng với vị thế hiện tại
            result = place_order(symbol, self.symbol_data[symbol]['side'], qty, self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty >= 0:
                    # Cập nhật giá trung bình và khối lượng
                    total_qty = abs(self.symbol_data[symbol]['qty']) + executed_qty
                    new_entry = (abs(self.symbol_data[symbol]['qty']) * self.symbol_data[symbol]['entry'] + executed_qty * avg_price) / total_qty
                    self.symbol_data[symbol]['entry'] = new_entry
                    self.symbol_data[symbol]['qty'] = total_qty if self.symbol_data[symbol]['side'] == "BUY" else -total_qty
                    
                    message = (
                        f"📈 <b>ĐÃ NHỒI LỆNH {symbol}</b>\n"
                        f"🔢 Lần nhồi: {self.symbol_data[symbol]['average_down_count'] + 1}\n"
                        f"📊 Khối lượng thêm: {executed_qty:.4f}\n"
                        f"🏷️ Giá nhồi: {avg_price:.4f}\n"
                        f"📈 Giá trung bình mới: {new_entry:.4f}\n"
                        f"💰 Tổng khối lượng: {total_qty:.4f}"
                    )
                    self.log(message)
                    return True
                    
            return False
            
        except Exception as e:
            self.log(f"❌ {symbol} - Lỗi nhồi lệnh: {str(e)}")
            return False

    def stop_symbol(self, symbol):
        """DỪNG SYMBOL - TỰ ĐỘNG TÌM COIN MỚI"""
        with self.symbol_management_lock:
            if symbol not in self.active_symbols:
                return False
            
            self.log(f"⛔ Đang dừng coin {symbol}...")
            
            # Nếu đang xử lý coin này, đợi nó xong
            if self.current_processing_symbol == symbol:
                timeout = time.time() + 10
                while self.current_processing_symbol == symbol and time.time() < timeout:
                    time.sleep(0.5)
            
            # Đóng vị thế nếu đang mở
            if self.symbol_data[symbol]['position_open']:
                self._close_symbol_position(symbol, "Dừng coin theo lệnh")
            
            # Dọn dẹp
            self.ws_manager.remove_symbol(symbol)
            self.coin_manager.unregister_coin(symbol)
            
            if symbol in self.symbol_data:
                del self.symbol_data[symbol]
            
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            
            self.log(f"✅ Đã dừng coin {symbol} | Còn lại: {len(self.active_symbols)}/{self.max_coins} coin")
            
            # 🔴 TỰ ĐỘNG TÌM COIN MỚI SAU KHI DỪNG COIN CŨ
            if len(self.active_symbols) < self.max_coins:
                self.log(f"🔄 Tự động tìm coin mới thay thế cho {symbol}...")
                threading.Thread(target=self._delayed_find_new_coin, daemon=True).start()
            
            return True

    def _delayed_find_new_coin(self):
        """TÌM COIN MỚI VỚI ĐỘ TRỄ"""
        time.sleep(2)
        self._find_and_add_new_coin()

    def stop_all_symbols(self):
        """DỪNG TẤT CẢ COIN"""
        self.log("⛔ Đang dừng tất cả coin...")
        
        symbols_to_stop = self.active_symbols.copy()
        stopped_count = 0
        
        for symbol in symbols_to_stop:
            if self.stop_symbol(symbol):
                stopped_count += 1
                time.sleep(1)
        
        self.log(f"✅ Đã dừng {stopped_count} coin, bot vẫn chạy và có thể thêm coin mới")
        return stopped_count

    def stop(self):
        """DỪNG TOÀN BỘ BOT"""
        self._stop = True
        stopped_count = self.stop_all_symbols()
        self.log(f"🔴 Bot dừng - Đã dừng {stopped_count} coin")

    def check_global_positions(self):
        """KIỂM TRA VỊ THẾ TOÀN TÀI KHOẢN"""
        try:
            positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            if not positions:
                self.global_long_count = 0
                self.global_short_count = 0
                self.global_long_pnl = 0
                self.global_short_pnl = 0
                return
            
            long_count = 0
            short_count = 0
            long_pnl_total = 0
            short_pnl_total = 0
            
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                
                if position_amt > 0:
                    long_count += 1
                    long_pnl_total += unrealized_pnl
                elif position_amt < 0:
                    short_count += 1
                    short_pnl_total += unrealized_pnl
            
            self.global_long_count = long_count
            self.global_short_count = short_count
            self.global_long_pnl = long_pnl_total
            self.global_short_pnl = short_pnl_total
            
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"❌ Lỗi kiểm tra vị thế toàn tài khoản: {str(e)}")
                self.last_error_log_time = time.time()

    def get_next_side_based_on_comprehensive_analysis(self):
        """XÁC ĐỊNH HƯỚNG LỆNH TIẾP THEO"""
        self.check_global_positions()
        
        long_pnl = self.global_long_pnl
        short_pnl = self.global_short_pnl
        
        if long_pnl > short_pnl:
            return "BUY"
        elif short_pnl > long_pnl:
            return "SELL"
        else:
            return random.choice(["BUY", "SELL"])

    def log(self, message):
        """LOG THÔNG TIN QUAN TRỌNG - ĐÃ SỬA LỖI TELEGRAM"""
        important_keywords = ['❌', '✅', '⛔', '💰', '📈', '📊', '🎯', '🛡️', '🔴', '🟢', '⚠️', '🚫']
        if any(keyword in message for keyword in important_keywords):
            logger.warning(f"[{self.bot_id}] {message}")
            if self.telegram_bot_token and self.telegram_chat_id:
                send_telegram(f"<b>{self.bot_id}</b>: {message}", 
                             chat_id=self.telegram_chat_id,
                             bot_token=self.telegram_bot_token, 
                             default_chat_id=self.telegram_chat_id)

# ========== BOT GLOBAL MARKET VỚI HỆ THỐNG RSI + KHỐI LƯỢNG ==========
class GlobalMarketBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager,
                 api_key, api_secret, telegram_bot_token, telegram_chat_id, bot_id=None, **kwargs):
        super().__init__(symbol, lev, percent, tp, sl, roi_trigger, ws_manager,
                         api_key, api_secret, telegram_bot_token, telegram_chat_id,
                         "Hệ-thống-RSI-Khối-lượng", bot_id=bot_id, **kwargs)

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()

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

        # 🔴 TÀI NGUYÊN DÙNG CHUNG
        self.coin_manager = CoinManager()
        self.symbol_locks = defaultdict(threading.Lock)

        # Kiểm tra kết nối Telegram khi khởi động
        if telegram_bot_token and telegram_chat_id:
            test_msg = "🤖 <b>HỆ THỐNG RSI + KHỐI LƯỢNG ĐÃ KHỞI ĐỘNG THÀNH CÔNG!</b>"
            if self._send_telegram_safe(test_msg, chat_id=telegram_chat_id):
                self.log("✅ Kết nối Telegram thành công")
            else:
                self.log("❌ Lỗi kết nối Telegram - kiểm tra token và chat_id")

        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT RSI + KHỐI LƯỢNG ĐÃ KHỞI ĐỘNG")

            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()

            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)
        else:
            self.log("⚡ BotManager khởi động ở chế độ không config")

    def _send_telegram_safe(self, message, chat_id=None, reply_markup=None):
        """Hàm gửi Telegram an toàn - KHÔNG GÂY TREO HỆ THỐNG"""
        try:
            if not self.telegram_bot_token:
                return False
            
            chat_id = chat_id or self.telegram_chat_id
            if not chat_id:
                return False
            
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            # ESCAPE MESSAGE ĐỂ TRÁNH LỖI HTML
            safe_message = escape_html(message)
            
            payload = {
                "chat_id": chat_id,
                "text": safe_message,
                "parse_mode": "HTML"
            }
            
            # 🔴 CHỈ THÊM REPLY_MARKUP NẾU CÓ
            if reply_markup is not None:
                payload["reply_markup"] = json.dumps(reply_markup)
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                self.log(f"❌ Telegram error ({response.status_code}): {response.text}")
                return False
                
        except Exception as e:
            self.log(f"❌ Telegram connection error: {str(e)}")
            return False

    def _verify_api_connection(self):
        """KIỂM TRA KẾT NỐI API"""
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
        """LẤY THỐNG KÊ TỔNG QUAN"""
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
            total_coins = 0
            trading_coins = 0
            
            for bot_id, bot in self.bots.items():
                active_coins = len(bot.active_symbols) if hasattr(bot, 'active_symbols') else 0
                total_coins += active_coins
                
                # Đếm số coin đang trade
                if hasattr(bot, 'symbol_data'):
                    for symbol, data in bot.symbol_data.items():
                        if data.get('position_open', False):
                            trading_coins += 1
                
                bot_info = {
                    'bot_id': bot_id,
                    'active_coins': active_coins,
                    'max_coins': bot.max_coins if hasattr(bot, 'max_coins') else 1,
                    'symbols': bot.active_symbols if hasattr(bot, 'active_symbols') else [],
                    'symbol_data': bot.symbol_data if hasattr(bot, 'symbol_data') else {},
                    'status': bot.status,
                    'leverage': bot.lev,
                    'percent': bot.percent
                }
                bot_details.append(bot_info)
            
            # Tạo báo cáo
            summary = "📊 **THỐNG KÊ CHI TIẾT - HỆ THỐNG RSI + KHỐI LƯỢNG**\n\n"
            
            # Phần 1: Số dư
            balance = get_balance(self.api_key, self.api_secret)
            if balance is not None:
                summary += f"💰 **SỐ DƯ**: {balance:.2f} USDC\n"
                summary += f"📈 **Tổng PnL**: {total_unrealized_pnl:.2f} USDC\n\n"
            else:
                summary += f"💰 **SỐ DƯ**: ❌ Lỗi kết nối\n\n"
            
            # Phần 2: Bot hệ thống
            summary += f"🤖 **BOT HỆ THỐNG**: {len(self.bots)} bot | {total_coins} coin | {trading_coins} coin đang trade\n\n"
            
            # Phần 3: Phân tích toàn diện
            summary += f"📈 **PHÂN TÍCH PnL VÀ KHỐI LƯỢNG**:\n"
            summary += f"   📊 Số lượng: LONG={total_long_count} | SHORT={total_short_count}\n"
            summary += f"   💰 PnL: LONG={total_long_pnl:.2f} USDC | SHORT={total_short_pnl:.2f} USDC\n"
            summary += f"   ⚖️ Chênh lệch: {abs(total_long_pnl - total_short_pnl):.2f} USDC\n\n"
            
            # Phần 4: Chi tiết từng bot
            if bot_details:
                summary += "📋 **CHI TIẾT TỪNG BOT**:\n"
                for bot in bot_details:
                    summary += f"🔹 **{bot['bot_id']}**\n"
                    summary += f"   📊 Coin: {bot['active_coins']}/{bot['max_coins']}\n"
                    summary += f"   💰 ĐB: {bot['leverage']}x | Vốn: {bot['percent']}%\n"
                    
                    if bot['symbols']:
                        for symbol in bot['symbols']:
                            symbol_info = bot['symbol_data'].get(symbol, {})
                            status = "🟢 Đang trade" if symbol_info.get('position_open') else "🟡 Chờ tín hiệu"
                            side = symbol_info.get('side', '')
                            qty = symbol_info.get('qty', 0)
                            
                            summary += f"   🔗 {symbol} | {status}"
                            if side:
                                summary += f" | {side} {abs(qty):.4f}"
                            summary += "\n"
                    
                    summary += "\n"
            
            summary += "⛔ **LỆNH DỪNG**:\n"
            summary += "• Chọn '⛔ Dừng Bot' để dừng từng coin hoặc bot\n"
            summary += "• 'DỪNG TẤT CẢ COIN' - Chỉ dừng coin, giữ bot chạy\n"
            summary += "• 'DỪNG TẤT CẢ BOT' - Dừng toàn bộ hệ thống\n"
            
            return summary
                    
        except Exception as e:
            return f"❌ Lỗi thống kê: {str(e)}"

    def log(self, message):
        """LOG THÔNG TIN QUAN TRỌNG"""
        important_keywords = ['❌', '✅', '⛔', '💰', '📈', '📊', '🎯', '🛡️', '🔴', '🟢', '⚠️', '🚫']
        if any(keyword in message for keyword in important_keywords):
            logger.warning(f"[SYSTEM] {message}")
            if self.telegram_bot_token and self.telegram_chat_id:
                self._send_telegram_safe(f"<b>SYSTEM</b>: {message}", chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = (
            "🤖 <b>BOT GIAO DỊCH FUTURES - HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH</b>\n\n"
            "🎯 <b>CHIẾN LƯỢC CHÍNH XÁC:</b>\n"
            "• Mỗi coin là thực thể độc lập\n"
            "• Vào lệnh nối tiếp từng coin\n"
            "• Tín hiệu dựa trên RSI và khối lượng\n\n"
            
            "📈 <b>ĐIỀU KIỆN VÀO LỆNH (20% khối lượng):</b>\n"
            "1. RSI ở vùng cực (&gt;80/&lt;20) + khối lượng giảm 20% + hồi về trung tâm\n"
            "2. RSI trong vùng 30-70 + khối lượng tăng 20% + theo xu hướng RSI\n\n"
            
            "🎯 <b>ĐIỀU KIỆN ĐÓNG LỆNH (40% khối lượng + ROI trigger):</b>\n"
            "• GIỐNG HỆT điều kiện vào lệnh\n"
            "• Nhưng khối lượng thay đổi 40% (thay vì 20%)\n"
            "• VÀ phải đạt ROI trigger do người dùng thiết lập\n"
            "• Chỉ chốt lời, không vào lệnh ngược\n\n"
            
            "🔄 <b>CƠ CHẾ NỐI TIẾP HOÀN CHỈNH:</b>\n"
            "• Xử lý từng coin một\n"
            "• Chờ 3s giữa các lệnh\n"
            "• Tự động tìm coin mới khi có slot\n"
            "• 🔴 TỰ ĐỘNG TÌM COIN MỚI KHI DỪNG COIN CŨ\n"
            "• 🔒 THREAD-SAFE - Đảm bảo an toàn đa luồng"
        )
        self._send_telegram_safe(welcome, chat_id, create_main_menu())

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
        
        # TẠO DUY NHẤT 1 BOT VỚI NHIỀU COIN
        try:
            if bot_mode == 'static' and symbol:
                bot_id = f"STATIC_{strategy_type}_{int(time.time())}"
            else:
                bot_id = f"DYNAMIC_{strategy_type}_{int(time.time())}"
            
            if bot_id in self.bots:
                return False
            
            bot_class = GlobalMarketBot
            
            # Tạo bot với số coin tối đa = bot_count
            bot = bot_class(
                symbol, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id,
                coin_manager=self.coin_manager,
                symbol_locks=self.symbol_locks,
                bot_id=bot_id,
                max_coins=bot_count
            )
            
            bot._bot_manager = self
            self.bots[bot_id] = bot
            created_count = 1
            
        except Exception as e:
            self.log(f"❌ Lỗi tạo bot: {str(e)}")
            return False
        
        if created_count > 0:
            roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else " | 🎯 ROI Trigger: Tắt"
            
            success_msg = (
                f"✅ <b>ĐÃ TẠO BOT HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH</b>\n\n"
                f"🎯 Chiến lược: {strategy_type}\n"
                f"💰 Đòn bẩy: {lev}x\n"
                f"📈 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl if sl is not None else 'Tắt'}%{roi_info}\n"
                f"🔧 Chế độ: {bot_mode}\n"
                f"🔢 Số coin tối đa: {bot_count}\n"
            )
            
            if bot_mode == 'static' and symbol:
                success_msg += f"🔗 Coin khởi tạo: {symbol}\n"
            else:
                success_msg += f"🔗 Coin: Tự động tìm kiếm\n"
            
            success_msg += f"\n🔄 <b>CƠ CHẾ NỐI TIẾP HOÀN CHỈNH ĐÃ KÍCH HOẠT</b>\n"
            success_msg += f"• Xử lý từng coin một theo thứ tự\n"
            success_msg += f"• Chờ 3s sau mỗi lệnh thành công\n"
            success_msg += f"• Tự động tìm coin mới khi có slot trống\n"
            success_msg += f"• 🔴 TỰ ĐỘNG TÌM COIN MỚI KHI DỪNG COIN CŨ\n"
            success_msg += f"• 🔒 THREAD-SAFE - Đảm bảo an toàn đa luồng\n\n"
            success_msg += f"🚫 <b>KIỂM TRA VỊ THẾ ĐÃ KÍCH HOẠT</b>\n"
            success_msg += f"• Tự động phát hiện coin có vị thế\n"
            success_msg += f"• Không vào lệnh trên coin đã có vị thế\n"
            success_msg += f"• Tự động chuyển sang tìm coin khác"
            
            self.log(success_msg)
            return True
        else:
            self.log("❌ Không thể tạo bot")
            return False

    def stop_bot_symbol(self, bot_id, symbol):
        """DỪNG MỘT COIN CỤ THỂ TRONG BOT"""
        bot = self.bots.get(bot_id)
        if bot and hasattr(bot, 'stop_symbol'):
            success = bot.stop_symbol(symbol)
            if success:
                self.log(f"⛔ Đã dừng coin {symbol} trong bot {bot_id}")
            return success
        return False

    def stop_all_bot_symbols(self, bot_id):
        """DỪNG TẤT CẢ COIN TRONG MỘT BOT"""
        bot = self.bots.get(bot_id)
        if bot and hasattr(bot, 'stop_all_symbols'):
            stopped_count = bot.stop_all_symbols()
            self.log(f"⛔ Đã dừng {stopped_count} coin trong bot {bot_id}")
            return stopped_count
        return 0

    def stop_all_coins(self):
        """DỪNG TẤT CẢ COIN TRONG TẤT CẢ BOT"""
        self.log("⛔ Đang dừng tất cả coin trong tất cả bot...")
        
        total_stopped = 0
        for bot_id, bot in self.bots.items():
            if hasattr(bot, 'stop_all_symbols'):
                stopped_count = bot.stop_all_symbols()
                total_stopped += stopped_count
                self.log(f"⛔ Đã dừng {stopped_count} coin trong bot {bot_id}")
        
        self.log(f"✅ Đã dừng tổng cộng {total_stopped} coin, hệ thống vẫn chạy và có thể thêm coin mới")
        return total_stopped

    def stop_bot(self, bot_id):
        """DỪNG TOÀN BỘ BOT"""
        bot = self.bots.get(bot_id)
        if bot:
            bot.stop()
            del self.bots[bot_id]
            self.log(f"🔴 Đã dừng bot {bot_id}")
            return True
        return False

    def stop_all(self):
        """DỪNG TẤT CẢ BOT"""
        self.log("🔴 Đang dừng tất cả bot...")
        for bot_id in list(self.bots.keys()):
            self.stop_bot(bot_id)
        self.log("🔴 Đã dừng tất cả bot, hệ thống vẫn chạy và có thể thêm bot mới")

    def _telegram_listener(self):
        """LISTENER TELEGRAM HOÀN CHỈNH"""
        last_update_id = 0
        
        while self.running and self.telegram_bot_token:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getUpdates"
                params = {
                    "offset": last_update_id + 1,
                    "timeout": 30,
                    "allowed_updates": ["message"]
                }
                
                response = requests.get(url, params=params, timeout=35)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        for update in data['result']:
                            update_id = update['update_id']
                            message = update.get('message', {})
                            chat_id = str(message.get('chat', {}).get('id'))
                            text = message.get('text', '').strip()
                            
                            # 🔴 CHỈ XỬ LÝ TIN NHẮN TỪ CHAT_ID ĐƯỢC CẤU HÌNH
                            if chat_id != self.telegram_chat_id:
                                continue
                            
                            if update_id > last_update_id:
                                last_update_id = update_id
                            
                            # XỬ LÝ TIN NHẮN
                            if text:
                                self._handle_telegram_message(chat_id, text)
                                
                    elif data.get('error_code') == 409:
                        logger.error("❌ Lỗi 409: Có thể đang chạy nhiều instance cùng bot token")
                        time.sleep(10)
                else:
                    logger.error(f"Lỗi HTTP {response.status_code}: {response.text}")
                    time.sleep(10)
                    
            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                logger.error(f"Lỗi Telegram listener: {str(e)}")
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        """XỬ LÝ TIN NHẮN TELEGRAM - HOÀN CHỈNH"""
        try:
            user_state = self.user_states.get(chat_id, {})
            current_step = user_state.get('step')
            
            # 🔴 THÊM LOG ĐỂ DEBUG
            logger.info(f"📱 Telegram nhận: {text} | Bước: {current_step}")
            
            # Xử lý các bước tạo bot
            if current_step == 'waiting_bot_count':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                else:
                    try:
                        bot_count = int(text)
                        if bot_count <= 0 or bot_count > 10:
                            self._send_telegram_safe("⚠️ Số lượng bot phải từ 1 đến 10. Vui lòng chọn lại:",
                                                chat_id, create_bot_count_keyboard())
                            return
        
                        user_state['bot_count'] = bot_count
                        user_state['step'] = 'waiting_bot_mode'
                        
                        self._send_telegram_safe(
                            f"🤖 Số lượng bot: {bot_count}\n\n"
                            f"Chọn chế độ bot:",
                            chat_id,
                            create_bot_mode_keyboard()
                        )
                    except ValueError:
                        self._send_telegram_safe("⚠️ Vui lòng nhập số hợp lệ cho số lượng bot:",
                                            chat_id, create_bot_count_keyboard())
        
            elif current_step == 'waiting_bot_mode':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                elif text in ["🤖 Bot Tĩnh - Coin cụ thể", "🔄 Bot Động - Tự tìm coin"]:
                    if text == "🤖 Bot Tĩnh - Coin cụ thể":
                        user_state['bot_mode'] = 'static'
                        user_state['step'] = 'waiting_symbol'
                        self._send_telegram_safe(
                            "🎯 <b>ĐÃ CHỌN: BOT TĨNH</b>\n\n"
                            "🤖 Bot sẽ giao dịch coin CỐ ĐỊNH\n"
                            "📊 Bạn cần chọn coin cụ thể\n\n"
                            "Chọn coin:",
                            chat_id,
                            create_symbols_keyboard()
                        )
                    else:
                        user_state['bot_mode'] = 'dynamic'
                        user_state['step'] = 'waiting_leverage'
                        self._send_telegram_safe(
                            "🎯 <b>ĐÃ CHỌN: BOT ĐỘNG</b>\n\n"
                            f"🤖 Hệ thống sẽ tạo bot quản lý <b>{user_state.get('bot_count', 1)} coin</b>\n"
                            f"🔄 Bot sẽ xử lý từng coin một theo thứ tự\n\n"
                            "Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard()
                        )
        
            elif current_step == 'waiting_symbol':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                else:
                    user_state['symbol'] = text
                    user_state['step'] = 'waiting_leverage'
                    self._send_telegram_safe(
                        f"🔗 Coin: {text}\n\n"
                        f"Chọn đòn bẩy:",
                        chat_id,
                        create_leverage_keyboard()
                    )
        
            elif current_step == 'waiting_leverage':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                else:
                    if text.endswith('x'):
                        lev_text = text[:-1]
                    else:
                        lev_text = text
        
                    try:
                        leverage = int(lev_text)
                        if leverage <= 0 or leverage > 100:
                            self._send_telegram_safe("⚠️ Đòn bẩy phải từ 1 đến 100. Vui lòng chọn lại:",
                                                chat_id, create_leverage_keyboard())
                            return
        
                        user_state['leverage'] = leverage
                        user_state['step'] = 'waiting_percent'
                        
                        balance = get_balance(self.api_key, self.api_secret)
                        balance_info = f"\n💰 Số dư hiện có: {balance:.2f} USDT" if balance else ""
                        
                        self._send_telegram_safe(
                            f"💰 Đòn bẩy: {leverage}x{balance_info}\n\n"
                            f"Chọn % số dư cho mỗi lệnh:",
                            chat_id,
                            create_percent_keyboard()
                        )
                    except ValueError:
                        self._send_telegram_safe("⚠️ Vui lòng nhập số hợp lệ cho đòn bẩy:",
                                            chat_id, create_leverage_keyboard())
        
            elif current_step == 'waiting_percent':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                else:
                    try:
                        percent = float(text)
                        if percent <= 0 or percent > 100:
                            self._send_telegram_safe("⚠️ % số dư phải từ 0.1 đến 100. Vui lòng chọn lại:",
                                                chat_id, create_percent_keyboard())
                            return
        
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        
                        balance = get_balance(self.api_key, self.api_secret)
                        actual_amount = balance * (percent / 100) if balance else 0
                        
                        self._send_telegram_safe(
                            f"📊 % Số dư: {percent}%\n"
                            f"💵 Số tiền mỗi lệnh: ~{actual_amount:.2f} USDT\n\n"
                            f"Chọn Take Profit (%):",
                            chat_id,
                            create_tp_keyboard()
                        )
                    except ValueError:
                        self._send_telegram_safe("⚠️ Vui lòng nhập số hợp lệ cho % số dư:",
                                            chat_id, create_percent_keyboard())
        
            elif current_step == 'waiting_tp':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                else:
                    try:
                        tp = float(text)
                        if tp <= 0:
                            self._send_telegram_safe("⚠️ Take Profit phải lớn hơn 0. Vui lòng chọn lại:",
                                                chat_id, create_tp_keyboard())
                            return
        
                        user_state['tp'] = tp
                        user_state['step'] = 'waiting_sl'
                        
                        self._send_telegram_safe(
                            f"🎯 Take Profit: {tp}%\n\n"
                            f"Chọn Stop Loss (%):",
                            chat_id,
                            create_sl_keyboard()
                        )
                    except ValueError:
                        self._send_telegram_safe("⚠️ Vui lòng nhập số hợp lệ cho Take Profit:",
                                            chat_id, create_tp_keyboard())
        
            elif current_step == 'waiting_sl':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                else:
                    try:
                        sl = float(text)
                        if sl < 0:
                            self._send_telegram_safe("⚠️ Stop Loss phải lớn hơn hoặc bằng 0. Vui lòng chọn lại:",
                                                chat_id, create_sl_keyboard())
                            return
        
                        user_state['sl'] = sl
                        user_state['step'] = 'waiting_roi_trigger'
                        
                        self._send_telegram_safe(
                            f"🛡️ Stop Loss: {sl}%\n\n"
                            f"🎯 <b>CHỌN NGƯỠNG ROI ĐỂ KÍCH HOẠT CƠ CHẾ CHỐT LỆNH THÔNG MINH</b>\n\n"
                            f"Chọn ngưỡng ROI trigger (%):",
                            chat_id,
                            create_roi_trigger_keyboard()
                        )
                    except ValueError:
                        self._send_telegram_safe("⚠️ Vui lòng nhập số hợp lệ cho Stop Loss:",
                                            chat_id, create_sl_keyboard())
        
            elif current_step == 'waiting_roi_trigger':
                if text == '❌ Hủy bỏ':
                    self.user_states[chat_id] = {}
                    self._send_telegram_safe("❌ Đã hủy thêm bot", chat_id, create_main_menu())
                elif text == '❌ Tắt tính năng':
                    user_state['roi_trigger'] = None
                    self._finish_bot_creation(chat_id, user_state)
                else:
                    try:
                        roi_trigger = float(text)
                        if roi_trigger <= 0:
                            self._send_telegram_safe("⚠️ ROI Trigger phải lớn hơn 0. Vui lòng chọn lại:",
                                                chat_id, create_roi_trigger_keyboard())
                            return
        
                        user_state['roi_trigger'] = roi_trigger
                        self._finish_bot_creation(chat_id, user_state)
                        
                    except ValueError:
                        self._send_telegram_safe("⚠️ Vui lòng nhập số hợp lệ cho ROI Trigger:",
                                            chat_id, create_roi_trigger_keyboard())
        
            # XỬ LÝ LỆNH DỪNG TỪNG COIN
            elif text.startswith("⛔ Coin: "):
                parts = text.replace("⛔ Coin: ", "").split(" | Bot: ")
                if len(parts) == 2:
                    symbol = parts[0].strip()
                    bot_id = parts[1].strip()
                    
                    if self.stop_bot_symbol(bot_id, symbol):
                        self._send_telegram_safe(f"✅ Đã dừng coin {symbol} trong bot {bot_id}", chat_id)
                    else:
                        self._send_telegram_safe(f"❌ Không thể dừng coin {symbol}", chat_id)
            
            # XỬ LÝ LỆNH DỪNG TẤT CẢ COIN
            elif text == "⛔ DỪNG TẤT CẢ COIN":
                stopped_count = self.stop_all_coins()
                self._send_telegram_safe(f"✅ Đã dừng {stopped_count} coin, hệ thống vẫn chạy", chat_id)
            
            # XỬ LÝ LỆNH DỪNG BOT
            elif text.startswith("⛔ Bot: "):
                bot_id = text.replace("⛔ Bot: ", "").strip()
                if self.stop_bot(bot_id):
                    self._send_telegram_safe(f"✅ Đã dừng bot {bot_id}", chat_id)
                else:
                    self._send_telegram_safe(f"❌ Không tìm thấy bot {bot_id}", chat_id)
            
            # XỬ LÝ LỆNH DỪNG TẤT CẢ BOT
            elif text == "⛔ DỪNG TẤT CẢ BOT":
                stopped_count = self.stop_all()
                self._send_telegram_safe(f"✅ Đã dừng {stopped_count} bot, hệ thống vẫn chạy", chat_id)
        
            elif text == "➕ Thêm Bot":
                self.user_states[chat_id] = {'step': 'waiting_bot_count'}
                balance = get_balance(self.api_key, self.api_secret)
                if balance is None:
                    self._send_telegram_safe("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key và kết nối mạng!", chat_id)
                    return
                
                self._send_telegram_safe(
                    f"🎯 <b>CHỌN SỐ LƯỢNG COIN CHO BOT</b>\n\n"
                    f"💰 Số dư hiện có: <b>{balance:.2f} USDT</b>\n\n"
                    f"Chọn số lượng coin tối đa bot được quản lý:",
                    chat_id,
                    create_bot_count_keyboard()
                )
            
            elif text == "📊 Danh sách Bot":
                summary = self.get_position_summary()
                self._send_telegram_safe(summary, chat_id)
            
            elif text == "⛔ Dừng Bot":
                if not self.bots:
                    self._send_telegram_safe("🤖 Không có bot nào đang chạy", chat_id)
                else:
                    message = "⛔ <b>CHỌN COIN HOẶC BOT ĐỂ DỪNG</b>\n\n"
                    
                    # Hiển thị tất cả coin đang chạy
                    coin_keyboard = []
                    bot_keyboard = []
                    
                    for bot_id, bot in self.bots.items():
                        if hasattr(bot, 'active_symbols') and bot.active_symbols:
                            for symbol in bot.active_symbols:
                                coin_keyboard.append([{"text": f"⛔ Coin: {symbol} | Bot: {bot_id}"}])
                        
                        bot_keyboard.append([{"text": f"⛔ Bot: {bot_id}"}])
                    
                    # Tạo keyboard
                    keyboard = []
                    
                    if coin_keyboard:
                        keyboard.extend(coin_keyboard)
                        keyboard.append([{"text": "⛔ DỪNG TẤT CẢ COIN"}])
                    
                    if bot_keyboard:
                        keyboard.extend(bot_keyboard)
                        keyboard.append([{"text": "⛔ DỪNG TẤT CẢ BOT"}])
                    
                    keyboard.append([{"text": "❌ Hủy bỏ"}])
                    
                    self._send_telegram_safe(
                        message, 
                        chat_id, 
                        {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True}
                    )
            
            elif text == "📊 Thống kê":
                summary = self.get_position_summary()
                self._send_telegram_safe(summary, chat_id)
            
            elif text == "💰 Số dư":
                try:
                    balance = get_balance(self.api_key, self.api_secret)
                    if balance is None:
                        self._send_telegram_safe("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key và kết nối mạng!", chat_id)
                    else:
                        self._send_telegram_safe(f"💰 <b>SỐ DƯ KHẢ DỤNG</b>: {balance:.2f} USDT", chat_id)
                except Exception as e:
                    self._send_telegram_safe(f"⚠️ Lỗi lấy số dư: {str(e)}", chat_id)
            
            elif text == "📈 Vị thế":
                try:
                    positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
                    if not positions:
                        self._send_telegram_safe("📭 Không có vị thế nào đang mở", chat_id)
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
                    
                    self._send_telegram_safe(message, chat_id)
                except Exception as e:
                    self._send_telegram_safe(f"⚠️ Lỗi lấy vị thế: {str(e)}", chat_id)
            
            elif text == "🎯 Chiến lược":
                strategy_info = (
                    "🎯 <b>HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH</b>\n\n"
                    
                    "📈 <b>ĐIỀU KIỆN VÀO LỆNH (20% khối lượng):</b>\n"
                    "1. RSI ở vùng cực (&gt;80/&lt;20) + khối lượng giảm 20% + hồi về trung tâm\n"
                    "2. RSI trong vùng 30-70 + khối lượng tăng 20% + theo xu hướng RSI\n\n"
                    
                    "🎯 <b>ĐIỀU KIỆN ĐÓNG LỆNH (40% khối lượng + ROI trigger):</b>\n"
                    "• GIỐNG HỆT điều kiện vào lệnh\n"
                    "• Nhưng khối lượng thay đổi 40% (thay vì 20%)\n"
                    "• VÀ phải đạt ROI trigger do người dùng thiết lập\n"
                    "• Chỉ chốt lời, không vào lệnh ngược\n\n"
                    
                    "🔄 <b>CƠ CHẾ NỐI TIẾP HOÀN CHỈNH:</b>\n"
                    "• Mỗi coin là thực thể độc lập\n"
                    "• Xử lý từng coin một theo thứ tự\n"
                    "• Chờ 3s giữa các lệnh\n"
                    "• Tự động tìm coin mới khi có slot trống\n"
                    "• 🔴 TỰ ĐỘNG TÌM COIN MỚI KHI DỪNG COIN CŨ\n"
                    "• 🔒 THREAD-SAFE - Đảm bảo an toàn đa luồng\n\n"
                    
                    "🚫 <b>KIỂM TRA VỊ THẾ:</b>\n"
                    "• Tự động phát hiện coin đã có vị thế\n"
                    "• Không vào lệnh trên coin đã có vị thế\n"
                    "• Tự động chuyển sang tìm coin khác"
                )
                self._send_telegram_safe(strategy_info, chat_id)
            
            elif text == "⚙️ Cấu hình":
                balance = get_balance(self.api_key, self.api_secret)
                api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
                
                total_coins = 0
                trading_coins = 0
                
                for bot in self.bots.values():
                    if hasattr(bot, 'active_symbols'):
                        total_coins += len(bot.active_symbols)
                        for symbol, data in bot.symbol_data.items():
                            if data.get('position_open', False):
                                trading_coins += 1
                
                config_info = (
                    "⚙️ <b>CẤU HÌNH HỆ THỐNG RSI + KHỐI LƯỢNG HOÀN CHỈNH</b>\n\n"
                    f"🔑 Binance API: {api_status}\n"
                    f"🤖 Tổng số bot: {len(self.bots)}\n"
                    f"📊 Tổng số coin: {total_coins}\n"
                    f"🟢 Coin đang trade: {trading_coins}\n"
                    f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối\n\n"
                    f"🔄 <b>CƠ CHẾ NỐI TIẾP ĐANG HOẠT ĐỘNG</b>\n"
                    f"🎯 <b>HỆ THỐNG RSI + KHỐI LƯỢNG ĐANG HOẠT ĐỘNG</b>\n"
                    f"🔴 <b>TỰ ĐỘNG TÌM COIN MỚI KHI DỪNG COIN CŨ</b>\n"
                    f"🔒 <b>THREAD-SAFE - AN TOÀN ĐA LUỒNG</b>"
                )
                self._send_telegram_safe(config_info, chat_id)
            
            elif text:
                self.send_main_menu(chat_id)
                
        except Exception as e:
            error_msg = f"❌ Lỗi xử lý Telegram: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # Gửi thông báo lỗi cho user
            self._send_telegram_safe(
                "⚠️ Có lỗi xảy ra trong quá trình xử lý. Vui lòng thử lại!",
                chat_id
            )
            
            # Reset state để tránh bị treo
            self.user_states[chat_id] = {}
            self.send_main_menu(chat_id)

    def _finish_bot_creation(self, chat_id, user_state):
        """HOÀN TẤT TẠO BOT - ĐÃ THÊM XỬ LÝ LỖI"""
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
            
            # 🔴 KIỂM TRA DỮ LIỆU BẮT BUỘC
            if None in [leverage, percent, tp, sl]:
                self._send_telegram_safe(
                    "❌ Thiếu thông tin cấu hình bot. Vui lòng tạo lại từ đầu!",
                    chat_id, 
                    create_main_menu()
                )
                self.user_states[chat_id] = {}
                return
            
            success = self.add_bot(
                symbol=symbol,
                lev=leverage,
                percent=percent,
                tp=tp,
                sl=sl,
                roi_trigger=roi_trigger,
                strategy_type="Hệ-thống-RSI-Khối-lượng",
                bot_mode=bot_mode,
                bot_count=bot_count
            )
            
            if success:
                roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else ""
                
                success_msg = (
                    f"✅ <b>ĐÃ TẠO BOT THÀNH CÔNG</b>\n\n"
                    f"🤖 Chiến lược: Hệ thống RSI + Khối lượng\n"
                    f"🔧 Chế độ: {bot_mode}\n"
                    f"🔢 Số coin tối đa: {bot_count}\n"
                    f"💰 Đòn bẩy: {leverage}x\n"
                    f"📊 % Số dư: {percent}%\n"
                    f"🎯 TP: {tp}%\n"
                    f"🛡️ SL: {sl}%{roi_info}"
                )
                if bot_mode == 'static' and symbol:
                    success_msg += f"\n🔗 Coin: {symbol}"
                
                success_msg += f"\n\n🔄 <b>CƠ CHẾ NỐI TIẾP HOÀN CHỈNH ĐÃ KÍCH HOẠT</b>\n"
                success_msg += f"• Xử lý từng coin một theo thứ tự\n"
                success_msg += f"• Chờ 3s sau mỗi lệnh thành công\n"
                success_msg += f"• Tự động tìm coin mới khi có slot trống\n"
                success_msg += f"• 🔴 TỰ ĐỘNG TÌM COIN MỚI KHI DỪNG COIN CŨ\n"
                success_msg += f"• 🔒 THREAD-SAFE - Đảm bảo an toàn đa luồng\n\n"
                success_msg += f"🎯 <b>HỆ THỐNG RSI + KHỐI LƯỢNG ĐÃ KÍCH HOẠT</b>\n"
                success_msg += f"• Vào lệnh: 20% khối lượng thay đổi\n"
                success_msg += f"• Đóng lệnh: 40% khối lượng thay đổi + ROI trigger\n"
                success_msg += f"• Tự động kiểm tra vị thế trước khi vào lệnh"
                
                self._send_telegram_safe(success_msg, chat_id, create_main_menu())
            else:
                self._send_telegram_safe(
                    "❌ Có lỗi khi tạo bot. Vui lòng kiểm tra:\n"
                    "• API Key có đúng không?\n" 
                    "• Có đủ số dư không?\n"
                    "• Kết nối mạng ổn định không?",
                    chat_id, 
                    create_main_menu()
                )
            
            self.user_states[chat_id] = {}
            
        except Exception as e:
            error_msg = f"❌ Lỗi nghiêm trọng khi tạo bot: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            self._send_telegram_safe(
                "❌ Có lỗi nghiêm trọng khi tạo bot. Vui lòng liên hệ admin!",
                chat_id,
                create_main_menu()
            )
            self.user_states[chat_id] = {}
