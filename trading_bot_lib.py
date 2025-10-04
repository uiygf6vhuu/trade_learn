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

def create_leverage_keyboard(strategy=None):
    if strategy == "Scalping":
        leverages = ["10", "25", "50", "75", "100"]
    elif strategy == "Reverse 24h":
        leverages = ["10", "25", "50", "75", "100"]
    elif strategy == "Safe Grid":
        leverages = ["5", "10", "15", "20", "25"]
    else:
        leverages = ["10", "25", "50", "75", "100"]
    
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

# ========== HÀM TÌM COIN TỰ ĐỘNG ==========
def get_qualified_symbols(api_key, api_secret, strategy_type, leverage, threshold=None, max_candidates=8, final_limit=2):
    """Tìm coin đủ điều kiện theo chiến lược - LOẠI BỎ BTC/ETH MẶC ĐỊNH"""
    try:
        # Kiểm tra API key
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE")
            return []
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return ["ADAUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT"]
        
        qualified_symbols = []
        
        for ticker in data:
            symbol = ticker.get('symbol', '')
            if symbol.endswith('USDT'):
                # LOẠI BỎ BTC VÀ ETH
                if symbol in ['BTCUSDT', 'ETHUSDT']:
                    continue
                    
                price_change = abs(float(ticker.get('priceChangePercent', 0)))
                volume = float(ticker.get('quoteVolume', 0))
                
                # TIÊU CHÍ THEO CHIẾN LƯỢC
                if strategy_type == "Reverse 24h":
                    if price_change >= threshold and volume > 5000000:  # 5M volume
                        qualified_symbols.append((symbol, price_change))
                        
                elif strategy_type == "Scalping":
                    if price_change >= 3.0 and volume > 10000000:  # 3% biến động, 10M volume
                        qualified_symbols.append((symbol, price_change))
                        
                elif strategy_type == "Safe Grid":
                    if 1.0 <= price_change <= 5.0 and volume > 2000000:  # Biến động vừa, 2M volume
                        qualified_symbols.append((symbol, price_change))
        
        # Sắp xếp theo biến động giảm dần
        qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        
        # Lấy top symbols và kiểm tra đòn bẩy
        final_symbols = []
        for symbol, change in qualified_symbols[:max_candidates]:
            if len(final_symbols) >= final_limit:
                break
                
            try:
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                if leverage_success:
                    final_symbols.append(symbol)
                    logger.info(f"✅ {symbol}: phù hợp {strategy_type} - biến động {change:.1f}%")
                time.sleep(0.1)
            except:
                continue
        
        # Nếu không đủ, thêm coin dự phòng
        backup_symbols = ["ADAUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT", "ATOMUSDT", "AVAXUSDT"]
        for symbol in backup_symbols:
            if len(final_symbols) < final_limit and symbol not in final_symbols:
                try:
                    leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                    if leverage_success:
                        final_symbols.append(symbol)
                except:
                    continue
        
        logger.info(f"🎯 {strategy_type}: tìm thấy {len(final_symbols)} coin")
        return final_symbols[:final_limit]
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin {strategy_type}: {str(e)}")
        return ["ADAUSDT", "DOTUSDT"]

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
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except urllib.error.HTTPError as e:
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
        
        # KHỞI TẠO BIẾN QUAN TRỌNG
        self.last_signal_check = 0
        self.last_price = 0
        self.previous_price = 0
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
        
        # COOLDOWN LINH HOẠT THEO CHIẾN LƯỢC
        if strategy_name == "Scalping":
            self.cooldown_period = 60  # 1 phút
        elif strategy_name == "Reverse 24h":
            self.cooldown_period = 300  # 5 phút
        elif strategy_name == "Safe Grid":
            self.cooldown_period = 180  # 3 phút
        else:
            self.cooldown_period = 180  # 3 phút
            
        self.max_position_attempts = 3
        self.position_attempt_count = 0
        
        self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log(f"🟢 Bot {strategy_name} khởi động cho {self.symbol}")

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
                        self.log(f"🎯 Nhận tín hiệu {signal}, đang mở lệnh...")
                        self.open_position(signal)
                        self.last_trade_time = current_time
                        
                if self.position_open and self.status == "open":
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    error_msg = f"❌ Lỗi hệ thống: {str(e)}"
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
                self.log(f"❌ Không thể kết nối Binance")
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
                self.log(f"❌ Lỗi khi đặt lệnh")
                return
                
            executed_qty = float(res.get('executedQty', 0))
            if executed_qty < 0:
                self.log(f"❌ Lệnh không khớp, số lượng thực thi: {executed_qty}")
                return

            self.entry = float(res.get('avgPrice', price))
            self.side = side
            self.qty = executed_qty if side == "BUY" else -executed_qty
            self.status = "open"
            self.position_open = True
            self.position_attempt_count = 0

            message = (
                f"✅ <b>ĐÃ MỞ VỊ THẾ {self.symbol}</b>\n"
                f"🤖 Chiến lược: {self.strategy_name}\n"
                f"📌 Hướng: {side}\n"
                f"🏷️ Giá vào: {self.entry:.4f}\n"
                f"📊 Khối lượng: {executed_qty}\n"
                f"💵 Giá trị: {executed_qty * self.entry:.2f} USDT\n"
                f"💰 Đòn bẩy: {self.lev}x\n"
                f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
            )
            self.log(message)

        except Exception as e:
            self.position_open = False
            error_msg = f"❌ Lỗi khi vào lệnh: {str(e)}"
            self.log(error_msg)

    def close_position(self, reason=""):
        try:
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            
            if abs(self.qty) > 0:
                close_side = "SELL" if self.side == "BUY" else "BUY"
                close_qty = abs(self.qty)
                
                step = get_step_size(self.symbol, self.api_key, self.api_secret)
                if step > 0:
                    steps = close_qty / step
                    close_qty = round(steps) * step
                
                close_qty = max(close_qty, 0)
                close_qty = round(close_qty, 8)
                
                res = place_order(self.symbol, close_side, close_qty, self.api_key, self.api_secret)
                if res:
                    price = float(res.get('avgPrice', 0))
                    message = (
                        f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ {self.symbol}</b>\n"
                        f"🤖 Chiến lược: {self.strategy_name}\n"
                        f"📌 Lý do: {reason}\n"
                        f"🏷️ Giá ra: {price:.4f}\n"
                        f"📊 Khối lượng: {close_qty}\n"
                        f"💵 Giá trị: {close_qty * price:.2f} USDT"
                    )
                    self.log(message)
                    
                    # GỌI CALLBACK KHI ĐÓNG LỆNH
                    if hasattr(self, 'on_position_closed'):
                        self.on_position_closed(self.symbol, reason)
                    
                    self.status = "waiting"
                    self.side = ""
                    self.qty = 0
                    self.entry = 0
                    self.position_open = False
                    self.last_trade_time = time.time()
                    self.last_close_time = time.time()
                else:
                    self.log(f"❌ Lỗi khi đóng lệnh")
        except Exception as e:
            error_msg = f"❌ Lỗi khi đóng lệnh: {str(e)}"
            self.log(error_msg)

