# trading_bot_lib.py - PHẦN 1
# HỆ THỐNG RSI + KHỐI LƯỢNG, GIAO DỊCH NỐI TIẾP + TỰ TÌM COIN MỚI
# Phần này gồm:
# - Import, SSL, logging
# - Telegram + menu
# - API Binance helpers
# - CoinManager, SmartCoinFinder (RSI + Volume)
# - WebSocketManager
# - BaseBot (logic giao dịch nối tiếp, TP/SL, ROI, nhồi Fibonacci, tìm coin mới)

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
import ssl

# =========================
# BYPASS SSL VERIFICATION
# =========================
ssl._create_default_https_context = ssl._create_unverified_context

# =========================
# LOGGING CƠ BẢN
# =========================
def setup_logging():
    logging.basicConfig(
        level=logging.WARNING,  # chỉ WARNING và ERROR
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_errors.log')
        ]
    )
    return logging.getLogger()

logger = setup_logging()

# =========================
# HÀM TELEGRAM
# =========================
def escape_html(text: str) -> str:
    if not text:
        return text
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

def send_telegram(message, chat_id=None, reply_markup=None, bot_token=None, default_chat_id=None):
    """
    Gửi message Telegram (HTML mode), trả về True/False.
    """
    if not bot_token:
        logger.warning("Telegram Bot Token chưa được thiết lập")
        return False

    chat_id = chat_id or default_chat_id
    if not chat_id:
        logger.warning("Telegram Chat ID chưa được thiết lập")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    safe_message = escape_html(message)
    payload = {
        "chat_id": chat_id,
        "text": safe_message,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return True
        else:
            logger.error(f"Lỗi Telegram ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Lỗi kết nối Telegram: {str(e)}")
        return False

# =========================
# KEYBOARD / MENU TELEGRAM
# =========================
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
            symbols = [
                "BTCUSDC", "ETHUSDC", "BNBUSDC", "ADAUSDC",
                "DOGEUSDC", "XRPUSDC", "DOTUSDC", "LINKUSDC"
            ]
    except Exception:
        symbols = [
            "BTCUSDC", "ETHUSDC", "BNBUSDC", "ADAUSDC",
            "DOGEUSDC", "XRPUSDC", "DOTUSDC", "LINKUSDC"
        ]

    keyboard = []
    row = []
    for sym in symbols:
        row.append({"text": sym})
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
    keyboard, row = [], []
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

# =========================
# HỖ TRỢ API BINANCE
# =========================
def sign(query, api_secret):
    try:
        return hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"Lỗi tạo chữ ký: {str(e)}")
        return ""

