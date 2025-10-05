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
            [{"text": "🔥 Trend Momentum"}, {"text": "🚀 Volatility Breakout"}],
            [{"text": "💎 Multi Timeframe"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard(strategy=None):
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

# ========== HÀM TÌM KIẾM COIN TỰ ĐỘNG - ĐÃ SỬA HOÀN TOÀN ==========
def get_top_volatile_symbols(limit=10, threshold=20):
    """Lấy danh sách coin có biến động 24h cao nhất - ĐÃ SỬA LỖI"""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return ["BTCUSDT", "ETHUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT"]
        
        volatile_pairs = []
        for ticker in data:
            symbol = ticker.get('symbol', '')
            if symbol.endswith('USDT'):
                try:
                    change = float(ticker.get('priceChangePercent', 0))
                    if abs(change) >= threshold:
                        volatile_pairs.append((symbol, abs(change)))
                except (ValueError, TypeError):
                    continue
        
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

def get_qualified_symbols_with_leverage(api_key, api_secret, threshold=30, leverage=3, max_candidates=15, final_limit=3):
    """TÌM COIN ĐỦ ĐIỀU KIỆN: biến động + đòn bẩy - ĐÃ SỬA HOÀN TOÀN"""
    try:
        # Kiểm tra API key trước
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE - Kiểm tra API Key")
            return []
        
        logger.info(f"🔍 Đang tìm coin đủ điều kiện: biến động ≥{threshold}% + đòn bẩy {leverage}x")
        
        # Lấy danh sách coin biến động
        volatile_candidates = get_top_volatile_symbols(limit=max_candidates, threshold=threshold)
        
        if not volatile_candidates:
            logger.warning(f"❌ Không tìm thấy coin nào có biến động ≥{threshold}%")
            return []
        
        qualified_symbols = []
        
        for symbol in volatile_candidates:
            if len(qualified_symbols) >= final_limit:
                break
                
            try:
                # KIỂM TRA ĐÒN BẨY TRƯỚC - QUAN TRỌNG
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                
                if leverage_success:
                    # Kiểm tra thêm biến động 24h
                    change_24h = get_24h_change(symbol)
                    if change_24h is not None and abs(change_24h) >= threshold:
                        qualified_symbols.append(symbol)
                        logger.info(f"✅ {symbol}: biến động {change_24h:.2f}% + đòn bẩy {leverage}x")
                    else:
                        logger.warning(f"⚠️ {symbol}: biến động không đạt ({change_24h:.2f}%)")
                else:
                    logger.warning(f"⚠️ {symbol}: không thể đặt đòn bẩy {leverage}x")
                    
                time.sleep(0.3)  # Tránh rate limit
                
            except Exception as e:
                logger.warning(f"⚠️ Lỗi kiểm tra {symbol}: {str(e)}")
                continue
        
        logger.info(f"🎯 Kết quả: {len(qualified_symbols)} coin đủ điều kiện")
        return qualified_symbols
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin đủ điều kiện: {str(e)}")
        return []

def find_trend_momentum_symbols(api_key, api_secret, leverage=10, limit=3):
    """Tìm coin có xu hướng và động lượng tốt nhất - ĐÃ SỬA"""
    try:
        logger.info("🔍 Đang tìm coin Trend Momentum...")
        symbols = get_top_volatile_symbols(limit=20, threshold=5)  # Lấy coin có biến động vừa
        best_symbols = []
        
        for symbol in symbols:
            try:
                # KIỂM TRA ĐÒN BẨY TRƯỚC
                if not set_leverage(symbol, leverage, api_key, api_secret):
                    continue
                    
                # Phân tích kỹ thuật
                url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&limit=50"
                data = binance_api_request(url)
                if not data or len(data) < 20:
                    continue
                
                closes = [float(k[4]) for k in data]
                if len(closes) < 21:
                    continue
                
                # Tính momentum
                momentum = (closes[-1] - closes[-10]) / closes[-10] * 100
                
                # Tính EMA
                ema_fast = calc_ema(closes, 8)
                ema_slow = calc_ema(closes, 21)
                
                if (ema_fast is not None and ema_slow is not None and 
                    momentum > 1.5 and ema_fast > ema_slow):
                    best_symbols.append((symbol, momentum))
                    
                time.sleep(0.2)
                
            except Exception as e:
                continue
        
        best_symbols.sort(key=lambda x: x[1], reverse=True)
        result = [symbol for symbol, score in best_symbols[:limit]]
        logger.info(f"✅ Tìm thấy {len(result)} coin Trend Momentum")
        return result
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin trend momentum: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

def find_volatility_breakout_symbols(api_key, api_secret, leverage=10, limit=3):
    """Tìm coin có biến động cao và sắp breakout - ĐÃ SỬA"""
    try:
        logger.info("🔍 Đang tìm coin Volatility Breakout...")
        symbols = get_top_volatile_symbols(limit=20, threshold=10)
        best_symbols = []
        
        for symbol in symbols:
            try:
                # KIỂM TRA ĐÒN BẨY TRƯỚC
                if not set_leverage(symbol, leverage, api_key, api_secret):
                    continue
                    
                url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=15m&limit=100"
                data = binance_api_request(url)
                if not data or len(data) < 50:
                    continue
                
                highs = [float(k[2]) for k in data]
                lows = [float(k[3]) for k in data]
                closes = [float(k[4]) for k in data]
                
                # Tính ATR
                atr_values = []
                for i in range(1, len(highs)):
                    tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                    atr_values.append(tr)
                
                if len(atr_values) < 14:
                    continue
                    
                atr = np.mean(atr_values[-14:])
                current_range = highs[-1] - lows[-1]
                
                if atr > 0:
                    volatility_score = (current_range / closes[-1]) * 100
                    if volatility_score > 1.5:  # Biến động > 1.5%
                        best_symbols.append((symbol, volatility_score))
                    
                time.sleep(0.2)
                
            except Exception as e:
                continue
        
        best_symbols.sort(key=lambda x: x[1], reverse=True)
        result = [symbol for symbol, score in best_symbols[:limit]]
        logger.info(f"✅ Tìm thấy {len(result)} coin Volatility Breakout")
        return result
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin volatility breakout: {str(e)}")
        return ["ADAUSDT", "DOGEUSDT", "XRPUSDT"]

def find_multi_timeframe_symbols(api_key, api_secret, leverage=10, limit=3):
    """Tìm coin có tín hiệu đồng thuận đa khung thời gian - ĐÃ SỬA"""
    try:
        logger.info("🔍 Đang tìm coin Multi Timeframe...")
        symbols = get_top_volatile_symbols(limit=15, threshold=5)
        best_symbols = []
        
        for symbol in symbols:
            try:
                # KIỂM TRA ĐÒN BẨY TRƯỚC
                if not set_leverage(symbol, leverage, api_key, api_secret):
                    continue
                    
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
                
                if total_signals == len(timeframes):
                    consensus_score = bullish_signals / total_signals
                    if consensus_score >= 0.7:  # 70% đồng thuận
                        best_symbols.append((symbol, consensus_score))
                
                time.sleep(0.2)
                
            except Exception as e:
                continue
        
        best_symbols.sort(key=lambda x: x[1], reverse=True)
        result = [symbol for symbol, score in best_symbols[:limit]]
        logger.info(f"✅ Tìm thấy {len(result)} coin Multi Timeframe")
        return result
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin multi timeframe: {str(e)}")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

# ========== API BINANCE - ĐÃ SỬA LỖI ==========
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
                
            if e.code == 400:
                logger.error(f"❌ LỖI 400 BAD REQUEST - Kiểm tra tham số: {url}")
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
    """Thiết lập đòn bẩy - ĐÃ SỬA KỸ LƯỠNG"""
    try:
        # Kiểm tra symbol có tồn tại không
        if not symbol or len(symbol) < 6:
            logger.error(f"❌ Symbol không hợp lệ: {symbol}")
            return False
            
        ts = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "leverage": int(lev),  # Đảm bảo là số nguyên
            "timestamp": ts
        }
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v1/leverage?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        response = binance_api_request(url, method='POST', headers=headers)
        
        if response is None:
            logger.error(f"❌ Không thể đặt đòn bẩy cho {symbol} - Lỗi kết nối")
            return False
            
        if response and 'leverage' in response:
            logger.info(f"✅ Đã đặt đòn bẩy {lev}x cho {symbol}")
            return True
            
        logger.warning(f"⚠️ Phản hồi đòn bẩy không hợp lệ cho {symbol}: {response}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Lỗi thiết lập đòn bẩy cho {symbol}: {str(e)}")
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
            "quantity": float(qty),  # Đảm bảo là float
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
    """Lấy % thay đổi giá 24h cho một symbol - ĐÃ SỬA LỖI"""
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

# ========== BASE BOT CLASS - ĐÃ SỬA LỖI KHỞI TẠO ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, strategy_name):
        self.symbol = symbol.upper()
        self.lev = int(lev)  # Đảm bảo là số nguyên
        self.percent = float(percent)  # Đảm bảo là float
        self.tp = float(tp) if tp else 0
        self.sl = float(sl) if sl else 0
        self.ws_manager = ws_manager
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.strategy_name = strategy_name
        
        # KHỞI TẠO TẤT CẢ THUỘC TÍNH QUAN TRỌNG - TRÁNH LỖI None
        self.last_signal_check = 0
        self.last_price = 0
        self.previous_price = 0
        self.price_change_24h = 0
        self.price_history = []
        self.max_history_size = 100
        self.prices = []
        
        # Trạng thái bot
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        
        # Control flags
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
        
        # Chiến lược cụ thể
        self._init_strategy_attributes()
        
        # Kiểm tra position
        self.check_position_status()
        
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot {strategy_name} khởi động cho {self.symbol}")

    def _init_strategy_attributes(self):
        """Khởi tạo thuộc tính cụ thể cho từng chiến lược"""
        # Các thuộc tính chung cho tất cả bot
        pass

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
                self.position_open = False
                self.status = "waiting"
                self.side = ""
                self.qty = 0
                self.entry = 0
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
                profit = (current_price - self.entry) * abs(self.qty)
            else:
                profit = (self.entry - current_price) * abs(self.qty)
                
            invested = self.entry * abs(self.qty) / self.lev
            if invested <= 0:
                return
                
            roi = (profit / invested) * 100
            
            if self.tp and roi >= self.tp:
                self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl and roi <= -self.sl:
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
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x")
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
                qty = math.floor(steps) * step  # Làm tròn xuống để đảm bảo hợp lệ
            
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

# ========== CHIẾN LƯỢC TỰ ĐỘNG TÌM COIN - ĐÃ SỬA HOÀN TOÀN ==========

class Reverse24hBot(BaseBot):
    """Bot tự động tìm coin biến động mạnh 24h để đảo chiều - ĐÃ SỬA"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, threshold=50):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Reverse 24h")
        self.threshold = float(threshold)
        self.last_24h_change = 0
        self.checked_24h_change = False
        self.signal_check_interval = 3600  # 1 giờ

    def _init_strategy_attributes(self):
        """Khởi tạo thuộc tính cho Reverse 24h"""
        self.last_24h_change = 0
        self.checked_24h_change = False
        self.signal_check_interval = 3600

    def get_signal(self):
        try:
            current_time = time.time()
            
            # Kiểm tra mỗi giờ một lần
            if not self.checked_24h_change or current_time - self.last_signal_check > self.signal_check_interval:
                change_24h = get_24h_change(self.symbol)
                if change_24h is not None:
                    self.price_change_24h = change_24h
                    self.last_24h_change = change_24h
                    self.checked_24h_change = True
                    self.last_signal_check = current_time
                    
                    self.log(f"📊 Biến động 24h: {self.price_change_24h:.2f}% | Ngưỡng: {self.threshold}%")
            
            if abs(self.price_change_24h) >= self.threshold:
                if self.price_change_24h > 0:
                    self.log(f"🎯 Tín hiệu SELL - Biến động: {self.price_change_24h:.2f}%")
                    return "SELL"
                else:
                    self.log(f"🎯 Tín hiệu BUY - Biến động: {self.price_change_24h:.2f}%")
                    return "BUY"
                    
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Reverse 24h: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class TrendMomentumBot(BaseBot):
    """Bot tự động tìm coin có xu hướng và động lượng mạnh - ĐÃ SỬA"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Momentum")
        self.ema_fast = 8
        self.ema_slow = 21
        self.rsi_period = 14
        self.momentum_period = 10
        self.last_ema_fast = None
        self.last_ema_slow = None
        self.last_rsi = None

    def _init_strategy_attributes(self):
        """Khởi tạo thuộc tính cho Trend Momentum"""
        self.ema_fast = 8
        self.ema_slow = 21
        self.rsi_period = 14
        self.momentum_period = 10
        self.last_ema_fast = None
        self.last_ema_slow = None
        self.last_rsi = None

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
            
            self.last_ema_fast = ema_fast
            self.last_ema_slow = ema_slow
            self.last_rsi = rsi
            
            if rsi > 60 and ema_fast > ema_slow and momentum > 1.5:
                self.log(f"🎯 Tín hiệu BUY - RSI: {rsi:.1f}, Momentum: {momentum:.2f}%")
                return "BUY"
            elif rsi < 40 and ema_fast < ema_slow and momentum < -1.5:
                self.log(f"🎯 Tín hiệu SELL - RSI: {rsi:.1f}, Momentum: {momentum:.2f}%")
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Trend Momentum: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class VolatilityBreakoutBot(BaseBot):
    """Bot tự động tìm coin có biến động cao và breakout - ĐÃ SỬA"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Volatility Breakout")
        self.volatility_period = 20
        self.breakout_threshold = 1.5
        self.last_volatility = None
        self.last_breakout_check = 0

    def _init_strategy_attributes(self):
        """Khởi tạo thuộc tính cho Volatility Breakout"""
        self.volatility_period = 20
        self.breakout_threshold = 1.5
        self.last_volatility = None
        self.last_breakout_check = 0

    def get_signal(self):
        try:
            current_time = time.time()
            if current_time - self.last_breakout_check < 300:  # 5 phút
                return None
                
            if len(self.prices) < self.volatility_period + 1:
                return None
                
            # Tính biến động
            returns = []
            for i in range(1, self.volatility_period + 1):
                if len(self.prices) >= i + 1:
                    ret = (self.prices[-i] - self.prices[-i-1]) / self.prices[-i-1]
                    returns.append(ret)
            
            if len(returns) < self.volatility_period:
                return None
                
            volatility = np.std(returns) * 100
            self.last_volatility = volatility
            
            if volatility < self.breakout_threshold:
                return None
                
            avg_price = np.mean(self.prices[-5:])
            current_price = self.prices[-1]
            
            self.last_breakout_check = current_time
            
            if current_price > avg_price * 1.01:  # Breakout lên
                self.log(f"🎯 Tín hiệu BUY - Biến động: {volatility:.2f}%, Breakout lên")
                return "BUY"
            elif current_price < avg_price * 0.99:  # Breakout xuống
                self.log(f"🎯 Tín hiệu SELL - Biến động: {volatility:.2f}%, Breakout xuống")
                return "SELL"
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Volatility Breakout: {str(e)}")
                self.last_error_log_time = time.time()
        return None

class MultiTimeframeBot(BaseBot):
    """Bot tự động tìm coin có tín hiệu đồng thuận đa khung thời gian - ĐÃ SỬA"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Multi Timeframe")
        self.timeframes = ['5m', '15m', '1h']
        self.last_multi_analysis = 0
        self.analysis_interval = 1800  # 30 phút

    def _init_strategy_attributes(self):
        """Khởi tạo thuộc tính cho Multi Timeframe"""
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
                    self.log(f"🎯 Tín hiệu BUY - Đồng thuận {bullish_count}/3 khung thời gian")
                    return "BUY"
                elif bullish_count <= 1:  # Ít nhất 2/3 khung thời gian bearish
                    self.log(f"🎯 Tín hiệu SELL - Đồng thuận {bullish_count}/3 khung thời gian")
                    return "SELL"
                    
        except Exception as e:
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi tín hiệu Multi Timeframe: {str(e)}")
                self.last_error_log_time = time.time()
        return None

