# trading_bot_perfect_system.py - HỆ THỐNG BOT GIAO DỊCH HOÀN CHỈNH VỚI CHIẾN LƯỢC TÍCH HỢP
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

# ========== CẤU HÌNH LOGGING CHUYÊN NGHIỆP ==========
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('perfect_bot_system.log')
        ]
    )
    return logging.getLogger()

logger = setup_logging()

# ========== HÀM TELEGRAM NÂNG CẤP ==========
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
def create_main_menu():
    return {
        "keyboard": [
            [{"text": "📊 Danh sách Bot"}, {"text": "📊 Thống kê"}],
            [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
            [{"text": "💰 Số dư"}, {"text": "📈 Vị thế"}],
            [{"text": "⚙️ Cấu hình"}, {"text": "🎯 Chiến lược"}],
            [{"text": "🚀 Khởi chạy hệ thống"}]
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
            [{"text": "🎯 Hệ thống Hoàn hảo"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_bot_count_keyboard():
    return {
        "keyboard": [
            [{"text": "1"}, {"text": "2"}, {"text": "3"}],
            [{"text": "5"}, {"text": "8"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_leverage_keyboard():
    leverages = ["3", "5", "10", "15", "20", "25"]
    
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
            [{"text": "1"}, {"text": "2"}, {"text": "3"}],
            [{"text": "5"}, {"text": "8"}, {"text": "10"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_tp_keyboard():
    return {
        "keyboard": [
            [{"text": "50"}, {"text": "100"}, {"text": "150"}],
            [{"text": "200"}, {"text": "300"}, {"text": "500"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_sl_keyboard():
    return {
        "keyboard": [
            [{"text": "TẮT SL"}, {"text": "30"}, {"text": "50"}],
            [{"text": "80"}, {"text": "100"}, {"text": "150"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def create_coin_per_bot_keyboard():
    return {
        "keyboard": [
            [{"text": "1"}, {"text": "2"}, {"text": "3"}],
            [{"text": "❌ Hủy bỏ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

# ========== HỆ THỐNG CHỈ BÁO XU HƯỚNG TÍCH HỢP HOÀN CHỈNH ==========
class PerfectTrendIndicatorSystem:
    """HỆ THỐNG CHỈ BÁO XU HƯỚNG HOÀN HẢO - KẾT HỢP ĐA CHỈ BÁO"""
    
    def __init__(self):
        self.ema_fast = 9
        self.ema_slow = 21
        self.ema_trend = 50
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.lookback = 100
        
    def calculate_ema(self, prices, period):
        """Tính EMA với xử lý lỗi"""
        if len(prices) < period:
            return prices[-1] if prices else 0
            
        ema = [prices[0]]
        multiplier = 2 / (period + 1)
        
        for i in range(1, len(prices)):
            ema_value = (prices[i] * multiplier) + (ema[i-1] * (1 - multiplier))
            ema.append(ema_value)
            
        return ema[-1]
    
    def calculate_rsi(self, prices, period=14):
        """Tính RSI chính xác"""
        if len(prices) < period + 1:
            return 50
            
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        if len(gains) < period:
            return 50
            
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 50
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(self, prices):
        """Tính MACD signal"""
        if len(prices) < self.macd_slow:
            return 0
            
        ema_fast = self.calculate_ema(prices, self.macd_fast)
        ema_slow = self.calculate_ema(prices, self.macd_slow)
        macd_line = ema_fast - ema_slow
        
        # Tính MACD signal line đơn giản
        macd_prices = [macd_line] * 10  # Giả lập dữ liệu MACD
        signal_line = self.calculate_ema(macd_prices, self.macd_signal)
        
        return macd_line - signal_line
    
    def get_volume_profile(self, symbol):
        """Phân tích volume nâng cao"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': '15m',
                'limit': 25
            }
            data = binance_api_request(url, params=params)
            if not data:
                return 1.0, 0.0
                
            volumes = [float(candle[5]) for candle in data]
            if len(volumes) < 5:
                return 1.0, 0.0
                
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[:-1])
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Độ biến động volume
            volume_volatility = np.std(volumes) / avg_volume if avg_volume > 0 else 0.0
            
            return volume_ratio, volume_volatility
            
        except Exception as e:
            logger.error(f"Lỗi phân tích volume {symbol}: {str(e)}")
            return 1.0, 0.0
    
    def get_market_structure(self, symbol):
        """Phân tích cấu trúc thị trường toàn diện"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': '1h',
                'limit': 50
            }
            data = binance_api_request(url, params=params)
            if not data or len(data) < 20:
                return 0, 0, "NEUTRAL"
                
            highs = [float(candle[2]) for candle in data]
            lows = [float(candle[3]) for candle in data]
            closes = [float(candle[4]) for candle in data]
            
            # Hỗ trợ và kháng cự động
            resistance = max(highs[-20:])
            support = min(lows[-20:])
            current_price = closes[-1]
            
            # Xác định xu hướng
            if current_price > resistance * 0.98:
                structure = "BULLISH"
            elif current_price < support * 1.02:
                structure = "BEARISH"
            else:
                structure = "RANGING"
            
            return support, resistance, structure
            
        except Exception as e:
            logger.error(f"Lỗi phân tích cấu trúc {symbol}: {str(e)}")
            return 0, 0, "NEUTRAL"
    
    def analyze_symbol(self, symbol):
        """PHÂN TÍCH HOÀN CHỈNH - KẾT HỢP 5 CHỈ BÁO QUAN TRỌNG"""
        try:
            klines = self.get_klines(symbol, '15m', self.lookback)
            if not klines or len(klines) < 50:
                return "NEUTRAL", 0.0
            
            closes = [float(candle[4]) for candle in klines]
            current_price = closes[-1]
            
            # 1. TÍN HIỆU EMA (25%)
            ema_fast = self.calculate_ema(closes, self.ema_fast)
            ema_slow = self.calculate_ema(closes, self.ema_slow)
            ema_trend = self.calculate_ema(closes, self.ema_trend)
            
            ema_signal = "NEUTRAL"
            ema_strength = 0
            
            if current_price > ema_fast > ema_slow > ema_trend:
                ema_signal = "BUY"
                ema_strength = 1.0
            elif current_price < ema_fast < ema_slow < ema_trend:
                ema_signal = "SELL" 
                ema_strength = 1.0
            elif current_price > ema_fast > ema_slow:
                ema_signal = "BUY"
                ema_strength = 0.7
            elif current_price < ema_fast < ema_slow:
                ema_signal = "SELL"
                ema_strength = 0.7
            elif (ema_signal == "NEUTRAL" and 
                  ((current_price > ema_fast and current_price > ema_slow) or 
                   (current_price < ema_fast and current_price < ema_slow))):
                ema_strength = 0.4
            else:
                ema_strength = 0.2
            
            # 2. TÍN HIỆU RSI (20%)
            rsi = self.calculate_rsi(closes, self.rsi_period)
            volume_ratio, volume_volatility = self.get_volume_profile(symbol)
            
            rsi_signal = "NEUTRAL"
            rsi_strength = 0
            
            if rsi < 25 and volume_ratio > 1.3:
                rsi_signal = "BUY"
                rsi_strength = min((30 - rsi) / 30 * volume_ratio, 1.0)
            elif rsi > 75 and volume_ratio > 1.3:
                rsi_signal = "SELL" 
                rsi_strength = min((rsi - 70) / 30 * volume_ratio, 1.0)
            elif 35 < rsi < 65:
                rsi_strength = 0.3
            elif (rsi < 35 and volume_ratio > 1.1) or (rsi > 65 and volume_ratio > 1.1):
                rsi_strength = 0.5
            
            # 3. TÍN HIỆU MARKET STRUCTURE (25%)
            support, resistance, structure = self.get_market_structure(symbol)
            sr_signal = "NEUTRAL"
            sr_strength = 0
            
            if support > 0 and resistance > 0:
                distance_to_resistance = (resistance - current_price) / current_price
                distance_to_support = (current_price - support) / current_price
                
                if structure == "BULLISH" and volume_ratio > 1.2:
                    sr_signal = "BUY"
                    sr_strength = min(volume_ratio * 0.8, 1.0)
                elif structure == "BEARISH" and volume_ratio > 1.2:
                    sr_signal = "SELL"
                    sr_strength = min(volume_ratio * 0.8, 1.0)
                elif distance_to_resistance < 0.008 and volume_ratio > 1.1:
                    sr_signal = "SELL"
                    sr_strength = 0.7
                elif distance_to_support < 0.008 and volume_ratio > 1.1:
                    sr_signal = "BUY" 
                    sr_strength = 0.7
                elif structure != "NEUTRAL":
                    sr_strength = 0.4
            
            # 4. TÍN HIỆU MACD (15%)
            macd_signal = "NEUTRAL"
            macd_strength = 0
            
            try:
                macd_value = self.calculate_macd(closes)
                if macd_value > 0.001:
                    macd_signal = "BUY"
                    macd_strength = min(abs(macd_value) * 100, 1.0)
                elif macd_value < -0.001:
                    macd_signal = "SELL"
                    macd_strength = min(abs(macd_value) * 100, 1.0)
                else:
                    macd_strength = 0.2
            except:
                macd_strength = 0.1
            
            # 5. TÍN HIỆU PRICE ACTION (15%)
            price_signal = self.analyze_price_action(closes)
            price_strength = 0.6 if price_signal != "NEUTRAL" else 0.2
            
            # TỔNG HỢP TẤT CẢ TÍN HIỆU VỚI TRỌNG SỐ
            signals = {
                "BUY": 0,
                "SELL": 0, 
                "NEUTRAL": 0
            }
            
            weights = {
                "EMA": 0.25,
                "RSI_VOLUME": 0.20, 
                "STRUCTURE": 0.25,
                "MACD": 0.15,
                "PRICE_ACTION": 0.15
            }
            
            # Áp dụng trọng số
            if ema_signal != "NEUTRAL":
                signals[ema_signal] += weights["EMA"] * ema_strength
                
            if rsi_signal != "NEUTRAL": 
                signals[rsi_signal] += weights["RSI_VOLUME"] * rsi_strength
                
            if sr_signal != "NEUTRAL":
                signals[sr_signal] += weights["STRUCTURE"] * sr_strength
                
            if macd_signal != "NEUTRAL":
                signals[macd_signal] += weights["MACD"] * macd_strength
                
            if price_signal != "NEUTRAL":
                signals[price_signal] += weights["PRICE_ACTION"] * price_strength
            
            # Xác định tín hiệu cuối cùng
            max_signal = max(signals, key=signals.get)
            confidence = signals[max_signal]
            
            if confidence >= 0.35:
                logger.info(f"🎯 {symbol} - {max_signal} (Độ tin cậy: {confidence:.1%})")
                logger.info(f"   📊 EMA:{ema_strength:.1%} RSI:{rsi_strength:.1%} STRUCT:{sr_strength:.1%} MACD:{macd_strength:.1%}")
                return max_signal, confidence
            else:
                logger.debug(f"⚪ {symbol} - Tín hiệu yếu (Confidence: {confidence:.1%})")
                return "NEUTRAL", confidence
                
        except Exception as e:
            logger.error(f"❌ Lỗi phân tích {symbol}: {str(e)}")
            return "NEUTRAL", 0.0
    
    def analyze_price_action(self, prices):
        """Phân tích price action đơn giản"""
        if len(prices) < 10:
            return "NEUTRAL"
            
        recent_trend = prices[-5:]
        prev_trend = prices[-10:-5]
        
        if (all(recent_trend[i] >= recent_trend[i-1] for i in range(1, len(recent_trend))) and
            recent_trend[-1] > max(prev_trend)):
            return "BUY"
        elif (all(recent_trend[i] <= recent_trend[i-1] for i in range(1, len(recent_trend))) and
              recent_trend[-1] < min(prev_trend)):
            return "SELL"
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
            logger.error(f"❌ Lỗi lấy nến {symbol} {interval}: {str(e)}")
            return None

# ========== QUẢN LÝ COIN THÔNG MINH ==========
class SmartCoinManager:
    """QUẢN LÝ COIN THÔNG MINH VỚI GIỚI HẠN ĐỘNG"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SmartCoinManager, cls).__new__(cls)
                cls._instance.managed_coins = {}
                cls._instance.max_coins = 10
                cls._instance.coin_scores = {}
        return cls._instance
    
    def set_max_coins(self, max_coins):
        """Thiết lập số coin tối đa"""
        with self._lock:
            self.max_coins = max_coins
    
    def can_add_coin(self, symbol=None):
        """Kiểm tra có thể thêm coin không"""
        with self._lock:
            return len(self.managed_coins) < self.max_coins
    
    def register_coin(self, symbol, bot_id, strategy, score=0.5):
        """Đăng ký coin với điểm số"""
        with self._lock:
            if symbol not in self.managed_coins and len(self.managed_coins) < self.max_coins:
                self.managed_coins[symbol] = {
                    "bot_id": bot_id,
                    "strategy": strategy,
                    "timestamp": time.time()
                }
                self.coin_scores[symbol] = score
                return True
            return False
    
    def unregister_coin(self, symbol):
        """Hủy đăng ký coin"""
        with self._lock:
            if symbol in self.managed_coins:
                del self.managed_coins[symbol]
                if symbol in self.coin_scores:
                    del self.coin_scores[symbol]
                return True
            return False
    
    def is_coin_managed(self, symbol):
        """Kiểm tra coin đã được quản lý chưa"""
        with self._lock:
            return symbol in self.managed_coins
    
    def get_managed_coins(self):
        """Lấy danh sách coin đang quản lý"""
        with self._lock:
            return self.managed_coins.copy()
    
    def get_available_slots(self):
        """Lấy số slot còn trống"""
        with self._lock:
            return max(0, self.max_coins - len(self.managed_coins))
    
    def get_lowest_score_coin(self):
        """Lấy coin có điểm số thấp nhất"""
        with self._lock:
            if not self.coin_scores:
                return None
            return min(self.coin_scores.items(), key=lambda x: x[1])

# ========== SMART COIN FINDER HOÀN CHỈNH ==========
class PerfectCoinFinder:
    """TÌM COIN HOÀN HẢO VỚI HỆ THỐNG ĐÁNH GIÁ ĐA TIÊU CHÍ"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.analyzer = PerfectTrendIndicatorSystem()
        self.leverage_cache = {}
        
    def check_leverage_support(self, symbol, required_leverage):
        """Kiểm tra coin hỗ trợ đòn bẩy"""
        try:
            cache_key = f"{symbol}_{required_leverage}"
            if cache_key in self.leverage_cache:
                return self.leverage_cache[cache_key]
                
            max_leverage = self.get_max_leverage(symbol)
            if max_leverage and max_leverage >= required_leverage:
                self.leverage_cache[cache_key] = True
                return True
            else:
                self.leverage_cache[cache_key] = False
                return False
                
        except Exception as e:
            return False
    
    def get_max_leverage(self, symbol):
        """Lấy đòn bẩy tối đa của coin"""
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

    def find_perfect_coin(self, target_direction, required_leverage, excluded_symbols=None):
        """TÌM COIN HOÀN HẢO THEO ĐA TIÊU CHÍ"""
        try:
            if excluded_symbols is None:
                excluded_symbols = set()
            
            logger.info(f"🔍 Tìm coin {target_direction} với đòn bẩy {required_leverage}x...")
            
            all_symbols = get_all_usdt_pairs(limit=400)
            if not all_symbols:
                logger.error("❌ Không lấy được danh sách coin từ Binance")
                return None
            
            # Xáo trộn để tránh thiên vị
            random.shuffle(all_symbols)
            
            best_coin = None
            best_score = 0
            qualified_coins = []
            
            for symbol in all_symbols:
                try:
                    # Bỏ qua các symbol đặc biệt và bị exclude
                    if (symbol in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'] or 
                        symbol in excluded_symbols or
                        "DOWN" in symbol or "UP" in symbol):
                        continue
                    
                    # Kiểm tra đòn bẩy
                    if not self.check_leverage_support(symbol, required_leverage):
                        continue
                    
                    # Phân tích coin
                    signal, confidence = self.analyzer.analyze_symbol(symbol)
                    
                    if signal == target_direction and confidence >= 0.4:
                        # Tính điểm tổng hợp
                        score = self.calculate_comprehensive_score(symbol, confidence, target_direction)
                        
                        qualified_coins.append({
                            'symbol': symbol,
                            'direction': target_direction,
                            'score': score,
                            'confidence': confidence,
                            'qualified': True
                        })
                        
                        if score > best_score:
                            best_score = score
                            best_coin = qualified_coins[-1]
                            
                except Exception as e:
                    continue
            
            # Log kết quả tìm kiếm
            if qualified_coins:
                logger.info(f"✅ Tìm thấy {len(qualified_coins)} coin {target_direction} phù hợp")
                for coin in sorted(qualified_coins, key=lambda x: x['score'], reverse=True)[:3]:
                    logger.info(f"   🥇 {coin['symbol']} - Điểm: {coin['score']:.2f} - Tin cậy: {coin['confidence']:.1%}")
            
            return best_coin if best_coin else self._find_fallback_coin(target_direction, excluded_symbols)
                
        except Exception as e:
            logger.error(f"❌ Lỗi tìm coin: {str(e)}")
            return None
    
    def calculate_comprehensive_score(self, symbol, confidence, target_direction):
        """Tính điểm tổng hợp cho coin"""
        try:
            base_score = confidence
            
            # Điểm volume
            volume_ratio, volume_volatility = self.analyzer.get_volume_profile(symbol)
            volume_score = min(volume_ratio, 2.0) / 2.0  # Chuẩn hóa về 0-1
            
            # Điểm biến động 24h
            change_24h = abs(get_24h_change(symbol))
            volatility_score = min(change_24h / 10.0, 1.0)  # Chuẩn hóa về 0-1
            
            # Điểm tổng hợp
            total_score = (base_score * 0.6 + volume_score * 0.25 + volatility_score * 0.15)
            
            return total_score
            
        except Exception:
            return confidence
    
    def _find_fallback_coin(self, target_direction, excluded_symbols):
        """Phương pháp dự phòng khi không tìm thấy coin tốt"""
        logger.info(f"🔄 Sử dụng fallback cho {target_direction}")
        
        all_symbols = get_all_usdt_pairs(limit=200)
        if not all_symbols:
            return None
            
        random.shuffle(all_symbols)
        
        for symbol in all_symbols:
            if symbol in ['BTCUSDT', 'ETHUSDT'] or symbol in excluded_symbols:
                continue
                
            try:
                change_24h = get_24h_change(symbol)
                if change_24h is None:
                    continue
                
                if target_direction == "BUY" and change_24h < -3:
                    return {
                        'symbol': symbol,
                        'direction': target_direction,
                        'score': 0.4,
                        'confidence': 0.4,
                        'fallback': True,
                        'qualified': True
                    }
                elif target_direction == "SELL" and change_24h > 3:
                    return {
                        'symbol': symbol,
                        'direction': target_direction,
                        'score': 0.4,
                        'confidence': 0.4,
                        'fallback': True,
                        'qualified': True
                    }
                        
            except Exception:
                continue
        
        return None

# ========== CÂN BẰNG VỊ THẾ THÔNG MINH ==========
class IntelligentPositionBalancer:
    """CÂN BẰNG VỊ THẾ THÔNG MINH DỰA TRÊN ĐA YẾU TỐ"""
    
    def __init__(self, bot_manager):
        self.bot_manager = bot_manager
        self.position_history = []
        self.max_history = 100
        
    def get_portfolio_balance(self):
        """Phân tích cân bằng toàn bộ portfolio"""
        try:
            all_positions = get_positions(api_key=self.bot_manager.api_key, 
                                        api_secret=self.bot_manager.api_secret)
            
            if not all_positions:
                return {"status": "empty", "recommendation": "NEUTRAL", "details": "Không có vị thế"}
            
            # Thống kê chi tiết
            stats = {
                'long_count': 0,
                'short_count': 0,
                'long_value': 0.0,
                'short_value': 0.0,
                'total_value': 0.0,
                'unrealized_pnl': 0.0
            }
            
            position_details = []
            
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry_price = float(pos.get('entryPrice', 0))
                    leverage = float(pos.get('leverage', 1))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    
                    position_value = abs(position_amt) * entry_price / leverage
                    stats['total_value'] += position_value
                    stats['unrealized_pnl'] += unrealized_pnl
                    
                    if position_amt > 0:
                        stats['long_count'] += 1
                        stats['long_value'] += position_value
                        position_details.append(f"{symbol}(LONG:${position_value:.0f})")
                    else:
                        stats['short_count'] += 1
                        stats['short_value'] += position_value
                        position_details.append(f"{symbol}(SHORT:${position_value:.0f})")
            
            # Tính tỷ lệ
            total_count = stats['long_count'] + stats['short_count']
            if total_count > 0:
                stats['long_ratio'] = stats['long_count'] / total_count
                stats['short_ratio'] = stats['short_count'] / total_count
            else:
                stats['long_ratio'] = stats['short_ratio'] = 0.5
                
            if stats['total_value'] > 0:
                stats['long_value_ratio'] = stats['long_value'] / stats['total_value']
                stats['short_value_ratio'] = stats['short_value'] / stats['total_value']
            else:
                stats['long_value_ratio'] = stats['short_value_ratio'] = 0.5
            
            # Đề xuất chiến lược
            recommendation = self._generate_recommendation(stats)
            
            # Lưu lịch sử
            self.position_history.append({
                'timestamp': time.time(),
                'stats': stats,
                'recommendation': recommendation
            })
            if len(self.position_history) > self.max_history:
                self.position_history.pop(0)
            
            return {
                "status": "analyzed",
                "recommendation": recommendation,
                "stats": stats,
                "details": position_details
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi phân tích portfolio: {str(e)}")
            return {"status": "error", "recommendation": "NEUTRAL", "details": str(e)}
    
    def _generate_recommendation(self, stats):
        """Tạo đề xuất chiến lược thông minh"""
        # Ưu tiên phân tích theo giá trị hơn là số lượng
        long_value_ratio = stats.get('long_value_ratio', 0.5)
        short_value_ratio = stats.get('short_value_ratio', 0.5)
        
        if long_value_ratio >= 0.7:
            return "SELL"
        elif short_value_ratio >= 0.7:
            return "BUY"
        elif long_value_ratio >= 0.6:
            return "SELL"
        elif short_value_ratio >= 0.6:
            return "BUY"
        elif long_value_ratio > short_value_ratio + 0.15:
            return "SELL"
        elif short_value_ratio > long_value_ratio + 0.15:
            return "BUY"
        else:
            # Ngẫu nhiên có trọng số nhẹ
            return "BUY" if random.random() > 0.5 else "SELL"
    
    def get_intelligent_direction(self):
        """Lấy hướng giao dịch thông minh"""
        analysis = self.get_portfolio_balance()
        
        if analysis["status"] == "empty":
            logger.info("⚖️ Portfolio trống → Chọn hướng ngẫu nhiên")
            return "BUY" if random.random() > 0.5 else "SELL"
        
        recommendation = analysis["recommendation"]
        stats = analysis["stats"]
        
        logger.info(f"⚖️ CÂN BẰNG: LONG {stats['long_count']}(${stats['long_value']:.0f}) "
                   f"vs SHORT {stats['short_count']}(${stats['short_value']:.0f}) "
                   f"→ {recommendation}")
        
        return recommendation

# ========== API BINANCE HOÀN CHỈNH ==========
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
            change = data['priceChangePercent']
            if change is None:
                return 0.0
            return float(change) if change is not None else 0.0
        return 0.0
    except Exception as e:
        logger.error(f"Lỗi lấy biến động 24h cho {symbol}: {str(e)}")
    return 0.0

# ========== WEBSOCKET MANAGER HOÀN CHỈNH ==========
class WebSocketManager:
    def __init__(self):
        self.connections = {}
        self.executor = ThreadPoolExecutor(max_workers=20)
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

# ========== BOT GIAO DỊCH HOÀN HẢO ==========
class PerfectTradingBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, config_key=None, bot_id=None):
        
        self.symbol = symbol.upper() if symbol else None
        self.lev = lev
        self.percent = percent
        self.tp = tp
        # Xử lý tắt SL
        self.sl = None if sl == 0 else sl
        self.ws_manager = ws_manager
        self.api_key = api_key
        self.api_secret = api_secret
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.config_key = config_key
        self.bot_id = bot_id or f"PERFECT_BOT_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Trạng thái bot
        self.status = "searching"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.position_open = False
        self._stop = False
        
        # Quản lý thời gian
        self.last_trade_time = 0
        self.last_close_time = 0
        self.last_position_check = 0
        self.last_analysis_time = 0
        
        self.cooldown_period = 180
        self.position_check_interval = 20
        self.analysis_interval = 120
        
        # Bảo vệ chống lặp
        self._close_attempted = False
        self._last_close_attempt = 0
        
        # Quản lý coin
        self.coin_manager = SmartCoinManager()
        self.coin_finder = PerfectCoinFinder(api_key, api_secret)
        self.position_balancer = None  # Sẽ được thiết lập bởi BotManager
        
        # Tìm kiếm coin
        self.current_target_direction = None
        self.last_find_time = 0
        self.find_interval = 30
        
        # Phân tích
        self.analyzer = PerfectTrendIndicatorSystem()
        
        # Chiếm slot
        self.coin_occupied = False
        
        # Khởi động
        self.check_position_status()
        if self.symbol:
            self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        # Log khởi động
        sl_display = "TẮT" if self.sl is None else f"{self.sl}%"
        self.log(f"🚀 Bot hoàn hảo khởi động | ĐB: {lev}x | Vốn: {percent}% | TP: {tp}% | SL: {sl_display}")

    def log(self, message):
        """Log thông minh - chỉ log quan trọng"""
        bot_info = f"[Bot {self.bot_id}]"
        logger.info(f"{bot_info} [{self.symbol or 'NO_COIN'}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            symbol_info = f"<b>{self.symbol}</b>" if self.symbol else "<i>Đang tìm coin...</i>"
            send_telegram(f"{symbol_info} (Bot {self.bot_id}): {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def _handle_price_update(self, price):
        """Xử lý cập nhật giá real-time"""
        if self._stop or not price or price <= 0:
            return
        try:
            # Có thể thêm xử lý price action real-time ở đây
            pass
        except Exception as e:
            self.log(f"❌ Lỗi xử lý giá: {str(e)}")

    def get_signal(self):
        """Lấy tín hiệu từ hệ thống phân tích hoàn hảo"""
        if not self.symbol:
            return None
            
        try:
            current_time = time.time()
            if current_time - self.last_analysis_time < self.analysis_interval:
                return None
            
            self.last_analysis_time = current_time
            
            signal, confidence = self.analyzer.analyze_symbol(self.symbol)
            
            if signal != "NEUTRAL":
                self.log(f"🎯 Nhận tín hiệu {signal} (Độ tin cậy: {confidence:.1%})")
            
            return signal
            
        except Exception as e:
            self.log(f"❌ Lỗi phân tích: {str(e)}")
            return None

    def get_intelligent_direction(self):
        """Xác định hướng giao dịch thông minh"""
        if self.position_balancer:
            return self.position_balancer.get_intelligent_direction()
        else:
            # Fallback cơ bản
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

    def find_and_acquire_coin(self):
        """Tìm và chiếm coin thông minh"""
        current_time = time.time()
        if current_time - self.last_find_time < self.find_interval:
            return False
        
        self.last_find_time = current_time
        
        # Kiểm tra slot còn trống
        if not self.coin_manager.can_add_coin():
            return False
        
        # Xác định hướng giao dịch thông minh
        self.current_target_direction = self.get_intelligent_direction()
        
        # Lấy danh sách coin đang được quản lý
        managed_coins = self.coin_manager.get_managed_coins()
        excluded_symbols = set(managed_coins.keys())
        
        # Tìm coin hoàn hảo
        coin_data = self.coin_finder.find_perfect_coin(
            self.current_target_direction, 
            self.lev,
            excluded_symbols
        )
    
        if coin_data and coin_data.get('qualified', False):
            new_symbol = coin_data['symbol']
            
            # Chiếm slot
            if self.coin_manager.register_coin(new_symbol, self.bot_id, "PerfectSystem", coin_data['score']):
                # Giải phóng coin cũ nếu có
                if self.symbol and self.coin_occupied:
                    self.ws_manager.remove_symbol(self.symbol)
                    self.coin_manager.unregister_coin(self.symbol)
                
                # Cập nhật coin mới
                self.symbol = new_symbol
                self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
                self.coin_occupied = True
                
                self.log(f"🎯 Đã tìm thấy coin hoàn hảo: {new_symbol} - {self.current_target_direction} (Điểm: {coin_data['score']:.2f})")
                return True
            else:
                self.log(f"❌ Không thể chiếm slot cho {new_symbol}")
                return False
        
        return False

    def check_position_status(self):
        """Kiểm tra trạng thái vị thế chính xác"""
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
            self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")

    def _reset_position(self):
        """Reset trạng thái an toàn"""
        if self.position_open and self.symbol and self.coin_occupied:
            self.coin_manager.unregister_coin(self.symbol)
            self.ws_manager.remove_symbol(self.symbol)
            self.coin_occupied = False
            
        self.position_open = False
        self.status = "searching" if not self.symbol else "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self._close_attempted = False
        self._last_close_attempt = 0

    def _run(self):
        """Vòng lặp chính thông minh"""
        while not self._stop:
            try:
                current_time = time.time()
                
                # Kiểm tra vị thế định kỳ
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                
                if not self.position_open:
                    # Tìm và chiếm coin nếu cần
                    if not self.symbol or not self.coin_occupied or self.status == "searching":
                        if self.find_and_acquire_coin():
                            time.sleep(2)
                            continue
                    
                    # Phân tích và giao dịch
                    signal = self.get_signal()
                    
                    if signal and signal != "NEUTRAL":
                        # Kiểm tra điều kiện giao dịch
                        if (current_time - self.last_trade_time > 15 and
                            current_time - self.last_close_time > self.cooldown_period):
                            
                            if self.open_position(signal):
                                self.last_trade_time = current_time
                            else:
                                # Không mở được vị thế, tìm coin khác
                                self.status = "searching"
                                if self.symbol and self.coin_occupied:
                                    self.coin_manager.unregister_coin(self.symbol)
                                    self.coin_occupied = False
                                self.symbol = None
                                time.sleep(2)
                        else:
                            time.sleep(1)
                    else:
                        # Tín hiệu trung lập, tìm coin khác sau một thời gian
                        if signal == "NEUTRAL" and current_time - self.last_find_time > 60:
                            self.status = "searching"
                            if self.symbol and self.coin_occupied:
                                self.coin_manager.unregister_coin(self.symbol)
                                self.coin_occupied = False
                            self.symbol = None
                        time.sleep(2)
                
                # Kiểm tra TP/SL
                if self.position_open and not self._close_attempted:
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception as e:
                self.log(f"❌ Lỗi hệ thống: {str(e)}")
                time.sleep(5)

    def stop(self):
        """Dừng bot an toàn"""
        self._stop = True
        if self.symbol and self.coin_occupied:
            self.ws_manager.remove_symbol(self.symbol)
            self.coin_manager.unregister_coin(self.symbol)
        self.log(f"🔴 Bot dừng")

    def open_position(self, side):
        """Mở vị thế thông minh"""
        try:
            self.check_position_status()
            if self.position_open:
                return False
    
            if not set_leverage(self.symbol, self.lev, self.api_key, self.api_secret):
                self.log(f"❌ Không thể đặt đòn bẩy {self.lev}x")
                return False
    
            balance = get_balance(self.api_key, self.api_secret)
            if balance is None or balance <= 0:
                self.log("❌ Không đủ số dư")
                return False
    
            current_price = get_current_price(self.symbol)
            if current_price <= 0:
                self.log("❌ Lỗi lấy giá")
                return False
    
            step_size = get_step_size(self.symbol, self.api_key, self.api_secret)
            usd_amount = balance * (self.percent / 100)
            qty = (usd_amount * self.lev) / current_price
            
            if step_size > 0:
                qty = math.floor(qty / step_size) * step_size
                qty = round(qty, 8)
    
            if qty < step_size:
                self.log(f"❌ Số lượng quá nhỏ: {qty}")
                return False
    
            self.log(f"📊 Đang mở lệnh {side} - SL: {step_size}, Qty: {qty}, Giá: {current_price}")
            
            result = place_order(self.symbol, side, qty, self.api_key, self.api_secret)
            if result and 'orderId' in result:
                executed_qty = float(result.get('executedQty', 0))
                avg_price = float(result.get('avgPrice', current_price))
                
                if executed_qty > 0:
                    self.entry = avg_price
                    self.side = side
                    self.qty = executed_qty if side == "BUY" else -executed_qty
                    self.position_open = True
                    self.status = "open"
                    
                    # Hiển thị SL
                    sl_display = "TẮT" if self.sl is None else f"{self.sl}%"
                    
                    message = (
                        f"✅ <b>MỞ VỊ THẾ THÀNH CÔNG</b>\n"
                        f"🔗 Coin: {self.symbol}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {self.entry:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💰 Giá trị: {executed_qty * self.entry:.2f} USDT\n"
                        f"💵 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {sl_display}"
                    )
                    self.log(message)
                    return True
                else:
                    self.log(f"❌ Lệnh không khớp - Số lượng: {qty}")
                    return False
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đặt lệnh {side}: {error_msg}")
                return False
                    
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False

    def close_position(self, reason=""):
        """Đóng vị thế an toàn"""
        try:
            self.check_position_status()
            
            if not self.position_open or abs(self.qty) <= 0:
                self.log(f"⚠️ Không có vị thế để đóng: {reason}")
                return False

            current_time = time.time()
            if self._close_attempted and current_time - self._last_close_attempt < 30:
                return False
            
            self._close_attempted = True
            self._last_close_attempt = current_time

            close_side = "SELL" if self.side == "BUY" else "BUY"
            close_qty = abs(self.qty)
            
            # Hủy tất cả lệnh chờ
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
            time.sleep(0.5)
            
            # Đóng lệnh
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
                    f"⛔ <b>ĐÓNG VỊ THẾ THÀNH CÔNG</b>\n"
                    f"🔗 Coin: {self.symbol}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDT"
                )
                self.log(message)
                
                # Reset trạng thái
                self._reset_position()
                self.last_close_time = time.time()
                
                time.sleep(2)
                self.check_position_status()
                
                return True
            else:
                self._close_attempted = False
                self.log("❌ Lỗi đóng lệnh")
                return False
                
        except Exception as e:
            self._close_attempted = False
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            return False

    def check_tp_sl(self):
        """Kiểm tra Take Profit và Stop Loss thông minh"""
        if not self.position_open or self.entry <= 0 or self._close_attempted:
            return

        current_price = get_current_price(self.symbol)
        if current_price <= 0:
            return

        # Tính ROI
        if self.side == "BUY":
            profit = (current_price - self.entry) * abs(self.qty)
        else:
            profit = (self.entry - current_price) * abs(self.qty)
            
        invested = self.entry * abs(self.qty) / self.lev
        if invested <= 0:
            return
            
        roi = (profit / invested) * 100

        # Kiểm tra TP
        if self.tp is not None and roi >= self.tp:
            self.close_position(f"✅ Đạt TP {self.tp}% (ROI: {roi:.2f}%)")
        # Kiểm tra SL (chỉ khi SL được bật)
        elif self.sl is not None and roi <= -self.sl:
            self.close_position(f"❌ Đạt SL {self.sl}% (ROI: {roi:.2f}%)")

# ========== HỆ THỐNG QUẢN LÝ HOÀN CHỈNH ==========
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
        
        # Hệ thống quản lý
        self.coin_manager = SmartCoinManager()
        self.position_balancer = IntelligentPositionBalancer(self)
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🚀 HỆ THỐNG BOT HOÀN HẢO ĐÃ KHỞI ĐỘNG")
            self.log("🎯 Kết hợp 5 chỉ báo: EMA + RSI + Volume + Market Structure + MACD")
            
            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()
            
            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)
        else:
            self.log("⚡ BotManager khởi động ở chế độ không config")

    def _verify_api_connection(self):
        """Kiểm tra kết nối API"""
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance API.")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def log(self, message):
        """Log hệ thống"""
        logger.info(f"[PERFECT_SYSTEM] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>HỆ THỐNG HOÀN HẢO</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        """Gửi menu chính"""
        welcome = (
            "🤖 <b>HỆ THỐNG BOT GIAO DỊCH HOÀN HẢO</b>\n\n"
            "🎯 <b>TÍCH HỢP 5 CHỈ BÁO THÔNG MINH</b>\n"
            "• 📈 EMA Đa khung (9,21,50)\n"
            "• 🔄 RSI + Volume confirmation\n"  
            "• 🏰 Market Structure & S/R\n"
            "• 📊 MACD Signal\n"
            "• ⚡ Price Action\n\n"
            "⚖️ <b>CÂN BẰNG VỊ THẾ THÔNG MINH</b>\n"
            "• Tự động phân tích portfolio\n"
            "• Đề xuất hướng giao dịch tối ưu\n"
            "• Quản lý rủi ro đa tầng\n\n"
            "🔢 <b>QUẢN LÝ COIN THÔNG MINH</b>\n"
            "• Giới hạn số coin tối đa\n"
            "• Tự động chuyển coin không phù hợp\n"
            "• Chiếm slot thông minh"
        )
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def start_perfect_system(self, bot_count, leverage, percent, tp, sl, max_coins):
        """Khởi chạy hệ thống hoàn hảo"""
        if not self.api_key or not self.api_secret:
            self.log("❌ Chưa thiết lập API Key")
            return False
        
        # Kiểm tra kết nối
        test_balance = get_balance(self.api_key, self.api_secret)
        if test_balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance")
            return False
        
        # Thiết lập giới hạn coin
        self.coin_manager.set_max_coins(max_coins)
        
        # Xử lý SL
        actual_sl = 0 if sl == "TẮT SL" else sl
        
        created_count = 0
        
        for i in range(bot_count):
            try:
                bot_id = f"PERFECT_BOT_{i}_{int(time.time())}"
                
                if bot_id in self.bots:
                    continue
                
                bot = PerfectTradingBot(
                    symbol=None,  # Bot động
                    lev=leverage,
                    percent=percent, 
                    tp=tp,
                    sl=actual_sl,
                    ws_manager=self.ws_manager,
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    telegram_bot_token=self.telegram_bot_token,
                    telegram_chat_id=self.telegram_chat_id,
                    bot_id=bot_id
                )
                
                # Kết nối position balancer
                bot.position_balancer = self.position_balancer
                
                self.bots[bot_id] = bot
                created_count += 1
                
            except Exception as e:
                self.log(f"❌ Lỗi tạo bot {i}: {str(e)}")
                continue
        
        if created_count > 0:
            sl_display = "TẮT" if actual_sl == 0 else f"{actual_sl}%"
            
            success_msg = (
                f"✅ <b>HỆ THỐNG HOÀN HẢO ĐÃ KHỞI CHẠY</b>\n\n"
                f"🤖 Số lượng bot: {created_count}\n"
                f"💰 Đòn bẩy: {leverage}x\n"
                f"📊 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl_display}\n"
                f"🔢 Coin tối đa: {max_coins}\n\n"
                f"🎯 <b>CHIẾN LƯỢC HOÀN HẢO</b>\n"
                f"• 5 chỉ báo tích hợp thông minh\n"
                f"• Cân bằng vị thế tự động\n"
                f"• Quản lý coin thông minh\n"
                f"• Tìm kiếm coin tối ưu\n"
                f"• Chuyển coin linh hoạt"
            )
            
            self.log(success_msg)
            return True
        else:
            self.log("❌ Không thể tạo bot nào")
            return False

    def stop_bot(self, bot_id):
        """Dừng bot cụ thể"""
        bot = self.bots.get(bot_id)
        if bot:
            bot.stop()
            del self.bots[bot_id]
            self.log(f"⛔ Đã dừng bot {bot_id}")
            return True
        return False

    def stop_all(self):
        """Dừng toàn bộ hệ thống"""
        self.log("⛔ Đang dừng toàn bộ hệ thống...")
        for bot_id in list(self.bots.keys()):
            self.stop_bot(bot_id)
        self.ws_manager.stop()
        self.running = False
        self.log("🔴 Hệ thống đã dừng hoàn toàn")

    def get_system_summary(self):
        """Lấy thống kê hệ thống chi tiết"""
        try:
            # Phân tích portfolio
            portfolio_analysis = self.position_balancer.get_portfolio_balance()
            
            # Thống kê bot
            bot_stats = {
                'total_bots': len(self.bots),
                'searching_bots': 0,
                'trading_bots': 0,
                'open_positions': 0
            }
            
            bot_details = []
            for bot_id, bot in self.bots.items():
                if bot.status == "searching":
                    bot_stats['searching_bots'] += 1
                elif bot.status in ["waiting", "open"]:
                    bot_stats['trading_bots'] += 1
                
                if bot.position_open:
                    bot_stats['open_positions'] += 1
                
                bot_details.append(f"{bot_id} - {bot.symbol or 'Tìm coin'} - {bot.status}")
            
            # Thống kê coin
            managed_coins = self.coin_manager.get_managed_coins()
            available_slots = self.coin_manager.get_available_slots()
            
            summary = (
                f"📊 <b>THỐNG KÊ HỆ THỐNG HOÀN HẢO</b>\n\n"
                f"🤖 <b>BOT</b>: {bot_stats['total_bots']} bots\n"
                f"   🔍 Đang tìm coin: {bot_stats['searching_bots']}\n"
                f"   📈 Đang trade: {bot_stats['trading_bots']}\n"
                f"   📊 Vị thế mở: {bot_stats['open_positions']}\n\n"
                f"🔢 <b>QUẢN LÝ COIN</b>\n"
                f"   🎯 Coin tối đa: {self.coin_manager.max_coins}\n"
                f"   🔗 Đang quản lý: {len(managed_coins)} coin\n"
                f"   🔓 Còn trống: {available_slots} slot\n"
            )
            
            if managed_coins:
                summary += f"\n📋 <b>Danh sách coin:</b>\n"
                for symbol in list(managed_coins.keys())[:8]:
                    summary += f"• {symbol}\n"
                if len(managed_coins) > 8:
                    summary += f"... và {len(managed_coins) - 8} coin khác\n"
            
            if portfolio_analysis["status"] == "analyzed":
                stats = portfolio_analysis["stats"]
                summary += (
                    f"\n💰 <b>PORTFOLIO BINANCE</b>\n"
                    f"   🟢 LONG: {stats['long_count']} (${stats['long_value']:.0f})\n"
                    f"   🔴 SHORT: {stats['short_count']} (${stats['short_value']:.0f})\n"
                    f"   📈 Tổng giá trị: ${stats['total_value']:.0f}\n"
                    f"   💰 PnL: ${stats['unrealized_pnl']:.2f}\n"
                    f"   ⚖️ Đề xuất: {portfolio_analysis['recommendation']}"
                )
            
            return summary
                    
        except Exception as e:
            return f"❌ Lỗi thống kê: {str(e)}"

    def _telegram_listener(self):
        """Lắng nghe tin nhắn Telegram"""
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
        """Xử lý tin nhắn Telegram"""
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        if text == "🚀 Khởi chạy hệ thống":
            self.user_states[chat_id] = {'step': 'waiting_bot_count'}
            
            balance = get_balance(self.api_key, self.api_secret)
            balance_info = f"\n💰 Số dư hiện có: <b>{balance:.2f} USDT</b>" if balance else ""
            
            send_telegram(
                "🚀 <b>KHỞI CHẠY HỆ THỐNG HOÀN HẢO</b>\n\n"
                f"{balance_info}\n\n"
                "Chọn số lượng bot độc lập:",
                chat_id,
                create_bot_count_keyboard(),
                self.telegram_bot_token, self.telegram_chat_id
            )
        
        elif current_step == 'waiting_bot_count':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    bot_count = int(text)
                    if bot_count <= 0 or bot_count > 8:
                        send_telegram("⚠️ Số bot phải từ 1-8. Chọn lại:",
                                    chat_id, create_bot_count_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['bot_count'] = bot_count
                    user_state['step'] = 'waiting_leverage'
                    
                    send_telegram(
                        f"🤖 Số bot: {bot_count}\n\n"
                        f"Chọn đòn bẩy:",
                        chat_id,
                        create_leverage_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng chọn số hợp lệ:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_leverage':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    lev_text = text[:-1] if text.endswith('x') else text
                    leverage = int(lev_text)
                    
                    if leverage <= 0 or leverage > 25:
                        send_telegram("⚠️ Đòn bẩy phải từ 1-25. Chọn lại:",
                                    chat_id, create_leverage_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['leverage'] = leverage
                    user_state['step'] = 'waiting_percent'
                    
                    send_telegram(
                        f"💰 Đòn bẩy: {leverage}x\n\n"
                        f"Chọn % số dư mỗi lệnh:",
                        chat_id,
                        create_percent_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng chọn đòn bẩy hợp lệ:",
                                chat_id, create_leverage_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_percent':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    percent = float(text)
                    if percent <= 0 or percent > 20:
                        send_telegram("⚠️ % số dư phải từ 0.1-20. Chọn lại:",
                                    chat_id, create_percent_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['percent'] = percent
                    user_state['step'] = 'waiting_tp'
                    
                    balance = get_balance(self.api_key, self.api_secret)
                    amount_info = f"\n💵 ~{balance * (percent/100):.2f} USDT/lệnh" if balance else ""
                    
                    send_telegram(
                        f"📊 % Số dư: {percent}%{amount_info}\n\n"
                        f"Chọn Take Profit (%):",
                        chat_id,
                        create_tp_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_percent_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_tp':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    tp = float(text)
                    if tp <= 0:
                        send_telegram("⚠️ Take Profit phải > 0. Chọn lại:",
                                    chat_id, create_tp_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    user_state['tp'] = tp
                    user_state['step'] = 'waiting_sl'
                    
                    send_telegram(
                        f"🎯 Take Profit: {tp}%\n\n"
                        f"Chọn Stop Loss (%):\n"
                        f"<i>Chọn 'TẮT SL' để không dừng lỗ</i>",
                        chat_id,
                        create_sl_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ:",
                                chat_id, create_tp_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_sl':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    if text == 'TẮT SL':
                        user_state['sl'] = "TẮT SL"
                    else:
                        sl = float(text)
                        if sl < 0:
                            send_telegram("⚠️ Stop Loss phải ≥ 0. Chọn lại:",
                                        chat_id, create_sl_keyboard(),
                                        self.telegram_bot_token, self.telegram_chat_id)
                            return
                        user_state['sl'] = sl
                    
                    user_state['step'] = 'waiting_max_coins'
                    
                    sl_display = "TẮT" if user_state['sl'] == "TẮT SL" else f"{user_state['sl']}%"
                    
                    send_telegram(
                        f"🛡️ Stop Loss: {sl_display}\n\n"
                        f"Chọn số lượng coin tối đa:",
                        chat_id,
                        create_coin_per_bot_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )
                except ValueError:
                    send_telegram("⚠️ Vui lòng nhập số hợp lệ hoặc chọn 'TẮT SL':",
                                chat_id, create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif current_step == 'waiting_max_coins':
            if text == '❌ Hủy bỏ':
                self.user_states[chat_id] = {}
                send_telegram("❌ Đã hủy", chat_id, create_main_menu(),
                            self.telegram_bot_token, self.telegram_chat_id)
            else:
                try:
                    max_coins = int(text)
                    if max_coins <= 0 or max_coins > 10:
                        send_telegram("⚠️ Số coin phải từ 1-10. Chọn lại:",
                                    chat_id, create_coin_per_bot_keyboard(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                        return

                    # Khởi chạy hệ thống
                    bot_count = user_state.get('bot_count')
                    leverage = user_state.get('leverage')
                    percent = user_state.get('percent')
                    tp = user_state.get('tp')
                    sl = user_state.get('sl')
                    
                    success = self.start_perfect_system(
                        bot_count=bot_count,
                        leverage=leverage,
                        percent=percent,
                        tp=tp,
                        sl=sl,
                        max_coins=max_coins
                    )
                    
                    if success:
                        sl_display = "TẮT" if sl == "TẮT SL" else f"{sl}%"
                        
                        success_msg = (
                            f"✅ <b>HỆ THỐNG HOÀN HẢO ĐÃ KHỞI CHẠY THÀNH CÔNG</b>\n\n"
                            f"🤖 Số bot: {bot_count}\n"
                            f"💰 Đòn bẩy: {leverage}x\n"
                            f"📊 % Số dư: {percent}%\n"
                            f"🎯 TP: {tp}%\n"
                            f"🛡️ SL: {sl_display}\n"
                            f"🔢 Coin tối đa: {max_coins}\n\n"
                            f"🎯 <b>CHIẾN LƯỢC ĐANG HOẠT ĐỘNG</b>\n"
                            f"• 5 chỉ báo thông minh\n"
                            f"• Cân bằng vị thế tự động\n"
                            f"• Quản lý coin thông minh\n"
                            f"• Tìm kiếm coin tối ưu"
                        )
                        
                        send_telegram(success_msg, chat_id, create_main_menu(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    else:
                        send_telegram("❌ Lỗi khởi chạy hệ thống", chat_id, create_main_menu(),
                                    self.telegram_bot_token, self.telegram_chat_id)
                    
                    self.user_states[chat_id] = {}
                    
                except ValueError:
                    send_telegram("⚠️ Vui lòng chọn số hợp lệ:",
                                chat_id, create_coin_per_bot_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)

        elif text == "📊 Danh sách Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                message = "🤖 <b>DANH SÁCH BOT HOÀN HẢO</b>\n\n"
                
                for i, (bot_id, bot) in enumerate(self.bots.items()):
                    symbol_info = bot.symbol if bot.symbol else "Đang tìm coin..."
                    status = "🟢 Đang trade" if bot.position_open else "🔍 Đang tìm"
                    sl_display = "TẮT" if bot.sl is None else f"{bot.sl}%"
                    
                    message += (
                        f"🔹 Bot {i+1}: {bot_id}\n"
                        f"   📊 {symbol_info} | {status}\n"
                        f"   💰 ĐB: {bot.lev}x | Vốn: {bot.percent}%\n"
                        f"   🎯 TP/SL: {bot.tp}%/{sl_display}\n\n"
                    )
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📊 Thống kê":
            summary = self.get_system_summary()
            send_telegram(summary, chat_id,
                         bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⛔ Dừng Bot":
            if not self.bots:
                send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            else:
                self.stop_all()
                send_telegram("⛔ Đã dừng toàn bộ hệ thống", chat_id, create_main_menu(),
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
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy số dư: {str(e)}", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "📈 Vị thế":
            try:
                positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
                open_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
                
                if not open_positions:
                    send_telegram("📭 Không có vị thế nào đang mở", chat_id,
                                bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
                    return
                
                message = "📈 <b>VỊ THẾ ĐANG MỞ TRÊN BINANCE</b>\n\n"
                for pos in open_positions[:10]:  # Giới hạn hiển thị
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry = float(pos.get('entryPrice', 0))
                    side = "LONG" if float(pos.get('positionAmt', 0)) > 0 else "SHORT"
                    pnl = float(pos.get('unRealizedProfit', 0))
                    leverage = float(pos.get('leverage', 1))
                    amount = abs(float(pos.get('positionAmt', 0)))
                    
                    message += (
                        f"🔹 {symbol} | {side}\n"
                        f"   📊 Đòn bẩy: {leverage}x\n"
                        f"   🏷️ Giá vào: {entry:.4f}\n"
                        f"   ⚖️ Khối lượng: {amount:.4f}\n"
                        f"   💰 PnL: {pnl:.2f} USDT\n\n"
                    )
                
                if len(open_positions) > 10:
                    message += f"... và {len(open_positions) - 10} vị thế khác"
                
                send_telegram(message, chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            except Exception as e:
                send_telegram(f"⚠️ Lỗi lấy vị thế: {str(e)}", chat_id,
                            bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "🎯 Chiến lược":
            strategy_info = (
                "🎯 <b>CHIẾN LƯỢC HỆ THỐNG HOÀN HẢO</b>\n\n"
                
                "🤖 <b>HỆ THỐNG 5 CHỈ BÁO TÍCH HỢP</b>\n"
                "• 📈 <b>EMA Đa khung</b> (9,21,50) - Xu hướng chính\n"
                "• 🔄 <b>RSI + Volume</b> - Quá mua/quá bán có xác nhận\n"
                "• 🏰 <b>Market Structure</b> - Hỗ trợ/kháng cự động\n"
                "• 📊 <b>MACD Signal</b> - Động lượng xu hướng\n"
                "• ⚡ <b>Price Action</b> - Hành động giá thực tế\n\n"
                
                "⚖️ <b>CÂN BẰNG VỊ THẾ THÔNG MINH</b>\n"
                "• Phân tích toàn bộ portfolio Binance\n"
                "• Đề xuất hướng dựa trên tỷ lệ LONG/SHORT\n"
                "• Ưu tiên cân bằng theo giá trị hơn số lượng\n"
                "• Tự động điều chỉnh chiến lược\n\n"
                
                "🔢 <b>QUẢN LÝ COIN THÔNG MINH</b>\n"
                "• Giới hạn số coin tối đa để đa dạng hóa\n"
                "• Tự động chuyển coin khi tín hiệu không phù hợp\n"
                "• Chiếm slot ngay khi tìm được coin tốt\n"
                "• Đánh giá coin theo điểm số đa tiêu chí\n\n"
                
                "🚀 <b>ƯU ĐIỂM VƯỢT TRỘI</b>\n"
                "• Độ chính xác cao với 5 chỉ báo độc lập\n"
                "• Quản lý rủi ro đa tầng thông minh\n"
                "• Thích ứng nhanh với thị trường\n"
                "• Tối ưu hóa hiệu suất portfolio"
            )
            send_telegram(strategy_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text == "⚙️ Cấu hình":
            balance = get_balance(self.api_key, self.api_secret)
            api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
            
            config_info = (
                "⚙️ <b>CẤU HÌNH HỆ THỐNG HOÀN HẢO</b>\n\n"
                f"🔑 Binance API: {api_status}\n"
                f"🤖 Số bot đang chạy: {len(self.bots)}\n"
                f"🔢 Coin tối đa: {self.coin_manager.max_coins}\n"
                f"🔗 Đang quản lý: {len(self.coin_manager.get_managed_coins())} coin\n"
                f"🌐 WebSocket: {len(self.ws_manager.connections)} kết nối\n"
                f"⚖️ Position Balancer: Đã sẵn sàng\n\n"
                f"🎯 <b>HỆ THỐNG ĐANG HOẠT ĐỘNG ỔN ĐỊNH</b>"
            )
            send_telegram(config_info, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        
        elif text:
            self.send_main_menu(chat_id)

# ========== KHỞI TẠO HỆ THỐNG TOÀN CẦU ==========
perfect_system = None

def initialize_perfect_system(api_key, api_secret, telegram_bot_token, telegram_chat_id):
    """Khởi tạo hệ thống hoàn hảo toàn cục"""
    global perfect_system
    perfect_system = PerfectBotManager(api_key, api_secret, telegram_bot_token, telegram_chat_id)
    return perfect_system
