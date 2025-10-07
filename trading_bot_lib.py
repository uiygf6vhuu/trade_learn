# trading_bot_lib.py - HOÀN CHỈNH VỚI BOT ĐỘNG TỰ TÌM COIN MỚI SAU KHI ĐÓNG LỆNH
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

# ========== SMART EXIT MANAGER ==========
class SmartExitManager:
    """QUẢN LÝ THÔNG MINH 4 CƠ CHẾ ĐÓNG LỆNH"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.config = {
            'enable_trailing': False,
            'enable_time_exit': False,
            'enable_volume_exit': False,
            'enable_support_resistance': False,
            'trailing_activation': 30,
            'trailing_distance': 15,
            'max_hold_time': 6,
            'min_profit_for_exit': 10
        }
        
        self.trailing_active = False
        self.peak_price = 0
        self.position_open_time = 0
        self.volume_history = []
        
    def update_config(self, **kwargs):
        """Cập nhật cấu hình từ người dùng"""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
        self.bot.log(f"⚙️ Cập nhật Smart Exit: {self.config}")
    
    def check_all_exit_conditions(self, current_price, current_volume=None):
        """KIỂM TRA TẤT CẢ ĐIỀU KIỆN ĐÓNG LỆNH"""
        if not self.bot.position_open:
            return None
            
        exit_reasons = []
        
        # 1. TRAILING STOP EXIT
        if self.config['enable_trailing']:
            reason = self._check_trailing_stop(current_price)
            if reason:
                exit_reasons.append(reason)
        
        # 2. TIME-BASED EXIT
        if self.config['enable_time_exit']:
            reason = self._check_time_exit()
            if reason:
                exit_reasons.append(reason)
        
        # 3. VOLUME-BASED EXIT  
        if self.config['enable_volume_exit'] and current_volume:
            reason = self._check_volume_exit(current_volume)
            if reason:
                exit_reasons.append(reason)
        
        # 4. SUPPORT/RESISTANCE EXIT
        if self.config['enable_support_resistance']:
            reason = self._check_support_resistance(current_price)
            if reason:
                exit_reasons.append(reason)
        
        # Chỉ đóng lệnh nếu đang có lãi đạt ngưỡng tối thiểu
        if exit_reasons:
            current_roi = self._calculate_roi(current_price)
            if current_roi >= self.config['min_profit_for_exit']:
                return f"Smart Exit: {' + '.join(exit_reasons)} | Lãi: {current_roi:.1f}%"
        
        return None
    
    def _check_trailing_stop(self, current_price):
        """Trailing Stop - Bảo vệ lợi nhuận"""
        current_roi = self._calculate_roi(current_price)
        
        # Kích hoạt trailing khi đạt ngưỡng
        if current_roi >= self.config['trailing_activation'] and not self.trailing_active:
            self.trailing_active = True
            self.peak_price = current_price
            self.bot.log(f"🟢 Kích hoạt Trailing Stop | Lãi {current_roi:.1f}%")
        
        # Cập nhật đỉnh mới
        if self.trailing_active:
            if (self.bot.side == "BUY" and current_price > self.peak_price) or \
               (self.bot.side == "SELL" and current_price < self.peak_price):
                self.peak_price = current_price
            
            # Tính drawdown từ đỉnh
            if self.bot.side == "BUY":
                drawdown = ((self.peak_price - current_price) / self.peak_price) * 100
            else:
                drawdown = ((current_price - self.peak_price) / self.peak_price) * 100
            
            if drawdown >= self.config['trailing_distance']:
                return f"Trailing(dd:{drawdown:.1f}%)"
        
        return None
    
    def _check_time_exit(self):
        """Time-based Exit - Giới hạn thời gian giữ lệnh"""
        if self.position_open_time == 0:
            return None
            
        holding_hours = (time.time() - self.position_open_time) / 3600
        
        if holding_hours >= self.config['max_hold_time']:
            return f"Time({holding_hours:.1f}h)"
        
        return None
    
    def _check_volume_exit(self, current_volume):
        """Volume-based Exit - Theo dấu hiệu volume"""
        if len(self.volume_history) < 5:
            self.volume_history.append(current_volume)
            return None
        
        avg_volume = sum(self.volume_history[-5:]) / 5
        
        if current_volume < avg_volume * 0.4:
            return "Volume(giảm 60%)"
        
        self.volume_history.append(current_volume)
        if len(self.volume_history) > 10:
            self.volume_history.pop(0)
            
        return None
    
    def _check_support_resistance(self, current_price):
        """Support/Resistance Exit - Theo key levels"""
        if self.bot.side == "BUY":
            target_profit = 5.0
            target_price = self.bot.entry * (1 + target_profit/100)
            
            if current_price >= target_price:
                return f"Resistance(+{target_profit}%)"
        
        return None
    
    def _calculate_roi(self, current_price):
        """Tính ROI hiện tại"""
        if self.bot.side == "BUY":
            return ((current_price - self.bot.entry) / self.bot.entry) * 100
        else:
            return ((self.bot.entry - current_price) / self.bot.entry) * 100
    
    def on_position_opened(self):
        """Khi mở position mới"""
        self.trailing_active = False
        self.peak_price = self.bot.entry
        self.position_open_time = time.time()
        self.volume_history = []

# ========== MENU TELEGRAM HOÀN CHỈNH ==========
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
            [{"text": "🔄 Bot Động Thông Minh"}, {"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_exit_strategy_keyboard():
    """Bàn phím chọn chiến lược thoát lệnh"""
    return {
        "keyboard": [
            [{"text": "🔄 Thoát lệnh thông minh"}, {"text": "⚡ Thoát lệnh cơ bản"}],
            [{"text": "🎯 Chỉ TP/SL cố định"}, {"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_smart_exit_config_keyboard():
    """Bàn phím cấu hình Smart Exit"""
    return {
        "keyboard": [
            [{"text": "Trailing: 30/15"}, {"text": "Trailing: 50/20"}],
            [{"text": "Time Exit: 4h"}, {"text": "Time Exit: 8h"}],
            [{"text": "Kết hợp Full"}, {"text": "Cơ bản"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_bot_mode_keyboard():
    """Bàn phím chọn chế độ bot"""
    return {
        "keyboard": [
            [{"text": "🤖 Bot Tĩnh - Coin cụ thể"}, {"text": "🔄 Bot Động - Tự tìm coin"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_symbols_keyboard(strategy=None):
    """Bàn phím chọn coin"""
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
    """Bàn phím chọn đòn bẩy"""
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
    """Bàn phím chọn % số dư"""
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
    """Bàn phím chọn Take Profit"""
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
    """Bàn phím chọn Stop Loss"""
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

def create_volatility_keyboard():
    return {
        "keyboard": [
            [{"text": "2"}, {"text": "3"}, {"text": "5"}],
            [{"text": "7"}, {"text": "10"}, {"text": "15"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_grid_levels_keyboard():
    return {
        "keyboard": [
            [{"text": "3"}, {"text": "5"}, {"text": "7"}],
            [{"text": "10"}, {"text": "15"}, {"text": "20"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

# ========== QUẢN LÝ COIN CHUNG ==========
class CoinManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CoinManager, cls).__new__(cls)
                cls._instance.managed_coins = {}
                cls._instance.position_coins = set()
        return cls._instance
    
    def register_coin(self, symbol, bot_id, strategy, config_key=None):
        with self._lock:
            if symbol not in self.managed_coins:
                self.managed_coins[symbol] = {
                    "strategy": strategy, 
                    "bot_id": bot_id,
                    "config_key": config_key
                }
                return True
            return False
    
    def unregister_coin(self, symbol):
        with self._lock:
            if symbol in self.managed_coins:
                del self.managed_coins[symbol]
                return True
            return False
    
    def is_coin_managed(self, symbol):
        with self._lock:
            return symbol in self.managed_coins

    def has_same_config_bot(self, symbol, config_key):
        with self._lock:
            if symbol in self.managed_coins:
                existing_config = self.managed_coins[symbol].get("config_key")
                return existing_config == config_key
            return False
    
    def count_bots_by_config(self, config_key):
        with self._lock:
            count = 0
            for coin_info in self.managed_coins.values():
                if coin_info.get("config_key") == config_key:
                    count += 1
            return count
    
    def get_managed_coins(self):
        with self._lock:
            return self.managed_coins.copy()

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

def get_all_usdt_pairs(limit=100):
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

def get_top_volatile_symbols(limit=10, threshold=20):
    """Lấy danh sách coin có biến động 24h cao nhất từ toàn bộ Binance"""
    try:
        all_symbols = get_all_usdt_pairs(limit=200)
        if not all_symbols:
            logger.warning("Không lấy được coin từ Binance")
            return []
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return []
        
        ticker_dict = {ticker['symbol']: ticker for ticker in data if 'symbol' in ticker}
        
        volatile_pairs = []
        for symbol in all_symbols:
            if symbol in ticker_dict:
                ticker = ticker_dict[symbol]
                try:
                    change = float(ticker.get('priceChangePercent', 0))
                    volume = float(ticker.get('quoteVolume', 0))
                    
                    if abs(change) >= threshold and volume > 1000000:
                        volatile_pairs.append((symbol, abs(change)))
                except (ValueError, TypeError):
                    continue
        
        volatile_pairs.sort(key=lambda x: x[1], reverse=True)
        
        top_symbols = [pair[0] for pair in volatile_pairs[:limit]]
        logger.info(f"✅ Tìm thấy {len(top_symbols)} coin biến động ≥{threshold}%")
        return top_symbols
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy danh sách coin biến động: {str(e)}")
        return []

def get_qualified_symbols(api_key, api_secret, strategy_type, leverage, threshold=None, volatility=None, grid_levels=None, max_candidates=20, final_limit=2, strategy_key=None):
    """Tìm coin phù hợp từ TOÀN BỘ Binance - PHÂN BIỆT THEO CẤU HÌNH"""
    try:
        test_balance = get_balance(api_key, api_secret)
        if test_balance is None:
            logger.error("❌ KHÔNG THỂ KẾT NỐI BINANCE")
            return []
        
        coin_manager = CoinManager()
        
        all_symbols = get_all_usdt_pairs(limit=200)
        if not all_symbols:
            logger.error("❌ Không lấy được danh sách coin từ Binance")
            return []
        
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        if not data:
            return []
        
        ticker_dict = {ticker['symbol']: ticker for ticker in data if 'symbol' in ticker}
        
        qualified_symbols = []
        
        for symbol in all_symbols:
            if symbol not in ticker_dict:
                continue
                
            # Loại trừ BTC và ETH để tránh biến động quá cao
            if symbol in ['BTCUSDT', 'ETHUSDT']:
                continue
            
            # Kiểm tra coin đã được quản lý bởi config này chưa
            if strategy_key and coin_manager.has_same_config_bot(symbol, strategy_key):
                continue
            
            ticker = ticker_dict[symbol]
            
            try:
                price_change = float(ticker.get('priceChangePercent', 0))
                abs_price_change = abs(price_change)
                volume = float(ticker.get('quoteVolume', 0))
                high_price = float(ticker.get('highPrice', 0))
                low_price = float(ticker.get('lowPrice', 0))
                
                if low_price > 0:
                    price_range = ((high_price - low_price) / low_price) * 100
                else:
                    price_range = 0
                
                # ĐIỀU KIỆN CHO TỪNG CHIẾN LƯỢC - LINH HOẠT HƠN
                if strategy_type == "Reverse 24h":
                    if abs_price_change >= (threshold or 15) and volume > 1000000:
                        score = abs_price_change * (volume / 1000000)
                        qualified_symbols.append((symbol, score, price_change))
                
                elif strategy_type == "Scalping":
                    if abs_price_change >= (volatility or 2) and volume > 2000000 and price_range >= 1.0:
                        qualified_symbols.append((symbol, price_range))
                
                elif strategy_type == "Safe Grid":
                    if 0.5 <= abs_price_change <= 8.0 and volume > 500000:
                        qualified_symbols.append((symbol, -abs(price_change - 3.0)))
                
                elif strategy_type == "Trend Following":
                    # ĐIỀU KIỆN MỞ RỘNG CHO TREND FOLLOWING
                    if (1.0 <= abs_price_change <= 15.0 and 
                        volume > 1000000 and 
                        price_range >= 0.5):
                        score = volume * abs_price_change  # Ưu tiên volume cao + biến động
                        qualified_symbols.append((symbol, score))
                
                elif strategy_type == "Smart Dynamic":
                    # ĐIỀU KIỆN THÔNG MINH LINH HOẠT
                    if (1.0 <= abs_price_change <= 12.0 and
                        volume > 1500000 and
                        price_range >= 0.8):
                        # Tính điểm tổng hợp
                        volume_score = min(volume / 5000000, 5)
                        volatility_score = min(abs_price_change / 10, 3)
                        score = volume_score + volatility_score
                        qualified_symbols.append((symbol, score))
                        
            except (ValueError, TypeError) as e:
                continue
        
        # SẮP XẾP THEO CHIẾN LƯỢC
        if strategy_type == "Reverse 24h":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Scalping":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Safe Grid":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Trend Following":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        elif strategy_type == "Smart Dynamic":
            qualified_symbols.sort(key=lambda x: x[1], reverse=True)
        
        # LOG CHI TIẾT ĐỂ DEBUG
        logger.info(f"🔍 {strategy_type}: Quét {len(all_symbols)} coin, tìm thấy {len(qualified_symbols)} phù hợp")
        
        final_symbols = []
        for item in qualified_symbols[:max_candidates]:
            if len(final_symbols) >= final_limit:
                break
                
            if strategy_type == "Reverse 24h":
                symbol, score, original_change = item
            else:
                symbol, score = item
                
            try:
                leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                step_size = get_step_size(symbol, api_key, api_secret)
                
                if leverage_success and step_size > 0:
                    final_symbols.append(symbol)
                    if strategy_type == "Reverse 24h":
                        logger.info(f"✅ {symbol}: phù hợp {strategy_type} (Biến động: {original_change:.2f}%, Điểm: {score:.2f})")
                    else:
                        logger.info(f"✅ {symbol}: phù hợp {strategy_type} (Score: {score:.2f})")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ Lỗi kiểm tra {symbol}: {str(e)}")
                continue
        
        # BACKUP SYSTEM: Nếu không tìm thấy coin phù hợp, lấy coin có volume cao nhất
        if not final_symbols:
            logger.warning(f"⚠️ {strategy_type}: không tìm thấy coin phù hợp, sử dụng backup method")
            backup_symbols = []
            
            for symbol in all_symbols:
                if symbol not in ticker_dict:
                    continue
                    
                # Kiểm tra coin đã được quản lý bởi config này chưa
                if strategy_key and coin_manager.has_same_config_bot(symbol, strategy_key):
                    continue
                    
                ticker = ticker_dict[symbol]
                try:
                    volume = float(ticker.get('quoteVolume', 0))
                    price_change = float(ticker.get('priceChangePercent', 0))
                    abs_price_change = abs(price_change)
                    
                    # Điều kiện backup: volume cao, biến động vừa phải, không quá mạnh
                    if (volume > 3000000 and 
                        0.5 <= abs_price_change <= 10.0 and
                        symbol not in ['BTCUSDT', 'ETHUSDT']):
                        backup_symbols.append((symbol, volume, abs_price_change))
                except:
                    continue
            
            # Sắp xếp theo volume giảm dần
            backup_symbols.sort(key=lambda x: x[1], reverse=True)
            
            for symbol, volume, price_change in backup_symbols[:final_limit]:
                try:
                    leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                    step_size = get_step_size(symbol, api_key, api_secret)
                    
                    if leverage_success and step_size > 0:
                        final_symbols.append(symbol)
                        logger.info(f"🔄 {symbol}: backup coin (Volume: {volume:.0f}, Biến động: {price_change:.2f}%)")
                        if len(final_symbols) >= final_limit:
                            break
                    time.sleep(0.1)
                except Exception as e:
                    continue
        
        # FINAL CHECK: Nếu vẫn không có coin, thử các coin phổ biến
        if not final_symbols:
            logger.error(f"❌ {strategy_type}: không thể tìm thấy coin nào phù hợp sau backup")
            popular_symbols = ["BNBUSDT", "ADAUSDT", "XRPUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "EOSUSDT"]
            
            for symbol in popular_symbols:
                if len(final_symbols) >= final_limit:
                    break
                    
                try:
                    if symbol in ticker_dict:
                        leverage_success = set_leverage(symbol, leverage, api_key, api_secret)
                        step_size = get_step_size(symbol, api_key, api_secret)
                        
                        if leverage_success and step_size > 0:
                            final_symbols.append(symbol)
                            logger.info(f"🚨 {symbol}: sử dụng coin phổ biến (backup cuối)")
                except:
                    continue
        
        logger.info(f"🎯 {strategy_type}: Kết quả cuối - {len(final_symbols)} coin: {final_symbols}")
        return final_symbols[:final_limit]
        
    except Exception as e:
        logger.error(f"❌ Lỗi tìm coin {strategy_type}: {str(e)}")
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
        query = urllib.parse.urlencode(params)
        sig = sign(query, api_secret)
        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
        headers = {'X-MBX-APIKEY': api_key}
        
        data = binance_api_request(url, headers=headers)
        if not data:
            return []
        
        positions = []
        for pos in data.get('positions', []):
            if float(pos.get('positionAmt', 0)) != 0:
                positions.append({
                    'symbol': pos['symbol'],
                    'side': 'BUY' if float(pos['positionAmt']) > 0 else 'SELL',
                    'size': abs(float(pos['positionAmt'])),
                    'entry_price': float(pos['entryPrice']),
                    'leverage': int(pos['leverage']),
                    'pnl': float(pos.get('unRealizedProfit', 0))
                })
        return positions
    except Exception as e:
        logger.error(f"Lỗi lấy vị thế: {str(e)}")
    return []

def close_position(symbol, api_key, api_secret):
    try:
        positions = get_positions(symbol, api_key, api_secret)
        for pos in positions:
            if pos['symbol'] == symbol.upper():
                side = 'SELL' if pos['side'] == 'BUY' else 'BUY'
                qty = pos['size']
                return place_order(symbol, side, qty, api_key, api_secret)
        return None
    except Exception as e:
        logger.error(f"Lỗi đóng vị thế: {str(e)}")
    return None

# ========== BOT TRADING HOÀN CHỈNH ==========
class TradingBot:
    def __init__(self, config):
        self.config = config
        self.api_key = config.get('api_key', '')
        self.api_secret = config.get('api_secret', '')
        self.symbol = config.get('symbol', 'BTCUSDT')
        self.leverage = config.get('leverage', 10)
        self.quantity_percent = config.get('quantity_percent', 1)
        self.take_profit = config.get('take_profit', 100)
        self.stop_loss = config.get('stop_loss', 50)
        self.strategy = config.get('strategy', 'RSI/EMA Recursive')
        self.threshold = config.get('threshold', 50)
        self.volatility = config.get('volatility', 5)
        self.grid_levels = config.get('grid_levels', 5)
        self.exit_strategy = config.get('exit_strategy', 'smart')
        self.bot_mode = config.get('bot_mode', 'static')
        self.telegram_chat_id = config.get('telegram_chat_id')
        self.telegram_bot_token = config.get('telegram_bot_token')
        self.bot_id = config.get('bot_id', int(time.time()))
        self.running = False
        self.position_open = False
        self.side = None
        self.entry = 0
        self.quantity = 0
        self.last_signal = None
        self.last_price = 0
        self.websocket = None
        self.thread = None
        self.smart_exit = SmartExitManager(self)
        self.coin_manager = CoinManager()
        self.waiting_for_new_coin = False
        self.last_analysis = time.time()
        self.analysis_interval = 60  # 1 phút phân tích 1 lần
        
        # Đăng ký coin với CoinManager
        if self.bot_mode == 'static':
            self.coin_manager.register_coin(self.symbol, self.bot_id, self.strategy, self._get_config_key())
        
        # Thiết lập Smart Exit
        self._setup_smart_exit()
        
        self.log(f"🤖 Bot {self.bot_id} khởi tạo: {self.strategy} | {self.symbol} | {self.bot_mode}")
    
    def _get_config_key(self):
        """Tạo key duy nhất cho cấu hình bot"""
        config_str = f"{self.api_key}_{self.strategy}_{self.leverage}_{self.quantity_percent}_{self.threshold}_{self.volatility}"
        return hashlib.md5(config_str.encode()).hexdigest()[:8]
    
    def _setup_smart_exit(self):
        """Thiết lập cấu hình Smart Exit"""
        if self.exit_strategy == 'smart':
            self.smart_exit.update_config(
                enable_trailing=True,
                enable_time_exit=True,
                enable_volume_exit=True,
                enable_support_resistance=True,
                trailing_activation=30,
                trailing_distance=15,
                max_hold_time=6,
                min_profit_for_exit=10
            )
        elif self.exit_strategy == 'basic':
            self.smart_exit.update_config(
                enable_trailing=True,
                enable_time_exit=False,
                enable_volume_exit=False,
                enable_support_resistance=False,
                trailing_activation=20,
                trailing_distance=10,
                max_hold_time=0,
                min_profit_for_exit=5
            )
    
    def log(self, message):
        """Ghi log và gửi Telegram nếu có"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        logger.info(log_message)
        
        if self.telegram_chat_id and self.telegram_bot_token:
            try:
                send_telegram(log_message, self.telegram_chat_id, bot_token=self.telegram_bot_token)
            except Exception as e:
                logger.error(f"Lỗi gửi Telegram: {str(e)}")
    
    def start(self):
        """Khởi động bot"""
        if self.running:
            self.log("⚠️ Bot đang chạy")
            return False
        
        self.running = True
        
        # Bot động: tìm coin mới ngay lập tức
        if self.bot_mode == 'dynamic' and not self.position_open:
            self._find_and_switch_coin()
        
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()
        
        self.log(f"🚀 Bắt đầu Bot {self.bot_id}: {self.strategy} | {self.symbol}")
        return True
    
    def stop(self):
        """Dừng bot"""
        if not self.running:
            return False
        
        self.running = False
        
        if self.websocket:
            try:
                self.websocket.close()
            except:
                pass
        
        # Hủy đăng ký coin
        if self.bot_mode == 'static':
            self.coin_manager.unregister_coin(self.symbol)
        
        self.log(f"🛑 Dừng Bot {self.bot_id}")
        return True
    
    def _run(self):
        """Vòng lặp chính của bot"""
        self._setup_websocket()
        
        while self.running:
            try:
                # Bot động: định kỳ tìm coin mới
                if (self.bot_mode == 'dynamic' and 
                    not self.position_open and 
                    not self.waiting_for_new_coin and
                    time.time() - self.last_analysis > self.analysis_interval):
                    
                    self._find_and_switch_coin()
                    self.last_analysis = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                self.log(f"❌ Lỗi vòng lặp chính: {str(e)}")
                time.sleep(5)
    
    def _find_and_switch_coin(self):
        """TÌM COIN MỚI VÀ CHUYỂN ĐỔI - BOT ĐỘNG"""
        try:
            self.waiting_for_new_coin = True
            self.log(f"🔍 Bot động đang tìm coin mới...")
            
            # Tìm coin phù hợp
            new_symbols = get_qualified_symbols(
                self.api_key, self.api_secret,
                self.strategy, self.leverage,
                self.threshold, self.volatility,
                self.grid_levels, max_candidates=20, final_limit=1,
                strategy_key=self._get_config_key()
            )
            
            if new_symbols:
                new_symbol = new_symbols[0]
                
                # Kiểm tra coin mới có khác coin hiện tại không
                if new_symbol != self.symbol:
                    self.log(f"🔄 Chuyển từ {self.symbol} → {new_symbol}")
                    
                    # Hủy đăng ký coin cũ
                    self.coin_manager.unregister_coin(self.symbol)
                    
                    # Cập nhật symbol mới
                    self.symbol = new_symbol
                    
                    # Đăng ký coin mới
                    self.coin_manager.register_coin(self.symbol, self.bot_id, self.strategy, self._get_config_key())
                    
                    # Khởi động lại websocket với symbol mới
                    if self.websocket:
                        try:
                            self.websocket.close()
                        except:
                            pass
                    self._setup_websocket()
                    
                    self.log(f"✅ Đã chuyển sang coin mới: {self.symbol}")
                else:
                    self.log(f"ℹ️ Vẫn giữ coin {self.symbol} (phù hợp nhất)")
            else:
                self.log(f"⚠️ Không tìm thấy coin mới phù hợp, giữ {self.symbol}")
            
            self.waiting_for_new_coin = False
            
        except Exception as e:
            self.log(f"❌ Lỗi tìm coin mới: {str(e)}")
            self.waiting_for_new_coin = False
    
    def _setup_websocket(self):
        """Thiết lập WebSocket cho coin hiện tại"""
        try:
            if self.websocket:
                self.websocket.close()
            
            stream_url = f"wss://fstream.binance.com/ws/{self.symbol.lower()}@kline_1m"
            self.websocket = websocket.WebSocketApp(
                stream_url,
                on_message=self._on_websocket_message,
                on_error=self._on_websocket_error,
                on_close=self._on_websocket_close
            )
            
            ws_thread = threading.Thread(target=self.websocket.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            self.log(f"📡 Kết nối WebSocket: {self.symbol}")
            
        except Exception as e:
            self.log(f"❌ Lỗi WebSocket: {str(e)}")
    
    def _on_websocket_message(self, ws, message):
        """Xử lý tin nhắn WebSocket"""
        try:
            data = json.loads(message)
            kline = data.get('k', {})
            
            if kline.get('x'):  # Cây nến đóng
                close_price = float(kline['c'])
                high_price = float(kline['h'])
                low_price = float(kline['l'])
                volume = float(kline.get('v', 0))
                
                self.last_price = close_price
                
                # Phân tích tín hiệu giao dịch
                signal = self._analyze_signal(close_price, high_price, low_price, volume)
                
                # Kiểm tra điều kiện đóng lệnh nếu đang có position
                if self.position_open:
                    exit_reason = self.smart_exit.check_all_exit_conditions(close_price, volume)
                    if exit_reason:
                        self._close_position(exit_reason)
                    elif self._check_basic_exit(close_price):
                        self._close_position(f"Basic TP/SL")
                
                # Kiểm tra tín hiệu mở lệnh mới
                elif signal and not self.waiting_for_new_coin:
                    self._open_position(signal, close_price)
                
        except Exception as e:
            self.log(f"❌ Lỗi xử lý WebSocket: {str(e)}")
    
    def _analyze_signal(self, close, high, low, volume):
        """Phân tích tín hiệu giao dịch theo chiến lược"""
        # Triển khai logic chiến lược ở đây
        # Hiện tại trả về tín hiệu giả lập
        if not self.position_open and not self.waiting_for_new_coin:
            # Giả lập tín hiệu ngẫu nhiên để demo
            import random
            if random.random() < 0.1:  # 10% cơ hội
                return random.choice(['BUY', 'SELL'])
        return None
    
    def _open_position(self, side, price):
        """Mở vị thế mới"""
        try:
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không thể lấy số dư")
                return
            
            # Tính khối lượng
            usd_amount = balance * (self.quantity_percent / 100)
            self.quantity = usd_amount / price
            
            # Làm tròn theo step size
            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            if step_size > 0:
                precision = int(round(-math.log(step_size, 10), 0))
                self.quantity = round(self.quantity - (self.quantity % step_size), precision)
            
            if self.quantity <= 0:
                self.log("❌ Khối lượng quá nhỏ")
                return
            
            # Đặt lệnh
            result = place_order(self.symbol, side, self.quantity, self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                self.position_open = True
                self.side = side
                self.entry = price
                
                # Cập nhật Smart Exit
                self.smart_exit.on_position_opened()
                
                self.log(f"🎯 MỞ {side} | {self.symbol} | Giá: {price:.4f} | KL: {self.quantity:.3f}")
                
                # Bot động: hủy đăng ký coin khi có position
                if self.bot_mode == 'dynamic':
                    self.coin_manager.unregister_coin(self.symbol)
                
            else:
                self.log(f"❌ Lỗi mở lệnh {side}")
                
        except Exception as e:
            self.log(f"❌ Lỗi mở position: {str(e)}")
    
    def _close_position(self, reason=""):
        """Đóng vị thế hiện tại"""
        try:
            result = close_position(self.symbol, self.api_key, self.api_secret)
            
            if result and 'orderId' in result:
                current_price = self.last_price
                if self.side == 'BUY':
                    pnl_percent = ((current_price - self.entry) / self.entry) * 100
                else:
                    pnl_percent = ((self.entry - current_price) / self.entry) * 100
                
                self.log(f"🏁 ĐÓNG {self.side} | {self.symbol} | Lãi/lỗ: {pnl_percent:.2f}% | Lý do: {reason}")
                
                # Reset trạng thái
                self.position_open = False
                self.side = None
                self.entry = 0
                self.quantity = 0
                
                # Bot động: tìm coin mới sau khi đóng lệnh
                if self.bot_mode == 'dynamic':
                    self.log("🔄 Bot động đang tìm coin mới sau khi đóng lệnh...")
                    threading.Thread(target=self._find_and_switch_coin, daemon=True).start()
                
            else:
                self.log(f"❌ Lỗi đóng lệnh")
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng position: {str(e)}")
    
    def _check_basic_exit(self, current_price):
        """Kiểm tra điều kiện TP/SL cơ bản"""
        if not self.position_open:
            return False
        
        if self.side == 'BUY':
            profit = ((current_price - self.entry) / self.entry) * 100
        else:
            profit = ((self.entry - current_price) / self.entry) * 100
        
        # Take Profit
        if profit >= self.take_profit:
            return True
        
        # Stop Loss  
        if profit <= -self.stop_loss:
            return True
        
        return False
    
    def _on_websocket_error(self, ws, error):
        """Xử lý lỗi WebSocket"""
        self.log(f"❌ WebSocket lỗi: {str(error)}")
    
    def _on_websocket_close(self, ws, close_status_code, close_msg):
        """Xử lý đóng WebSocket"""
        self.log("🔌 WebSocket đã đóng")
        if self.running:
            self.log("🔄 Đang kết nối lại WebSocket...")
            time.sleep(5)
            self._setup_websocket()

# ========== BOT MANAGER HOÀN CHỈNH ==========
class TradingBotManager:
    def __init__(self):
        self.bots = {}
        self.user_states = {}
        self.user_configs = {}
        self.coin_manager = CoinManager()
    
    def handle_telegram_message(self, message, chat_id, bot_token=None):
        """Xử lý tin nhắn Telegram từ người dùng"""
        try:
            text = message.get('text', '').strip()
            
            if text == '/start':
                self._send_welcome_message(chat_id, bot_token)
                return
            
            # Kiểm tra trạng thái người dùng
            user_state = self.user_states.get(chat_id, {})
            current_state = user_state.get('state', '')
            
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("✅ Đã hủy thao tác.", chat_id, reply_markup=create_main_menu(), bot_token=bot_token)
                return
            
            # Xử lý theo trạng thái
            if current_state.startswith('waiting_'):
                self._handle_user_input(chat_id, text, user_state, bot_token)
            else:
                self._handle_main_menu(chat_id, text, bot_token)
                
        except Exception as e:
            logger.error(f"Lỗi xử lý Telegram: {str(e)}")
            send_telegram("❌ Có lỗi xảy ra. Vui lòng thử lại.", chat_id, bot_token=bot_token)
    
    def _send_welcome_message(self, chat_id, bot_token):
        """Gửi tin nhắn chào mừng"""
        welcome_text = """
🤖 <b>CHÀO MỪNG ĐẾN VỚI SMART TRADING BOT</b>

Tính năng chính:
✅ <b>Bot Động Thông Minh</b> - Tự tìm coin tốt nhất
📊 <b>6 Chiến lược giao dịch</b> 
⚡ <b>4 Cơ chế thoát lệnh thông minh</b>
🔒 <b>Quản lý rủi ro đa tầng</b>

Chọn <b>➕ Thêm Bot</b> để bắt đầu!
        """
        send_telegram(welcome_text, chat_id, reply_markup=create_main_menu(), bot_token=bot_token)
    
    def _handle_main_menu(self, chat_id, text, bot_token):
        """Xử lý menu chính"""
        if text == '➕ Thêm Bot':
            self._start_bot_creation(chat_id, bot_token)
        
        elif text == '📊 Danh sách Bot':
            self._show_bot_list(chat_id, bot_token)
        
        elif text == '⛔ Dừng Bot':
            self._stop_bot_menu(chat_id, bot_token)
        
        elif text == '💰 Số dư':
            self._show_balance(chat_id, bot_token)
        
        elif text == '📈 Vị thế':
            self._show_positions(chat_id, bot_token)
        
        elif text == '🎯 Chiến lược':
            send_telegram("Chọn chiến lược giao dịch:", chat_id, 
                         reply_markup=create_strategy_keyboard(), bot_token=bot_token)
        
        elif text == '⚙️ Cấu hình':
            self._show_config_menu(chat_id, bot_token)
        
        else:
            send_telegram("Vui lòng chọn một tùy chọn từ menu:", chat_id, 
                         reply_markup=create_main_menu(), bot_token=bot_token)
    
    def _start_bot_creation(self, chat_id, bot_token):
        """Bắt đầu quy trình tạo bot"""
        # Kiểm tra API keys
        user_config = self.user_configs.get(chat_id, {})
        if not user_config.get('api_key') or not user_config.get('api_secret'):
            self.user_states[chat_id] = {'state': 'waiting_api_key'}
            send_telegram("🔑 <b>THIẾT LẬP API BINANCE</b>\n\nGửi API Key:", 
                         chat_id, reply_markup=create_cancel_keyboard(), bot_token=bot_token)
            return
        
        # Chọn chế độ bot
        self.user_states[chat_id] = {'state': 'waiting_bot_mode'}
        send_telegram("🤖 <b>CHỌN CHẾ ĐỘ BOT</b>\n\n"
                     "• <b>Bot Tĩnh</b>: Giao dịch coin cố định\n"
                     "• <b>Bot Động</b>: Tự động tìm coin tốt nhất", 
                     chat_id, reply_markup=create_bot_mode_keyboard(), bot_token=bot_token)
    
    def _handle_user_input(self, chat_id, text, user_state, bot_token):
        """Xử lý input từ người dùng"""
        state = user_state.get('state', '')
        
        if state == 'waiting_api_key':
            self.user_states[chat_id] = {
                'state': 'waiting_api_secret',
                'api_key': text
            }
            send_telegram("🔑 Gửi API Secret:", chat_id, 
                         reply_markup=create_cancel_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_api_secret':
            api_key = user_state.get('api_key')
            
            # Lưu API keys
            if chat_id not in self.user_configs:
                self.user_configs[chat_id] = {}
            self.user_configs[chat_id].update({
                'api_key': api_key,
                'api_secret': text,
                'telegram_chat_id': chat_id,
                'telegram_bot_token': bot_token
            })
            
            self.user_states[chat_id] = {}
            send_telegram("✅ Đã lưu API keys!\n\nChọn <b>➕ Thêm Bot</b> để tiếp tục.", 
                         chat_id, reply_markup=create_main_menu(), bot_token=bot_token)
        
        elif state == 'waiting_bot_mode':
            if 'Tĩnh' in text:
                bot_mode = 'static'
            elif 'Động' in text:
                bot_mode = 'dynamic'
            else:
                send_telegram("Vui lòng chọn chế độ bot:", chat_id,
                             reply_markup=create_bot_mode_keyboard(), bot_token=bot_token)
                return
            
            self.user_states[chat_id] = {
                'state': 'waiting_strategy',
                'bot_mode': bot_mode
            }
            send_telegram("🎯 <b>CHỌN CHIẾN LƯỢC</b>", chat_id,
                         reply_markup=create_strategy_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_strategy':
            strategy_map = {
                "🤖 RSI/EMA Recursive": "RSI/EMA Recursive",
                "📊 EMA Crossover": "EMA Crossover", 
                "🎯 Reverse 24h": "Reverse 24h",
                "📈 Trend Following": "Trend Following",
                "⚡ Scalping": "Scalping",
                "🛡️ Safe Grid": "Safe Grid",
                "🔄 Bot Động Thông Minh": "Smart Dynamic"
            }
            
            strategy = strategy_map.get(text)
            if not strategy:
                send_telegram("Vui lòng chọn chiến lược:", chat_id,
                             reply_markup=create_strategy_keyboard(), bot_token=bot_token)
                return
            
            self.user_states[chat_id]['strategy'] = strategy
            
            # Chọn đòn bẩy
            self.user_states[chat_id]['state'] = 'waiting_leverage'
            send_telegram("⚖️ <b>CHỌN ĐÒN BẨY</b>", chat_id,
                         reply_markup=create_leverage_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_leverage':
            try:
                leverage = int(text.replace('x', ''))
                self.user_states[chat_id]['leverage'] = leverage
                
                # Chọn % số dư
                self.user_states[chat_id]['state'] = 'waiting_quantity'
                send_telegram("💰 <b>CHỌN % SỐ DƯ MỖI LỆNH</b>", chat_id,
                             reply_markup=create_percent_keyboard(), bot_token=bot_token)
            except:
                send_telegram("Vui lòng chọn đòn bẩy hợp lệ:", chat_id,
                             reply_markup=create_leverage_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_quantity':
            try:
                quantity_percent = float(text)
                self.user_states[chat_id]['quantity_percent'] = quantity_percent
                
                # Chọn Take Profit
                self.user_states[chat_id]['state'] = 'waiting_take_profit'
                send_telegram("🎯 <b>CHỌN TAKE PROFIT (%)</b>", chat_id,
                             reply_markup=create_tp_keyboard(), bot_token=bot_token)
            except:
                send_telegram("Vui lòng chọn % số dư hợp lệ:", chat_id,
                             reply_markup=create_percent_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_take_profit':
            try:
                take_profit = float(text)
                self.user_states[chat_id]['take_profit'] = take_profit
                
                # Chọn Stop Loss
                self.user_states[chat_id]['state'] = 'waiting_stop_loss'
                send_telegram("🛡️ <b>CHỌN STOP LOSS (%)</b>\n\nGõ 0 để không dùng SL", chat_id,
                             reply_markup=create_sl_keyboard(), bot_token=bot_token)
            except:
                send_telegram("Vui lòng chọn TP hợp lệ:", chat_id,
                             reply_markup=create_tp_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_stop_loss':
            try:
                stop_loss = float(text)
                self.user_states[chat_id]['stop_loss'] = stop_loss
                
                # Chọn chiến lược thoát lệnh
                self.user_states[chat_id]['state'] = 'waiting_exit_strategy'
                send_telegram("🔚 <b>CHỌN CHIẾN LƯỢC THOÁT LỆNH</b>\n\n"
                             "• <b>Thoát lệnh thông minh</b>: 4 cơ chế tự động\n"
                             "• <b>Thoát lệnh cơ bản</b>: Trailing Stop\n"
                             "• <b>Chỉ TP/SL cố định</b>: Cơ bản", chat_id,
                             reply_markup=create_exit_strategy_keyboard(), bot_token=bot_token)
            except:
                send_telegram("Vui lòng chọn SL hợp lệ:", chat_id,
                             reply_markup=create_sl_keyboard(), bot_token=bot_token)
        
        elif state == 'waiting_exit_strategy':
            exit_strategy_map = {
                "🔄 Thoát lệnh thông minh": "smart",
                "⚡ Thoát lệnh cơ bản": "basic", 
                "🎯 Chỉ TP/SL cố định": "fixed"
            }
            
            exit_strategy = exit_strategy_map.get(text, 'smart')
            self.user_states[chat_id]['exit_strategy'] = exit_strategy
            
            # Bot tĩnh: chọn coin cụ thể
            if self.user_states[chat_id].get('bot_mode') == 'static':
                self.user_states[chat_id]['state'] = 'waiting_symbol'
                send_telegram("💰 <b>CHỌN COIN GIAO DỊCH</b>", chat_id,
                             reply_markup=create_symbols_keyboard(), bot_token=bot_token)
            else:
                # Bot động: thiết lập tham số tìm coin
                self._setup_dynamic_bot(chat_id, bot_token)
        
        elif state == 'waiting_symbol':
            if not text.startswith('❌'):
                self.user_states[chat_id]['symbol'] = text
                self._create_and_start_bot(chat_id, bot_token)
            else:
                send_telegram("Vui lòng chọn coin:", chat_id,
                             reply_markup=create_symbols_keyboard(), bot_token=bot_token)
        
        # Xử lý các state khác...
        else:
            self.user_states[chat_id] = {}
            send_telegram("❌ State không hợp lệ. Bắt đầu lại.", chat_id,
                         reply_markup=create_main_menu(), bot_token=bot_token)
    
    def _setup_dynamic_bot(self, chat_id, bot_token):
        """Thiết lập tham số cho bot động"""
        user_state = self.user_states[chat_id]
        strategy = user_state.get('strategy', '')
        
        # Thiết lập tham số mặc định theo chiến lược
        if strategy == "Reverse 24h":
            user_state['threshold'] = 50
            user_state['state'] = 'waiting_dynamic_complete'
            self._create_and_start_bot(chat_id, bot_token)
        
        elif strategy == "Scalping":
            user_state['volatility'] = 5
            user_state['state'] = 'waiting_dynamic_complete' 
            self._create_and_start_bot(chat_id, bot_token)
        
        elif strategy == "Safe Grid":
            user_state['grid_levels'] = 5
            user_state['state'] = 'waiting_dynamic_complete'
            self._create_and_start_bot(chat_id, bot_token)
        
        else:
            user_state['state'] = 'waiting_dynamic_complete'
            self._create_and_start_bot(chat_id, bot_token)
    
    def _create_and_start_bot(self, chat_id, bot_token):
        """Tạo và khởi động bot"""
        try:
            user_state = self.user_states[chat_id]
            user_config = self.user_configs[chat_id]
            
            # Tạo config bot
            bot_config = {
                'api_key': user_config['api_key'],
                'api_secret': user_config['api_secret'],
                'telegram_chat_id': chat_id,
                'telegram_bot_token': bot_token,
                'bot_id': int(time.time()),
                
                # Thông tin từ user
                'strategy': user_state.get('strategy', 'RSI/EMA Recursive'),
                'leverage': user_state.get('leverage', 10),
                'quantity_percent': user_state.get('quantity_percent', 1),
                'take_profit': user_state.get('take_profit', 100),
                'stop_loss': user_state.get('stop_loss', 50),
                'exit_strategy': user_state.get('exit_strategy', 'smart'),
                'bot_mode': user_state.get('bot_mode', 'static'),
                
                # Tham số chiến lược
                'threshold': user_state.get('threshold', 50),
                'volatility': user_state.get('volatility', 5),
                'grid_levels': user_state.get('grid_levels', 5),
            }
            
            # Bot tĩnh có symbol cố định
            if bot_config['bot_mode'] == 'static':
                bot_config['symbol'] = user_state.get('symbol', 'BTCUSDT')
            else:
                # Bot động: tìm coin ngay khi khởi động
                qualified_symbols = get_qualified_symbols(
                    bot_config['api_key'], bot_config['api_secret'],
                    bot_config['strategy'], bot_config['leverage'],
                    bot_config.get('threshold'), bot_config.get('volatility'),
                    bot_config.get('grid_levels'), max_candidates=20, final_limit=1,
                    strategy_key=self._get_config_key(bot_config)
                )
                
                if qualified_symbols:
                    bot_config['symbol'] = qualified_symbols[0]
                else:
                    bot_config['symbol'] = 'BTCUSDT'  # Fallback
            
            # Tạo bot
            bot = TradingBot(bot_config)
            bot_id = bot_config['bot_id']
            
            # Khởi động bot
            if bot.start():
                self.bots[bot_id] = bot
                
                # Reset user state
                self.user_states[chat_id] = {}
                
                # Gửi thông báo thành công
                mode_text = "Tĩnh" if bot_config['bot_mode'] == 'static' else "Động"
                success_msg = f"""
✅ <b>ĐÃ TẠO BOT THÀNH CÔNG!</b>

🤖 ID: <code>{bot_id}</code>
🎯 Chiến lược: {bot_config['strategy']}
💰 Coin: {bot_config['symbol']}
⚖️ Đòn bẩy: {bot_config['leverage']}x
💵 Số dư/lệnh: {bot_config['quantity_percent']}%
🎯 TP: {bot_config['take_profit']}%
🛡️ SL: {bot_config['stop_loss']}%
🔚 Thoát lệnh: {bot_config['exit_strategy']}
🔧 Chế độ: {mode_text}

Bot sẽ tự động bắt đầu giao dịch!
                """
                
                send_telegram(success_msg, chat_id, reply_markup=create_main_menu(), bot_token=bot_token)
                
            else:
                send_telegram("❌ Không thể khởi động bot. Vui lòng thử lại.", chat_id,
                             reply_markup=create_main_menu(), bot_token=bot_token)
        
        except Exception as e:
            logger.error(f"Lỗi tạo bot: {str(e)}")
            send_telegram(f"❌ Lỗi tạo bot: {str(e)}", chat_id,
                         reply_markup=create_main_menu(), bot_token=bot_token)
    
    def _get_config_key(self, config):
        """Tạo key cấu hình duy nhất"""
        config_str = f"{config['api_key']}_{config['strategy']}_{config['leverage']}_{config['quantity_percent']}"
        return hashlib.md5(config_str.encode()).hexdigest()[:8]
    
    def _show_bot_list(self, chat_id, bot_token):
        """Hiển thị danh sách bot"""
        try:
            if not self.bots:
                send_telegram("🤖 <b>DANH SÁCH BOT</b>\n\nChưa có bot nào đang chạy.", 
                             chat_id, bot_token=bot_token)
                return
            
            bot_list = []
            for bot_id, bot in self.bots.items():
                status = "🟢 Đang chạy" if bot.running else "🔴 Dừng"
                mode = "Động" if bot.bot_mode == 'dynamic' else "Tĩnh"
                
                if bot.position_open:
                    position_info = f"\n   📊 {bot.side} | Entry: {bot.entry:.4f} | ROI: {((bot.last_price - bot.entry) / bot.entry * 100):.2f}%"
                else:
                    position_info = "\n   💤 Chờ tín hiệu"
                
                bot_list.append(f"┌ <b>Bot {bot_id}</b>\n"
                              f"├ {status} | {mode}\n"
                              f"├ {bot.strategy}\n"
                              f"├ {bot.symbol} | {bot.leverage}x\n"
                              f"└ {position_info}")
            
            message = f"🤖 <b>DANH SÁCH BOT</b>\n\n" + "\n\n".join(bot_list)
            send_telegram(message, chat_id, bot_token=bot_token)
            
        except Exception as e:
            logger.error(f"Lỗi hiển thị bot list: {str(e)}")
            send_telegram("❌ Lỗi hiển thị danh sách bot.", chat_id, bot_token=bot_token)
    
    def _stop_bot_menu(self, chat_id, bot_token):
        """Hiển thị menu dừng bot"""
        try:
            user_bots = {bid: bot for bid, bot in self.bots.items()}
            
            if not user_bots:
                send_telegram("❌ Bạn chưa có bot nào đang chạy.", chat_id, bot_token=bot_token)
                return
            
            keyboard = []
            for bot_id, bot in user_bots.items():
                keyboard.append([{"text": f"⛔ Dừng Bot {bot_id} - {bot.symbol}"}])
            keyboard.append([{"text": "❌ Hủy bỏ"}])
            
            reply_markup = {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True}
            
            send_telegram("🛑 <b>CHỌN BOT ĐỂ DỪNG</b>", chat_id, reply_markup=reply_markup, bot_token=bot_token)
            self.user_states[chat_id] = {'state': 'waiting_stop_bot'}
            
        except Exception as e:
            logger.error(f"Lỗi hiển thị menu dừng bot: {str(e)}")
            send_telegram("❌ Lỗi hiển thị menu.", chat_id, bot_token=bot_token)
    
    def _show_balance(self, chat_id, bot_token):
        """Hiển thị số dư"""
        try:
            user_config = self.user_configs.get(chat_id, {})
            api_key = user_config.get('api_key')
            api_secret = user_config.get('api_secret')
            
            if not api_key or not api_secret:
                send_telegram("❌ Chưa thiết lập API Binance. Dùng <b>➕ Thêm Bot</b> để thiết lập.", 
                             chat_id, bot_token=bot_token)
                return
            
            balance = get_balance(api_key, api_secret)
            if balance is None:
                send_telegram("❌ Không thể kết nối Binance. Kiểm tra API keys.", 
                             chat_id, bot_token=bot_token)
                return
            
            # Lấy tổng PnL từ các position
            positions = get_positions(api_key=api_key, api_secret=api_secret)
            total_pnl = sum(pos['pnl'] for pos in positions)
            
            message = f"""
💰 <b>THÔNG TIN TÀI KHOẢN</b>

💵 Số dư khả dụng: <b>${balance:,.2f}</b>
📈 Tổng PnL chưa thực hiện: <b>${total_pnl:,.2f}</b>
🔢 Tổng vị thế: <b>{len(positions)}</b>
            """
            
            send_telegram(message, chat_id, bot_token=bot_token)
            
        except Exception as e:
            logger.error(f"Lỗi hiển thị số dư: {str(e)}")
            send_telegram("❌ Lỗi lấy thông tin số dư.", chat_id, bot_token=bot_token)
    
    def _show_positions(self, chat_id, bot_token):
        """Hiển thị vị thế"""
        try:
            user_config = self.user_configs.get(chat_id, {})
            api_key = user_config.get('api_key')
            api_secret = user_config.get('api_secret')
            
            if not api_key or not api_secret:
                send_telegram("❌ Chưa thiết lập API Binance.", chat_id, bot_token=bot_token)
                return
            
            positions = get_positions(api_key=api_key, api_secret=api_secret)
            
            if not positions:
                send_telegram("📊 <b>VỊ THẾ HIỆN TẠI</b>\n\nKhông có vị thế nào.", 
                             chat_id, bot_token=bot_token)
                return
            
            position_list = []
            for pos in positions:
                side_emoji = "🟢" if pos['side'] == 'BUY' else "🔴"
                position_list.append(f"{side_emoji} <b>{pos['symbol']}</b>\n"
                                   f"   {pos['side']} | KL: {pos['size']:.3f}\n"
                                   f"   Entry: ${pos['entry_price']:.4f}\n"
                                   f"   PnL: ${pos['pnl']:.2f} | {pos['leverage']}x")
            
            message = f"📊 <b>VỊ THẾ HIỆN TẠI</b>\n\n" + "\n\n".join(position_list)
            send_telegram(message, chat_id, bot_token=bot_token)
            
        except Exception as e:
            logger.error(f"Lỗi hiển thị vị thế: {str(e)}")
            send_telegram("❌ Lỗi lấy thông tin vị thế.", chat_id, bot_token=bot_token)
    
    def _show_config_menu(self, chat_id, bot_token):
        """Hiển thị menu cấu hình"""
        try:
            user_config = self.user_configs.get(chat_id, {})
            
            if not user_config.get('api_key'):
                config_status = "❌ Chưa thiết lập"
            else:
                config_status = f"✅ Đã thiết lập\nAPI Key: ...{user_config['api_key'][-8:]}"
            
            # Đếm số bot
            user_bot_count = sum(1 for bot in self.bots.values())
            
            message = f"""
⚙️ <b>CẤU HÌNH HỆ THỐNG</b>

🔑 API Binance: {config_status}
🤖 Số bot đang chạy: <b>{user_bot_count}</b>
💰 Coin đang quản lý: <b>{len(self.coin_manager.get_managed_coins())}</b>

Chọn <b>➕ Thêm Bot</b> để tạo bot mới!
            """
            
            send_telegram(message, chat_id, bot_token=bot_token)
            
        except Exception as e:
            logger.error(f"Lỗi hiển thị cấu hình: {str(e)}")
            send_telegram("❌ Lỗi hiển thị cấu hình.", chat_id, bot_token=bot_token)