# ========== BOT MANAGER ĐA CHIẾN LƯỢC - ĐÃ SỬA HOÀN TOÀN ==========
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
        """Thêm bot - ĐÃ SỬA HOÀN TOÀN"""
        try:
            # Chuyển đổi kiểu dữ liệu
            lev = int(lev)
            percent = float(percent)
            tp = float(tp) if tp else 0
            sl = float(sl) if sl else 0
            
            if sl == 0:
                sl = None
                
            # Kiểm tra API key
            test_balance = get_balance(self.api_key, self.api_secret)
            if test_balance is None:
                self.log("❌ LỖI: API Key không hợp lệ. Vui lòng kiểm tra lại!")
                return False
            
            # ========== CHIẾN LƯỢC TỰ ĐỘNG TÌM COIN ==========
            auto_strategies = {
                "Reverse 24h": {
                    "function": get_qualified_symbols_with_leverage,
                    "bot_class": Reverse24hBot,
                    "params": {"threshold": kwargs.get('threshold', 30), "leverage": lev}
                },
                "Trend Momentum": {
                    "function": find_trend_momentum_symbols, 
                    "bot_class": TrendMomentumBot,
                    "params": {"leverage": lev}
                },
                "Volatility Breakout": {
                    "function": find_volatility_breakout_symbols,
                    "bot_class": VolatilityBreakoutBot, 
                    "params": {"leverage": lev}
                },
                "Multi Timeframe": {
                    "function": find_multi_timeframe_symbols,
                    "bot_class": MultiTimeframeBot,
                    "params": {"leverage": lev}
                }
            }
            
            if strategy_type in auto_strategies:
                strategy_info = auto_strategies[strategy_type]
                auto_symbols = strategy_info["function"](self.api_key, self.api_secret, 
                                                       limit=3, **strategy_info["params"])
                
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
                        f"🎯 TP: {tp}% | 🛡️ SL: {sl if sl else 'Tắt'}%"
                    )
                    self.log(success_msg)
                    return True
                else:
                    self.log("❌ Không thể tạo bot nào")
                    return False
            
            # ========== CHIẾN LƯỢC THÔNG THƯỜNG ==========
            else:
                if not symbol:
                    self.log("❌ Vui lòng chọn symbol")
                    return False
                    
                symbol = symbol.upper()
                bot_id = f"{symbol}_{strategy_type}"
                
                if bot_id in self.bots:
                    self.log(f"⚠️ Đã có bot {strategy_type} cho {symbol}")
                    return False
                    
                try:
                    # Kiểm tra đòn bẩy trước
                    if not set_leverage(symbol, lev, self.api_key, self.api_secret):
                        self.log(f"❌ Không thể đặt đòn bẩy {lev}x cho {symbol}")
                        return False
                    
                    if strategy_type == "RSI/EMA Recursive":
                        from trading_bot_lib import RSIEMABot
                        bot = RSIEMABot(symbol, lev, percent, tp, sl, self.ws_manager, 
                                       self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                    elif strategy_type == "EMA Crossover":
                        from trading_bot_lib import EMACrossoverBot
                        bot = EMACrossoverBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                             self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                    elif strategy_type == "Trend Following":
                        from trading_bot_lib import TrendFollowingBot
                        bot = TrendFollowingBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                               self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                    elif strategy_type == "Scalping":
                        from trading_bot_lib import ScalpingBot
                        bot = ScalpingBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                         self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                    elif strategy_type == "Safe Grid":
                        from trading_bot_lib import SafeGridBot
                        bot = SafeGridBot(symbol, lev, percent, tp, sl, self.ws_manager,
                                         self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        self.log(f"❌ Chiến lược {strategy_type} không được hỗ trợ")
                        return False
                    
                    self.bots[bot_id] = bot
                    self.log(f"✅ Đã thêm bot {strategy_type}: {symbol} | ĐB: {lev}x | %: {percent} | TP/SL: {tp}%/{sl if sl else 'Tắt'}%")
                    return True
                    
                except Exception as e:
                    error_msg = f"❌ Lỗi tạo bot {symbol}: {str(e)}\n{traceback.format_exc()}"
                    self.log(error_msg)
                    return False
                    
        except Exception as e:
            error_msg = f"❌ Lỗi hệ thống khi thêm bot: {str(e)}"
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

    def _status_monitor(self):
        while self.running:
            try:
                time.sleep(6 * 3600)  # 6 giờ
                
                uptime = time.time() - self.start_time
                hours, rem = divmod(uptime, 3600)
                minutes, seconds = divmod(rem, 60)
                uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                
                active_bots = [bot_id for bot_id, bot in self.bots.items() if not bot._stop]
                balance = get_balance(self.api_key, self.api_secret)
                
                if balance is None:
                    status_msg = "❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key!"
                else:
                    status_msg = (
                        f"📊 <b>BÁO CÁO HỆ THỐNG</b>\n"
                        f"⏱ Thời gian hoạt động: {uptime_str}\n"
                        f"🤖 Số bot đang chạy: {len(active_bots)}\n"
                        f"💰 Số dư khả dụng: {balance:.2f} USDT"
                    )
                send_telegram(status_msg,
                            bot_token=self.telegram_bot_token,
                            default_chat_id=self.telegram_chat_id)
                
            except Exception as e:
                logger.error(f"Lỗi báo cáo trạng thái: {str(e)}")

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
                            
                            if chat_id != self.admin_chat_id:
                                continue
                            
                            if update_id > last_update_id:
                                last_update_id = update_id
                            
                            self._handle_telegram_message(chat_id, text)
                elif response.status_code == 409:
                    logger.error("Lỗi xung đột: Chỉ một instance bot có thể lắng nghe Telegram")
                    time.sleep(60)
                else:
                    time.sleep(10)
                
            except Exception as e:
                logger.error(f"Lỗi Telegram listener: {str(e)}")
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        # Xử lý các bước thêm bot
        if current_step == 'waiting_strategy':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            elif text in ["🤖 RSI/EMA Recursive", "📊 EMA Crossover", "🎯 Reverse 24h", 
                         "📈 Trend Following", "⚡ Scalping", "🛡️ Safe Grid",
                         "🔥 Trend Momentum", "🚀 Volatility Breakout", "💎 Multi Timeframe"]:
                strategy_map = {
                    "🤖 RSI/EMA Recursive": "RSI/EMA Recursive",
                    "📊 EMA Crossover": "EMA Crossover", 
                    "🎯 Reverse 24h": "Reverse 24h",
                    "📈 Trend Following": "Trend Following",
                    "⚡ Scalping": "Scalping",
                    "🛡️ Safe Grid": "Safe Grid",
                    "🔥 Trend Momentum": "Trend Momentum",
                    "🚀 Volatility Breakout": "Volatility Breakout",
                    "💎 Multi Timeframe": "Multi Timeframe"
                }
                strategy = strategy_map[text]
                user_state['strategy'] = strategy
                
                if strategy == "Reverse 24h":
                    user_state['step'] = 'waiting_threshold'
                    send_telegram(
                        f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                        f"Chọn ngưỡng biến động 24h (%):\n"
                        f"💡 <i>Gợi ý: 30, 50, 70 (càng cao càng ít coin)</i>",
                        chat_id,
                        create_threshold_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                elif strategy in ["Trend Momentum", "Volatility Breakout", "Multi Timeframe"]:
                    user_state['step'] = 'waiting_leverage'
                    send_telegram(
                        f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                        f"🤖 Bot sẽ tự động tìm coin đủ điều kiện\n\n"
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
                            f"🎯 <b>THIẾT LẬP REVERSE 24H</b>\n"
                            f"📊 Ngưỡng biến động: {threshold}%\n\n"
                            f"Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard(user_state.get('strategy')),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        send_telegram("⚠️ Ngưỡng phải lớn hơn 0", chat_id,
                                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                except:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id,
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
                
                if user_state.get('strategy') in ["Reverse 24h", "Trend Momentum", "Volatility Breakout", "Multi Timeframe"]:
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
                    if 0.1 <= percent <= 100:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        
                        if user_state.get('strategy') in ["Reverse 24h", "Trend Momentum", "Volatility Breakout", "Multi Timeframe"]:
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
                        send_telegram("⚠️ Vui lòng nhập % từ 0.1-100", chat_id,
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
                        
                        if user_state.get('strategy') in ["Reverse 24h", "Trend Momentum", "Volatility Breakout", "Multi Timeframe"]:
                            send_telegram(
                                f"🎯 Chiến lược: {user_state['strategy']}\n"
                                f"💰 ĐB: {user_state['leverage']}x\n"
                                f"📊 %: {user_state['percent']}%\n"
                                f"🎯 TP: {tp}%\n\n"
                                f"Nhập % Stop Loss (0 để tắt SL):\n"
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
                                f"Nhập % Stop Loss (0 để tắt SL):\n"
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
                        
                        if strategy in ["Reverse 24h", "Trend Momentum", "Volatility Breakout", "Multi Timeframe"]:
                            additional_params = {}
                            if strategy == "Reverse 24h":
                                additional_params['threshold'] = user_state.get('threshold', 30)
                                
                            if self.add_bot(symbol=None, lev=leverage, percent=percent, tp=tp, sl=sl, 
                                          strategy_type=strategy, **additional_params):
                                success_msg = (
                                    f"✅ <b>ĐÃ THÊM BOT {strategy} THÀNH CÔNG</b>\n\n"
                                    f"🎯 Chiến lược: {strategy}\n"
                                    f"💰 Đòn bẩy: {leverage}x\n"
                                    f"📊 % Số dư: {percent}%\n"
                                    f"🎯 TP: {tp}%\n"
                                    f"🛡️ SL: {sl if sl else 'Tắt'}%\n\n"
                                    f"🤖 Bot sẽ tự động tìm và giao dịch coin tốt nhất"
                                )
                                if strategy == "Reverse 24h":
                                    success_msg += f"\n📊 Ngưỡng biến động: {user_state.get('threshold', 30)}%"
                                    
                                send_telegram(
                                    success_msg,
                                    chat_id,
                                    create_main_menu(),
                                    self.telegram_bot_token, self.telegram_chat_id
                                )
                            else:
                                send_telegram("❌ Không thể thêm bot, không tìm thấy coin nào phù hợp", chat_id, create_main_menu(),
                                            self.telegram_bot_token, self.telegram_chat_id)
                        else:
                            symbol = user_state['symbol']
                            if self.add_bot(symbol, leverage, percent, tp, sl, strategy):
                                success_msg = (
                                    f"✅ <b>ĐÃ THÊM BOT THÀNH CÔNG</b>\n\n"
                                    f"📌 Cặp: {symbol}\n"
                                    f"🎯 Chiến lược: {strategy}\n"
                                    f"💰 Đòn bẩy: {leverage}x\n"
                                    f"📊 % Số dư: {percent}%\n"
                                    f"🎯 TP: {tp}%\n"
                                    f"🛡️ SL: {sl if sl else 'Tắt'}%"
                                )
                                send_telegram(
                                    success_msg,
                                    chat_id,
                                    create_main_menu(),
                                    self.telegram_bot_token, self.telegram_chat_id
                                )
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
        
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_strategy'}
            
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>\nVui lòng kiểm tra API Key trước khi thêm bot!", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"🎯 <b>CHỌN CHIẾN LƯỢC GIAO DỊCH</b>\n\n"
                f"💰 Số dư hiện có: {balance:.2f} USDT\n\n"
                f"🤖 <b>Chiến lược tự động</b>:\n"
                f"• Reverse 24h - Tìm coin biến động\n"
                f"• Trend Momentum - Xu hướng + Động lượng\n" 
                f"• Volatility Breakout - Biến động cao\n"
                f"• Multi Timeframe - Đa khung thời gian\n\n"
                f"Chọn chiến lược phù hợp:",
                chat_id,
                create_strategy_keyboard(),
                self.telegram_bot_token, self.telegram_chat_id
            )
        
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
            if bot_id in self.bots:
                self.stop_bot(bot_id)
                send_telegram(f"⛔ Đã gửi lệnh dừng bot {bot_id}", chat_id, create_main_menu(),
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
                "🤖 <b>RSI/EMA Recursive</b>\n"
                "   - Phân tích RSI + EMA đệ quy\n\n"
                "📊 <b>EMA Crossover</b>\n"
                "   - Giao cắt EMA nhanh/chậm\n\n"
                "🎯 <b>Reverse 24h</b>\n"
                "   - TỰ ĐỘNG tìm coin biến động mạnh\n"
                "   - Đảo chiều biến động 24h\n\n"
                "📈 <b>Trend Following</b>\n"
                "   - Theo xu hướng EMA\n\n"
                "⚡ <b>Scalping</b>\n"
                "   - Giao dịch tốc độ cao\n\n"
                "🛡️ <b>Safe Grid</b>\n"
                "   - Grid an toàn nhiều lệnh\n\n"
                "🔥 <b>Trend Momentum</b>\n"
                "   - TỰ ĐỘNG tìm coin xu hướng + động lượng\n\n"
                "🚀 <b>Volatility Breakout</b>\n"
                "   - TỰ ĐỘNG tìm coin biến động cao\n\n"
                "💎 <b>Multi Timeframe</b>\n"
                "   - TỰ ĐỘNG tìm coin đa khung thời gian"
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
                f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

# Thêm các class chiến lược còn thiếu
class RSIEMABot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "RSI/EMA Recursive")
        self.rsi_period = 14
        self.ema_short = 9
        self.ema_long = 21

    def _init_strategy_attributes(self):
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

    def _init_strategy_attributes(self):
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

class TrendFollowingBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Following")
        self.ema_period = 20

    def _init_strategy_attributes(self):
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

    def _init_strategy_attributes(self):
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

    def _init_strategy_attributes(self):
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