# ========== REVERSE 24H BOT ==========
class Reverse24hBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, threshold=30):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Reverse 24h")
        self.threshold = threshold
        self.signal_check_interval = 300  # 5 phút
        self.last_signal_check = 0
        
        # HỆ THỐNG TÌM COIN TỰ ĐỘNG
        self.last_symbol_refresh = 0
        self.symbol_refresh_interval = 300  # 5 phút refresh khi chưa đủ coin
        self.max_symbols = 2  # TỐI ĐA 2 COIN
        self.current_symbols = [] if symbol is None else [symbol]
        self.active_symbols = {}  # Coin đang có vị thế
        self.auto_symbol_mode = symbol is None
        
        # Khởi tạo danh sách coin ngay từ đầu
        if self.auto_symbol_mode:
            self.refresh_qualified_symbols(force_refresh=True)

    def refresh_qualified_symbols(self, force_refresh=False):
        """Làm mới danh sách coin đủ điều kiện - CHỈ TÌM KHI CHƯA ĐỦ 2 COIN"""
        try:
            if not self.auto_symbol_mode:
                return
                
            current_time = time.time()
            
            # Nếu đã đủ coin và không phải force refresh, không cần tìm thêm
            if len(self.current_symbols) >= self.max_symbols and not force_refresh:
                return
                
            # Kiểm tra thời gian refresh
            if not force_refresh and current_time - self.last_symbol_refresh < self.symbol_refresh_interval:
                return
                
            self.log(f"🔄 Đang tìm coin mới đủ điều kiện (ngưỡng: ±{self.threshold}%)...")
            
            # Số lượng coin cần tìm thêm
            needed_symbols = self.max_symbols - len(self.current_symbols)
            
            new_symbols = get_qualified_symbols(
                self.api_key, self.api_secret,
                strategy_type="Reverse 24h",
                leverage=self.lev,
                threshold=self.threshold,
                final_limit=needed_symbols
            )
            
            if new_symbols:
                # Thêm coin mới vào danh sách (không vượt quá max_symbols)
                for symbol in new_symbols:
                    if len(self.current_symbols) < self.max_symbols and symbol not in self.current_symbols:
                        self.current_symbols.append(symbol)
                        self.log(f"✅ Thêm coin mới: {symbol}")
                
                self.log(f"📊 Danh sách coin hiện tại: {', '.join(self.current_symbols)}")
                self.last_symbol_refresh = current_time
                
            else:
                self.log(f"⚠️ Không tìm thấy coin nào đủ điều kiện")
                
        except Exception as e:
            self.log(f"❌ Lỗi refresh symbol: {str(e)}")

    def on_position_closed(self, symbol, reason=""):
        """Callback khi một vị thế được đóng - TÌM COIN THAY THẾ NGAY"""
        try:
            # Xóa symbol khỏi active symbols
            if symbol in self.active_symbols:
                del self.active_symbols[symbol]
                self.log(f"🗑️ Đã xóa {symbol} khỏi danh sách active")
            
            # Xóa symbol khỏi current symbols để tìm coin mới
            if symbol in self.current_symbols:
                self.current_symbols.remove(symbol)
                self.log(f"🗑️ Đã xóa {symbol} khỏi danh sách hiện tại")
            
            # FORCE REFRESH ngay lập tức để tìm coin thay thế
            self.log(f"🔎 Tìm coin thay thế cho {symbol}...")
            self.refresh_qualified_symbols(force_refresh=True)
            
        except Exception as e:
            self.log(f"❌ Lỗi trong on_position_closed: {str(e)}")

    def get_signal(self):
        current_time = time.time()
        
        # Refresh danh sách coin định kỳ
        self.refresh_qualified_symbols()
        
        if current_time - self.last_signal_check < self.signal_check_interval:
            return None
            
        self.last_signal_check = current_time
        
        try:
            # Nếu không có coin nào, không có tín hiệu
            if not self.current_symbols:
                return None
                
            # Kiểm tra tất cả coin trong danh sách
            for symbol in self.current_symbols:
                # Kiểm tra nếu coin này đã có vị thế
                if symbol in self.active_symbols:
                    continue
                    
                change_24h = get_24h_change(symbol)
                
                if abs(change_24h) >= self.threshold:
                    # Cập nhật symbol hiện tại nếu tìm thấy tín hiệu
                    if symbol != self.symbol:
                        self.symbol = symbol
                        self.log(f"🔄 Chuyển sang coin: {symbol} (Biến động: {change_24h:.2f}%)")
                    
                    # Thêm vào active symbols
                    self.active_symbols[symbol] = "BUY" if change_24h < 0 else "SELL"
                    
                    if change_24h > 0:
                        signal_info = (
                            f"🎯 <b>TÍN HIỆU REVERSE 24H - SELL</b>\n"
                            f"📊 Coin: {symbol}\n"
                            f"📈 Biến động 24h: {change_24h:+.2f}%\n"
                            f"🎯 Ngưỡng kích hoạt: ±{self.threshold}%\n"
                            f"💰 Đòn bẩy: {self.lev}x"
                        )
                        self.log(signal_info)
                        return "SELL"
                    else:
                        signal_info = (
                            f"🎯 <b>TÍN HIỆU REVERSE 24H - BUY</b>\n"
                            f"📊 Coin: {symbol}\n"
                            f"📉 Biến động 24h: {change_24h:+.2f}%\n"
                            f"🎯 Ngưỡng kích hoạt: ±{self.threshold}%\n"
                            f"💰 Đòn bẩy: {self.lev}x"
                        )
                        self.log(signal_info)
                        return "BUY"
            
            self.log(f"➖ Không có tín hiệu - Đang theo dõi {len(self.current_symbols)} coin")
            return None
            
        except Exception as e:
            error_msg = f"❌ Lỗi tín hiệu Reverse 24h: {str(e)}"
            self.log(error_msg)
            return None

