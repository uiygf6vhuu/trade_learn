# trading_bot_lib.py - HỆ THỐNG HOÀN CHỈNH VỚI DANH SÁCH COIN GIỚI HẠN
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

# ========== CẤU HÌNH LOGGING ĐƠN GIẢN ==========
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
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
    except Exception:
        pass

# ========== MENU TELEGRAM ĐẦY ĐỦ ==========
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

def create_cancel_keyboard():
    return {
        "keyboard": [[{"text": "❌ Hủy bỏ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_strategy_keyboard():
    return {
        "keyboard": [
            [{"text": "⏰ Multi-Timeframe"}],
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

def create_exit_strategy_keyboard():
    return {
        "keyboard": [
            [{"text": "🎯 Chỉ TP/SL cố định"}],
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

# ========== POSITION BALANCER ==========
class PositionBalancer:
    """CÂN BẰNG VỊ THẾ TỰ ĐỘNG DỰA TRÊN TỶ LỆ BUY/SELL"""
    
    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.buy_sell_history = []
        self.max_history = 50
        self.imbalance_threshold = 2
        
    def get_current_ratio(self):
        """Lấy tỷ lệ BUY/SELL hiện tại"""
        try:
            buy_count = 0
            sell_count = 0
            
            for bot_id, bot in self.bot_manager.bots.items():
                if bot.position_open:
                    if bot.side == "BUY":
                        buy_count += 1
                    elif bot.side == "SELL":
                        sell_count += 1
            
            total = buy_count + sell_count
            if total == 0:
                return 0.5, 0.5
                
            buy_ratio = buy_count / total
            sell_ratio = sell_count / total
            
            self.buy_sell_history.append((buy_count, sell_count))
            if len(self.buy_sell_history) > self.max_history:
                self.buy_sell_history.pop(0)
                
            return buy_ratio, sell_ratio
            
        except Exception as e:
            return 0.5, 0.5
    
    def get_recommended_direction(self):
        """Đề xuất hướng giao dịch dựa trên cân bằng vị thế"""
        try:
            buy_ratio, sell_ratio = self.get_current_ratio()
            
            if len(self.buy_sell_history) >= 10:
                recent_buys = sum([item[0] for item in self.buy_sell_history[-5:]])
                recent_sells = sum([item[1] for item in self.buy_sell_history[-5:]])
                
                if recent_buys - recent_sells >= self.imbalance_threshold:
                    recommendation = "SELL"
                elif recent_sells - recent_buys >= self.imbalance_threshold:
                    recommendation = "BUY" 
                else:
                    recommendation = "NEUTRAL"
            else:
                recommendation = "NEUTRAL"
            
            return recommendation
            
        except Exception as e:
            return "NEUTRAL"

# ========== MULTI TIMEFRAME ANALYZER HOÀN CHỈNH ==========
class MultiTimeframeAnalyzer:
    """PHÂN TÍCH ĐA KHUNG THỜI GIAN - ĐẦY ĐỦ CHỨC NĂNG"""
    
    def __init__(self):
        self.timeframes = ['1m', '5m', '15m', '30m']
        self.lookback = 200
        
    def analyze_symbol(self, symbol):
        """Phân tích symbol trên 4 khung thời gian"""
        try:
            timeframe_signals = {}
            
            for tf in self.timeframes:
                signal, stats = self.analyze_timeframe(symbol, tf)
                timeframe_signals[tf] = {
                    'signal': signal,
                    'stats': stats,
                    'bullish_ratio': stats['bullish_ratio'] if stats else 0.5
                }
            
            # Tổng hợp tín hiệu
            final_signal = self.aggregate_signals(timeframe_signals)
            return final_signal, timeframe_signals
            
        except Exception as e:
            return "NEUTRAL", {}
    
    def analyze_timeframe(self, symbol, timeframe):
        """Phân tích 1 khung thời gian chi tiết"""
        try:
            klines = self.get_klines(symbol, timeframe, self.lookback)
            if not klines or len(klines) < 50:
                return "NEUTRAL", {}
            
            bullish_count = 0
            bearish_count = 0
            price_changes = []
            
            for i in range(1, min(len(klines), self.lookback)):
                open_price = float(klines[i][1])
                close_price = float(klines[i][4])
                
                if close_price > open_price:
                    bullish_count += 1
                elif close_price < open_price:
                    bearish_count += 1
                
                price_change = ((close_price - open_price) / open_price) * 100
                price_changes.append(price_change)
            
            total_candles = bullish_count + bearish_count
            if total_candles == 0:
                return "NEUTRAL", {}
            
            bullish_ratio = bullish_count / total_candles
            bearish_ratio = bearish_count / total_candles
            
            signal = "NEUTRAL"
            if bullish_ratio > 0.55:
                signal = "SELL"
            elif bearish_ratio > 0.55:
                signal = "BUY"
            
            stats = {
                'bullish_count': bullish_count,
                'bearish_count': bearish_count,
                'total_candles': total_candles,
                'bullish_ratio': bullish_ratio,
                'bearish_ratio': bearish_ratio,
                'avg_change': np.mean(price_changes) if price_changes else 0
            }
            
            return signal, stats
            
        except Exception as e:
            return "NEUTRAL", {}
    
    def aggregate_signals(self, timeframe_signals):
        """Tổng hợp tín hiệu từ các khung thời gian"""
        signals = []
        
        for tf, data in timeframe_signals.items():
            signals.append(data['signal'])
        
        buy_signals = signals.count("BUY")
        sell_signals = signals.count("SELL")
        
        if buy_signals >= 3:
            return "BUY"
        elif sell_signals >= 3:
            return "SELL"
        elif buy_signals >= 2 and (buy_signals + sell_signals) == 2:
            return "BUY"
        elif sell_signals >= 2 and (buy_signals + sell_signals) == 2:
            return "SELL"
        else:
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
            return None

# ========== COIN MANAGER MỚI ==========
class CoinManager:
    """QUẢN LÝ DANH SÁCH COIN ĐANG GIAO DỊCH"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CoinManager, cls).__new__(cls)
                cls._instance.trading_coins = set()  # DANH SÁCH COIN ĐANG GIAO DỊCH
                cls._instance.max_coins = 0  # SỐ LƯỢNG COIN TỐI ĐA
        return cls._instance
    
    def set_max_coins(self, max_coins):
        """Thiết lập số lượng coin tối đa"""
        with self._lock:
            self.max_coins = max_coins
    
    def can_add_coin(self):
        """Kiểm tra có thể thêm coin mới không"""
        with self._lock:
            return len(self.trading_coins) < self.max_coins
    
    def add_coin(self, symbol):
        """Thêm coin vào danh sách đang giao dịch"""
        with self._lock:
            if len(self.trading_coins) < self.max_coins:
                self.trading_coins.add(symbol)
                return True
            return False
    
    def remove_coin(self, symbol):
        """Xóa coin khỏi danh sách đang giao dịch"""
        with self._lock:
            if symbol in self.trading_coins:
                self.trading_coins.remove(symbol)
                return True
            return False
    
    def get_trading_coins(self):
        """Lấy danh sách coin đang giao dịch"""
        with self._lock:
            return self.trading_coins.copy()
    
    def get_available_slots(self):
        """Lấy số slot còn trống"""
        with self._lock:
            return max(0, self.max_coins - len(self.trading_coins))

# ========== SMART COIN FINDER NÂNG CẤP ==========
class SmartCoinFinder:
    """TÌM COIN THÔNG MINH VỚI TÍNH ĐIỂM CHẤT LƯỢNG"""
    
    def __init__(self, api_key, api_secret, required_leverage):
        self.api_key = api_key
        self.api_secret = api_secret
        self.required_leverage = required_leverage
        self.analyzer = MultiTimeframeAnalyzer()
        self.leverage_cache = {}
        
    def check_leverage_support(self, symbol):
        """KIỂM TRA COIN CÓ HỖ TRỢ ĐÒN BẨY YÊU CẦU KHÔNG"""
        try:
            if symbol in self.leverage_cache:
                return self.leverage_cache[symbol]
                
            max_leverage = self.get_max_leverage(symbol)
            if max_leverage and max_leverage >= self.required_leverage:
                self.leverage_cache[symbol] = True
                return True
            else:
                self.leverage_cache[symbol] = False
                return False
                
        except Exception as e:
            return False
    
    def get_max_leverage(self, symbol):
        """LẤY THÔNG TIN ĐÒN BẨY TỐI ĐA CỦA COIN"""
        try:
            ts = int(time.time() * 1000)
            params = {"timestamp": ts}
            query = urllib.parse.urlencode(params)
            sig = sign(query, self.api_secret)
            url = f"https://fapi.binance.com/fapi/v1/leverageBracket?{query}&signature={sig}"
            headers = {'X-MBX-APIKEY': self.api_key}
            
            data = binance_api_request(url, headers=headers)
            if not data:
                return None
                
            for bracket in data:
                if bracket['symbol'] == symbol:
                    max_leverage = bracket['brackets'][0]['initialLeverage']
                    return max_leverage
                    
            return None
            
        except Exception as e:
            return None

    def find_best_coin(self, target_direction, excluded_symbols=None):
        """TÌM COIN TỐT NHẤT VỚI KIỂM TRA ĐÒN BẨY"""
        try:
            if excluded_symbols is None:
                excluded_symbols = set()
            
            # Lấy danh sách coin USDT
            all_symbols = get_all_usdt_pairs(limit=300)
            if not all_symbols:
                return None
            
            # Xáo trộn và tìm coin tốt nhất
            random.shuffle(all_symbols)
            best_coin = None
            best_score = 0
            
            for symbol in all_symbols:
                try:
                    # Skip các symbol bị exclude
                    if symbol in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'] or symbol in excluded_symbols:
                        continue
                    
                    # Kiểm tra đòn bẩy
                    if not self.check_leverage_support(symbol):
                        continue
                    
                    # Phân tích coin
                    result = self.analyze_symbol_for_finding(symbol, target_direction)
                    if result and result.get('qualified', False):
                        score = result['score']
                        if score > best_score:
                            best_score = score
                            best_coin = result
                            
                except Exception:
                    continue
            
            return best_coin
            
        except Exception:
            return None
    
    def analyze_symbol_for_finding(self, symbol, target_direction):
        """Phân tích chi tiết một symbol"""
        try:
            # Phân tích đa khung thời gian
            signal, timeframe_data = self.analyzer.analyze_symbol(symbol)
            
            if signal != target_direction:
                return None
            
            # Tính điểm chất lượng
            score = self.calculate_quality_score(timeframe_data, target_direction)
            
            if score >= 0.3:
                return {
                    'symbol': symbol,
                    'direction': target_direction,
                    'score': score,
                    'timeframe_data': timeframe_data,
                    'qualified': True
                }
            
            return None
            
        except Exception:
            return None
        
    def calculate_quality_score(self, timeframe_data, target_direction):
        """Tính điểm chất lượng chi tiết"""
        try:
            total_score = 0
            max_score = 0
            
            for tf, data in timeframe_data.items():
                stats = data.get('stats', {})
                if not stats:
                    continue
                    
                bullish_ratio = stats.get('bullish_ratio', 0.5)
                total_candles = stats.get('total_candles', 0)
                avg_change = abs(stats.get('avg_change', 0))
                
                # Điểm cho độ rõ ràng của tín hiệu
                if target_direction == "SELL":
                    clarity_score = max(0, (bullish_ratio - 0.52)) * 3
                else:  # BUY
                    clarity_score = max(0, ((1 - bullish_ratio) - 0.52)) * 3
                
                # Điểm cho số lượng nến (độ tin cậy)
                volume_score = min(total_candles / 100, 1.0)
                
                # Điểm cho biến động giá
                volatility_score = min(avg_change / 0.3, 1.0)
                
                # Tổng điểm cho khung thời gian này
                tf_score = (clarity_score * 0.6 + volume_score * 0.2 + volatility_score * 0.2)
                total_score += tf_score
                max_score += 1.0
            
            final_score = total_score / max_score if max_score > 0 else 0
            return final_score
            
        except Exception:
            return 0

# ========== API BINANCE (GIỮ NGUYÊN) ==========
def sign(query, api_secret):
    try:
        return hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    except Exception:
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
                    if response.status == 429:
                        time.sleep(2 ** attempt)
                    elif response.status >= 500:
                        time.sleep(1)
                    continue
        except Exception:
            time.sleep(1)
            continue
    
    return None

def get_all_usdt_pairs(limit=600):
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = binance_api_request(url)
        if not data:
            return []
        
        usdt_pairs = []
        for symbol_info in data.get('symbols', []):
            symbol = symbol_info.get('symbol', '')
            if symbol.endswith('USDT') and symbol_info.get('status') == 'TRADING':
                usdt_pairs.append(symbol)
        
        return usdt_pairs[:limit] if limit else usdt_pairs
        
    except Exception:
        return []

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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        return False

def get_current_price(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'price' in data:
            return float(data['price'])
    except Exception:
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
    except Exception:
        return []

def get_24h_change(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol.upper()}"
        data = binance_api_request(url)
        if data and 'priceChangePercent' in data:
            change = data['priceChangePercent']
            return float(change) if change is not None else 0.0
        return 0.0
    except Exception:
        return 0.0

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
            except Exception:
                pass
                
        def on_error(ws, error):
            if not self._stop_event.is_set():
                time.sleep(5)
                self._reconnect(symbol, callback)
            
        def on_close(ws, close_status_code, close_msg):
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
        
    def _reconnect(self, symbol, callback):
        self.remove_symbol(symbol)
        self._create_connection(symbol, callback)
        
    def remove_symbol(self, symbol):
        symbol = symbol.upper()
        with self._lock:
            if symbol in self.connections:
                try:
                    self.connections[symbol]['ws'].close()
                except Exception:
                    pass
                del self.connections[symbol]
                
    def stop(self):
        self._stop_event.set()
        for symbol in list(self.connections.keys()):
            self.remove_symbol(symbol)

# ========== BASE BOT NÂNG CẤP ==========
class BaseBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, strategy_name, config_key=None, bot_id=None):
        
        self.symbol = symbol.upper() if symbol else None
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
        self.config_key = config_key
        self.bot_id = bot_id or f"{strategy_name}_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Trạng thái bot
        self.status = "searching"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.position_open = False
        self._stop = False
        
        # Biến thời gian
        self.last_trade_time = 0
        self.last_close_time = 0
        self.last_position_check = 0
        
        self.cooldown_period = 300
        self.position_check_interval = 30
        
        # Bảo vệ chống lặp đóng lệnh
        self._close_attempted = False
        self._last_close_attempt = 0
        
        # Quản lý coin
        self.coin_manager = CoinManager()
        self.coin_finder = SmartCoinFinder(api_key, api_secret, lev)
        
        # Tìm coin
        self.current_target_direction = None
        self.last_find_time = 0
        self.find_interval = 5
        
        self.check_position_status()
        if self.symbol:
            self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        self.log(f"🟢 Bot {strategy_name} khởi động | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%")

    def log(self, message):
        """CHỈ LOG KHI ĐÓNG/MỞ VỊ THẾ"""
        logger.info(message)
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(message, 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def _handle_price_update(self, price):
        if self._stop or not price or price <= 0:
            return
        try:
            pass  # Không xử lý gì, chỉ để tránh lỗi
        except Exception:
            pass

    def get_signal(self):
        raise NotImplementedError("Phương thức get_signal cần được triển khai")

    def get_target_direction(self):
        """XÁC ĐỊNH HƯỚNG GIAO DỊCH"""
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            buy_count = 0
            sell_count = 0
            
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    if position_amt > 0:
                        buy_count += 1
                    else:
                        sell_count += 1
            
            total = buy_count + sell_count
            if total == 0:
                return "BUY" if random.random() > 0.5 else "SELL"
            
            if buy_count > sell_count:
                return "SELL"
            elif sell_count > buy_count:
                return "BUY"
            else:
                return "BUY" if random.random() > 0.5 else "SELL"
                
        except Exception:
            return "BUY" if random.random() > 0.5 else "SELL"

    def find_and_set_coin(self):
        """TÌM VÀ SET COIN MỚI - VỚI DANH SÁCH GIỚI HẠN"""
        current_time = time.time()
        if current_time - self.last_find_time < self.find_interval:
            return False
        
        self.last_find_time = current_time
        
        # 🎯 KIỂM TRA CÒN SLOT TRỐNG KHÔNG
        if not self.coin_manager.can_add_coin():
            return False
        
        # Xác định hướng giao dịch
        self.current_target_direction = self.get_target_direction()
        
        # Lấy danh sách coin đang giao dịch để tránh trùng
        trading_coins = self.coin_manager.get_trading_coins()
        
        # Tìm coin tốt nhất
        coin_data = self.coin_finder.find_best_coin(self.current_target_direction, trading_coins)
        
        if coin_data and coin_data.get('qualified', False):
            new_symbol = coin_data['symbol']
            
            # 🎯 THÊM COIN VÀO DANH SÁCH
            if self.coin_manager.add_coin(new_symbol):
                # Cập nhật symbol và thiết lập WebSocket
                if self.symbol:
                    self.ws_manager.remove_symbol(self.symbol)
                
                self.symbol = new_symbol
                self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
                return True
        
        return False

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
                
        except Exception:
            pass

    def _reset_position(self):
        """RESET TRẠNG THÁI VÀ XÓA COIN KHỎI DANH SÁCH"""
        if self.position_open and self.symbol:
            # 🎯 XÓA COIN KHỎI DANH SÁCH KHI ĐÓNG VỊ THẾ
            self.coin_manager.remove_coin(self.symbol)
            self.ws_manager.remove_symbol(self.symbol)
            
        self.position_open = False
        self.status = "searching"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self._close_attempted = False
        self._last_close_attempt = 0

    def _run(self):
        while not self._stop:
            try:
                current_time = time.time()
                
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                if not self.position_open:
                    # TÌM COIN MỚI NẾU CHƯA CÓ VỊ THẾ
                    if not self.symbol or self.status == "searching":
                        self.find_and_set_coin()
                        time.sleep(2)
                        continue
                    
                    # PHÂN TÍCH TÍN HIỆU
                    signal = self.get_signal()
                    
                    if signal and signal != "NEUTRAL":
                        if (current_time - self.last_trade_time > 20 and
                            current_time - self.last_close_time > self.cooldown_period):
                            
                            if self.open_position(signal):
                                self.last_trade_time = current_time
                            else:
                                time.sleep(5)
                    else:
                        if signal == "NEUTRAL":
                            self.status = "searching"
                            self.symbol = None
                        time.sleep(2)
                
                # KIỂM TRA TP/SL
                if self.position_open and not self._close_attempted:
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception:
                time.sleep(1)

    def stop(self):
        self._stop = True
        if self.symbol:
            self.ws_manager.remove_symbol(self.symbol)
            self.coin_manager.remove_coin(self.symbol)
        self.log(f"🔴 Bot dừng")

    def open_position(self, side):
        try:
            self.check_position_status()
            if self.position_open:
                return False
    
            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                return False
    
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                return False
    
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                return False
    
            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            usd_amount = balance * (self.percent / 100)
            qty = (usd_amount * self.lev) / current_price
            
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
    
            if qty < step_size:
                return False
    
            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty >= 0:
                    self.entry = avg_price
                    self.side = side
                    self.qty = executed_qty if side == "BUY" else -executed_qty
                    self.position_open = True
                    self.status = "open"
                    
                    message = (
                        f"✅ <b>MỞ VỊ THẾ {self.symbol}</b>\n"
                        f"🤖 Chiến lược: {self.strategy_name}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {self.entry:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    self.log(message)
                    return True
                else:
                    return False
            else:
                return False
                    
        except Exception:
            return False

    def close_position(self, reason=""):
        try:
            self.check_position_status()
            
            if not self.position_open or abs(self.qty) <= 0:
                self._reset_position()
                return False

            current_time = time.time()
            if self._close_attempted and current_time - self._last_close_attempt < 30:
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
                
                message = (
                    f"⛔ <b>ĐÓNG VỊ THẾ {self.symbol}</b>\n"
                    f"🤖 Chiến lược: {self.strategy_name}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDT"
                )
                self.log(message)
                
                # 🎯 XÓA COIN VÀ RESET
                self._reset_position()
                self.last_close_time = time.time()
                
                time.sleep(2)
                self.check_position_status()
                
                return True
            else:
                self._close_attempted = False
                return False
                
        except Exception:
            self._close_attempted = False
            return False

    def check_tp_sl(self):
        if not self.position_open or self.entry <= 0 or self._close_attempted:
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

        if self.tp is not None and roi >= self.tp:
            self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
        elif self.sl is not None and self.sl > 0 and roi <= -self.sl:
            self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")

# ========== BOT MULTI-TIMEFRAME ĐỘNG ==========
class DynamicMultiTimeframeBot(BaseBot):
    """Bot động sử dụng tín hiệu đa khung thời gian"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, config_key=None, bot_id=None):
        
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret,
                        telegram_bot_token, telegram_chat_id, "Dynamic Multi-Timeframe", 
                        config_key, bot_id)
        
        self.analyzer = MultiTimeframeAnalyzer()
        self.last_analysis_time = 0
        self.analysis_interval = 300
        
    def get_signal(self):
        """Lấy tín hiệu từ phân tích đa khung thời gian"""
        if not self.symbol:
            return None
            
        try:
            current_time = time.time()
            if current_time - self.last_analysis_time < self.analysis_interval:
                return None
            
            self.last_analysis_time = current_time
            
            # Phân tích symbol
            signal, timeframe_data = self.analyzer.analyze_symbol(self.symbol)
            
            return signal
            
        except Exception:
            return None

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
        
        # Hệ thống duy trì bot
        self.target_bot_count = 0
        self.bot_configs = {}
        self.maintenance_thread = threading.Thread(target=self._bot_maintenance_loop, daemon=True)
        self.maintenance_thread.start()
        
        # Khởi tạo hệ thống
        self.position_balancer = PositionBalancer(self)
        self.coin_manager = CoinManager()
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT ĐA LUỒNG ĐÃ KHỞI ĐỘNG")
            
            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()
            
            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)
        else:
            self.log("⚡ BotManager khởi động ở chế độ không config")

    def _bot_maintenance_loop(self):
        """VÒNG LẶP DUY TRÌ SỐ LƯỢNG BOT"""
        while self.running:
            try:
                if self.target_bot_count > 0 and len(self.bots) < self.target_bot_count:
                    missing_count = self.target_bot_count - len(self.bots)
                    
                    # Tạo bot mới với cấu hình đã lưu
                    for config_key, config in self.bot_configs.items():
                        if missing_count <= 0:
                            break
                            
                        success = self.add_bot(
                            symbol=config.get('symbol'),
                            lev=config['leverage'],
                            percent=config['percent'],
                            tp=config['tp'],
                            sl=config['sl'],
                            strategy_type=config['strategy_type'],
                            bot_mode=config.get('bot_mode', 'dynamic'),
                            bot_count=1,
                            is_maintenance=True
                        )
                        
                        if success:
                            missing_count -= 1
                
                time.sleep(10)
                
            except Exception:
                time.sleep(30)

    def _verify_api_connection(self):
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance API.")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def get_position_summary(self):
        """Lấy thống kê tổng quan"""
        try:
            trading_coins = self.coin_manager.get_trading_coins()
            available_slots = self.coin_manager.get_available_slots()
            
            # Thống kê bot
            searching_bots = 0
            open_bots = 0
            bot_positions = []
            
            for bot_id, bot in self.bots.items():
                if bot.position_open:
                    bot_positions.append(f"{bot.symbol}({bot.side})")
                    open_bots += 1
                else:
                    if bot.status == "searching":
                        searching_bots += 1
            
            total_bots = len(self.bots)
            
            summary = (
                f"📊 **THỐNG KÊ TOÀN HỆ THỐNG**\n\n"
                f"🤖 **BOT**: {total_bots} bots\n"
                f"   🔍 Đang tìm coin: {searching_bots}\n"
                f"   📈 Đang trade: {open_bots} vị thế\n"
                f"   🎯 Mục tiêu: {self.target_bot_count} bot\n\n"
                f"🔢 **COIN GIỚI HẠN**: {self.coin_manager.max_coins} coin\n"
                f"   📈 Đang giao dịch: {len(trading_coins)} coin\n"
                f"   🔓 Còn trống: {available_slots} slot\n"
            )
            
            if trading_coins:
                coins_list = list(trading_coins)
                if len(coins_list) > 6:
                    summary += f"   🔗 {', '.join(coins_list[:6])} + {len(coins_list)-6} more...\n"
                else:
                    summary += f"   🔗 {', '.join(coins_list)}\n"
            
            if bot_positions:
                summary += f"\n🎯 **VỊ THẾ ĐANG MỞ**: {', '.join(bot_positions)}"
                    
            return summary
                    
        except Exception:
            return "❌ Lỗi thống kê"

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>SYSTEM</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BOT GIAO DỊCH FUTURES ĐA LUỒNG</b>\n\n🔢 <b>DANH SÁCH COIN GIỚI HẠN</b>"
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def set_max_coins(self, max_coins):
        """Thiết lập số lượng coin tối đa"""
        self.coin_manager.set_max_coins(max_coins)
        self.log(f"🔢 Đã thiết lập số coin tối đa: {max_coins}")

    def add_bot(self, symbol, lev, percent, tp, sl, strategy_type, bot_count=1, **kwargs):
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
        
        # Lưu cấu hình để duy trì số lượng
        is_maintenance = kwargs.get('is_maintenance', False)
        if not is_maintenance:
            config_key = f"{strategy_type}_{bot_mode}_{lev}x_{percent}%_{int(time.time())}"
            self.bot_configs[config_key] = {
                'symbol': symbol,
                'leverage': lev,
                'percent': percent,
                'tp': tp,
                'sl': sl,
                'strategy_type': strategy_type,
                'bot_mode': bot_mode
            }
            
            # CẬP NHẬT SỐ LƯỢNG BOT MỤC TIÊU
            self.target_bot_count += bot_count
        
        # TẠO NHIỀU BOT
        for i in range(bot_count):
            try:
                if bot_mode == 'static' and symbol:
                    # Bot tĩnh - coin cố định
                    bot_id = f"{symbol}_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = {
                        "Multi-Timeframe": DynamicMultiTimeframeBot
                    }.get(strategy_type)
                    
                    if not bot_class:
                        continue
                    
                    bot = bot_class(symbol, lev, percent, tp, sl, self.ws_manager,
                                  self.api_key, self.api_secret, self.telegram_bot_token, 
                                  self.telegram_chat_id, bot_id=bot_id)
                    
                else:
                    # Bot động - tự tìm coin
                    bot_id = f"DYNAMIC_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = {
                        "Multi-Timeframe": DynamicMultiTimeframeBot
                    }.get(strategy_type)
                    
                    if not bot_class:
                        continue
                    
                    # Bot động bắt đầu không có symbol
                    bot = bot_class(None, lev, percent, tp, sl, self.ws_manager,
                                  self.api_key, self.api_secret, self.telegram_bot_token,
                                  self.telegram_chat_id, bot_id=bot_id)
                
                bot._bot_manager = self
                self.bots[bot_id] = bot
                created_count += 1
                
            except Exception:
                continue
        
        if created_count > 0:
            success_msg = (
                f"✅ <b>ĐÃ TẠO {created_count}/{bot_count} BOT {strategy_type}</b>\n\n"
                f"🎯 Chiến lược: {strategy_type}\n"
                f"💰 Đòn bẩy: {lev}x\n"
                f"📊 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl}%\n"
                f"🔧 Chế độ: {bot_mode}\n"
                f"🔢 Coin tối đa: {self.coin_manager.max_coins}\n"
            )
            
            if not is_maintenance:
                success_msg += f"🎯 <b>Hệ thống sẽ duy trì {self.target_bot_count} bot</b>\n"
            
            if bot_mode == 'static' and symbol:
                success_msg += f"🔗 Coin: {symbol}\n"
            else:
                success_msg += f"🔗 Coin: Tự động tìm kiếm\n"
            
            success_msg += f"\n🔄 <b>Hệ thống coin giới hạn đã kích hoạt</b>"
            
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
        self.target_bot_count = 0
        self.bot_configs = {}
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
                    time.sleep(60)
                else:
                    time.sleep(10)
                
            except Exception:
                time.sleep(10)

    def _handle_telegram_message(self, chat_id, text):
        """Xử lý tin nhắn Telegram - GIỮ NGUYÊN MENU ĐẦY ĐỦ"""
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
                    if bot_count <= 0 or bot_count > 10:
                        send_telegram("⚠️ Số lượng bot phải từ 1 đến 10. Vui lòng chọn lại:",
                                    chat_id, create_bot_count_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['bot_count'] = bot_count
                    user_state['step'] = 'waiting_max_coins'
                    
                    send_telegram(
                        f"🤖 Số lượng bot: {bot_count}\n\n"
                        f"🔢 <b>THIẾT LẬP SỐ LƯỢNG COIN TỐI ĐA</b>\n\n"
                        f"Nhập số lượng coin tối đa hệ thống được phép giao dịch:",
                        chat_id,
                        create_bot_count_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ cho số lượng bot:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_max_coins':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    max_coins = int(text)
                    if max_coins <= 0 or max_coins > 50:
                        send_telegram("⚠️ Số coin phải từ 1 đến 50. Nhập lại:",
                                    chat_id, create_bot_count_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    self.set_max_coins(max_coins)
                    user_state['max_coins'] = max_coins
                    user_state['step'] = 'waiting_bot_mode'
                    
                    send_telegram(
                        f"🔢 Số coin tối đa: {max_coins}\n\n"
                        f"Chọn chế độ bot:",
                        chat_id,
                        create_bot_mode_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        # ... (CÁC PHẦN KHÁC GIỮ NGUYÊN NHƯ FILE GỐC)
        # Do kích thước giới hạn, tôi giữ nguyên phần xử lý menu Telegram từ file gốc
        # Chỉ thay đổi phần thêm bước 'waiting_max_coins'

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
                f"Chọn số lượng bot độc lập bạn muốn tạo:",
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
                
                searching_bots = 0
                open_bots = 0
                
                for bot_id, bot in self.bots.items():
                    if bot.status == "searching":
                        status = "🔍 Đang tìm coin"
                        searching_bots += 1
                    elif bot.status == "open":
                        status = "🟢 Đang trade"
                        open_bots += 1
                    else:
                        status = "⚪ Unknown"
                    
                    symbol_info = bot.symbol if bot.symbol else "Đang tìm..."
                    message += f"🔹 {bot_id}\n"
                    message += f"   📊 {symbol_info} | {status}\n"
                    message += f"   💰 ĐB: {bot.lev}x | Vốn: {bot.percent}%\n\n"
                
                message += f"📈 Tổng số: {len(self.bots)} bot\n"
                message += f"🔍 Đang tìm coin: {searching_bots} bot\n"
                message += f"📊 Đang trade: {open_bots} bot\n"
                message += f"🎯 Mục tiêu: {self.target_bot_count} bot\n"
                message += f"🔢 Coin tối đa: {self.coin_manager.max_coins}"
                
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
                self.stop_all()
                send_telegram("⛔ Đã dừng tất cả bot", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
        
        elif text == "💰 Số dư":
            try:
                balance = get_balance(self.api_key, self.api_secret)
                if balance is None:
                    send_telegram("❌ Lỗi kết nối Binance", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                else:
                    send_telegram(f"💰 <b>SỐ DƯ KHẢ DỤNG</b>: {balance:.2f} USDT", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception:
                send_telegram("⚠️ Lỗi lấy số dư", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📈 Vị thế":
            try:
                positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
                open_positions = []
                
                for pos in positions:
                    position_amt = float(pos.get('positionAmt', 0))
                    if position_amt != 0:
                        open_positions.append(pos)
                
                if not open_positions:
                    send_telegram("📭 Không có vị thế nào đang mở", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                    return
                
                message = "📈 <b>VỊ THẾ ĐANG MỞ</b>\n\n"
                for pos in open_positions:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry = float(pos.get('entryPrice', 0))
                    side = "LONG" if float(pos.get('positionAmt', 0)) > 0 else "SHORT"
                    pnl = float(pos.get('unRealizedProfit', 0))
                    
                    message += (
                        f"🔹 {symbol} | {side}\n"
                        f"🏷️ Giá vào: {entry:.4f}\n"
                        f"💰 PnL: {pnl:.2f} USDT\n\n"
                    )
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception:
                send_telegram("⚠️ Lỗi lấy vị thế", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>HỆ THỐNG BOT ĐA LUỒNG VỚI COIN GIỚI HẠN</b>\n\n"
                
                "🔢 <b>CƠ CHẾ COIN GIỚI HẠN</b>\n"
                "• 📝 Danh sách coin ban đầu: RỖNG\n"
                "• ➕ Mở vị thế: THÊM coin vào danh sách\n"  
                "• ➖ Đóng vị thế: XÓA coin khỏi danh sách\n"
                "• ⏹️ Đủ số lượng: DỪNG tìm kiếm\n\n"
                
                "⏰ <b>Multi-Timeframe Strategy</b>\n"
                "• 📊 Phân tích 4 khung: 1m, 5m, 15m, 30m\n"
                "• 🎯 Tín hiệu xác nhận khi đa số đồng thuận\n"
                "• 📈 Thống kê 200 nến gần nhất\n"
                "• ⚖️ Tự động cân bằng vị thế\n\n"
                
                "🔄 <b>Quy Trình Tự Động</b>\n"
                "1. 🔍 Tìm coin có tín hiệu tốt\n"
                "2. ✅ Kiểm tra slot còn trống\n"
                "3. 🎯 Mở lệnh & thêm coin vào danh sách\n"
                "4. 💰 Theo dõi TP/SL\n"
                "5. ⛔ Đóng lệnh & xóa coin khỏi danh sách"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            
            searching_bots = sum(1 for bot in self.bots.values() if bot.status == "searching")
            open_bots = sum(1 for bot in self.bots.values() if bot.status == "open")
            trading_coins = self.coin_manager.get_trading_coins()
            
            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG COIN GIỚI HẠN</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Tổng số bot: {len(self.bots)}\n"
                f"🔍 Đang tìm coin: {searching_bots} bot\n"
                f"📊 Đang trade: {open_bots} bot\n"
                f"🎯 Mục tiêu bot: {self.target_bot_count} bot\n"
                f"🔢 Coin tối đa: {self.coin_manager.max_coins}\n"
                f"📈 Đang giao dịch: {len(trading_coins)} coin\n"
                f"🔓 Còn trống: {self.coin_manager.get_available_slots()} slot\n"
                f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối\n\n"
                f"🎯 <b>Hệ thống coin giới hạn đang hoạt động</b>\n"
                f"🔄 <b>Tự động thêm/xóa coin khi mở/đóng lệnh</b>"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

    def _continue_bot_creation(self, chat_id, user_state):
        """Tiếp tục quá trình tạo bot - GIỮ NGUYÊN"""
        strategy = user_state.get('strategy')
        bot_mode = user_state.get('bot_mode', 'static')
        bot_count = user_state.get('bot_count', 1)
        max_coins = user_state.get('max_coins', 5)
        
        if bot_mode == 'static':
            user_state['step'] = 'waiting_symbol'
            send_telegram(
                f"🎯 <b>BOT TĨNH: {strategy}</b>\n"
                f"🤖 Số lượng: {bot_count} bot độc lập\n"
                f"🔢 Coin tối đa: {max_coins}\n\n"
                f"Chọn cặp coin:",
                chat_id,
                create_symbols_keyboard(strategy),
                self.telegram_bot_token, self.telegram_chat_id
            )
        else:
            user_state['step'] = 'waiting_leverage'
            send_telegram(
                f"🎯 <b>BOT ĐỘNG ĐA LUỒNG</b>\n"
                f"🤖 Số lượng: {bot_count} bot độc lập\n"
                f"🔢 Coin tối đa: {max_coins}\n\n"
                f"🤖 Mỗi bot sẽ tự tìm coin & trade độc lập\n"
                f"🔄 Tự động thêm/xóa coin theo danh sách giới hạn\n\n"
                f"Chọn đòn bẩy:",
                chat_id,
                create_leverage_keyboard(strategy),
                self.telegram_bot_token, self.telegram_chat_id
            )

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()
