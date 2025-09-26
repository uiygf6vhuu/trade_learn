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
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Detailed logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_errors.log')
    ]
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get configuration from environment variables
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Get bot configuration from environment variables (JSON format)
bot_config_json = os.getenv('BOT_CONFIGS', '[]')
try:
    BOT_CONFIGS = json.loads(bot_config_json)
except Exception as e:
    logging.error(f"Error parsing BOT_CONFIGS: {e}")
    BOT_CONFIGS = []

API_KEY = BINANCE_API_KEY
API_SECRET = BINANCE_SECRET_KEY

# ========== TELEGRAM FUNCTIONS ==========
def send_telegram(message, chat_id=None, reply_markup=None):
    """Sends a message via Telegram with detailed error handling."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram Bot Token is not configured.")
        return

    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not chat_id:
        logger.warning("Telegram Chat ID is not configured.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
            error_msg = response.text
            logger.error(f"Telegram send error ({response.status_code}): {error_msg}")
    except Exception as e:
        logger.error(f"Telegram connection error: {str(e)}")

def create_menu_keyboard():
    """Creates a 3-button menu for Telegram."""
    return {
        "keyboard": [
            [{"text": "📊 Danh sách Bot"}],
            [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
            [{"text": "💰 Số dư tài khoản"}, {"text": "📈 Vị thế đang mở"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def create_cancel_keyboard():
    """Creates a cancel keyboard."""
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard():
    """Creates a keyboard for selecting coin pairs."""
    popular_symbols = ["SUIUSDT", "DOGEUSDT", "1000PEPEUSDT", "TRUMPUSDT", "XRPUSDT", "ADAUSDT"]
    keyboard = []
    row = []
    for symbol in popular_symbols:
        row.append({"text": symbol})
        if len(row) == 2:
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

def create_leverage_keyboard():
    """Creates a keyboard for selecting leverage."""
    leverages = ["3", "8", "10", "20", "30", "50", "75", "100"]
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

# ========== BINANCE API HELPER FUNCTIONS ==========
def sign(query):
    try:
        return hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"Error creating signature: {str(e)}")
        send_telegram(f"⚠️ <b>SIGN ERROR:</b> {str(e)}")
        return ""

def binance_api_request(url, method='GET', params=None, headers=None):
    """General function for Binance API requests with detailed error handling."""
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
                    logger.error(f"API Error ({response.status}): {response.read().decode()}")
                    if response.status == 429:  # Rate limit
                        time.sleep(2 ** attempt)  # Exponential backoff
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP Error ({e.code}): {e.reason}")
            if e.code == 429:  # Rate limit
                time.sleep(2 ** attempt)  # Exponential backoff
            elif e.code >= 500:
                time.sleep(1)
            continue
        except Exception as e:
            logger.error(f"API connection error: {str(e)}")
            time.sleep(1)

    logger.error(f"Failed to make API request after {max_retries} attempts")
    return None

def get_step_size(symbol):
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
        logger.error(f"Error getting step size: {str(e)}")
        send_telegram(f"⚠️ <b>STEP SIZE ERROR:</b> {symbol} - {str(e)}")
    return 0.001

def set_leverage(symbol, lev):
    try:
        ts = int(time.time() * 1000)
        params = {
            "symbol": symbol.upper(),
            "leverage": lev,
            "timestamp": ts
        }
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/leverage?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}

        response = binance_api_request(url, method='POST', headers=headers)
        if response and 'leverage' in response:
            return True
    except Exception as e:
        logger.error(f"Error setting leverage: {str(e)}")
        send_telegram(f"⚠️ <b>LEVERAGE ERROR:</b> {symbol} - {str(e)}")
    return False

def get_balance():
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}

        data = binance_api_request(url, headers=headers)
        if not data:
            return 0

        for asset in data['assets']:
            if asset['asset'] == 'USDT':
                return float(asset['availableBalance'])
    except Exception as e:
        logger.error(f"Error getting balance: {str(e)}")
        send_telegram(f"⚠️ <b>BALANCE ERROR:</b> {str(e)}")
    return 0

def place_order(symbol, side, qty):
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
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/order?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}

        return binance_api_request(url, method='POST', headers=headers)
    except Exception as e:
        logger.error(f"Error placing order: {str(e)}")
        send_telegram(f"⚠️ <b>ORDER ERROR:</b> {symbol} - {str(e)}")
    return None

def cancel_all_orders(symbol):
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v1/allOpenOrders?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}

        binance_api_request(url, method='DELETE', headers=headers)
        return True
    except Exception as e:
        logger.error(f"Error canceling orders: {str(e)}")
        send_telegram(f"⚠️ <b>CANCEL ORDER ERROR:</b> {symbol} - {str(e)}")
    return False

def get_current_price(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            return float(data['price'])
    except Exception as e:
        logger.error(f"Error getting price: {str(e)}")
        send_telegram(f"⚠️ <b>PRICE ERROR:</b> {symbol} - {str(e)}")
    return 0

def get_positions(symbol=None):
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        if symbol:
            params["symbol"] = symbol.upper()

        query = urllib.parse.urlencode(params)
        sig = sign(query)
        url = f"https://fapi.binance.com/fapi/v2/positionRisk?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': API_KEY}

        positions = binance_api_request(url, headers=headers)
        if not positions:
            return []

        if symbol:
            for pos in positions:
                if pos['symbol'] == symbol.upper():
                    return [pos]

        return positions
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        send_telegram(f"⚠️ <b>POSITIONS ERROR:</b> {symbol if symbol else ''} - {str(e)}")
    return []

def get_klines(symbol, interval, limit=200):
    """Lấy dữ liệu nến với xử lý lỗi tốt hơn"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
            data = binance_api_request(url)
            
            if data and len(data) > 0:
                df = pd.DataFrame(data, columns=["open_time", "open", "high", "low", "close", "volume", 
                                               "close_time", "quote_asset_volume", "number_of_trades", 
                                               "taker_buy_base", "taker_buy_quote", "ignore"])
                # Chuyển đổi kiểu dữ liệu
                numeric_columns = ["open", "high", "low", "close", "volume"]
                for col in numeric_columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Loại bỏ NaN values
                df = df.dropna()
                return df
                
        except Exception as e:
            logger.error(f"Error getting klines for {symbol}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)
    
    return pd.DataFrame()

# ========== TECHNICAL INDICATORS ==========
def calc_rsi(series, period=14):
    try:
        delta = series.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.rolling(period).mean()
        ma_down = down.rolling(period).mean()
        rs = ma_up / ma_down
        return 100 - (100 / (1 + rs))
    except Exception as e:
        logger.error(f"Error calculating RSI: {str(e)}")
        return pd.Series([None] * len(series))

def calc_ema(series, period):
    try:
        return series.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.error(f"Error calculating EMA: {str(e)}")
        return pd.Series([None] * len(series))

def calc_atr(df, period=14):
    try:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()
    except Exception as e:
        logger.error(f"Error calculating ATR: {str(e)}")
        return pd.Series([None] * len(df))

def calc_macd(series, fast_period=12, slow_period=26, signal_period=9):
    try:
        ema_fast = series.ewm(span=fast_period, adjust=False).mean()
        ema_slow = series.ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        macd_hist = macd - signal
        return macd, signal, macd_hist
    except Exception as e:
        logger.error(f"Error calculating MACD: {str(e)}")
        empty_series = pd.Series([None] * len(series))
        return empty_series, empty_series, empty_series

def calc_ichimoku(df):
    try:
        high_9 = df['high'].rolling(window=9).max()
        low_9 = df['low'].rolling(window=9).min()
        tenkan_sen = (high_9 + low_9) / 2

        high_26 = df['high'].rolling(window=26).max()
        low_26 = df['low'].rolling(window=26).min()
        kijun_sen = (high_26 + low_26) / 2

        return tenkan_sen, kijun_sen
    except Exception as e:
        logger.error(f"Error calculating Ichimoku: {str(e)}")
        empty_series = pd.Series([None] * len(df))
        return empty_series, empty_series

def calc_adx(df, period=14):
    try:
        # Simplified ADX calculation for demonstration
        plus_di = df['high'].diff().rolling(period).mean()
        minus_di = df['low'].diff().rolling(period).mean()
        adx = (plus_di + minus_di).abs() / 2
        return adx
    except Exception as e:
        logger.error(f"Error calculating ADX: {str(e)}")
        return pd.Series([None] * len(df))

def add_technical_indicators(df):
    """Adds all technical indicators to the DataFrame."""
    if df.empty or len(df) < 50:
        return df

    # Tính Volume SMA trước
    df['volume_sma'] = df['volume'].rolling(window=20).mean()

    # Các chỉ báo khác
    df['RSI'] = calc_rsi(df['close'], 14)
    df['EMA9'] = calc_ema(df['close'], 9)
    df['EMA21'] = calc_ema(df['close'], 21)
    
    # MACD
    macd, macd_signal, macd_hist = calc_macd(df['close'])
    df['MACD'] = macd
    df['MACD_Signal'] = macd_signal
    df['MACD_Hist'] = macd_hist

    # Stochastic
    df['stoch_k'] = 100 * ((df['close'] - df['low'].rolling(14).min()) / 
                          (df['high'].rolling(14).max() - df['low'].rolling(14).min()))
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # Bollinger Bands
    df['bollinger_high'] = df['close'].rolling(20).mean() + 2 * df['close'].rolling(20).std()
    df['bollinger_low'] = df['close'].rolling(20).mean() - 2 * df['close'].rolling(20).std()

    # Ichimoku
    tenkan, kijun = calc_ichimoku(df)
    df['ichimoku_tenkan_sen'] = tenkan
    df['ichimoku_kijun_sen'] = kijun

    # ADX và DI
    df['plus_di'] = df['high'].diff().rolling(14).mean()
    df['minus_di'] = df['low'].diff().rolling(14).mean()
    df['ADX'] = (df['plus_di'] + df['minus_di']).abs() / 2

    return df

# ========== NEW SIGNAL FUNCTIONS ==========
def get_raw_indicator_signals(df):
    """Calculates raw signals (+1/-1/0) for each indicator."""
    if len(df) < 2:  # Cần ít nhất 2 nến để so sánh
        return {}
        
    current_signals = {}
    current = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else current
    
    # RSI: Tín hiệu mua khi quá bán (< 30), tín hiệu bán khi quá mua (> 70)
    rsi_value = current['RSI'] if pd.notna(current['RSI']) else 50
    if rsi_value < 20 or 60 < rsi_value < 80:
        current_signals["RSI"] = 1
    elif rsi_value > 80 or 20 < rsi_value < 40:
        current_signals["RSI"] = -1
    else:
        current_signals["RSI"] = 0

    # MACD: MACD line > signal line là tăng
    if pd.notna(current['MACD']) and pd.notna(current['MACD_Signal']):
        if current['MACD'] > current['MACD_Signal']:
            current_signals["MACD"] = 1
        else:
            current_signals["MACD"] = -1
    else:
        current_signals["MACD"] = 0

    # EMA Crossover: EMA9 > EMA21 là tăng
    if pd.notna(current['EMA9']) and pd.notna(current['EMA21']):
        if current['EMA9'] > current['EMA21']:
            current_signals["EMA_Crossover"] = 1
        else:
            current_signals["EMA_Crossover"] = -1
    else:
        current_signals["EMA_Crossover"] = 0

    # Volume Confirmation: Nến tăng + volume cao là tăng
    if pd.notna(current['volume']) and pd.notna(current['volume_sma']):
        volume_condition = current['volume'] > current['volume_sma'] * 1.5
        if current['close'] > current['open'] and volume_condition:
            current_signals["Volume_Confirmation"] = 1
        elif current['close'] < current['open'] and volume_condition:
            current_signals["Volume_Confirmation"] = -1
        else:
            current_signals["Volume_Confirmation"] = 0
    else:
        current_signals["Volume_Confirmation"] = 0

    # Stochastic Oscillator: K line > D line
    if pd.notna(current['stoch_k']) and pd.notna(current['stoch_d']):
        if current['stoch_k'] > current['stoch_d']:
            current_signals["Stochastic"] = 1
        else:
            current_signals["Stochastic"] = -1
    else:
        current_signals["Stochastic"] = 0

    # Bollinger Bands: Giá dưới dải dưới là tăng, trên dải trên là giảm
    if pd.notna(current['bollinger_low']) and pd.notna(current['bollinger_high']):
        if current['close'] < current['bollinger_low']:
            current_signals["BollingerBands"] = 1
        elif current['close'] > current['bollinger_high']:
            current_signals["BollingerBands"] = -1
        else:
            current_signals["BollingerBands"] = 0
    else:
        current_signals["BollingerBands"] = 0

    # Ichimoku: Tenkan Sen > Kijun Sen là tín hiệu tăng
    if pd.notna(current['ichimoku_tenkan_sen']) and pd.notna(current['ichimoku_kijun_sen']):
        if current['ichimoku_tenkan_sen'] > current['ichimoku_kijun_sen']:
            current_signals["Ichimoku"] = 1
        else:
            current_signals["Ichimoku"] = -1
    else:
        current_signals["Ichimoku"] = 0

    # ADX: ADX > 25 và (+DI > -DI) là tín hiệu tăng
    if pd.notna(current['ADX']) and pd.notna(current['plus_di']) and pd.notna(current['minus_di']):
        if current['ADX'] > 25 and current['plus_di'] > current['minus_di']:
            current_signals["ADX"] = 1
        elif current['ADX'] > 25 and current['minus_di'] > current['plus_di']:
            current_signals["ADX"] = -1
        else:
            current_signals["ADX"] = 0
    else:
        current_signals["ADX"] = 0
        
    return current_signals

def update_weights_and_stats(current_signals, price_change_percent, indicator_weights, indicator_stats, is_initial_training):
    """
    Dynamically adjusts indicator weights based on their performance on a single candle.
    This function is used for both initial training and real-time learning.
    """
    
    is_price_up = price_change_percent > 0
    is_price_down = price_change_percent < 0
    
    # Giai đoạn huấn luyện ban đầu (điểm số)
    if is_initial_training:
        for indicator, signal in current_signals.items():
            if indicator in indicator_stats:
                if (signal == 1 and is_price_up) or (signal == -1 and is_price_down):
                    indicator_stats[indicator] += 1
                elif (signal == 1 and is_price_down) or (signal == -1 and is_price_up):
                    indicator_stats[indicator] -= 1
    
    # Giai đoạn hoạt động thực tế (tỷ lệ phần trăm)
    else:
        # SỬ DỤNG ĐIỀU CHỈNH CỐ ĐỊNH: 0.5% của tổng 100%
        adjustment_unit = 0.5  # Điều chỉnh 0.5 đơn vị (0.5%) mỗi nến
        for indicator, signal in current_signals.items():
            if indicator in indicator_weights:
                current_weight = indicator_weights[indicator]
                
                # Xác định nếu tín hiệu (signal) trùng với hướng giá (price_up)
                signal_matched_price = (signal == 1 and is_price_up) or \
                                       (signal == -1 and is_price_down)
                
                # --- LOGIC CỘNG/TRỪ CỐ ĐỊNH (Cho phép đảo dấu) ---
                
                # 1. Tín hiệu ĐÚNG: Củng cố (Move W AWAY from 0)
                if (current_weight >= 0 and signal_matched_price) or \
                   (current_weight < 0 and not signal_matched_price):
                    
                    if current_weight >= 0:
                        # W > 0, Đúng -> Tăng (Dương hơn)
                        indicator_weights[indicator] += adjustment_unit
                    else:
                        # W < 0, Đúng (Vai trò nghịch) -> Giảm (Âm sâu hơn)
                        indicator_weights[indicator] -= adjustment_unit

                # 2. Tín hiệu SAI: Suy yếu (Move W TOWARDS 0, hoặc đảo dấu)
                else:
                    if current_weight > 0:
                        # W > 0, Sai -> Giảm (Về 0, có thể âm)
                        indicator_weights[indicator] -= adjustment_unit
                    else:
                        # W <= 0, Sai -> Tăng (Về 0, có thể dương)
                        indicator_weights[indicator] += adjustment_unit

        # CHUẨN HÓA LẠI: (Phần này vẫn giữ nguyên logic chuẩn hóa theo tổng |W|)
        total_abs_weight = sum(abs(w) for w in indicator_weights.values())
        if total_abs_weight > 0:
            for indicator in indicator_weights:
                indicator_weights[indicator] = (indicator_weights[indicator] / total_abs_weight) * 100
        else:
            num_indicators = len(indicator_weights)
            if num_indicators > 0:
                for indicator in indicator_weights:
                    indicator_weights[indicator] = 100.0 / num_indicators
    
    # ... (Phần log sau đó giữ nguyên) ...
    logging.info("--- New weights and stats ---")
    if is_initial_training:
        for indicator, score in indicator_stats.items():
            logging.info(f"📊 {indicator}: Score {score}")
    else:
        for indicator, weight in indicator_weights.items():
            logging.info(f"📊 {indicator}: Weight {weight:.2f}%")
        
    return indicator_weights, indicator_stats

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
                logger.error(f"WebSocket message processing error {symbol}: {str(e)}")

        def on_error(ws, error):
            logger.error(f"WebSocket error {symbol}: {str(error)}")
            if not self._stop_event.is_set():
                time.sleep(5)
                self._reconnect(symbol, callback)

        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed {symbol}: {close_status_code} - {close_msg}")
            if not self._stop_event.is_set() and symbol in self.connections:
                time.sleep(5)
                self._reconnect(symbol, callback)

        def on_open(ws):
            logger.info(f"WebSocket connected for {symbol}")

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()

        self.connections[symbol] = {
            'ws': ws,
            'thread': thread,
            'callback': callback
        }
        logger.info(f"WebSocket started for {symbol}")

    def _reconnect(self, symbol, callback):
        logger.info(f"Reconnecting WebSocket for {symbol}")
        self.remove_symbol(symbol)
        time.sleep(2)
        self._create_connection(symbol, callback)

    def remove_symbol(self, symbol):
        symbol = symbol.upper()
        with self._lock:
            if symbol in self.connections:
                try:
                    self.connections[symbol]['ws'].close()
                except Exception as e:
                    logger.error(f"Error closing WebSocket {symbol}: {str(e)}")
                del self.connections[symbol]
                logger.info(f"WebSocket removed for {symbol}")

    def stop(self):
        self._stop_event.set()
        for symbol in list(self.connections.keys()):
            self.remove_symbol(symbol)

# ========== MAIN BOT CLASS ==========
class IndicatorBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, initial_weights=None):
        self.symbol = symbol.upper()
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.ws_manager = ws_manager
        
        # FIX: Sửa lỗi weights từ training
        if initial_weights and isinstance(initial_weights, dict) and self._are_weights_valid(initial_weights):
            self.indicator_weights = initial_weights
            weights_info = " | ".join([f"{k}:{v:.1f}%" for k, v in initial_weights.items()])
            if all(w < 0 for w in initial_weights.values()):
                self.log(f"⚠️ Tất cả weights âm từ training 200 nến: {weights_info}")
            else:
                self.log(f"✅ Sử dụng weights từ training 200 nến: {weights_info}")
        else:
            self.indicator_weights = self._create_default_weights()
            default_weights_info = " | ".join([f"{k}:{v:.1f}%" for k, v in self.indicator_weights.items()])
            self.log(f"⚠️ Dùng weights mặc định: {default_weights_info}")

        self.indicator_stats = {k: 0 for k in self.indicator_weights.keys()}

        self.check_position_status()
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []

        self._stop = False
        self.signal_threshold = 25
        self.position_open = False
        self.last_trade_time = 0
        self.position_check_interval = 30
        self.last_position_check = 0
        self.last_error_log_time = 0
        self.last_close_time = 0
        self.cooldown_period = 10
        self.max_position_attempts = 3
        self.position_attempt_count = 0
        self.last_candle_timestamp = 0

        # Bắt đầu WebSocket và main loop
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot started for {self.symbol} | Lev: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}%")

    def calculate_roi(self):
        """
        Tính ROI (%) của vị thế hiện tại.
        """
        if not self.position_open or self.entry == 0:
            return 0.0
        
        current_price = self.prices[-1] if self.prices else self.entry
        if self.side == "BUY":
            roi = ((current_price - self.entry) / self.entry) * self.lev * 100
        else:  # SELL
            roi = ((self.entry - current_price) / self.entry) * self.lev * 100
        
        return roi


    def _are_weights_valid(self, weights):
        if not isinstance(weights, dict):
            return False
        if len(weights) == 0:
            return False
        # ✅ Chỉ cần có ít nhất 1 trọng số khác 0 (có thể âm hoặc dương)
        return any(weight != 0 for weight in weights.values())


    def _create_default_weights(self):
        """Tạo trọng số mặc định"""
        default_weights = {
            "RSI": 15.0, "MACD": 15.0, "EMA_Crossover": 15.0, "Volume_Confirmation": 10.0,
            "Stochastic": 15.0, "BollingerBands": 15.0, "Ichimoku": 10.0, "ADX": 5.0
        }
        total = sum(default_weights.values())
        return {k: (v / total) * 100 for k, v in default_weights.items()}

    def log(self, message, is_critical=True):
        """Ghi log và chỉ gửi Telegram nếu là thông báo quan trọng."""
        logger.info(f"[SYSTEM] {message}") 
        if is_critical:
            send_telegram(f"<b>SYSTEM</b>: {message}")

    def _handle_price_update(self, price):
        """Xử lý giá real-time từ WebSocket"""
        if self._stop:
            return
        
        current_time = time.time()
        # Chỉ xử lý nếu có giá mới
        if not self.prices or price != self.prices[-1]:
            self.prices.append(price)
            if len(self.prices) > 100:
                self.prices = self.prices[-100:]
            
            # Kiểm tra TP/SL real-time
            if self.position_open:
                self.check_tp_sl()

    def get_signal(self, df):
        try:
            current_signals = get_raw_indicator_signals(df)
    
            # Tính điểm tổng: tín hiệu * trọng số (có thể âm/dương)
            total_score = 0.0
            for indicator, signal in current_signals.items():
                weight = self.indicator_weights.get(indicator, 0.0)
                total_score += signal * weight
    
            # Chuẩn hóa ngưỡng theo tổng trọng số tuyệt đối
            total_weight_abs = sum(abs(w) for w in self.indicator_weights.values())
            threshold = self.signal_threshold * (total_weight_abs / 100.0)
    
            if total_score > threshold:
                return "BUY", current_signals, total_score
            elif total_score < -threshold:
                return "SELL", current_signals, total_score
            return None, current_signals, total_score
    
        except Exception as e:
            self.log(f"get_signal error: {str(e)}")
            return None, None, None

    def _run(self):
        """Main loop với xử lý nến 1 phút và học liên tục"""
        self.log("🔍 Starting main loop with 1-minute candle processing...")
        
        while not self._stop:
            try:
                current_time = time.time()
                
                # Kiểm tra vị trí mỗi 30 giây
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                    
                # Lấy dữ liệu nến 1 phút
                df = get_klines(self.symbol, "1m", 100)
                if df.empty or len(df) < 50:
                    time.sleep(2)
                    continue

                # Thêm chỉ báo kỹ thuật
                df = add_technical_indicators(df)
                
                # Kiểm tra dữ liệu hợp lệ
                if df.iloc[-1].isnull().any():
                    time.sleep(1)
                    continue
                    
                # Phát hiện nến mới bằng timestamp
                latest_candle_timestamp = df['close_time'].iloc[-1] / 1000  # Chuyển sang seconds
                
                if latest_candle_timestamp > self.last_candle_timestamp:
                    self.last_candle_timestamp = latest_candle_timestamp
                    
                    # Tính biến động giá và tín hiệu
                    price_change_percent = ((df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1]) * 100
                    current_signals = get_raw_indicator_signals(df)
                    
                    # HỌC LIÊN TỤC TỪ DỮ LIỆU MỚI
                    self.indicator_weights, _ = update_weights_and_stats(
                        current_signals, price_change_percent, self.indicator_weights, self.indicator_stats, False
                    )
                    
                    # Kiểm tra tín hiệu giao dịch
                    signal, current_signals, total_score = self.get_signal(df)
                    
                    # Log thông tin tín hiệu
                    if signal:
                        self.log(f"📊 Signal: {signal}, Score: {total_score:.2f}", is_critical=False)
                    
                    # FIX: Xử lý đảo chiều ĐÚNG CÁCH
                    if self.position_open:
                        if (self.side == "BUY" and signal == "SELL"):
                            # Đóng lệnh hiện tại trước, KHÔNG mở lệnh mới ngay
                            roi = self.calculate_roi()  # hàm có sẵn trong bot
                            if roi < 0 and roi != -5000 and roi != 5000:
                                self.close_position(f"🔄 Đảo chiều: {self.side} → {signal} | ROI hiện tại: {roi:.2f}%")
                                # Lệnh mới sẽ được mở ở vòng loop tiếp theo sau khi đóng hoàn tất
                        if (self.side == "SELL" and signal == "BUY"):
                            # Đóng lệnh hiện tại trước, KHÔNG mở lệnh mới ngay
                            roi = self.calculate_roi()  # hàm có sẵn trong bot
                            if (roi < -300 or roi > 10) and roi != -5000 and roi != 5000:
                                self.close_position(f"🔄 Đảo chiều: {self.side} → {signal} | ROI hiện tại: {roi:.2f}%")
                                # Lệnh mới sẽ được mở ở vòng loop tiếp theo sau khi đóng hoàn tất
                        else:
                            self.check_tp_sl()  # Kiểm tra TP/SL
                    else:
                        # Vào lệnh mới nếu có tín hiệu
                        if signal and current_time - self.last_trade_time > self.cooldown_period:
                            self.open_position(signal, current_signals)
                            self.last_trade_time = current_time
                        
                time.sleep(5)  # Sleep ngắn để phản ứng nhanh
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 30:
                    self.log(f"❌ Main loop error: {str(e)}", is_critical=False)
                    self.last_error_log_time = time.time()
                time.sleep(10)

    def stop(self):
        self._stop = True
        self.ws_manager.remove_symbol(self.symbol)
        try:
            cancel_all_orders(self.symbol)
        except Exception as e:
            self.log(f"Order cancellation error: {str(e)}")
        self.log(f"🔴 Bot stopped for {self.symbol}")

    def check_position_status(self):
        try:
            positions = get_positions(self.symbol)
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
            if time.time() - self.last_error_log_time > 30:
                self.log(f"Position check error: {str(e)}")
                self.last_error_log_time = time.time()

    def check_tp_sl(self):
        if not self.position_open or not self.entry or not self.qty:
            return
            
        try:
            current_price = self.prices[-1] if self.prices else get_current_price(self.symbol)
            if current_price <= 0:
                return
                
            if self.side == "BUY":
                profit = (current_price - self.entry) * abs(self.qty)
            else:  # SELL
                profit = (self.entry - current_price) * abs(self.qty)
                
            invested = self.entry * abs(self.qty) / self.lev
            if invested <= 0:
                return
                
            roi = (profit / invested) * 100
            
            if roi >= self.tp:
                self.close_position(f"✅ TP hit at {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl is not None and roi <= -self.sl:
                self.close_position(f"❌ SL hit at {self.sl}% (ROI: {roi:.2f}%)")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"TP/SL check error: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side, current_indicators=None):
        self.check_position_status()
        if self.position_open:
            self.log("⚠️ Position already open, skipping")
            return
            
        try:
            # Hủy tất cả orders cũ
            cancel_all_orders(self.symbol)
            
            # Set leverage
            if not set_leverage(self.symbol, self.lev):
                self.log(f"❌ Could not set leverage to {self.lev}")
                return
                
            # Tính số lượng
            balance = get_balance()
            if balance <= 0:
                self.log("❌ Insufficient USDT balance")
                return
                
            usdt_amount = balance * (min(max(self.percent, 1), 100) / 100)
            price = get_current_price(self.symbol)
            if price <= 0:
                self.log("❌ Error getting price")
                return
                
            step = get_step_size(self.symbol)
            if step <= 0:
                step = 0.001
                
            qty = (usdt_amount * self.lev) / price
            if step > 0:
                qty = math.floor(qty / step) * step
                
            qty = max(qty, step)  # Đảm bảo không nhỏ hơn step size
            qty = round(qty, 8)
            
            if qty < step:
                self.log(f"⚠️ Quantity too small: {qty} < {step}")
                return
                
            # Đặt lệnh
            res = place_order(self.symbol, side, qty)
            if not res:
                self.log("❌ Error placing order")
                return
                
            executed_qty = float(res.get('executedQty', 0))
            if executed_qty < 0:
                self.log(f"❌ Order not filled: {executed_qty}")
                return
                
            # Cập nhật trạng thái
            self.entry = float(res.get('avgPrice', price))
            self.side = side
            self.qty = executed_qty if side == "BUY" else -executed_qty
            self.status = "open"
            self.position_open = True
            self.position_attempt_count = 0

            # Gửi thông báo
            # Gửi thông báo VÀ IN LOG CHỈ BÁO CHI TIẾT
            indicator_info = "Không đủ dữ liệu chỉ báo."
            total_score = 0.0
            
            if current_indicators:
                indicator_info = "Phân tích tín hiệu:\n"
                
                for indicator, status in current_indicators.items():
                    weight = self.indicator_weights.get(indicator, 0)
                    score_contribution = status * weight
                    total_score += score_contribution
                    
                    sign_text = "🟢 Tăng" if status == 1 else "🔴 Giảm" if status == -1 else "⚪ Trung lập"
                    
                    # Xác định màu sắc/biểu tượng dựa trên đóng góp vào tín hiệu cuối cùng
                    if score_contribution > 0:
                        color_tag = "✅"
                    elif score_contribution < 0:
                        color_tag = "❌"
                    else:
                        color_tag = "⚪"
                    
                    indicator_info += (f"{color_tag} {indicator}: Trọng số **{weight:+.1f}%** "
                                       f"(Tín hiệu: {sign_text}, Score: {score_contribution:+.2f})\n")

            message = (f"✅ <b>POSITION OPENED {self.symbol}</b>\n"
                       f"📌 Direction: {side}\n"
                       f"🏷️ Entry Price: {self.entry:.4f}\n"
                       f"📊 Quantity: {executed_qty}\n"
                       f"💵 Value: {executed_qty * self.entry:.2f} USDT\n"
                       f" Leverage: {self.lev}x\n"
                       f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%\n"
                       f"🔥 **TOTAL SCORE: {total_score:+.2f}**\n\n"
                       f"{indicator_info}")
            
            # Gửi Telegram (is_critical=True là mặc định)
            self.log(message, is_critical=True)
            
        except Exception as e:
            self.position_open = False
            self.log(f"❌ Error entering position: {str(e)}")

    def close_position(self, reason=""):
        # Lấy logic đóng lệnh từ file 42: Đóng vị thế với số lượng chính xác
        try:
            cancel_all_orders(self.symbol)
            if abs(self.qty) > 0:
                close_side = "SELL" if self.side == "BUY" else "BUY"
                close_qty = abs(self.qty)
                
                # Làm tròn số lượng CHÍNH XÁC
                step = get_step_size(self.symbol)
                if step > 0:
                    # Tính toán chính xác số bước
                    steps = close_qty / step
                    # Làm tròn đến số nguyên gần nhất
                    close_qty = round(steps) * step
                
                close_qty = max(close_qty, 0)
                close_qty = round(close_qty, 8)
                
                res = place_order(self.symbol, close_side, close_qty)
                if res:
                    price = float(res.get('avgPrice', 0))
                    
                    # Tính ROI cho thông báo đóng lệnh (dùng hàm đã có trong 43)
                    roi = self.calculate_roi() 

                    message = (f"⛔ <b>POSITION CLOSED {self.symbol}</b>\n"
                              f"📌 Reason: {reason}\n"
                              f"🏷️ Exit Price: {price:.4f}\n"
                              f"📊 Quantity: {close_qty}\n"
                              f"💵 Value: {close_qty * price:.2f} USDT\n"
                              f"🔥 ROI: {roi:.2f}%") # Thêm ROI vào thông báo
                    self.log(message)
                    
                    # Cập nhật trạng thái NGAY LẬP TỨC (quan trọng)
                    self.status = "waiting"
                    self.side = ""
                    self.qty = 0
                    self.entry = 0
                    self.position_open = False
                    self.last_trade_time = time.time()
                    self.last_close_time = time.time()
                else:
                    self.log("❌ Error closing position")
        except Exception as e:
            self.log(f"❌ Error closing position: {str(e)}")

# ========== BOT MANAGER ==========
class BotManager:
    def __init__(self):
        self.ws_manager = WebSocketManager()
        self.bots = {}
        self.running = True
        self.start_time = time.time()
        self.user_states = {}
        self.admin_chat_id = TELEGRAM_CHAT_ID
        self.log("🟢 BOT SYSTEM STARTED")
        self.status_thread = threading.Thread(target=self._status_monitor, daemon=True)
        self.status_thread.start()
        self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
        self.telegram_thread.start()
        if self.admin_chat_id:
            self.send_main_menu(self.admin_chat_id)

    def log(self, message, is_critical=True):
        """Ghi log và chỉ gửi Telegram nếu là thông báo quan trọng."""
        logger.info(f"[SYSTEM] {message}") 
        if is_critical:
            send_telegram(f"<b>SYSTEM</b>: {message}")

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BINANCE FUTURES TRADING BOT</b>\n\nChoose an option below:"
        send_telegram(welcome, chat_id, create_menu_keyboard())

    def add_bot(self, symbol, lev, percent, tp, sl, initial_weights=None):
        if sl == 0:
            sl = None
        symbol = symbol.upper()
        if symbol in self.bots:
            self.log(f"⚠️ Bot already exists for {symbol}")
            return False
            
        if not API_KEY or not API_SECRET:
            self.log("❌ API Key and Secret Key not configured!")
            return False
            
        try:
            # Kiểm tra symbol có tồn tại
            price = get_current_price(symbol)
            if price <= 0:
                self.log(f"❌ Cannot get price for {symbol}")
                return False
                
            # Tạo bot
            bot = IndicatorBot(symbol, lev, percent, tp, sl, self.ws_manager, initial_weights)
            self.bots[symbol] = bot
            self.log(f"✅ Bot added: {symbol} | Lev: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}%")
            return True
            
        except Exception as e:
            self.log(f"❌ Error creating bot {symbol}: {str(e)}")
            return False

    def stop_bot(self, symbol):
        symbol = symbol.upper()
        bot = self.bots.get(symbol)
        if bot:
            bot.stop()
            if bot.status == "open":
                bot.close_position("⛔ Manual bot stop")
            self.log(f"⛔ Bot stopped for {symbol}")
            del self.bots[symbol]
            return True
        return False

    def stop_all(self):
        self.log("⛔ Stopping all bots...")
        for symbol in list(self.bots.keys()):
            self.stop_bot(symbol)
        self.ws_manager.stop()
        self.running = False
        self.log("🔴 System stopped")

    def _status_monitor(self):
        while self.running:
            try:
                uptime = time.time() - self.start_time
                hours, rem = divmod(uptime, 3600)
                minutes, seconds = divmod(rem, 60)
                uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                active_bots = [s for s, b in self.bots.items() if not b._stop]
                balance = get_balance()
                
                status_msg = (f"📊 <b>SYSTEM STATUS</b>\n"
                             f"⏱ Uptime: {uptime_str}\n"
                             f"🤖 Active Bots: {len(active_bots)}\n"
                             f"📈 Active Pairs: {', '.join(active_bots) if active_bots else 'None'}\n"
                             f"💰 Available Balance: {balance:.2f} USDT")
                send_telegram(status_msg)
                
            except Exception as e:
                logger.error(f"Status report error: {str(e)}")
            time.sleep(6 * 3600)  # 6 hours

    def _telegram_listener(self):
        last_update_id = 0
        while self.running:
            try:
                if not TELEGRAM_BOT_TOKEN:
                    time.sleep(60)
                    continue
                    
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id+1}&timeout=30"
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
                    logger.error("Conflict error: Only one bot instance can listen to Telegram")
                    time.sleep(60)
                else:
                    time.sleep(10)
                    
            except Exception as e:
                logger.error(f"Telegram listener error: {str(e)}")
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        if current_step == 'waiting_symbol':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                symbol = text.upper()
                self.user_states[chat_id] = {'step': 'waiting_leverage', 'symbol': symbol}
                send_telegram(f"Choose leverage for {symbol}:", chat_id, create_leverage_keyboard())
                
        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            elif 'x' in text:
                leverage = int(text.replace('', '').replace('x', '').strip())
                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                send_telegram(f"Enter % of balance to use (1-100):", chat_id, create_cancel_keyboard())
                
        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    percent = float(text)
                    if 1 <= percent <= 100:
                        user_state['percent'] = percent
                        user_state['step'] = 'waiting_tp'
                        send_telegram(f"Enter % Take Profit (e.g., 10):", chat_id, create_cancel_keyboard())
                    else:
                        send_telegram("⚠️ Please enter a % from 1-100", chat_id)
                except Exception:
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)
                    
        elif current_step == 'waiting_tp':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    tp = float(text)
                    if tp > 0:
                        user_state['tp'] = tp
                        user_state['step'] = 'waiting_sl'
                        send_telegram(f"Enter % Stop Loss (e.g., 5, 0 for no SL):", chat_id, create_cancel_keyboard())
                    else:
                        send_telegram("⚠️ TP must be greater than 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)
                    
        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    sl = float(text)
                    if sl >= 0:
                        symbol = user_state['symbol']
                        leverage = user_state['leverage']
                        percent = user_state['percent']
                        tp = user_state['tp']
        
                        # ✅ Training 200 nến trước khi tạo bot
                        try:
                            temp_config = [symbol, leverage, percent, tp, sl]
                            perform_initial_training(self, [temp_config])  # training cho 1 symbol
                            initial_weights = temp_config[5]
                        except Exception as e:
                            send_telegram(f"❌ Training thất bại cho {symbol}: {str(e)}", chat_id, create_menu_keyboard())
                            self.user_states[chat_id] = {}
                            return
        
                        # ✅ Chỉ tạo bot nếu training thành công
                        if initial_weights and self.add_bot(symbol, leverage, percent, tp, sl, initial_weights):
                            send_telegram(
                                f"✅ <b>BOT ADDED SUCCESSFULLY</b>\n\n"
                                f"📌 Pair: {symbol}\n"
                                f" Leverage: {leverage}x\n"
                                f"📊 % Balance: {percent}%\n"
                                f"🎯 TP: {tp}%\n"
                                f"🛡️ SL: {sl}%",
                                chat_id,
                                create_menu_keyboard()
                            )
                        else:
                            send_telegram("❌ Could not add bot (training failed)", chat_id, create_menu_keyboard())
                        
                        self.user_states[chat_id] = {}
                    else:
                        send_telegram("⚠️ SL must be greater than or equal to 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Invalid value, please enter a number", chat_id)

                    
        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 No bots are currently running", chat_id)
            else:
                message = "🤖 <b>LIST OF RUNNING BOTS</b>\n\n"
                for symbol, bot in self.bots.items():
                    status = "🟢 Open" if bot.status == "open" else "🟡 Waiting"
                    message += f"🔹 {symbol} | {status} | {bot.side} | Lev: {bot.lev}x\n"
                send_telegram(message, chat_id)
                
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_symbol'}
            send_telegram("Choose a coin pair:", chat_id, create_symbols_keyboard())
            
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 No bots are currently running", chat_id)
            else:
                message = "⛔ <b>CHOOSE BOT TO STOP</b>\n\n"
                keyboard = []
                row = []
                for i, symbol in enumerate(self.bots.keys()):
                    message += f"🔹 {symbol}\n"
                    row.append({"text": f"⛔ {symbol}"})
                    if len(row) == 2 or i == len(self.bots) - 1:
                        keyboard.append(row)
                        row = []
                keyboard.append([{"text": "❌ Hủy bỏ"}])
                send_telegram(message, chat_id, {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True})
                
        elif text.startswith("⛔ "):
            symbol = text.replace("⛔ ", "").strip().upper()
            if symbol in self.bots:
                self.stop_bot(symbol)
                send_telegram(f"⛔ Stop command sent for bot {symbol}", chat_id, create_menu_keyboard())
            else:
                send_telegram(f"⚠️ Bot not found {symbol}", chat_id, create_menu_keyboard())
                
        elif text == "💰 Số dư tài khoản":
            try:
                balance = get_balance()
                send_telegram(f"💰 <b>AVAILABLE BALANCE</b>: {balance:.2f} USDT", chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Error getting balance: {str(e)}", chat_id)
                
        elif text == "📈 Vị thế đang mở":
            try:
                positions = get_positions()
                if not positions:
                    send_telegram("📭 No open positions", chat_id)
                    return
                message = "📈 <b>OPEN POSITIONS</b>\n\n"
                for pos in positions:
                    position_amt = float(pos.get('positionAmt', 0))
                    if position_amt != 0:
                        symbol = pos.get('symbol', 'UNKNOWN')
                        entry = float(pos.get('entryPrice', 0))
                        side = "LONG" if position_amt > 0 else "SHORT"
                        pnl = float(pos.get('unRealizedProfit', 0))
                        message += (f"🔹 {symbol} | {side}\n"
                                  f"📊 Quantity: {abs(position_amt):.4f}\n"
                                  f"🏷️ Entry Price: {entry:.4f}\n"
                                  f"💰 PnL: {pnl:.2f} USDT\n\n")
                send_telegram(message, chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Error getting positions: {str(e)}", chat_id)
        elif text:
            self.send_main_menu(chat_id)

# ========== FUNCTIONS FOR INITIAL TRAINING ==========
def perform_initial_training(manager, bot_configs):
    """
    Performs initial training on historical data for all bot configurations.
    Sử dụng 200 nến lịch sử để huấn luyện ban đầu.
    """
    if not bot_configs:
        manager.log("⚠️ No bot configurations found for training.")
        return

    manager.log("⏳ Starting initial training on 200 candles historical data...")

    for config in bot_configs:
        try:
            symbol = config[0]

            # Khởi tạo điểm số cho từng chỉ báo
            indicator_stats = {
                "RSI": 0, "MACD": 0, "EMA_Crossover": 0, "Volume_Confirmation": 0,
                "Stochastic": 0, "BollingerBands": 0, "Ichimoku": 0, "ADX": 0,
            }

            # Lấy 200 nến lịch sử để huấn luyện
            df_history = get_klines(symbol, '1m', 200)

            if not df_history.empty and len(df_history) >= 100:
                manager.log(f"🚀 Training {symbol} with {len(df_history)} candles...")

                # ✅ Tính indicators cho toàn bộ 200 nến một lần duy nhất
                df_history = add_technical_indicators(df_history)

                # Huấn luyện trên từng nến (bắt đầu từ nến 50 cho an toàn)
                for i in range(50, len(df_history) - 1):
                    try:
                        if df_history.iloc[i].isnull().any():
                            continue

                        df_slice = df_history.iloc[:i+1]
                        current_signals = get_raw_indicator_signals(df_slice)

                        current_close = df_history['close'].iloc[i]
                        next_open = df_history['open'].iloc[i+1]
                        price_change_percent = ((next_open - current_close) / current_close) * 100

                        is_price_up = price_change_percent > 0
                        is_price_down = price_change_percent < 0

                        # Cập nhật điểm: đúng +1, sai -1
                        for indicator, signal in current_signals.items():
                            if indicator in indicator_stats:
                                if (signal == 1 and is_price_up) or (signal == -1 and is_price_down):
                                    indicator_stats[indicator] += 1
                                elif (signal == 1 and is_price_down) or (signal == -1 and is_price_up):
                                    indicator_stats[indicator] -= 1

                    except Exception:
                        continue

                # ✅ Dùng tổng score có dấu để tạo trọng số
                total_abs_score = sum(abs(score) for score in indicator_stats.values())

                if total_abs_score > 0:
                    # Trọng số CÓ DẤU (có thể âm)
                    indicator_weights = {
                        ind: (score / total_abs_score) * 100
                        for ind, score in indicator_stats.items()
                    }
                else:
                    # Nếu tất cả score đều bằng 0, dùng trọng số mặc định dương
                    num_indicators = len(indicator_stats)
                    indicator_weights = {ind: 100.0 / num_indicators for ind in indicator_stats.keys()}

                # Lưu weights vào config
                if len(config) == 5:
                    config.append(indicator_weights)
                elif len(config) > 5:
                    config[5] = indicator_weights
                else:
                    while len(config) < 5:
                        config.append(None)
                    config.append(indicator_weights)

                # Log kết quả
                score_info = " | ".join([f"{k}: {v:+d}" for k, v in indicator_stats.items()])
                weight_info = " | ".join([f"{k}: {v:.1f}%" for k, v in indicator_weights.items()])

                manager.log(f"✅ Training completed for {symbol}")
                manager.log(f"📊 Scores: {score_info}")
                manager.log(f"🎯 Weights: {weight_info}")

            else:
                manager.log(f"❌ Not enough data for {symbol} (got {len(df_history)} candles)")
                if len(config) == 5:
                    config.append(None)

        except Exception as e:
            manager.log(f"❌ Training error for {symbol}: {str(e)}")
            if len(config) == 5:
                config.append(None)

# ========== MAIN FUNCTION ==========
def main():
    manager = BotManager()

    # Huấn luyện ban đầu với 200 nến
    if BOT_CONFIGS:
        perform_initial_training(manager, BOT_CONFIGS)
        
        # DEBUG: Kiểm tra kết quả training
        manager.log("🔍 KIỂM TRA KẾT QUẢ TRAINING:")
        for i, config in enumerate(BOT_CONFIGS):
            if len(config) > 5 and config[5] is not None:
                manager.log(f"✅ Config {i}: {config[0]} - Có weights từ training")
            else:
                manager.log(f"❌ Config {i}: {config[0]} - KHÔNG có weights từ training")
        
        for config in BOT_CONFIGS:
            if len(config) >= 5:
                symbol, lev, percent, tp, sl = config[0], config[1], config[2], config[3], config[4]
                
                # FIX: Lấy weights từ index 5 (sau training)
                initial_weights = config[5] if len(config) > 5 and config[5] is not None else None
                
                if manager.add_bot(symbol, lev, percent, tp, sl, initial_weights):
                    manager.log(f"✅ Bot for {symbol} started successfully")
                else:
                    manager.log(f"⚠️ Bot for {symbol} failed to start")
    else:
        manager.log("⚠️ No bot configurations found! Please set BOT_CONFIGS environment variable.")

    try:
        balance = get_balance()
        manager.log(f"💰 INITIAL BALANCE: {balance:.2f} USDT")
    except Exception as e:
        manager.log(f"⚠️ Error getting initial balance: {str(e)}")

    try:
        while manager.running:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.log("👋 Received stop signal...")
    except Exception as e:
        manager.log(f"❌ SYSTEM ERROR: {str(e)}")
    finally:
        manager.stop_all()

if __name__ == "__main__":
    main()