# ========== SCALPING BOT ==========
class ScalpingBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Scalping")
        
        # CẤU HÌNH SCALPING
        self.last_scalp_time = 0
        self.scalp_cooldown = 60  # 1 phút
        self.volatility_threshold = 2.0  # Ngưỡng biến động 2%
        
        # HỆ THỐNG TÌM COIN TỰ ĐỘNG
        self.last_symbol_refresh = 0
        self.symbol_refresh_interval = 300  # 5 phút
        self.max_symbols = 2  # TỐI ĐA 2 COIN
        self.current_symbols = [] if symbol is None else [symbol]
        self.active_symbols = {}
        self.auto_symbol_mode = symbol is None
        
        if self.auto_symbol_mode:
            self.refresh_scalping_symbols(force_refresh=True)

    def refresh_scalping_symbols(self, force_refresh=False):
        """Tìm coin phù hợp cho Scalping"""
        try:
            if not self.auto_symbol_mode:
                return
                
            current_time = time.time()
            
            if len(self.current_symbols) >= self.max_symbols and not force_refresh:
                return
                
            if not force_refresh and current_time - self.last_symbol_refresh < self.symbol_refresh_interval:
                return
                
            self.log(f"🔄 Đang tìm coin Scalping (biến động ≥{self.volatility_threshold}%)...")
            
            needed_symbols = self.max_symbols - len(self.current_symbols)
            
            new_symbols = get_qualified_symbols(
                self.api_key, self.api_secret,
                strategy_type="Scalping",
                leverage=self.lev,
                final_limit=needed_symbols
            )
            
            if new_symbols:
                for symbol in new_symbols:
                    if len(self.current_symbols) < self.max_symbols and symbol not in self.current_symbols:
                        self.current_symbols.append(symbol)
                        self.log(f"✅ Thêm coin Scalping: {symbol}")
                
                self.log(f"📊 Danh sách coin Scalping: {', '.join(self.current_symbols)}")
                self.last_symbol_refresh = current_time
            else:
                self.log(f"⚠️ Không tìm thấy coin Scalping nào")
                
        except Exception as e:
            self.log(f"❌ Lỗi refresh Scalping symbol: {str(e)}")

    def on_position_closed(self, symbol, reason=""):
        """Callback khi đóng lệnh - tìm coin thay thế"""
        try:
            if symbol in self.active_symbols:
                del self.active_symbols[symbol]
            if symbol in self.current_symbols:
                self.current_symbols.remove(symbol)
            
            self.log(f"🔎 Tìm coin Scalping thay thế cho {symbol}...")
            self.refresh_scalping_symbols(force_refresh=True)
            
        except Exception as e:
            self.log(f"❌ Lỗi trong on_position_closed Scalping: {str(e)}")

    def get_signal(self):
        current_time = time.time()
        
        self.refresh_scalping_symbols()
        
        if current_time - self.last_scalp_time < self.scalp_cooldown:
            return None
            
        if not self.current_symbols:
            return None
            
        try:
            for symbol in self.current_symbols:
                if symbol in self.active_symbols:
                    continue
                    
                # Logic Scalping đơn giản - biến động nhanh
                price_data = self.get_recent_prices(symbol)
                if len(price_data) < 10:
                    continue
                    
                price_change = ((price_data[-1] - price_data[0]) / price_data[0]) * 100
                
                if abs(price_change) > self.volatility_threshold:
                    if symbol != self.symbol:
                        self.symbol = symbol
                        self.log(f"🔄 Chuyển sang coin Scalping: {symbol}")
                    
                    self.active_symbols[symbol] = "SELL" if price_change > 0 else "BUY"
                    self.last_scalp_time = current_time
                    
                    if price_change > 0:
                        self.log(f"⚡ Tín hiệu Scalping SELL - Biến động: {price_change:.2f}%")
                        return "SELL"
                    else:
                        self.log(f"⚡ Tín hiệu Scalping BUY - Biến động: {price_change:.2f}%")
                        return "BUY"
                        
            return None
            
        except Exception as e:
            self.log(f"❌ Lỗi tín hiệu Scalping: {str(e)}")
            return None

    def get_recent_prices(self, symbol, limit=10):
        """Lấy giá gần đây cho coin"""
        try:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit={limit}"
            data = binance_api_request(url)
            if data:
                return [float(k[4]) for k in data]  # Close prices
        except:
            pass
        return []

