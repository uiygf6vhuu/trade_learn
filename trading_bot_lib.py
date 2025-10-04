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
    """Bàn phím chọn chiến lược giao dịch - BƯỚC ĐẦU TIÊN"""
    return {
        "keyboard": [
            [{"text": "🤖 RSI/EMA Recursive"}, {"text": "📊 EMA Crossover"}],
            [{"text": "🎯 Reverse 24h"}, {"text": "📈 Trend Following"}],
            [{"text": "⚡ Scalping"}, {"text": "🛡️ Safe Grid"}],
            [{"text": "🔥 Trend Momentum"}, {"text": "🚀 Volatility Breakout"}],
            [{"text": "💎 Multi Timeframe"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard(strategy=None):
    """Bàn phím chọn coin - có thể tùy chỉnh theo chiến lược"""
    if strategy in ["Reverse 24h", "Trend Momentum", "Volatility Breakout", "Multi Timeframe"]:
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
    """Bàn phím chọn đòn bẩy - có thể tùy chỉnh theo chiến lược"""
    if strategy == "Scalping":
        leverages = ["3", "5", "10", "15", "20", "25", "50", "75", "100"]
    elif strategy in ["Reverse 24h", "Trend Momentum", "Volatility Breakout"]:
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

# ========== HÀM TÌM KIẾM COIN TỰ ĐỘNG ==========
def get_top_volatile_symbols(limit=10, threshold=20):
    """Lấy danh sách coin có biến động 24h cao nhất"""
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

def get_qualified_symbols(api_key, api_secret, threshold=30, leverage=3, max_candidates=8, final_limit=3):
    """Tìm coin đủ điều kiện: biến động cao + đòn bẩy khả dụng"""
    try:
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE - Kiểm tra API Key")
            return []
        
        volatile_candidates = get_top_volatile_symbols(limit=max_candidates, threshold=threshold)
        
        if not volatile_candidates:
            logger.warning(f"❌ Không tìm thấy coin nào có biến động ≥{threshold}%")
            return []
        
        logger.info(f"📊 Tìm thấy {len(volatile_candidates)} coin biến động cao: {', '.join(volatile_candidates)}")
        
        qualified_symbols = []
        
        for symbol in volatile_candidates:
            if len(qualified_symbols) >= final_limit:
                break
                
            try:
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                
                if leverage_success:
                    qualified_symbols.append(symbol)
                    logger.info(f"✅ {symbol}: biến động ≥{threshold}% + đòn bẩy {leverage}x")
                else:
                    logger.warning(f"⚠️ {symbol}: không thể đặt đòn bẩy {leverage}x")
                    
                time.sleep(0.2)
                
            except Exception as e:
                logger.warning(f"⚠️ Lỗi kiểm tra {symbol}: {str(e)}")
                continue
        
        logger.info(f"🎯 Kết quả: {len(qualified_symbols)} coin đủ điều kiện")
        return qualified_symbols
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin đủ điều kiện: {str(e)}")
        return []

def find_trend_momentum_symbols(api_key, api_secret, limit=3):
    """Tìm coin có xu hướng và động lượng tốt nhất"""
    try:
        symbols = get_top_volatile_symbols(limit=15, threshold=10)
        best_symbols = []
        
        for symbol in symbols:
            try:
                url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&limit=50"
                data = binance_api_request(url)
                if not data or len(data) < 20:
                    continue
                
                closes = [float(k[4]) for k in data]
                highs = [float(k[2]) for k in data]
                lows = [float(k[3]) for k in data]
                
                # Tính momentum
                momentum = (closes[-1] - closes[-10]) / closes[-10] * 100
                
                # Tính trend strength
                ema_fast = calc_ema(closes, 8)
                ema_slow = calc_ema(closes, 21)
                
                if ema_fast and ema_slow and momentum > 2 and ema_fast > ema_slow:
                    best_symbols.append((symbol, momentum))
                    
                time.sleep(0.1)
                
            except Exception as e:
                continue
        
        best_symbols.sort(key=lambda x: x[1], reverse=True)
        return [symbol for symbol, score in best_symbols[:limit]]
        
    except Exception as e:
        logger.error(f"Lỗi tìm coin trend momentum: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

def find_volatility_breakout_symbols(api_key, api_secret, limit=3):
    """Tìm coin có biến động cao và sắp breakout"""
    try:
        symbols = get_top_volatile_symbols(limit=15, threshold=15)
        best_symbols = []
        
        for symbol in symbols:
            try:
                url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=15m&limit=100"
                data = binance_api_request(url)
                if not data or len(data) < 50:
                    continue
                
                highs = [float(k[2]) for k in data]
                lows = [float(k[3]) for k in data]
                closes = [float(k[4]) for k in data]
                
                # Tính ATR (Average True Range)
                atr_values = []
                for i in range(1, len(highs)):
                    tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                    atr_values.append(tr)
                
                atr = np.mean(atr_values[-14:]) if len(atr_values) >= 14 else 0
                current_range = highs[-1] - lows[-1]
                
                # Điểm số dựa trên biến động và breakout tiềm năng
                volatility_score = (current_range / closes[-1]) * 100 if closes[-1] > 0 else 0
                
                if volatility_score > 2 and atr > 0:
                    best_symbols.append((symbol, volatility_score))
                    
                time.sleep(0.1)
                
            except Exception as e:
                continue
        
        best_symbols.sort(key=lambda x: x[1], reverse=True)
        return [symbol for symbol, score in best_symbols[:limit]]
        
    except Exception as e:
        logger.error(f"Lỗi tìm coin volatility breakout: {str(e)}")
        return ["ADAUSDT", "DOGEUSDT", "XRPUSDT"]

def find_multi_timeframe_symbols(api_key, api_secret, limit=3):
    """Tìm coin có tín hiệu đồng thuận đa khung thời gian"""
    try:
        symbols = get_top_volatile_symbols(limit=12, threshold=8)
        best_symbols = []
        
        for symbol in symbols:
            try:
                # Lấy dữ liệu đa khung thời gian
                timeframes = ['5m', '15m', '1h']
                bullish_signals = 0
                total_signals = 0
                
                for tf in timeframes:
                    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={tf}&limit=50"
                    data = binance_api_request(url)
                    if not data or len(data) < 20:
                        continue
                    
                    closes = [float(k[4]) for k in data]
                    ema_fast = calc_ema(closes, 9)
                    ema_slow = calc_ema(closes, 21)
                    
                    if ema_fast and ema_slow:
                        total_signals += 1
                        if ema_fast > ema_slow:
                            bullish_signals += 1
                
                if total_signals == len(timeframes):  # Có đủ tín hiệu từ tất cả khung thời gian
                    consensus_score = bullish_signals / total_signals
                    if consensus_score >= 0.7:  # 70% khung thời gian đồng thuận
                        best_symbols.append((symbol, consensus_score))
                
                time.sleep(0.1)
                
            except Exception as e:
                continue
        
        best_symbols.sort(key=lambda x: x[1], reverse=True)
        return [symbol for symbol, score in best_symbols[:limit]]
        
    except Exception as e:
        logger.error(f"Lỗi tìm coin multi timeframe: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

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
                        logger.error("❌ LỖI 401 UNAUTHORIZED - Kiểm tra API Key!")
                        return None
                    
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            logger.error(f"Lỗi HTTP ({e.code}): {e.reason}")
            
            if e.code == 401:
                logger.error("❌ LỖI 401 UNAUTHORIZED - Vui lòng kiểm tra API Key!")
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
            logger.error(f"❌ Không thể đặt đòn bẩy cho {symbol} do lỗi xác thực")
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
    try:
        prices = np.array(prices)
        if len(prices) < period:
            return None
        weights = np.exp(np.linspace(-1., 0., period))
        weights /= weights.sum()
        ema = np.convolve(prices, weights, mode='valid')
        return float(ema[-1])
    except Exception as e:
        logger.error(f"Lỗi tính EMA: {str(e)}")
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
        self.symbol = symbol.upper()
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
        
        # Biến quan trọng
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
        
        self._ensure_required_attributes()
        
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
                
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                    
                signal = self.get_signal()
                
                if not self.position_open and self.status == "waiting":
                    if current_time - self.last_close_time < self.cooldown_period:
                        time.sleep(1)
                        continue

                    if signal and current_time - self.last_trade_time > 60:
                        self.open_position(signal)
                        self.last_trade_time = current_time
                        
                if self.position_open and self.status == "open":
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    error_msg = f"❌ Lỗi hệ thống: {str(e)}\n{traceback.format_exc()}"
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
        self.log(f"🔴 Bot dừng cho {self.symbol}")

    def check_position_status(self):
        try:
            positions = get_positions(self.symbol, self.api_key, self.api_secret)
            
            if not positions or len(positions) == 0:
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
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")
                self.last_error_log_time = time.time()

    def check_tp_sl(self):
        if not self.position_open or not self.entry or not self.qty:
            return
            
        try:
            if len(self.prices) > 0:
                current_price = self.prices[-1]
            else:
                current_price = get_current_price(self.symbol)
                
            if current_price <= 0:
                return
                
            if self.side == "BUY":
                profit = (current_price - self.entry) * self.qty
            else:
                profit = (self.entry - current_price) * abs(self.qty)
                
            invested = self.entry * abs(self.qty) / self.lev
            if invested <= 0:
                return
                
            roi = (profit / invested) * 100
            
            if roi >= self.tp:
                self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl is not None and roi <= -self.sl:
                self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra TP/SL: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side):
        self.check_position_status()    
        try:
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            
            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}")
                return
            
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                self.log(f"❌ Không thể kết nối Binance - Kiểm tra API Key")
                return
                
            if balance <= 0:
                self.log(f"❌ Không đủ số dư USDT")
                return
            
            if self.percent > 100:
                self.percent = 100
            elif self.percent <= 0:
                self.percent = 0.1
                
            usdt_amount = balance * (self.percent / 100)
            price = get_current_price(self.symbol)
            if price <= 0:
                self.log(f"❌ Lỗi lấy giá")
                return
                
            step = get_step_size(self.symbol, self.api_key, self.api_secret)
            if step <= 0:
                step = 0.001
            
            qty = (usdt_amount * self.lev) / price
            
            if step > 0:
                steps = qty / step
                qty = round(steps) * step
            
            qty = max(qty, 0)
            qty = round(qty, 8)
            
            min_qty = step
            
            if qty < min_qty:
                self.log(f"⚠️ Số lượng quá nhỏ ({qty}), không đặt lệnh")
                return
                
            self.position_attempt_count += 1
            if self.position_attempt_count > self.max_position_attempts:
                self.log(f"⚠️ Đã đạt giới hạn số lần thử mở lệnh ({self.max_position_attempts})")
                self.position_attempt_count = 0
                return
                
            res = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if not res:
                self.log(f"❌ Lỗi khi đặt lệnh {side}")
                return
                
            if res.get('status') == 'FILLED':
                self.position_open = True
                self.status = "open"
                self.side = side
                self.qty = qty if side == "BUY" else -qty
                self.entry = float(res.get('avgPrice', price))
                self.position_attempt_count = 0
                
                self.log(f"✅ Mở {side} {qty} {self.symbol} @ {self.entry:.4f}")
            else:
                self.log(f"⚠️ Lệnh {side} chưa được khớp: {res.get('status')}")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi mở vị thế: {str(e)}")
                self.last_error_log_time = time.time()

    def close_position(self, reason=""):
        try:
            if not self.position_open or not self.qty:
                return
                
            side = "SELL" if self.side == "BUY" else "BUY"
            qty = abs(self.qty)
            
            res = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if not res:
                self.log(f"❌ Lỗi khi đóng lệnh {side}")
                return
                
            if res.get('status') == 'FILLED':
                current_price = float(res.get('avgPrice', self.prices[-1] if self.prices else self.entry))
                
                if self.side == "BUY":
                    profit = (current_price - self.entry) * qty
                else:
                    profit = (self.entry - current_price) * qty
                    
                invested = self.entry * qty / self.lev
                roi = (profit / invested) * 100 if invested > 0 else 0
                
                self.position_open = False
                self.status = "waiting"
                self.side = ""
                self.qty = 0
                self.entry = 0
                self.last_close_time = time.time()
                
                self.log(f"🔒 Đóng lệnh {reason} | ROI: {roi:.2f}% | Lợi nhuận: {profit:.2f} USDT")
            else:
                self.log(f"⚠️ Lệnh đóng chưa khớp: {res.get('status')}")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi đóng vị thế: {str(e)}")
                self.last_error_log_time = time.time()

# ========== CHIẾN LƯỢC TỰ ĐỘNG TÌM COIN ==========

class Reverse24hBot(BaseBot):
    """Bot tự động tìm coin biến động mạnh 24h để đảo chiều"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, threshold=50):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Reverse 24h")
        self.threshold = threshold
        self.last_24h_change = 0
        self.checked_24h_change = False

    def get_signal(self):
        try:
            current_time = time.time()
            
            if not self.checked_24h_change or current_time - self.last_signal_check > 3600:
                self.price_change_24h = get_24h_change(self.symbol)
                self.last_24h_change = self.price_change_24h
                self.checked_24h_change = True
                self.last_signal_check = current_time
                
                self.log(f"📊 Biến động 24h: {self.price_change_24h:.2f}% | Ngưỡng: {self.threshold}%")
            
            if abs(self.price_change_24h) >= self.threshold:
                if self.price_change_24h > 0:
                    return "SELL"
                else:
                    return "BUY"
                    
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Reverse 24h: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class TrendMomentumBot(BaseBot):
    """Bot tự động tìm coin có xu hướng và động lượng mạnh"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Momentum")
        self.ema_fast = 8
        self.ema_slow = 21
        self.rsi_period = 14
        self.momentum_period = 10

    def get_signal(self):
        try:
            if len(self.prices) < 50:
                return None
                
            prices = self.prices[-50:]
            
            ema_fast = calc_ema(prices, self.ema_fast)
            ema_slow = calc_ema(prices, self.ema_slow)
            rsi = calc_rsi(prices, self.rsi_period)
            
            if ema_fast is None or ema_slow is None or rsi is None:
                return None
            
            momentum = (prices[-1] - prices[-self.momentum_period]) / prices[-self.momentum_period] * 100
            
            if rsi > 60 and ema_fast > ema_slow and momentum > 2:
                return "BUY"
            elif rsi < 40 and ema_fast < ema_slow and momentum < -2:
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Trend Momentum: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class VolatilityBreakoutBot(BaseBot):
    """Bot tự động tìm coin có biến động cao và breakout"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Volatility Breakout")
        self.volatility_period = 20
        self.breakout_threshold = 1.5

    def get_signal(self):
        try:
            if len(self.prices) < self.volatility_period + 1:
                return None
                
            returns = []
            for i in range(1, self.volatility_period + 1):
                ret = (self.prices[-i] - self.prices[-i-1]) / self.prices[-i-1]
                returns.append(ret)
            volatility = np.std(returns) * 100
            
            if volatility < self.breakout_threshold:
                return None
                
            avg_price = np.mean(self.prices[-5:])
            current_price = self.prices[-1]
            
            if current_price > avg_price:
                return "BUY"
            else:
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Volatility Breakout: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class MultiTimeframeBot(BaseBot):
    """Bot tự động tìm coin có tín hiệu đồng thuận đa khung thời gian"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Multi Timeframe")
        self.timeframes = ['5m', '15m', '1h']
        self.last_multi_analysis = 0
        self.analysis_interval = 1800

    def get_signal(self):
        try:
            current_time = time.time()
            if current_time - self.last_multi_analysis < self.analysis_interval:
                return None
                
            bullish_count = 0
            total_count = 0
            
            for tf in self.timeframes:
                try:
                    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={self.symbol}&interval={tf}&limit=50"
                    data = binance_api_request(url)
                    if not data or len(data) < 20:
                        continue
                    
                    closes = [float(k[4]) for k in data]
                    ema_fast = calc_ema(closes, 9)
                    ema_slow = calc_ema(closes, 21)
                    
                    if ema_fast and ema_slow:
                        total_count += 1
                        if ema_fast > ema_slow:
                            bullish_count += 1
                            
                    time.sleep(0.1)
                    
                except Exception as e:
                    continue
            
            self.last_multi_analysis = current_time
            
            if total_count == len(self.timeframes):
                if bullish_count >= 2:  # Ít nhất 2/3 khung thời gian bullish
                    return "BUY"
                elif bullish_count <= 1:  # Ít nhất 2/3 khung thời gian bearish
                    return "SELL"
                    
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Multi Timeframe: {str(e)}")
                self.last_error_log_time = time.time()
        return None

# ========== CHIẾN LƯỢC THÔNG THƯỜNG ==========

class RSIEMABot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "RSI/EMA Recursive")
        self.rsi_period = 14
        self.ema_short = 9
        self.ema_long = 21

    def get_signal(self):
        try:
            if len(self.prices) < 50:
                return None
                
            prices = self.prices[-50:]
            
            rsi = calc_rsi(prices, self.rsi_period)
            ema_short = calc_ema(prices, self.ema_short)
            ema_long = calc_ema(prices, self.ema_long)
            
            if rsi is None or ema_short is None or ema_long is None:
                return None
                
            if rsi < 30 and ema_short > ema_long:
                return "BUY"
            elif rsi > 70 and ema_short < ema_long:
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu RSI/EMA: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class EMACrossoverBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "EMA Crossover")
        self.ema_fast = 5
        self.ema_slow = 13

    def get_signal(self):
        try:
            if len(self.prices) < 30:
                return None
                
            prices = self.prices[-30:]
            
            ema_fast = calc_ema(prices, self.ema_fast)
            ema_slow = calc_ema(prices, self.ema_slow)
            
            if ema_fast is None or ema_slow is None:
                return None
                
            if ema_fast > ema_slow:
                return "BUY"
            elif ema_fast < ema_slow:
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu EMA Crossover: {str(e)}")
                self.last_error_log_time = time.time()
        return None

