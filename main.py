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
    """Creates menu with volatility coins button"""
    return {
        "keyboard": [
            [{"text": "📊 Danh sách Bot"}],
            [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
            [{"text": "💰 Số dư tài khoản"}, {"text": "📈 Vị thế đang mở"}],
            [{"text": "🎯 Coin biến động"}]
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

def create_threshold_keyboard():
    """Creates keyboard for selecting volatility threshold"""
    thresholds = ["20", "25", "30", "35", "40", "50"]
    keyboard = []
    row = []
    for thresh in thresholds:
        row.append({"text": f"{thresh}%"})
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

# ========== 24H VOLATILITY FUNCTIONS ==========
def get_24h_ticker_data():
    """Get 24h ticker data for all symbols from Binance"""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting 24h ticker data: {str(e)}")
        return []

def get_24h_change(symbol):
    """Lấy % thay đổi giá 24h cho một symbol"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'priceChangePercent' in data:
            return float(data['priceChangePercent'])
    except Exception as e:
        logger.error(f"Error getting 24h change for {symbol}: {str(e)}")
    return 0

def get_high_volatility_coins(threshold=30):
    """
    Lấy danh sách coin có biến động > threshold% trong 24h
    """
    try:
        tickers = get_24h_ticker_data()
        volatile_coins = []
        
        for ticker in tickers:
            try:
                symbol = ticker['symbol']
                price_change_percent = float(ticker['priceChangePercent'])
                
                # Chỉ lấy các cặp USDT và lọc theo ngưỡng
                if symbol.endswith('USDT') and abs(price_change_percent) >= threshold:
                    volatile_coins.append({
                        'symbol': symbol,
                        'change_percent': price_change_percent,
                        'direction': "UP" if price_change_percent > 0 else "DOWN"
                    })
            except Exception as e:
                logger.error(f"Error processing ticker {ticker.get('symbol', 'unknown')}: {str(e)}")
        
        # Sắp xếp theo biến động giảm dần
        volatile_coins.sort(key=lambda x: abs(x['change_percent']), reverse=True)
        return volatile_coins
        
    except Exception as e:
        logger.error(f"Error getting volatile coins: {str(e)}")
        return []

# ========== SIGNAL FUNCTIONS (LOGIC MỚI THEO YÊU CẦU) ==========
def get_signal(symbol):
    """
    LOGIC MỚI: Tín hiệu dựa trên biến động 24h
    - Tăng >30% -> SELL (kỳ vọng điều chỉnh giảm)
    - Giảm >30% -> BUY (kỳ vọng phục hồi)
    """
    change_24h = get_24h_change(symbol)
    
    if abs(change_24h) >= 30:
        if change_24h > 0:
            return "SELL", change_24h
        else:
            return "BUY", abs(change_24h)
    
    return None, change_24h

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
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager):
        self.symbol = symbol.upper()
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.ws_manager = ws_manager
        
        self.indicator_weights = {} 
        self.indicator_stats = {} 
        
        self.check_position_status()
        self.status = "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = []

        self._stop = False
        self.position_open = False
        self.last_trade_time = 0
        self.position_check_interval = 30
        self.last_position_check = 0
        self.last_error_log_time = 0
        self.last_signal_check = 0
        self.signal_check_interval = 300  # Check for signals every 5 minutes
        self.cooldown_period = 900

        # Start WebSocket and main loop
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot started for {self.symbol} | Lev: {lev}x | %: {percent} | TP/SL: {tp}%/{sl}% | Logic: 24h Reverse")

    def calculate_roi(self):
        """Calculate current ROI of position"""
        if not self.position_open or self.entry == 0:
            return 0.0
        
        current_price = self.prices[-1] if self.prices else self.entry
        if self.side == "BUY":
            roi = ((current_price - self.entry) / self.entry) * self.lev * 100
        else:  # SELL
            roi = ((self.entry - current_price) / self.entry) * self.lev * 100
        
        return roi

    def log(self, message, is_critical=True):
        """Log and send Telegram for important messages"""
        logger.info(f"[{self.symbol}] {message}") 
        if is_critical:
            send_telegram(f"<b>{self.symbol}</b>: {message}")

    def _handle_price_update(self, price):
        """Handle real-time price updates from WebSocket"""
        if self._stop:
            return
        
        if not self.prices or price != self.prices[-1]:
            self.prices.append(price)
            if len(self.prices) > 100:
                self.prices = self.prices[-100:]
            
            # Check real-time TP/SL
            if self.position_open:
                self.check_tp_sl()

    def _run(self):
        """Main loop with 24h volatility checking"""
        self.log("🔍 Starting main loop with 24h volatility monitoring...")
        
        while not self._stop:
            try:
                current_time = time.time()
                
                # Check position status every 30 seconds
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                # Check for trading signals every 5 minutes
                if current_time - self.last_signal_check > self.signal_check_interval:
                    # Only check signal if we don't have an open position
                    if not self.position_open:
                        signal, change_percent = get_signal(self.symbol)
                        
                        if signal:
                            log_msg = f"📈 24h Change: {change_percent:.2f}% | Signal: {signal}"
                            self.log(log_msg, is_critical=False)
                            
                            # Check cooldown period
                            if current_time - self.last_trade_time > self.cooldown_period:
                                self.open_position(signal, change_percent)
                                self.last_trade_time = current_time
                    
                    self.last_signal_check = current_time
                
                # Check TP/SL for open positions
                if self.position_open:
                    self.check_tp_sl()
                
                time.sleep(5)
                
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
                
            roi = self.calculate_roi()
            
            if roi >= self.tp:
                self.close_position(f"✅ TP hit at {self.tp}% (ROI: {roi:.2f}%)")
            elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
                self.close_position(f"❌ SL hit at {self.sl}% (ROI: {roi:.2f}%)")
                
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"TP/SL check error: {str(e)}")
                self.last_error_log_time = time.time()

    def open_position(self, side, change_percent):
        self.check_position_status()
        if self.position_open:
            self.log("⚠️ Position already open, skipping")
            return
            
        try:
            # Cancel all existing orders
            cancel_all_orders(self.symbol)
            
            # Set leverage
            if not set_leverage(self.symbol, self.lev):
                self.log(f"❌ Could not set leverage to {self.lev}")
                return
                
            # Calculate quantity
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
                
            qty = max(qty, step)
            qty = round(qty, 8)
            
            if qty < step:
                self.log(f"⚠️ Quantity too small: {qty} < {step}")
                return
                
            # Place order
            res = place_order(self.symbol, side, qty)
            if not res:
                self.log("❌ Error placing order")
                return
                
            executed_qty = float(res.get('executedQty', 0))
            if executed_qty <= 0:
                self.log(f"❌ Order not filled: {executed_qty}")
                return
                
            # Update status
            self.entry = float(res.get('avgPrice', price))
            self.side = side
            self.qty = executed_qty if side == "BUY" else -executed_qty
            self.status = "open"
            self.position_open = True

            # Send notification with 24h change info
            message = (f"✅ <b>POSITION OPENED {self.symbol}</b>\n"
                       f"📌 Direction: {side}\n"
                       f"🎯 Strategy: Reverse 24h Move\n"
                       f"📈 24h Change: {change_percent:.2f}%\n"
                       f"🏷️ Entry Price: {self.entry:.4f}\n"
                       f"📊 Quantity: {executed_qty}\n"
                       f"💵 Value: {executed_qty * self.entry:.2f} USDT\n"
                       f" Leverage: {self.lev}x\n"
                       f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%")
            
            self.log(message, is_critical=True)
            
        except Exception as e:
            self.position_open = False
            self.log(f"❌ Error entering position: {str(e)}")

    def close_position(self, reason=""):
        try:
            cancel_all_orders(self.symbol)
            if abs(self.qty) > 0:
                close_side = "SELL" if self.side == "BUY" else "BUY"
                close_qty = abs(self.qty)
                
                # Round quantity precisely
                step = get_step_size(self.symbol)
                if step > 0:
                    steps = close_qty / step
                    close_qty = round(steps) * step
                
                close_qty = max(close_qty, 0)
                close_qty = round(close_qty, 8)
                
                res = place_order(self.symbol, close_side, close_qty)
                if res:
                    price = float(res.get('avgPrice', 0))
                    roi = self.calculate_roi()

                    message = (f"⛔ <b>POSITION CLOSED {self.symbol}</b>\n"
                              f"📌 Reason: {reason}\n"
                              f"🏷️ Exit Price: {price:.4f}\n"
                              f"📊 Quantity: {close_qty}\n"
                              f"💵 Value: {close_qty * price:.2f} USDT\n"
                              f"🔥 ROI: {roi:.2f}%")
                    self.log(message)
                    
                    # Update status immediately
                    self.status = "waiting"
                    self.side = ""
                    self.qty = 0
                    self.entry = 0
                    self.position_open = False
                    self.last_trade_time = time.time()
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
        self.log("🟢 BOT SYSTEM STARTED - 24H REVERSE STRATEGY")
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
        welcome = "🤖 <b>BINANCE FUTURES TRADING BOT</b>\n\n🎯 <b>Strategy: Reverse 24h Moves >30%</b>\n\nChoose an option below:"
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
            bot = IndicatorBot(symbol, lev, percent, tp, sl, self.ws_manager)
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
        
        if current_step == 'waiting_threshold':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            elif text.endswith('%'):
                try:
                    threshold = float(text.replace('%', '').strip())
                    if threshold > 0:
                        self.user_states[chat_id] = {'step': 'waiting_leverage', 'threshold': threshold}
                        send_telegram(f"Chọn leverage cho các coin biến động >{threshold}%:", 
                                    chat_id, create_leverage_keyboard())
                    else:
                        send_telegram("⚠️ Ngưỡng phải lớn hơn 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
                
        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            elif 'x' in text:
                leverage = int(text.replace('', '').replace('x', '').strip())
                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                send_telegram(f"Nhập % số dư sử dụng (1-100):", chat_id, create_cancel_keyboard())
                
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
                        send_telegram(f"Nhập % Take Profit (ví dụ: 10):", chat_id, create_cancel_keyboard())
                    else:
                        send_telegram("⚠️ Vui lòng nhập % từ 1-100", chat_id)
                except Exception:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
                    
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
                        send_telegram(f"Nhập % Stop Loss (ví dụ: 5, 0 để tắt SL):", 
                                    chat_id, create_cancel_keyboard())
                    else:
                        send_telegram("⚠️ TP phải lớn hơn 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
                    
        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Bot addition cancelled", chat_id, create_menu_keyboard())
            else:
                try:
                    sl = float(text)
                    if sl >= 0:
                        threshold = user_state['threshold']
                        leverage = user_state['leverage']
                        percent = user_state['percent']
                        tp = user_state['tp']
                        
                        # TÌM VÀ TẠO BOT CHO CÁC COIN BIẾN ĐỘNG
                        volatile_coins = get_high_volatility_coins(threshold)
                        
                        if not volatile_coins:
                            send_telegram(f"❌ Không tìm thấy coin nào biến động >{threshold}%", 
                                        chat_id, create_menu_keyboard())
                            self.user_states[chat_id] = {}
                            return
                        
                        success_count = 0
                        message = f"✅ <b>ĐANG TẠO BOT CHO CÁC COIN BIẾN ĐỘNG >{threshold}%</b>\n\n"
                        
                        for coin in volatile_coins[:100]:  # Giới hạn 10 coin
                            symbol = coin['symbol']
                            change_percent = coin['change_percent']
                            
                            if self.add_bot(symbol, leverage, percent, tp, sl):
                                success_count += 1
                                message += f"🟢 {symbol}: {change_percent:.1f}%\n"
                            else:
                                message += f"🔴 {symbol}: FAILED\n"
                        
                        message += f"\n📊 Tổng số bot được tạo: {success_count}/{len(volatile_coins[:10])}"
                        send_telegram(message, chat_id, create_menu_keyboard())
                        
                        self.user_states[chat_id] = {}
                        
                    else:
                        send_telegram("⚠️ SL phải lớn hơn hoặc bằng 0", chat_id)
                except Exception:
                    send_telegram("⚠️ Giá trị không hợp lệ, vui lòng nhập số", chat_id)
                    
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
            self.user_states[chat_id] = {'step': 'waiting_threshold'}
            send_telegram("Chọn ngưỡng biến động 24h (%):", chat_id, create_threshold_keyboard())
            
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

        elif text == "🎯 Coin biến động":
            try:
                # Mặc định hiển thị coin biến động >30%
                volatile_coins = get_high_volatility_coins(30)
                
                if not volatile_coins:
                    send_telegram("📊 Không có coin nào biến động >30% trong 24h", chat_id)
                else:
                    message = "🎯 <b>COIN BIẾN ĐỘNG >30% (24H)</b>\n\n"
                    
                    for coin in volatile_coins[:20]:  # Hiển thị 15 coin đầu
                        arrow = "🟢" if coin['direction'] == "UP" else "🔴"
                        message += f"{arrow} {coin['symbol']}: {coin['change_percent']:.2f}%\n"
                    
                    if len(volatile_coins) > 15:
                        message += f"\n...và {len(volatile_coins) - 15} coin khác"
                    
                    send_telegram(message, chat_id)
                    
            except Exception as e:
                send_telegram(f"❌ Lỗi khi lấy danh sách coin: {str(e)}", chat_id)
                
        elif text:
            self.send_main_menu(chat_id)

# ========== MAIN FUNCTION ==========
def main():
    manager = BotManager()

    if BOT_CONFIGS:
        for config in BOT_CONFIGS:
            if len(config) >= 5:
                symbol, lev, percent, tp, sl = config[0], config[1], config[2], config[3], config[4]
                
                if manager.add_bot(symbol, lev, percent, tp, sl, initial_weights=None):
                    manager.log(f"✅ Bot for {symbol} started successfully (24H Reverse Strategy)")
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