# ========== SAFE GRID BOT ==========
class SafeGridBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Safe Grid")
        
        # CẤU HÌNH SAFE GRID
        self.grid_levels = 3
        self.orders_placed = 0
        
        # HỆ THỐNG TÌM COIN TỰ ĐỘNG
        self.last_symbol_refresh = 0
        self.symbol_refresh_interval = 300  # 5 phút
        self.max_symbols = 2  # TỐI ĐA 2 COIN
        self.current_symbols = [] if symbol is None else [symbol]
        self.active_symbols = {}
        self.auto_symbol_mode = symbol is None
        
        if self.auto_symbol_mode:
            self.refresh_safegrid_symbols(force_refresh=True)

    def refresh_safegrid_symbols(self, force_refresh=False):
        """Tìm coin phù hợp cho Safe Grid"""
        try:
            if not self.auto_symbol_mode:
                return
                
            current_time = time.time()
            
            if len(self.current_symbols) >= self.max_symbols and not force_refresh:
                return
                
            if not force_refresh and current_time - self.last_symbol_refresh < self.symbol_refresh_interval:
                return
                
            self.log(f"🔄 Đang tìm coin Safe Grid...")
            
            needed_symbols = self.max_symbols - len(self.current_symbols)
            
            new_symbols = get_qualified_symbols(
                self.api_key, self.api_secret,
                strategy_type="Safe Grid",
                leverage=self.lev,
                final_limit=needed_symbols
            )
            
            if new_symbols:
                for symbol in new_symbols:
                    if len(self.current_symbols) < self.max_symbols and symbol not in self.current_symbols:
                        self.current_symbols.append(symbol)
                        self.log(f"✅ Thêm coin Safe Grid: {symbol}")
                
                self.log(f"📊 Danh sách coin Safe Grid: {', '.join(self.current_symbols)}")
                self.last_symbol_refresh = current_time
            else:
                self.log(f"⚠️ Không tìm thấy coin Safe Grid nào")
                
        except Exception as e:
            self.log(f"❌ Lỗi refresh Safe Grid symbol: {str(e)}")

    def on_position_closed(self, symbol, reason=""):
        """Callback khi đóng lệnh - tìm coin thay thế"""
        try:
            if symbol in self.active_symbols:
                del self.active_symbols[symbol]
            if symbol in self.current_symbols:
                self.current_symbols.remove(symbol)
            
            self.log(f"🔎 Tìm coin Safe Grid thay thế cho {symbol}...")
            self.refresh_safegrid_symbols(force_refresh=True)
            
        except Exception as e:
            self.log(f"❌ Lỗi trong on_position_closed Safe Grid: {str(e)}")

    def get_signal(self):
        self.refresh_safegrid_symbols()
        
        if not self.current_symbols:
            return None
            
        try:
            # Logic Grid đơn giản - luân phiên mua/bán
            for symbol in self.current_symbols:
                if symbol in self.active_symbols:
                    continue
                    
                if symbol != self.symbol:
                    self.symbol = symbol
                    self.log(f"🔄 Chuyển sang coin Safe Grid: {symbol}")
                
                self.active_symbols[symbol] = "BUY"
                self.orders_placed += 1
                
                if self.orders_placed % 2 == 1:
                    self.log(f"🛡️ Tín hiệu Safe Grid BUY - Lệnh #{self.orders_placed}")
                    return "BUY"
                else:
                    self.log(f"🛡️ Tín hiệu Safe Grid SELL - Lệnh #{self.orders_placed}")
                    return "SELL"
                    
            return None
            
        except Exception as e:
            self.log(f"❌ Lỗi tín hiệu Safe Grid: {str(e)}")
            return None