# ========== BOT MANAGER ĐA CHIẾN LƯỢC ==========
class BotManager:
    def __init__(self, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}
        self.admin_chat_id = telegram_chat_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        
        self._verify_api_connection()
        
        self.log("🟢 HỆ THỐNG BOT ĐA CHIẾN LƯỢC ĐÃ KHỞI ĐỘNG")
        
        self.status_thread = threading.Thread(target=self._status_monitor, daemon=True)
        self.status_thread.start()
        
        self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
        self.telegram_thread.start()
        
        if self.admin_chat_id:
            self.send_main_menu(self.admin_chat_id)

    def _verify_api_connection(self):
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance API. Kiểm tra API Key!")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        send_telegram(f"<b>SYSTEM</b>: {message}", 
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = (
            "🤖 <b>BOT GIAO DỊCH FUTURES BINANCE</b>\n\n"
            "🎯 <b>HỆ THỐNG ĐA CHIẾN LƯỢC</b>\n"
            "Chọn một trong các tùy chọn bên dưới:"
        )
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bot(self, symbol, lev, percent, tp, sl, strategy_type, **kwargs):
        if sl == 0:
            sl = None
            
        test_balance = get_balance(self.api_key, self.api_secret)
        if test_balance is None:
            self.log("❌ LỖI: API Key không hợp lệ. Vui lòng kiểm tra lại!")
            return False
        
        # ========== CHIẾN LƯỢC TỰ ĐỘNG TÌM COIN ==========
        auto_strategies = {
            "Reverse 24h": {
                "function": get_qualified_symbols,
                "bot_class": Reverse24hBot,
                "params": {"threshold": kwargs.get('threshold', 30)}
            },
            "Trend Momentum": {
                "function": find_trend_momentum_symbols, 
                "bot_class": TrendMomentumBot,
                "params": {}
            },
            "Volatility Breakout": {
                "function": find_volatility_breakout_symbols,
                "bot_class": VolatilityBreakoutBot, 
                "params": {}
            },
            "Multi Timeframe": {
                "function": find_multi_timeframe_symbols,
                "bot_class": MultiTimeframeBot,
                "params": {}
            }
        }
        
        if strategy_type in auto_strategies:
            strategy_info = auto_strategies[strategy_type]
            auto_symbols = strategy_info["function"](self.api_key, self.api_secret, limit=3)
            
            if not auto_symbols:
                self.log(f"❌ Không tìm thấy coin nào phù hợp cho {strategy_type}")
                return False
            
            success_count = 0
            created_bots = []
            
            for auto_symbol in auto_symbols:
                bot_id = f"{auto_symbol}_{strategy_type}"
                
                if bot_id in self.bots:
                    continue
                    
                try:
                    if strategy_type == "Reverse 24h":
                        bot = Reverse24hBot(auto_symbol, lev, percent, tp, sl, self.ws_manager,
                                           self.api_key, self.api_secret, self.telegram_bot_token, 
                                           self.telegram_chat_id, kwargs.get('threshold', 30))
                    else:
                        bot_class = strategy_info["bot_class"]
                        bot = bot_class(auto_symbol, lev, percent, tp, sl, self.ws_manager,
                                      self.api_key, self.api_secret, self.telegram_bot_token, 
                                      self.telegram_chat_id)
                    
                    self.bots[bot_id] = bot
                    success_count += 1
                    created_bots.append(auto_symbol)
                    
                except Exception as e:
                    self.log(f"❌ Lỗi tạo bot {auto_symbol}: {str(e)}")
            
            if success_count > 0:
                bot_list = "\n".join([f"🔸 {symbol}" for symbol in created_bots])
                success_msg = (
                    f"✅ <b>ĐÃ TẠO {success_count} BOT {strategy_type}</b>\n\n"
                    f"🤖 Coin được chọn:\n{bot_list}\n\n"
                    f"💰 Đòn bẩy: {lev}x\n"
                    f"📊 % vốn: {percent}%\n" 
                    f"🎯 TP: {tp}% | 🛡️ SL: {sl}%"
                )
                self.log(success_msg)
                return True
            else:
                self.log("❌ Không thể tạo bot nào")
                return False
        
        # ========== CHIẾN LƯỢC THÔNG THƯỜNG ==========
        else:
            symbol = symbol.upper()
            bot_id = f"{symbol}_{strategy_type}"
            
            if bot_id in self.bots:
                self.log(f"⚠️ Đã có bot {strategy_type} cho {symbol}")
                return False
                
            try:
                if strategy_type == "RSI/EMA Recursive":
                    bot = RSIEMABot(symbol, lev, percent, tp, sl, self.ws_manager, 
                                   self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                elif strategy_type == "EMA Crossover":
                    bot = EMACrossoverBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                         self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                elif strategy_type == "Trend Following":
                    bot = TrendFollowingBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                           self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                elif strategy_type == "Scalping":
                    bot = ScalpingBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                     self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                elif strategy_type == "Safe Grid":
                    bot = SafeGridBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                     self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                else:
                    self.log(f"❌ Chiến lược {strategy_type} không được hỗ trợ")
                    return False
                
                self.bots[bot_id] = bot
                self.log(f"✅ Đã thêm bot {strategy_type}: {symbol} | ĐB: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}%")
                return True
                
            except Exception as e:
                error_msg = f"❌ Lỗi tạo bot {symbol}: {str(e)}\n{traceback.format_exc()}"
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

    # ... (phần còn lại của BotManager giữ nguyên từ file gốc)
    # Bao gồm: _status_monitor, _telegram_listener, _handle_telegram_message

# Thêm các class còn thiếu
class TrendFollowingBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Following")
        self.ema_period = 20

    def get_signal(self):
        try:
            if len(self.prices) < 25:
                return None
                
            prices = self.prices[-25:]
            current_price = prices[-1]
            
            ema_trend = calc_ema(prices, self.ema_period)
            
            if ema_trend is None:
                return None
                
            if current_price > ema_trend:
                return "BUY"
            elif current_price < ema_trend:
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Trend Following: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class ScalpingBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Scalping")
        self.rsi_period = 7

    def get_signal(self):
        try:
            if len(self.prices) < 15:
                return None
                
            prices = self.prices[-15:]
            
            rsi = calc_rsi(prices, self.rsi_period)
            
            if rsi is None:
                return None
                
            if rsi < 25:
                return "BUY"
            elif rsi > 75:
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Scalping: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class SafeGridBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Safe Grid")
        self.grid_levels = 3
        self.grid_spacing = 0.02
        self.last_grid_check = 0

    def get_signal(self):
        try:
            current_time = time.time()
            if current_time - self.last_grid_check < 300:
                return None
                
            if len(self.prices) < 10:
                return None
                
            current_price = self.prices[-1]
            avg_price = np.mean(self.prices[-10:])
            
            price_diff = (current_price - avg_price) / avg_price
            
            if abs(price_diff) >= self.grid_spacing:
                if price_diff > 0:
                    return "SELL"
                else:
                    return "BUY"
                    
            self.last_grid_check = current_time
            
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Safe Grid: {str(e)}")
                self.last_error_log_time = time.time()
        return None