def binance_api_request(url, method='GET', params=None, headers=None):
    """
    Wrapper chung gọi API Binance (có retry + User-Agent, xử lý 451).
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if headers is None:
                headers = {}
            if 'User-Agent' not in headers:
                headers['User-Agent'] = (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36'
                )

            req_url = url
            data = None
            if method.upper() == 'GET':
                if params:
                    query = urllib.parse.urlencode(params)
                    req_url = f"{url}?{query}"
                req = urllib.request.Request(req_url, headers=headers)
            else:
                if params:
                    data = urllib.parse.urlencode(params).encode()
                req = urllib.request.Request(url, data=data, headers=headers, method=method)

            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
                else:
                    content = resp.read().decode()
                    logger.error(f"Lỗi API ({resp.status}): {content}")
                    if resp.status == 401:
                        return None
                    if resp.status == 429:
                        time.sleep(2 ** attempt)
                    elif resp.status >= 500:
                        time.sleep(1)
                    continue

        except urllib.error.HTTPError as e:
            if e.code == 451:
                logger.error("❌ Lỗi 451: Bị chặn truy cập (có thể do vùng địa lý / IP).")
                # có thể đổi domain ở đây nếu cần
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

    logger.error(f"Không thể thực hiện API sau {max_retries} lần thử")
    return None

def _last_closed_1m_quote_volume(symbol):
    """
    Lấy quoteVolume của nến 1m đã đóng gần nhất.
    Dùng cho việc xếp hạng coin theo volume.
    """
    data = binance_api_request(
        "https://fapi.binance.com/fapi/v1/klines",
        params={"symbol": symbol, "interval": "1m", "limit": 2}
    )
    if not data or len(data) < 2:
        return None
    k = data[-2]
    return float(k[7])  # quoteVolume

def get_all_usdc_pairs(limit=100):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            logger.warning("Không lấy được exchangeInfo, trả về list rỗng")
            return []
        usdc_pairs = []
        for s in data.get("symbols", []):
            sym = s.get("symbol", "")
            if sym.endswith("USDC") and s.get("status") == "TRADING":
                usdc_pairs.append(sym)
        return usdc_pairs[:limit] if limit else usdc_pairs
    except Exception as e:
        logger.error(f"❌ Lỗi get_all_usdc_pairs: {str(e)}")
        return []

def get_top_volume_symbols(limit=100):
    """
    Lấy top coin theo quoteVolume nến 1m đã đóng (đa luồng).
    """
    try:
        universe = get_all_usdc_pairs(limit=100) or []
        if not universe:
            logger.warning("❌ Không có USDC pair nào")
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
        return [s for s, _ in scored[:limit]]
    except Exception as e:
        logger.error(f"❌ Lỗi get_top_volume_symbols: {str(e)}")
        return []

def get_max_leverage(symbol, api_key, api_secret):
    try:
        data = binance_api_request("https://fapi.binance.com/fapi/v1/exchangeInfo")
        if not data:
            return 100
        for s in data.get("symbols", []):
            if s.get("symbol") == symbol.upper():
                for f in s.get("filters", []):
                    if f.get("filterType") == "LEVERAGE" and "maxLeverage" in f:
                        return int(f["maxLeverage"])
        return 100
    except Exception as e:
        logger.error(f"Lỗi get_max_leverage {symbol}: {str(e)}")
        return 100

def get_step_size(symbol, api_key, api_secret):
    if not symbol:
        logger.error("❌ Symbol None khi get_step_size")
        return 0.001
    try:
        data = binance_api_request("https://fapi.binance.com/fapi/v1/exchangeInfo")
        if not data:
            return 0.001
        for s in data.get("symbols", []):
            if s.get("symbol") == symbol.upper():
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        return float(f.get("stepSize", 0.001))
        return 0.001
    except Exception as e:
        logger.error(f"Lỗi get_step_size {symbol}: {str(e)}")
        return 0.001

def set_leverage(symbol, lev, api_key, api_secret):
    if not symbol:
        logger.error("❌ Symbol None khi set_leverage")
        return False
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "leverage": lev, "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v1/leverage?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": api_key}
        resp = binance_api_request(url, method="POST", headers=headers)
        if resp and "leverage" in resp:
            return True
        return False
    except Exception as e:
        logger.error(f"Lỗi set_leverage {symbol}: {str(e)}")
        return False

def get_balance(api_key, api_secret):
    """
    Lấy availableBalance USDC để tính khối lượng.
    """
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": api_key}
        data = binance_api_request(url, headers=headers)
        if not data:
            logger.error("❌ Không lấy được account info")
            return None
        for a in data.get("assets", []):
            if a.get("asset") == "USDC":
                avail = float(a.get("availableBalance", 0))
                total = float(a.get("walletBalance", 0))
                logger.info(f"💰 Số dư USDC: avail={avail:.2f}, total={total:.2f}")
                return avail
        return 0
    except Exception as e:
        logger.error(f"Lỗi get_balance: {str(e)}")
        return None

def place_order(symbol, side, qty, api_key, api_secret):
    if not symbol:
        logger.error("❌ Symbol None khi place_order")
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
        headers = {"X-MBX-APIKEY": api_key}
        return binance_api_request(url, method="POST", headers=headers)
    except Exception as e:
        logger.error(f"Lỗi place_order {symbol}: {str(e)}")
        return None

def cancel_all_orders(symbol, api_key, api_secret):
    if not symbol:
        logger.error("❌ Symbol None khi cancel_all_orders")
        return False
    try:
        ts = int(time.time() * 1000)
        params = {"symbol": symbol.upper(), "timestamp": ts}
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v1/allOpenOrders?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": api_key}
        binance_api_request(url, method="DELETE", headers=headers)
        return True
    except Exception as e:
        logger.error(f"Lỗi cancel_all_orders {symbol}: {str(e)}")
        return False

def get_current_price(symbol):
    if not symbol:
        logger.error("❌ Symbol None khi get_current_price")
        return 0
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and "price" in data:
            p = float(data["price"])
            if p > 0:
                return p
        return 0
    except Exception as e:
        logger.error(f"Lỗi get_current_price {symbol}: {str(e)}")
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
        headers = {"X-MBX-APIKEY": api_key}
        data = binance_api_request(url, headers=headers)
        if not data:
            return []
        if symbol:
            return [p for p in data if p.get("symbol") == symbol.upper()]
        return data
    except Exception as e:
        logger.error(f"Lỗi get_positions: {str(e)}")
        return []

# =========================
# COIN MANAGER
# =========================
class CoinManager:
    """
    Quản lý tập coin đang được các bot sử dụng để tránh trùng lặp.
    """
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

# =========================
# SMART COIN FINDER (RSI + VOLUME)
# =========================
class SmartCoinFinder:
    """
    Phân tích RSI + khối lượng 5m để sinh tín hiệu BUY/SELL
    và tìm coin phù hợp với hướng target.
    """
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret

    def get_symbol_leverage(self, symbol):
        return get_max_leverage(symbol, self.api_key, self.api_secret)

    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50
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
        """
        Logic RSI + khối lượng mới:
        - Dựa trên 3 nến gần nhất khung 5m
        - Kết hợp hướng giá + thay đổi volume để xác định BUY/SELL
        """
        try:
            data = binance_api_request(
                "https://fapi.binance.com/fapi/v1/klines",
                params={"symbol": symbol, "interval": "5m", "limit": 15}
            )
            if not data or len(data) < 15:
                return None

            prev_candle = data[-3]
            current_candle = data[-2]
            latest_candle = data[-1]

            closes = [float(k[4]) for k in data]
            rsi_current = self.calculate_rsi(closes)

            prev_close = float(prev_candle[4])
            current_close = float(current_candle[4])
            latest_close = float(latest_candle[4]) if len(latest_candle) > 4 else current_close

            prev_volume = float(prev_candle[5])
            current_volume = float(current_candle[5])

            price_increase = current_close > prev_close
            price_decrease = current_close < prev_close

            volume_increase = current_volume > prev_volume * (1 + volume_threshold / 100)
            volume_decrease = current_volume < prev_volume * (1 - volume_threshold / 100)

            # Logic mới (có thể chỉnh lại theo ý bạn)
            if rsi_current > 80:
                if price_increase and volume_increase:
                    return "SELL"
                elif price_increase and volume_decrease:
                    return "BUY"
            elif rsi_current < 20:
                if price_decrease and volume_decrease:
                    return "SELL"
                elif price_decrease and volume_increase:
                    return "BUY"
            elif rsi_current > 20 and not price_decrease and volume_decrease:
                return "BUY"
            elif rsi_current < 80 and not price_increase and volume_increase:
                return "SELL"

            return None
        except Exception as e:
            logger.error(f"Lỗi phân tích RSI {symbol}: {str(e)}")
            return None

    def get_entry_signal(self, symbol):
        return self.get_rsi_signal(symbol, volume_threshold=20)

    def get_exit_signal(self, symbol):
        return self.get_rsi_signal(symbol, volume_threshold=40)

    def has_existing_position(self, symbol):
        """
        Kiểm tra trên Binance xem coin đã có vị thế thật chưa.
        Nếu có -> tránh mở/scan lại coin đó cho bot này.
        """
        try:
            positions = get_positions(symbol, self.api_key, self.api_secret)
            if positions:
                for p in positions:
                    amt = float(p.get("positionAmt", 0))
                    if abs(amt) > 0:
                        logger.info(f"⚠️ Phát hiện vị thế {symbol}: {amt}")
                        return True
            return False
        except Exception as e:
            logger.error(f"Lỗi has_existing_position {symbol}: {str(e)}")
            return True

    def find_best_coin(self, target_direction, excluded_coins=None, required_leverage=10):
        """
        Tìm một coin phù hợp với target_direction (BUY/SELL),
        không trùng với excluded_coins, đủ leverage.
        """
        try:
            all_symbols = get_all_usdc_pairs(limit=50)
            if not all_symbols:
                return None

            valid = []
            for sym in all_symbols:
                if excluded_coins and sym in excluded_coins:
                    continue
                if self.has_existing_position(sym):
                    continue

                max_lev = self.get_symbol_leverage(sym)
                if max_lev < required_leverage:
                    continue

                sig = self.get_entry_signal(sym)
                if sig == target_direction:
                    valid.append(sym)

            if not valid:
                return None

            chosen = random.choice(valid)
            if self.has_existing_position(chosen):
                return None
            return chosen
        except Exception as e:
            logger.error(f"Lỗi find_best_coin: {str(e)}")
            return None

# =========================
# WEBSOCKET MANAGER
# =========================
class WebSocketManager:
    """
    Quản lý nối WebSocket cho từng symbol, cập nhật giá realtime.
    """
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
                d = json.loads(message)
                if "p" in d:
                    price = float(d["p"])
                    self.executor.submit(callback, price)
            except Exception as e:
                logger.error(f"Lỗi on_message WS {symbol}: {str(e)}")

        def on_error(ws, error):
            logger.error(f"Lỗi WebSocket {symbol}: {error}")
            if not self._stop_event.is_set():
                time.sleep(5)
                self._reconnect(symbol, callback)

        def on_close(ws, code, msg):
            logger.info(f"WS đóng {symbol}: {code}, {msg}")
            if not self._stop_event.is_set() and symbol in self.connections:
                time.sleep(5)
                self._reconnect(symbol, callback)

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        th = threading.Thread(target=ws.run_forever, daemon=True)
        th.start()
        self.connections[symbol] = {"ws": ws, "thread": th, "callback": callback}
        logger.info(f"🔗 WS start {symbol}")

    def _reconnect(self, symbol, callback):
        logger.info(f"Reconnect WS {symbol}")
        self.remove_symbol(symbol)
        self._create_connection(symbol, callback)

    def remove_symbol(self, symbol):
        if not symbol:
            return
        symbol = symbol.upper()
        with self._lock:
            if symbol in self.connections:
                try:
                    self.connections[symbol]["ws"].close()
                except Exception as e:
                    logger.error(f"Lỗi close WS {symbol}: {str(e)}")
                del self.connections[symbol]

    def stop(self):
        self._stop_event.set()
        for sym in list(self.connections.keys()):
            self.remove_symbol(sym)

# =========================
# BASE BOT (GIAO DỊCH NỐI TIẾP)
# =========================
class BaseBot:
    """
    Bot cơ sở:
    - Quản lý nhiều coin cùng lúc (max_coins)
    - Xử lý nối tiếp: mỗi vòng chỉ xử lý 1 coin, nhưng vẫn check TP/SL & nhồi cho tất cả
    - Tự tìm coin mới bằng SmartCoinFinder
    - TP/SL, ROI trigger, nhồi Fibonacci, quản lý vị thế theo từng symbol
    """
    def __init__(
        self,
        symbol,
        lev,
        percent,
        tp,
        sl,
        roi_trigger,
        ws_manager,
        api_key,
        api_secret,
        telegram_bot_token,
        telegram_chat_id,
        strategy_name,
        config_key=None,
        bot_id=None,
        coin_manager=None,
        symbol_locks=None,
        max_coins=1
    ):
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

        # luôn ở trạng thái searching
        self.status = "searching"
        self._stop = False

        # quản lý nối tiếp
        self.current_processing_symbol = None
        self.last_trade_completion_time = 0
        self.trade_cooldown = 3  # giãn cách giữa các lần xử lý

        # thống kê toàn tài khoản
        self.last_global_position_check = 0
        self.last_error_log_time = 0
        self.global_position_check_interval = 10
        self.global_long_count = 0
        self.global_short_count = 0
        self.global_long_pnl = 0
        self.global_short_pnl = 0

        self.coin_manager = coin_manager or CoinManager()
        self.symbol_locks = symbol_locks
        self.coin_finder = SmartCoinFinder(api_key, api_secret)

        self.find_new_bot_after_close = True
        self.bot_creation_time = time.time()

        self.symbol_management_lock = threading.Lock()

        # nếu có symbol ban đầu và chưa có vị thế thì thêm ngay
        if symbol and not self.coin_finder.has_existing_position(symbol):
            self._add_symbol(symbol)

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        roi_info = f" | 🎯 ROI Trigger: {roi_trigger}%" if roi_trigger else " | 🎯 ROI Trigger: Tắt"
        self.log(
            f"🟢 Bot {strategy_name} khởi động | Tối đa: {max_coins} coin | "
            f"ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%{roi_info}"
        )

    # =========================
    # VÒNG LẶP CHÍNH
    # =========================
    def _run(self):
        while not self._stop:
            try:
                now = time.time()

                if now - self.last_global_position_check > self.global_position_check_interval:
                    self.check_global_positions()
                    self.last_global_position_check = now

                # cooldown
                if now - self.last_trade_completion_time < self.trade_cooldown:
                    time.sleep(0.5)
                    continue

                # luôn cố gắng tìm coin mới nếu chưa đủ
                if len(self.active_symbols) < self.max_coins:
                    if self._find_and_add_new_coin():
                        self.last_trade_completion_time = now
                        time.sleep(3)
                        continue

                if self.active_symbols:
                    sym_to_process = self.active_symbols[0]
                    self.current_processing_symbol = sym_to_process

                    # xử lý chính 1 coin
                    self._process_single_symbol(sym_to_process)

                    # check TP/SL + nhồi cho các coin còn lại
                    for s in self.active_symbols:
                        if s != sym_to_process:
                            self._check_symbol_tp_sl(s)
                            self._check_symbol_averaging_down(s)

                    self.last_trade_completion_time = time.time()
                    time.sleep(3)

                    # xoay vòng
                    if len(self.active_symbols) > 1:
                        self.active_symbols.append(self.active_symbols.pop(0))

                    self.current_processing_symbol = None
                else:
                    time.sleep(5)

            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    self.log(f"❌ Lỗi hệ thống: {str(e)}")
                    self.last_error_log_time = time.time()
                time.sleep(1)

    # =========================
    # XỬ LÝ 1 SYMBOL
    # =========================
    def _process_single_symbol(self, symbol):
        try:
            info = self.symbol_data[symbol]
            now = time.time()

            # check vị thế định kỳ
            if now - info.get("last_position_check", 0) > 30:
                self._check_symbol_position(symbol)
                info["last_position_check"] = now

            # nếu Binance có vị thế mà bot đang nghĩ là không có
            if self.coin_finder.has_existing_position(symbol) and not info["position_open"]:
                self.log(f"⚠️ {symbol} - phát hiện có vị thế thật, dừng theo dõi")
                self.stop_symbol(symbol)
                return False

            if info["position_open"]:
                # đóng thông minh theo ROI + tín hiệu exit
                if self._check_smart_exit_condition(symbol):
                    return True
                # TP/SL
                self._check_symbol_tp_sl(symbol)
                # nhồi Fibonacci
                self._check_symbol_averaging_down(symbol)
            else:
                # xét tín hiệu vào lệnh
                if (now - info["last_trade_time"] > 60 and
                    now - info["last_close_time"] > 3600):

                    target_side = self.get_next_side_based_on_comprehensive_analysis()
                    entry_signal = self.coin_finder.get_entry_signal(symbol)

                    if entry_signal == target_side:
                        if self.coin_finder.has_existing_position(symbol):
                            self.log(f"🚫 {symbol} - đã có vị thế thật, bỏ qua")
                            self.stop_symbol(symbol)
                            return False
                        if self._open_symbol_position(symbol, target_side):
                            info["last_trade_time"] = now
                            return True
            return False
        except Exception as e:
            self.log(f"❌ Lỗi _process_single_symbol {symbol}: {str(e)}")
            return False

    # =========================
    # TÌM COIN MỚI
    # =========================
    def _find_and_add_new_coin(self):
        with self.symbol_management_lock:
            try:
                if len(self.active_symbols) >= self.max_coins:
                    return False

                active = self.coin_manager.get_active_coins()
                target = self.get_next_side_based_on_comprehensive_analysis()

                new_sym = self.coin_finder.find_best_coin(
                    target_direction=target,
                    excluded_coins=active,
                    required_leverage=self.lev
                )
                if not new_sym:
                    return False

                if self.coin_finder.has_existing_position(new_sym):
                    return False

                if self._add_symbol(new_sym):
                    self.log(f"✅ Thêm coin mới: {new_sym} (tổng {len(self.active_symbols)})")
                    time.sleep(1)
                    if self.coin_finder.has_existing_position(new_sym):
                        self.log(f"🚫 {new_sym} - có vị thế sau khi thêm, dừng theo dõi")
                        self.stop_symbol(new_sym)
                        return False
                    return True
                return False
            except Exception as e:
                self.log(f"❌ Lỗi _find_and_add_new_coin: {str(e)}")
                return False

    def _add_symbol(self, symbol):
        with self.symbol_management_lock:
            if symbol in self.active_symbols:
                return False
            if len(self.active_symbols) >= self.max_coins:
                return False
            if self.coin_finder.has_existing_position(symbol):
                return False

            self.symbol_data[symbol] = {
                "status": "waiting",
                "side": "",
                "qty": 0,
                "entry": 0,
                "current_price": 0,
                "position_open": False,
                "last_trade_time": 0,
                "last_close_time": 0,
                "entry_base": 0,
                "average_down_count": 0,
                "last_average_down_time": 0,
                "high_water_mark_roi": 0,
                "roi_check_activated": False,
                "close_attempted": False,
                "last_close_attempt": 0,
                "last_position_check": 0,
            }

            self.active_symbols.append(symbol)
            self.coin_manager.register_coin(symbol)
            self.ws_manager.add_symbol(symbol, lambda price, sym=symbol: self._handle_price_update(price, sym))

            self._check_symbol_position(symbol)
            if self.symbol_data[symbol]["position_open"]:
                self.stop_symbol(symbol)
                return False
            return True

    def _handle_price_update(self, price, symbol):
        if symbol in self.symbol_data:
            self.symbol_data[symbol]["current_price"] = price

    # =========================
    # QUẢN LÝ VỊ THẾ TỪ BINANCE
    # =========================
    def _check_symbol_position(self, symbol):
        try:
            positions = get_positions(symbol, self.api_key, self.api_secret)
            if not positions:
                self._reset_symbol_position(symbol)
                return

            found = False
            for p in positions:
                if p.get("symbol") == symbol:
                    amt = float(p.get("positionAmt", 0))
                    if abs(amt) > 0:
                        found = True
                        d = self.symbol_data[symbol]
                        d["position_open"] = True
                        d["status"] = "open"
                        d["side"] = "BUY" if amt > 0 else "SELL"
                        d["qty"] = amt
                        d["entry"] = float(p.get("entryPrice", 0))

                        cur = get_current_price(symbol)
                        if cur > 0 and self.roi_trigger:
                            if d["side"] == "BUY":
                                profit = (cur - d["entry"]) * abs(d["qty"])
                            else:
                                profit = (d["entry"] - cur) * abs(d["qty"])
                            invested = d["entry"] * abs(d["qty"]) / self.lev
                            if invested > 0:
                                roi = profit / invested * 100
                                if roi >= self.roi_trigger:
                                    d["roi_check_activated"] = True
                        break
                    else:
                        found = True
                        self._reset_symbol_position(symbol)
                        break
            if not found:
                self._reset_symbol_position(symbol)
        except Exception as e:
            self.log(f"❌ Lỗi _check_symbol_position {symbol}: {str(e)}")

    def _reset_symbol_position(self, symbol):
        if symbol in self.symbol_data:
            d = self.symbol_data[symbol]
            d["position_open"] = False
            d["status"] = "waiting"
            d["side"] = ""
            d["qty"] = 0
            d["entry"] = 0
            d["close_attempted"] = False
            d["last_close_attempt"] = 0
            d["entry_base"] = 0
            d["average_down_count"] = 0
            d["high_water_mark_roi"] = 0
            d["roi_check_activated"] = False

    # =========================
    # MỞ / ĐÓNG VỊ THẾ
    # =========================
    def _open_symbol_position(self, symbol, side):
        try:
            if self.coin_finder.has_existing_position(symbol):
                self.log(f"⚠️ {symbol} đã có vị thế, bỏ qua")
                self.stop_symbol(symbol)
                return False

            self._check_symbol_position(symbol)
            if self.symbol_data[symbol]["position_open"]:
                return False

            cur_lev = self.coin_finder.get_symbol_leverage(symbol)
            if cur_lev < self.lev:
                self.log(f"❌ {symbol} leverage không đủ: {cur_lev}x < {self.lev}x")
                self.stop_symbol(symbol)
                return False

            if not set_leverage(symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ {symbol} không set được leverage")
                self.stop_symbol(symbol)
                return False

            bal = get_balance(self.api_key, self.api_secret)
            if not bal or bal <= 0:
                self.log(f"❌ {symbol} không đủ số dư")
                return False

            price = get_current_price(symbol)
            if price <= 0:
                self.log(f"❌ {symbol} lỗi giá")
                self.stop_symbol(symbol)
                return False

            step = get_step_size(symbol, self.api_key, self.api_secret)
            usd_amount = bal * (self.percent / 100)
            qty = (usd_amount * self.lev) / price
            if step > 0:
                qty = math.floor(qty / step) * step
                qty = round(qty, 8)
            if qty <= 0 or qty < step:
                self.log(f"❌ {symbol} khối lượng không hợp lệ")
                self.stop_symbol(symbol)
                return False

            cancel_all_orders(symbol, self.api_key, self.api_secret)
            time.sleep(0.2)

            res = place_order(symbol, side, qty, self.api_key, self.api_secret)
            if res and "orderId" in res:
                exec_qty = float(res.get("executedQty", 0))
                avg_price = float(res.get("avgPrice", price))
                if exec_qty >= 0:
                    time.sleep(1)
                    self._check_symbol_position(symbol)
                    if not self.symbol_data[symbol]["position_open"]:
                        self.log(f"❌ {symbol} lệnh khớp nhưng không tạo vị thế")
                        self.stop_symbol(symbol)
                        return False

                    d = self.symbol_data[symbol]
                    d["entry"] = avg_price
                    d["entry_base"] = avg_price
                    d["average_down_count"] = 0
                    d["side"] = side
                    d["qty"] = exec_qty if side == "BUY" else -exec_qty
                    d["position_open"] = True
                    d["status"] = "open"
                    d["high_water_mark_roi"] = 0
                    d["roi_check_activated"] = False

                    msg = (
                        f"✅ <b>MỞ VỊ THẾ {symbol}</b>\n"
                        f"🤖 Bot: {self.bot_id}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {avg_price:.4f}\n"
                        f"📊 Khối lượng: {exec_qty:.4f}\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    if self.roi_trigger:
                        msg += f" | 🎯 ROI Trigger: {self.roi_trigger}%"
                    self.log(msg)
                    return True
                else:
                    self.log(f"❌ {symbol} lệnh không khớp")
                    self.stop_symbol(symbol)
                    return False
            else:
                err = res.get("msg", "Unknown") if res else "No response"
                self.log(f"❌ {symbol} lỗi đặt lệnh: {err}")
                self.stop_symbol(symbol)
                return False
        except Exception as e:
            self.log(f"❌ {symbol} lỗi _open_symbol_position: {str(e)}")
            self.stop_symbol(symbol)
            return False

    def _close_symbol_position(self, symbol, reason=""):
        try:
            self._check_symbol_position(symbol)
            d = self.symbol_data[symbol]
            if not d["position_open"] or abs(d["qty"]) <= 0:
                return True

            now = time.time()
            if d["close_attempted"] and now - d["last_close_attempt"] < 30:
                return False

            d["close_attempted"] = True
            d["last_close_attempt"] = now

            close_side = "SELL" if d["side"] == "BUY" else "BUY"
            close_qty = abs(d["qty"])

            cancel_all_orders(symbol, self.api_key, self.api_secret)
            time.sleep(0.5)

            res = place_order(symbol, close_side, close_qty, self.api_key, self.api_secret)
            if res and "orderId" in res:
                cur_price = get_current_price(symbol)
                pnl = 0
                if d["entry"] > 0:
                    if d["side"] == "BUY":
                        pnl = (cur_price - d["entry"]) * abs(d["qty"])
                    else:
                        pnl = (d["entry"] - cur_price) * abs(d["qty"])

                msg = (
                    f"⛔ <b>ĐÓNG VỊ THẾ {symbol}</b>\n"
                    f"🤖 Bot: {self.bot_id}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {cur_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDC\n"
                    f"📈 Số lần nhồi: {d['average_down_count']}"
                )
                self.log(msg)
                d["last_close_time"] = time.time()
                self._reset_symbol_position(symbol)
                return True
            else:
                err = res.get("msg", "Unknown") if res else "No response"
                self.log(f"❌ {symbol} lỗi đóng lệnh: {err}")
                d["close_attempted"] = False
                return False
        except Exception as e:
            self.log(f"❌ {symbol} lỗi _close_symbol_position: {str(e)}")
            self.symbol_data[symbol]["close_attempted"] = False
            return False

    # =========================
    # TP/SL + ROI TRIGGER
    # =========================
    def _check_smart_exit_condition(self, symbol):
        try:
            d = self.symbol_data[symbol]
            if not d["position_open"] or not d["roi_check_activated"]:
                return False

            cur = get_current_price(symbol)
            if cur <= 0:
                return False

            if d["side"] == "BUY":
                profit = (cur - d["entry"]) * abs(d["qty"])
            else:
                profit = (d["entry"] - cur) * abs(d["qty"])
            invested = d["entry"] * abs(d["qty"]) / self.lev
            if invested <= 0:
                return False
            roi = profit / invested * 100

            if roi >= self.roi_trigger:
                exit_sig = self.coin_finder.get_exit_signal(symbol)
                if exit_sig:
                    reason = f"🎯 ROI {self.roi_trigger}% + tín hiệu exit (ROI: {roi:.2f}%)"
                    self._close_symbol_position(symbol, reason)
                    return True
            return False
        except Exception as e:
            self.log(f"❌ {symbol} lỗi _check_smart_exit_condition: {str(e)}")
            return False

    def _check_symbol_tp_sl(self, symbol):
        d = self.symbol_data[symbol]
        if (not d["position_open"] or
            d["entry"] <= 0 or
            d["close_attempted"]):
            return False

        cur = get_current_price(symbol)
        if cur <= 0:
            return False

        if d["side"] == "BUY":
            profit = (cur - d["entry"]) * abs(d["qty"])
        else:
            profit = (d["entry"] - cur) * abs(d["qty"])
        invested = d["entry"] * abs(d["qty"]) / self.lev
        if invested <= 0:
            return False

        roi = profit / invested * 100

        if roi > d["high_water_mark_roi"]:
            d["high_water_mark_roi"] = roi

        if (self.roi_trigger is not None and
            d["high_water_mark_roi"] >= self.roi_trigger and
            not d["roi_check_activated"]):
            d["roi_check_activated"] = True

        closed = False
        if self.tp is not None and roi >= self.tp:
            self._close_symbol_position(symbol, f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
            closed = True
        elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
            self._close_symbol_position(symbol, f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")
            closed = True

        return closed

    # =========================
    # NHỒI FIBONACCI
    # =========================
    def _check_symbol_averaging_down(self, symbol):
        d = self.symbol_data[symbol]
        if (not d["position_open"] or
            not d["entry_base"] or
            d["average_down_count"] >= 7):
            return False
        try:
            now = time.time()
            if now - d["last_average_down_time"] < 60:
                return False

            cur = get_current_price(symbol)
            if cur <= 0:
                return False

            if d["side"] == "BUY":
                profit = (cur - d["entry_base"]) * abs(d["qty"])
            else:
                profit = (d["entry_base"] - cur) * abs(d["qty"])
            invested = d["entry_base"] * abs(d["qty"]) / self.lev
            if invested <= 0:
                return False

            roi = profit / invested * 100
            if roi >= 0:
                return False

            roi_negative = abs(roi)
            fib_levels = [200, 300, 500, 800, 1300, 2100, 3400]
            if d["average_down_count"] < len(fib_levels):
                target = fib_levels[d["average_down_count"]]
                if roi_negative >= target:
                    if self._execute_symbol_average_down(symbol):
                        d["last_average_down_time"] = now
                        d["average_down_count"] += 1
                        self.log(f"📈 {symbol} nhồi Fibonacci mốc {target}% lỗ")
                        return True
            return False
        except Exception as e:
            self.log(f"❌ {symbol} lỗi _check_symbol_averaging_down: {str(e)}")
            return False

    def _execute_symbol_average_down(self, symbol):
        try:
            d = self.symbol_data[symbol]
            bal = get_balance(self.api_key, self.api_secret)
            if not bal or bal <= 0:
                return False
            cur = get_current_price(symbol)
            if cur <= 0:
                return False

            add_percent = self.percent * (d["average_down_count"] + 1)
            usd_amount = bal * (add_percent / 100)
            qty = (usd_amount * self.lev) / cur

            step = get_step_size(symbol, self.api_key, self.api_secret)
            if step > 0:
                qty = math.floor(qty / step) * step
                qty = round(qty, 8)
            if qty < step:
                return False

            res = place_order(symbol, d["side"], qty, self.api_key, self.api_secret)
            if res and "orderId" in res:
                exec_qty = float(res.get("executedQty", 0))
                avg_price = float(res.get("avgPrice", cur))
                if exec_qty >= 0:
                    total_qty = abs(d["qty"]) + exec_qty
                    new_entry = (
                        abs(d["qty"]) * d["entry"] + exec_qty * avg_price
                    ) / total_qty
                    d["entry"] = new_entry
                    d["qty"] = total_qty if d["side"] == "BUY" else -total_qty

                    msg = (
                        f"📈 <b>NHỒI LỆNH {symbol}</b>\n"
                        f"🔢 Lần nhồi: {d['average_down_count'] + 1}\n"
                        f"📊 Thêm: {exec_qty:.4f}\n"
                        f"🏷️ Giá nhồi: {avg_price:.4f}\n"
                        f"📈 Entry mới: {new_entry:.4f}\n"
                        f"💰 Tổng khối lượng: {total_qty:.4f}"
                    )
                    self.log(msg)
                    return True
            return False
        except Exception as e:
            self.log(f"❌ {symbol} lỗi _execute_symbol_average_down: {str(e)}")
            return False

    # =========================
    # DỪNG SYMBOL / BOT
    # =========================
    def stop_symbol(self, symbol):
        with self.symbol_management_lock:
            if symbol not in self.active_symbols:
                return False

            self.log(f"⛔ Dừng coin {symbol}...")

            if self.current_processing_symbol == symbol:
                timeout = time.time() + 10
                while self.current_processing_symbol == symbol and time.time() < timeout:
                    time.sleep(0.5)

            if self.symbol_data[symbol]["position_open"]:
                self._close_symbol_position(symbol, "Dừng coin theo lệnh")

            self.ws_manager.remove_symbol(symbol)
            self.coin_manager.unregister_coin(symbol)

            if symbol in self.symbol_data:
                del self.symbol_data[symbol]
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)

            self.log(f"✅ Đã dừng {symbol} | Còn lại {len(self.active_symbols)}/{self.max_coins}")

            if len(self.active_symbols) < self.max_coins:
                self.log(f"🔄 Tự tìm coin mới thay {symbol}...")
                threading.Thread(target=self._delayed_find_new_coin, daemon=True).start()
            return True

    def _delayed_find_new_coin(self):
        time.sleep(2)
        self._find_and_add_new_coin()

    def stop_all_symbols(self):
        self.log("⛔ Dừng tất cả coin...")
        to_stop = self.active_symbols.copy()
        stopped = 0
        for s in to_stop:
            if self.stop_symbol(s):
                stopped += 1
                time.sleep(1)
        self.log(f"✅ Đã dừng {stopped} coin, bot vẫn chạy (có thể thêm coin mới)")
        return stopped

    def stop(self):
        self._stop = True
        stopped = self.stop_all_symbols()
        self.log(f"🔴 Bot dừng - đã dừng {stopped} coin")

    # =========================
    # PHÂN TÍCH TOÀN TÀI KHOẢN
    # =========================
    def check_global_positions(self):
        try:
            pos = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            if not pos:
                self.global_long_count = 0
                self.global_short_count = 0
                self.global_long_pnl = 0
                self.global_short_pnl = 0
                return
            lc = sc = 0
            lpnl = spnl = 0
            for p in pos:
                amt = float(p.get("positionAmt", 0))
                upnl = float(p.get("unRealizedProfit", 0))
                if amt > 0:
                    lc += 1
                    lpnl += upnl
                elif amt < 0:
                    sc += 1
                    spnl += upnl
            self.global_long_count = lc
            self.global_short_count = sc
            self.global_long_pnl = lpnl
            self.global_short_pnl = spnl
        except Exception as e:
            if time.time() - self.last_error_log_time > 30:
                self.log(f"❌ Lỗi check_global_positions: {str(e)}")
                self.last_error_log_time = time.time()

    def get_next_side_based_on_comprehensive_analysis(self):
        self.check_global_positions()
        lp = self.global_long_pnl
        sp = self.global_short_pnl
        if lp > sp:
            return "BUY"
        elif sp > lp:
            return "SELL"
        else:
            return random.choice(["BUY", "SELL"])

    # =========================
    # LOG
    # =========================
    def log(self, message):
        important = ['❌', '✅', '⛔', '💰', '📈', '📊', '🎯', '🛡️', '🔴', '🟢', '⚠️', '🚫']
        if any(k in message for k in important):
            logger.warning(f"[{self.bot_id}] {message}")
            if self.telegram_bot_token and self.telegram_chat_id:
                send_telegram(
                    f"<b>{self.bot_id}</b>: {message}",
                    chat_id=self.telegram_chat_id,
                    bot_token=self.telegram_bot_token,
                    default_chat_id=self.telegram_chat_id
                )
# ========== BOT GLOBAL MARKET VỚI HỆ THỐNG RSI + KHỐI LƯỢNG ==========
class GlobalMarketBot(BaseBot):
    def __init__(self, symbol, lev, percent, tp, sl, roi_trigger, ws_manager,
                 api_key, api_secret, telegram_bot_token, telegram_chat_id, bot_id=None, **kwargs):
        super().__init__(symbol, lev, percent, tp, sl, roi_trigger, ws_manager,
                         api_key, api_secret, telegram_bot_token, telegram_chat_id,
                         "Hệ-thống-RSI-Khối-lượng", bot_id=bot_id, **kwargs)

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()

# ========== BOT MANAGER HOÀN CHỈNH VỚI HỆ THỐNG RSI + KHỐI LƯỢNG ==========
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

        # Kiểm tra API / Telegram
        self.configured = False
        if self.api_key and self.api_secret:
            self.configured = self._verify_api_connection()
        else:
            self.log("⚠️ Chưa cấu hình API Key/Secret")

        # Khởi động Telegram listener nếu có token
        if self.telegram_bot_token:
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
                self.log("   - API Key và Secret có đúng không")
                self.log("   - Tài khoản đã bật Futures chưa")
                self.log("   - IP / Quyền truy cập API")
                return False

            self.log(f"✅ Kết nối Binance thành công. Số dư USDC: {balance:.2f}")
            return True
        except Exception as e:
            self.log(f"❌ LỖI: Kiểm tra API thất bại: {str(e)}")
            return False

    # ========== LOG HỆ THỐNG ==========
    def log(self, message):
        prefix = "[MANAGER]"
        logger.warning(f"{prefix} {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(
                f"<b>{prefix}</b> {escape_html(message)}",
                chat_id=self.telegram_chat_id,
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

    # ========== GỬI MENU CHÍNH ==========
    def send_main_menu(self, chat_id):
        try:
            send_telegram(
                "📋 <b>Menu chính - Hệ thống RSI + Khối lượng</b>\n"
                "Chọn chức năng:",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
        except Exception as e:
            logger.error(f"Lỗi send_main_menu: {str(e)}")

    # ========== TELEGRAM LISTENER ==========
    def _telegram_listener(self):
        """
        Listener đơn giản, dùng long-polling để nhận update từ Telegram
        """
        self.log("📨 Bắt đầu lắng nghe Telegram updates...")
        offset = None

        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getUpdates"
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset

                resp = requests.get(url, params=params, timeout=35)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        for update in data.get("result", []):
                            offset = update["update_id"] + 1
                            self._handle_telegram_update(update)
                else:
                    logger.error(f"Lỗi getUpdates: {resp.status_code} {resp.text}")

            except Exception as e:
                logger.error(f"Lỗi trong telegram listener: {str(e)}")
                time.sleep(5)

    def _handle_telegram_update(self, update):
        """
        Xử lý tin nhắn từ Telegram
        """
        try:
            if "message" not in update:
                return

            msg = update["message"]
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "").strip()

            if chat_id not in self.user_states:
                self.user_states[chat_id] = {}

            state = self.user_states[chat_id]

            # Các lệnh slash
            if text.startswith("/start"):
                self._handle_start_command(chat_id, state)
                return
            elif text.startswith("/stop"):
                self._handle_stop_all_command(chat_id, state)
                return
            elif text.startswith("/status"):
                self._handle_status_command(chat_id, state)
                return

            # Nếu đang ở chế độ nhập từng bước
            if state.get("awaiting_input"):
                self._handle_step_input(chat_id, text, state)
            else:
                # Xử lý menu chính
                self._handle_main_menu(chat_id, text, state)

        except Exception as e:
            logger.error(f"Lỗi xử lý update: {str(e)}")

    # ========== XỬ LÝ COMMAND CƠ BẢN ==========
    def _handle_start_command(self, chat_id, state):
        self.user_states[chat_id] = {}
        send_telegram(
            "👋 <b>Chào mừng đến Hệ thống RSI + Khối lượng</b>\n"
            "Sử dụng menu để cấu hình và khởi động bot.",
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_stop_all_command(self, chat_id, state):
        stopped = 0
        for bot_id, bot in list(self.bots.items()):
            try:
                bot.stop()
                stopped += 1
            except Exception:
                pass
        self.bots.clear()

        send_telegram(
            f"⛔ Đã dừng toàn bộ {stopped} bot.",
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_status_command(self, chat_id, state):
        if not self.bots:
            send_telegram(
                "⚠️ <b>Hiện không có bot nào đang chạy.</b>",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        summary = "📊 <b>Trạng thái các bot đang chạy:</b>\n\n"
        for bot_id, bot in self.bots.items():
            uptime = time.time() - bot.bot_creation_time if hasattr(bot, 'bot_creation_time') else 0
            uptime_min = int(uptime // 60)

            summary += f"🤖 <b>{bot_id}</b>\n"
            summary += f"   ⏱️ Uptime: {uptime_min} phút\n"
            summary += f"   🔢 Số coin: {len(bot.active_symbols)}/{bot.max_coins}\n"

            if bot.active_symbols:
                summary += "   🔗 Coin đang chạy:\n"
                for sym in bot.active_symbols:
                    d = bot.symbol_data.get(sym, {})
                    st = "🟢 Đang trade" if d.get("position_open") else "🟡 Chờ tín hiệu"
                    side = d.get("side", "")
                    qty = d.get("qty", 0)
                    summary += f"    • {sym} | {st}"
                    if side:
                        summary += f" | {side} {abs(qty):.4f}"
                    summary += "\n"
            summary += "\n"

        send_telegram(
            summary,
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== XỬ LÝ MENU CHÍNH ==========
    def _handle_main_menu(self, chat_id, text, state):
        if text == "📊 Danh sách Bot":
            self._show_bot_list(chat_id, state)
        elif text == "➕ Thêm Bot":
            self._start_bot_creation(chat_id, state)
        elif text == "⛔ Dừng Bot":
            self._start_stop_bot_flow(chat_id, state)
        elif text == "💰 Số dư":
            self._show_balance(chat_id, state)
        elif text == "📈 Vị thế":
            self._show_positions(chat_id, state)
        elif text == "📊 Thống kê":
            self._show_system_stats(chat_id, state)
        elif text == "⚙️ Cấu hình":
            self._show_config_info(chat_id, state)
        elif text == "🎯 Chiến lược":
            self._show_strategy_info(chat_id, state)
        else:
            self.send_main_menu(chat_id)

    # ========== HIỂN THỊ DANH SÁCH BOT ==========
    def _show_bot_list(self, chat_id, state):
        if not self.bots:
            send_telegram(
                "⚠️ <b>Chưa có bot nào đang chạy.</b>",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        msg = "📊 <b>Danh sách Bot đang chạy:</b>\n\n"
        for bot_id, bot in self.bots.items():
            msg += f"🤖 <b>{bot_id}</b>\n"
            msg += f"   🔢 Số coin: {len(bot.active_symbols)}/{bot.max_coins}\n"
            if bot.active_symbols:
                msg += "   🔗 Coin: " + ", ".join(bot.active_symbols) + "\n"
            msg += "\n"

        send_telegram(
            msg,
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== KHỞI TẠO BOT MỚI ==========
    def _start_bot_creation(self, chat_id, state):
        state.clear()
        state["awaiting_input"] = True
        state["step"] = "select_strategy"

        keyboard = create_strategy_keyboard()
        send_telegram(
            "🎯 <b>Chọn chiến lược giao dịch:</b>",
            chat_id,
            keyboard,
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== DỪNG BOT ==========
    def _start_stop_bot_flow(self, chat_id, state):
        if not self.bots:
            send_telegram(
                "⚠️ <b>Không có bot nào để dừng.</b>",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state.clear()
        state["awaiting_input"] = True
        state["step"] = "select_bot_to_stop"

        keyboard = {
            "keyboard": [[{"text": bot_id}] for bot_id in self.bots.keys()] + [[{"text": "❌ Hủy bỏ"}]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

        send_telegram(
            "⛔ <b>Chọn Bot muốn dừng:</b>",
            chat_id,
            keyboard,
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== HIỂN THỊ SỐ DƯ ==========
    def _show_balance(self, chat_id, state):
        try:
            bal = get_balance(self.api_key, self.api_secret)
            if bal is None:
                msg = "❌ Không thể lấy số dư. Kiểm tra API."
            else:
                msg = f"💰 <b>Số dư USDC khả dụng:</b> {bal:.4f}"

            send_telegram(
                msg,
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
        except Exception as e:
            send_telegram(
                f"❌ Lỗi lấy số dư: {str(e)}",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

    # ========== HIỂN THỊ VỊ THẾ ==========
    def _show_positions(self, chat_id, state):
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            if not all_positions:
                send_telegram(
                    "ℹ️ <b>Không có vị thế nào đang mở.</b>",
                    chat_id,
                    create_main_menu(),
                    bot_token=self.telegram_bot_token,
                    default_chat_id=self.telegram_chat_id
                )
                return

            msg = "📈 <b>Các vị thế Futures đang mở:</b>\n\n"
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

                    side = "LONG" if position_amt > 0 else "SHORT"
                    msg += (
                        f"🔹 {symbol} | {side}\n"
                        f"   🔢 Số lượng: {abs(position_amt):.4f}\n"
                        f"   🏷️ Entry: {entry_price:.4f}\n"
                        f"   💰 Đòn bẩy: {leverage}x\n"
                        f"   💸 Giá trị (ước tính): {position_value:.4f} USDC\n"
                        f"   📊 PnL chưa chốt: {unrealized_pnl:.4f} USDC\n\n"
                    )

                    binance_positions.append(symbol)

            msg += f"📊 <b>Tổng PnL chưa chốt:</b> {total_unrealized_pnl:.4f} USDC\n\n"

            # Đối chiếu với bot nội bộ
            msg += "🤖 <b>Đối chiếu với Bot nội bộ:</b>\n"
            for bot_id, bot in self.bots.items():
                msg += f"\n🤖 <b>{bot_id}</b>\n"
                if bot.active_symbols:
                    for symbol in bot.active_symbols:
                        symbol_info = bot.symbol_data.get(symbol, {})
                        status = "🟢 Đang trade" if symbol_info.get('position_open') else "🟡 Chờ tín hiệu"
                        side = symbol_info.get('side', '')
                        qty = symbol_info.get('qty', 0)

                        msg += f"   🔗 {symbol} | {status}"
                        if side:
                            msg += f" | {side} {abs(qty):.4f}"
                        msg += "\n"
                else:
                    msg += "   ⚠️ Bot chưa có coin nào hoạt động.\n"

            send_telegram(
                msg,
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

        except Exception as e:
            send_telegram(
                f"❌ Lỗi lấy vị thế: {str(e)}",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

    # ========== THỐNG KÊ HỆ THỐNG ==========
    def _show_system_stats(self, chat_id, state):
        uptime = time.time() - self.start_time
        uptime_min = int(uptime // 60)
        bot_count = len(self.bots)

        msg = (
            "📊 <b>Thống kê hệ thống</b>\n"
            f"⏱️ Uptime: {uptime_min} phút\n"
            f"🤖 Số bot đang chạy: {bot_count}\n"
        )

        total_symbols = sum(len(bot.active_symbols) for bot in self.bots.values())
        msg += f"🔗 Tổng số coin đang chạy: {total_symbols}\n"

        send_telegram(
            msg,
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== THÔNG TIN CẤU HÌNH ==========
    def _show_config_info(self, chat_id, state):
        msg = (
            "⚙️ <b>Thông tin cấu hình</b>\n"
            f"🔐 API Key: {'Đã cấu hình' if self.api_key else 'Chưa cấu hình'}\n"
            f"📡 Telegram Bot: {'Đã cấu hình' if self.telegram_bot_token else 'Chưa cấu hình'}\n"
        )

        send_telegram(
            msg,
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== THÔNG TIN CHIẾN LƯỢC ==========
    def _show_strategy_info(self, chat_id, state):
        msg = (
            "🎯 <b>Chiến lược Hệ thống RSI + Khối lượng</b>\n\n"
            "- Phân tích RSI khung 5 phút kết hợp khối lượng tăng/giảm.\n"
            "- Tự động tìm coin theo USDC, ưu tiên volume lớn.\n"
            "- Giao dịch nối tiếp, tránh mở quá nhiều lệnh cùng lúc.\n"
            "- Tự nhồi lệnh theo Fibonacci khi âm sâu.\n"
            "- Hỗ trợ TP/SL và ROI Trigger thông minh.\n"
        )

        send_telegram(
            msg,
            chat_id,
            create_main_menu(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    # ========== XỬ LÝ TỪNG BƯỚC TẠO BOT ==========
    def _handle_step_input(self, chat_id, text, state):
        # Hủy bỏ
        if text == "❌ Hủy bỏ":
            self.user_states[chat_id] = {}
            send_telegram(
                "❌ Đã hủy thao tác.",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        step = state.get("step")

        if step == "select_strategy":
            self._handle_select_strategy(chat_id, text, state)
        elif step == "select_mode":
            self._handle_select_mode(chat_id, text, state)
        elif step == "select_symbols":
            self._handle_select_symbols(chat_id, text, state)
        elif step == "select_leverage":
            self._handle_select_leverage(chat_id, text, state)
        elif step == "select_percent":
            self._handle_select_percent(chat_id, text, state)
        elif step == "select_tp":
            self._handle_select_tp(chat_id, text, state)
        elif step == "select_sl":
            self._handle_select_sl(chat_id, text, state)
        elif step == "select_roi_trigger":
            self._handle_select_roi_trigger(chat_id, text, state)
        elif step == "select_bot_count":
            self._handle_select_bot_count(chat_id, text, state)
        elif step == "confirm_creation":
            self._handle_confirm_creation(chat_id, text, state)
        elif step == "select_bot_to_stop":
            self._handle_select_bot_to_stop(chat_id, text, state)
        else:
            self.user_states[chat_id] = {}
            self.send_main_menu(chat_id)

    # ========== CÁC BƯỚC TẠO BOT ==========
    def _handle_select_strategy(self, chat_id, text, state):
        if text == "📊 Hệ thống RSI + Khối lượng":
            state["strategy_type"] = "RSI_VOLUME"
            state["step"] = "select_mode"

            keyboard = create_bot_mode_keyboard()
            send_telegram(
                "🤖 <b>Chọn chế độ bot:</b>\n"
                "- Bot Tĩnh: chạy trên các coin cố định.\n"
                "- Bot Động: tự tìm coin mới theo tín hiệu.",
                chat_id,
                keyboard,
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
        else:
            send_telegram(
                "⚠️ Vui lòng chọn chiến lược hợp lệ.",
                chat_id,
                create_strategy_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

    def _handle_select_mode(self, chat_id, text, state):
        if text == "🤖 Bot Tĩnh - Coin cụ thể":
            state["mode"] = "static"
            state["step"] = "select_symbols"

            keyboard = create_symbols_keyboard()
            send_telegram(
                "🔗 <b>Chọn coin muốn chạy bot</b>\n"
                "Bạn có thể chọn nhiều coin, bot sẽ phân bổ theo tín hiệu.\n"
                "Nhập trực tiếp (VD: BTCUSDC,ETHUSDC) hoặc dùng nút.",
                chat_id,
                keyboard,
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

        elif text == "🔄 Bot Động - Tự tìm coin":
            state["mode"] = "dynamic"
            state["step"] = "select_leverage"

            send_telegram(
                "💥 <b>Chọn đòn bẩy</b>\n"
                "Hệ thống sẽ tự tìm coin phù hợp theo tín hiệu.",
                chat_id,
                create_leverage_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
        else:
            send_telegram(
                "⚠️ Vui lòng chọn chế độ hợp lệ.",
                chat_id,
                create_bot_mode_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

    def _handle_select_symbols(self, chat_id, text, state):
        if text == "❌ Hủy bỏ":
            self.user_states[chat_id] = {}
            self.send_main_menu(chat_id)
            return

        selected_symbols = []

        if "," in text:
            parts = text.split(",")
            for p in parts:
                s = p.strip().upper()
                if s.endswith("USDC"):
                    selected_symbols.append(s)
        else:
            if text.upper().endswith("USDC"):
                selected_symbols.append(text.upper())

        if not selected_symbols:
            send_telegram(
                "⚠️ Vui lòng nhập/ chọn ít nhất 1 coin USDC hợp lệ.",
                chat_id,
                create_symbols_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state["symbols"] = selected_symbols
        state["step"] = "select_leverage"

        send_telegram(
            "💥 <b>Chọn đòn bẩy</b>",
            chat_id,
            create_leverage_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_select_leverage(self, chat_id, text, state):
        if not text.endswith("x"):
            send_telegram(
                "⚠️ Vui lòng chọn đòn bẩy hợp lệ từ menu.",
                chat_id,
                create_leverage_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        try:
            lev = int(text.replace("x", ""))
            if lev <= 0 or lev > 125:
                raise ValueError("leverage out of range")
        except Exception:
            send_telegram(
                "⚠️ Đòn bẩy không hợp lệ. Vui lòng chọn lại.",
                chat_id,
                create_leverage_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state["leverage"] = lev
        state["step"] = "select_percent"

        send_telegram(
            "💵 <b>Chọn % vốn sử dụng cho mỗi lệnh</b>",
            chat_id,
            create_percent_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_select_percent(self, chat_id, text, state):
        try:
            percent = float(text)
            if percent <= 0 or percent > 100:
                raise ValueError("percent range")
        except Exception:
            send_telegram(
                "⚠️ Phần trăm vốn không hợp lệ. Nhập số (VD: 3, 5, 10).",
                chat_id,
                create_percent_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state["percent"] = percent
        state["step"] = "select_tp"

        send_telegram(
            "🎯 <b>Chọn TP (%)</b>\n"
            "VD: 50, 100, 200. (TP theo ROI, không phải giá tuyệt đối)",
            chat_id,
            create_tp_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_select_tp(self, chat_id, text, state):
        try:
            tp = float(text)
            if tp <= 0:
                tp = None
        except Exception:
            send_telegram(
                "⚠️ Vui lòng nhập TP hợp lệ (số dương).",
                chat_id,
                create_tp_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state["tp"] = tp
        state["step"] = "select_sl"

        send_telegram(
            "🛡️ <b>Chọn SL (%)</b>\n"
            "VD: 200 (tức lỗ 200% vốn ký quỹ sẽ cắt).",
            chat_id,
            create_sl_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_select_sl(self, chat_id, text, state):
        try:
            sl = float(text)
            if sl < 0:
                sl = None
        except Exception:
            send_telegram(
                "⚠️ Vui lòng nhập SL hợp lệ.",
                chat_id,
                create_sl_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state["sl"] = sl
        state["step"] = "select_roi_trigger"

        send_telegram(
            "🎯 <b>Chọn ROI Trigger (%)</b>\n"
            "Khi ROI vượt mức này và có tín hiệu đảo chiều, bot sẽ ưu tiên thoát lệnh.\n"
            "Chọn '❌ Tắt tính năng' để bỏ qua.",
            chat_id,
            create_roi_trigger_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_select_roi_trigger(self, chat_id, text, state):
        if text == "❌ Tắt tính năng":
            state["roi_trigger"] = None
        else:
            try:
                roi_trigger = float(text)
                if roi_trigger <= 0:
                    roi_trigger = None
                state["roi_trigger"] = roi_trigger
            except Exception:
                send_telegram(
                    "⚠️ Vui lòng nhập ROI Trigger hợp lệ hoặc chọn '❌ Tắt tính năng'.",
                    chat_id,
                    create_roi_trigger_keyboard(),
                    bot_token=self.telegram_bot_token,
                    default_chat_id=self.telegram_chat_id
                )
                return

        state["step"] = "select_bot_count"

        send_telegram(
            "🔢 <b>Chọn số coin tối đa bot sẽ chạy</b>\n"
            "VD: 1, 2, 3...",
            chat_id,
            create_bot_count_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_select_bot_count(self, chat_id, text, state):
        try:
            bot_count = int(text)
            if bot_count <= 0:
                raise ValueError("bot_count")
        except Exception:
            send_telegram(
                "⚠️ Vui lòng nhập số coin tối đa hợp lệ.",
                chat_id,
                create_bot_count_keyboard(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            return

        state["bot_count"] = bot_count
        state["step"] = "confirm_creation"

        strategy_type = state.get("strategy_type", "RSI_VOLUME")
        mode = state.get("mode", "static")
        symbols = state.get("symbols", [])
        lev = state.get("leverage")
        percent = state.get("percent")
        tp = state.get("tp")
        sl = state.get("sl")
        roi_trigger = state.get("roi_trigger")

        msg = (
            "✅ <b>Xác nhận tạo Bot mới:</b>\n\n"
            f"🎯 Chiến lược: {strategy_type}\n"
            f"🤖 Chế độ: {'Bot Tĩnh' if mode == 'static' else 'Bot Động'}\n"
            f"💥 Đòn bẩy: {lev}x\n"
            f"💵 Vốn mỗi lệnh: {percent}%\n"
            f"🎯 TP: {tp if tp is not None else 'Tắt'}%\n"
            f"🛡️ SL: {sl if sl is not None else 'Tắt'}%\n"
            f"🎯 ROI Trigger: {roi_trigger if roi_trigger is not None else 'Tắt'}%\n"
            f"🔢 Số coin tối đa: {bot_count}\n"
        )

        if mode == "static":
            msg += f"🔗 Coin: {', '.join(symbols)}\n"

        msg += "\nGõ 'OK' để xác nhận, hoặc '❌ Hủy bỏ' để hủy."

        send_telegram(
            msg,
            chat_id,
            create_cancel_keyboard(),
            bot_token=self.telegram_bot_token,
            default_chat_id=self.telegram_chat_id
        )

    def _handle_confirm_creation(self, chat_id, text, state):
        if text.upper() != "OK":
            self.user_states[chat_id] = {}
            self.send_main_menu(chat_id)
            return

        # Tạo bot theo state
        try:
            strategy_type = state.get("strategy_type", "RSI_VOLUME")
            mode = state.get("mode", "static")
            symbols = state.get("symbols", [])
            lev = state.get("leverage")
            percent = state.get("percent")
            tp = state.get("tp")
            sl = state.get("sl")
            roi_trigger = state.get("roi_trigger")
            bot_count = state.get("bot_count", 1)

            if not self.configured:
                send_telegram(
                    "❌ Chưa cấu hình API hợp lệ, không thể tạo bot.",
                    chat_id,
                    create_main_menu(),
                    bot_token=self.telegram_bot_token,
                    default_chat_id=self.telegram_chat_id
                )
                self.user_states[chat_id] = {}
                return

            if mode == "static" and not symbols:
                send_telegram(
                    "❌ Chưa chọn coin nào cho Bot Tĩnh.",
                    chat_id,
                    create_main_menu(),
                    bot_token=self.telegram_bot_token,
                    default_chat_id=self.telegram_chat_id
                )
                self.user_states[chat_id] = {}
                return

            created_count = 0

            if mode == "static":
                for sym in symbols:
                    bot_id = f"STATIC_{sym}_{int(time.time())}"
                    if bot_id in self.bots:
                        continue

                    bot_class = GlobalMarketBot

                    bot = bot_class(
                        sym, lev, percent, tp, sl, roi_trigger, self.ws_manager,
                        self.api_key, self.api_secret, self.telegram_bot_token, self.telegram_chat_id,
                        coin_manager=self.coin_manager,
                        symbol_locks=self.symbol_locks,
                        bot_id=bot_id,
                        max_coins=1
                    )

                    bot._bot_manager = self
                    self.bots[bot_id] = bot
                    created_count += 1

            elif mode == "dynamic":
                symbol = None

                if strategy_type == "RSI_VOLUME":
                    symbol = None

                if mode == 'static' and symbol:
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
            send_telegram(
                f"✅ Đã tạo thành công {created_count} bot.",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
        else:
            send_telegram(
                "⚠️ Không tạo được bot nào.",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

        self.user_states[chat_id] = {}

    def _handle_select_bot_to_stop(self, chat_id, text, state):
        if text not in self.bots:
            send_telegram(
                "⚠️ Bot không tồn tại hoặc đã dừng.",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
            self.user_states[chat_id] = {}
            return

        bot_id = text
        bot = self.bots.get(bot_id)
        if bot:
            bot.stop()
            del self.bots[bot_id]

            send_telegram(
                f"⛔ Đã dừng bot {bot_id}.",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )
        else:
            send_telegram(
                "⚠️ Không tìm thấy bot để dừng.",
                chat_id,
                create_main_menu(),
                bot_token=self.telegram_bot_token,
                default_chat_id=self.telegram_chat_id
            )

        self.user_states[chat_id] = {}

# ========== HÀM KHỞI ĐỘNG HỆ THỐNG ==========
def start_trading_system(api_key, api_secret, telegram_bot_token=None, telegram_chat_id=None):
    """Khởi động hệ thống giao dịch hoàn chỉnh"""
    try:
        logger.info("🚀 Đang khởi động Hệ thống RSI + Khối lượng...")

        # Tạo BotManager
        bot_manager = BotManager(
            api_key=api_key,
            api_secret=api_secret,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id
        )

        logger.info("✅ Hệ thống đã khởi động thành công!")
        return bot_manager

    except Exception as e:
        logger.error(f"❌ Lỗi khởi động hệ thống: {str(e)}")
        return None