# ========== CÁC BOT KHÁC (GIỮ NGUYÊN) ==========
class RSIEMABot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "RSI/EMA Recursive")
        self.rsi_history = []
        self.ema_fast = None
        self.ema_slow = None

    def get_signal(self):
        # ... (giữ nguyên code cũ)
        return None

class EMACrossoverBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "EMA Crossover")
        self.ema_fast_period = 9
        self.ema_slow_period = 21

    def get_signal(self):
        # ... (giữ nguyên code cũ)
        return None

class TrendFollowingBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id):
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, telegram_bot_token, telegram_chat_id, "Trend Following")
        self.ema_period = 20
        self.rsi_period = 14

    def get_signal(self):
        # ... (giữ nguyên code cũ)
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

# ========== BOT MANAGER ==========
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
            self.log("❌ LỖI: Không thể kết nối Binance API.")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        send_telegram(f"<b>SYSTEM</b>: {message}", 
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BOT GIAO DỊCH FUTURES BINANCE</b>\n\n🎯 <b>HỆ THỐNG ĐA CHIẾN LƯỢC</b>"
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bot(self, symbol, lev, percent, tp, sl, strategy_type, **kwargs):
        if sl == 0:
            sl = None
            
        test_balance = get_balance(self.api_key, self.api_secret)
        if test_balance is None:
            self.log("❌ LỖI: API Key không hợp lệ.")
            return False
            
        # XỬ LÝ CÁC CHIẾN LƯỢC TỰ ĐỘNG TÌM COIN
        if strategy_type in ["Reverse 24h", "Scalping", "Safe Grid"]:
            threshold = kwargs.get('threshold', 30)
            
            # Tạo bot với symbol=None để kích hoạt chế độ tự động
            bot_id = f"AUTO_{strategy_type}_{int(time.time())}"
            
            try:
                if strategy_type == "Reverse 24h":
                    bot = Reverse24hBot(None, lev, percent, tp, sl, self.ws_manager,
                                       self.api_key, self.api_secret, self.telegram_bot_token, 
                                       self.telegram_chat_id, threshold)
                elif strategy_type == "Scalping":
                    bot = ScalpingBot(None, lev, percent, tp, sl, self.ws_manager,
                                     self.api_key, self.api_secret, self.telegram_bot_token, 
                                     self.telegram_chat_id)
                elif strategy_type == "Safe Grid":
                    bot = SafeGridBot(None, lev, percent, tp, sl, self.ws_manager,
                                     self.api_key, self.api_secret, self.telegram_bot_token, 
                                     self.telegram_chat_id)
                
                self.bots[bot_id] = bot
                
                success_msg = (
                    f"✅ <b>ĐÃ TẠO BOT {strategy_type} TỰ ĐỘNG</b>\n\n"
                    f"🎯 Chiến lược: {strategy_type}\n"
                    f"💰 Đòn bẩy: {lev}x\n"
                    f"📊 % Số dư: {percent}%\n"
                    f"🎯 TP: {tp}%\n"
                    f"🛡️ SL: {sl}%\n\n"
                    f"🤖 Bot sẽ tự động tìm và giao dịch trên 2 coin phù hợp nhất"
                )
                if strategy_type == "Reverse 24h":
                    success_msg += f"\n📊 Ngưỡng biến động: {threshold}%"
                    
                self.log(success_msg)
                return True
                
            except Exception as e:
                error_msg = f"❌ Lỗi tạo bot {strategy_type}: {str(e)}"
                self.log(error_msg)
                return False
        
        # CÁC CHIẾN LƯỢC KHÁC (MANUAL)
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
                else:
                    self.log(f"❌ Chiến lược {strategy_type} không được hỗ trợ")
                    return False
                
                self.bots[bot_id] = bot
                self.log(f"✅ Đã thêm bot {strategy_type}: {symbol}")
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

    def _status_monitor(self):
        while self.running:
            try:
                uptime = time.time() - self.start_time
                hours, rem = divmod(uptime, 3600)
                minutes, seconds = divmod(rem, 60)
                uptime_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                
                active_bots = [bot_id for bot_id, bot in self.bots.items() if not bot._stop]
                balance = get_balance(self.api_key, self.api_secret)
                
                if balance is None:
                    status_msg = "❌ <b>LỖI KẾT NỐI BINANCE</b>"
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
            
            time.sleep(6 * 3600)

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
                
                # XỬ LÝ ĐẶC BIỆT CHO CÁC CHIẾN LƯỢC TỰ ĐỘNG
                if strategy in ["Reverse 24h", "Scalping", "Safe Grid"]:
                    if strategy == "Reverse 24h":
                        user_state['step'] = 'waiting_threshold'
                        send_telegram(
                            f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                            f"🤖 Bot sẽ tự động tìm 2 coin phù hợp nhất\n\n"
                            f"Chọn ngưỡng biến động (%):",
                            chat_id,
                            create_threshold_keyboard(),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                    else:
                        user_state['step'] = 'waiting_leverage'
                        send_telegram(
                            f"🎯 <b>ĐÃ CHỌN: {strategy}</b>\n\n"
                            f"🤖 Bot sẽ tự động tìm 2 coin phù hợp nhất\n\n"
                            f"Chọn đòn bẩy:",
                            chat_id,
                            create_leverage_keyboard(strategy),
                            self.telegram_bot_token, self.telegram_chat_id
                        )
                else:
                    user_state['step'] = 'waiting_symbol'
                    send_telegram("Chọn cặp coin:", chat_id,
                                create_symbols_keyboard(strategy),
                                self.telegram_bot_token, self.telegram_chat_id)
        
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
        
        # ... (phần còn lại của _handle_telegram_message giữ nguyên)
        
        elif text == "➕ Thêm Bot":
            self.user_states[chat_id] = {'step': 'waiting_strategy'}
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None:
                send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                return
            
            send_telegram(
                f"🎯 <b>CHỌN CHIẾN LƯỢC GIAO DỊCH</b>\n\n"
                f"💡 <b>Chiến lược tự động:</b>\n• Reverse 24h\n• Scalping  \n• Safe Grid\n\n"
                f"🤖 Sẽ tự động tìm 2 coin phù hợp nhất",
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
                    send_telegram("❌ <b>LỖI KẾT NỐI BINANCE</b>", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                else:
                    send_telegram(f"💰 <b>SỐ DƯ KHẢ DỤNG</b>: {balance:.2f} USDT", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy số dư: {str(e)}", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>DANH SÁCH CHIẾN LƯỢC</b>\n\n"
                "🎯 <b>Reverse 24h</b> - TỰ ĐỘNG\n"
                "• Đảo chiều biến động 24h\n"
                "• Tự tìm 2 coin biến động cao\n"
                "• Loại bỏ BTC/ETH\n\n"
                "⚡ <b>Scalping</b> - TỰ ĐỘNG\n"
                "• Giao dịch tốc độ cao\n"
                "• Tự tìm 2 coin biến động nhanh\n"
                "• Loại bỏ BTC/ETH\n\n"
                "🛡️ <b>Safe Grid</b> - TỰ ĐỘNG\n"
                "• Grid an toàn\n"
                "• Tự tìm 2 coin ổn định\n"
                "• Loại bỏ BTC/ETH"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

# Thêm hàm create_symbols_keyboard nếu chưa có
def create_symbols_keyboard(strategy=None):
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOTUSDT"]
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
