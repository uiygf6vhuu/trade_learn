# trading_bot_lib.py - HỆ THỐNG TRADING BOT HOÀN CHỈNH
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
from collections import deque

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
            [{"text": "⏰ Trend System"}],
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

# ========== HỆ THỐNG THỐNG KÊ XÁC SUẤT & KỲ VỌNG ==========
class ProbabilityAnalyzer:
    """PHÂN TÍCH XÁC SUẤT THẮNG CỦA CÁC CHỈ BÁO"""
    
    def __init__(self, lookback=200, evaluation_period=20):
        self.lookback = lookback
        self.evaluation_period = evaluation_period
        self.history_data = {}
        self.probability_stats = {
            'rsi': {
                'ranges': [(0, 20), (20, 45), (45, 55), (55, 80), (80, 100)],
                'correct_predictions': {i: 0 for i in range(5)},
                'total_predictions': {i: 0 for i in range(5)},
                'expectations': {i: 0.0 for i in range(5)},
                'variances': {i: 0.0 for i in range(5)}
            },
            'ema': {
                'conditions': ['above_fast', 'below_fast', 'above_slow', 'below_slow', 
                             'above_trend', 'below_trend', 'golden_cross', 'death_cross'],
                'correct_predictions': {cond: 0 for cond in ['above_fast', 'below_fast', 'above_slow', 'below_slow', 
                                                           'above_trend', 'below_trend', 'golden_cross', 'death_cross']},
                'total_predictions': {cond: 0 for cond in ['above_fast', 'below_fast', 'above_slow', 'below_slow', 
                                                         'above_trend', 'below_trend', 'golden_cross', 'death_cross']},
                'expectations': {cond: 0.0 for cond in ['above_fast', 'below_fast', 'above_slow', 'below_slow', 
                                                      'above_trend', 'below_trend', 'golden_cross', 'death_cross']},
                'variances': {cond: 0.0 for cond in ['above_fast', 'below_fast', 'above_slow', 'below_slow', 
                                                   'above_trend', 'below_trend', 'golden_cross', 'death_cross']}
            },
            'volume': {
                'ratios': [1.2, 1.5, 1.8, 2.0],
                'correct_predictions': {i: 0 for i in range(4)},
                'total_predictions': {i: 0 for i in range(4)},
                'expectations': {i: 0.0 for i in range(4)},
                'variances': {i: 0.0 for i in range(4)}
            }
        }
        self.last_update_time = 0
        self.update_interval = 3600  # Cập nhật mỗi giờ
    
    def get_rsi_range_index(self, rsi_value):
        """Xác định index của khoảng RSI"""
        for i, (low, high) in enumerate(self.probability_stats['rsi']['ranges']):
            if low <= rsi_value < high:
                return i
        return 2  # Mặc định về trung lập
    
    def get_volume_ratio_index(self, volume_ratio):
        """Xác định index của khoảng volume ratio"""
        for i, ratio in enumerate(self.probability_stats['volume']['ratios']):
            if volume_ratio >= ratio:
                return i
        return 0  # Dưới 1.2
    
    def analyze_historical_performance(self, symbol):
        """PHÂN TÍCH HIỆU SUẤT LỊCH SỬ 200 NẾN"""
        try:
            current_time = time.time()
            if current_time - self.last_update_time < self.update_interval:
                return self.probability_stats
            
            logger.info(f"📊 Đang phân tích hiệu suất lịch sử cho {symbol}...")
            
            # Lấy dữ liệu nến
            klines = self.get_historical_klines(symbol, '15m', self.lookback + self.evaluation_period)
            if not klines or len(klines) < self.lookback + 10:
                logger.warning(f"Không đủ dữ liệu lịch sử cho {symbol}")
                return self.probability_stats
            
            # Reset thống kê
            self._reset_stats()
            
            analyzer = TrendIndicatorSystem()
            
            # Phân tích từng điểm trong lịch sử
            for i in range(self.evaluation_period, len(klines) - self.evaluation_period):
                try:
                    # Dữ liệu hiện tại
                    current_data = klines[i]
                    current_close = float(current_data[4])
                    
                    # Dữ liệu tương lai để đánh giá
                    future_data = klines[i + self.evaluation_period]
                    future_close = float(future_data[4])
                    
                    # Tính biến động giá
                    price_change = (future_close - current_close) / current_close * 100
                    is_price_up = price_change > 0
                    
                    # Phân tích chỉ báo tại thời điểm hiện tại
                    historical_klines = klines[:i+1]
                    closes = [float(candle[4]) for candle in historical_klines]
                    
                    if len(closes) < 50:
                        continue
                    
                    # 1. PHÂN TÍCH RSI
                    rsi = analyzer.calculate_rsi(closes, analyzer.rsi_period)
                    rsi_index = self.get_rsi_range_index(rsi)
                    
                    # Đánh giá dự đoán RSI
                    rsi_prediction = self._get_rsi_prediction(rsi)
                    if rsi_prediction is not None:
                        is_correct = (rsi_prediction == "BUY" and is_price_up) or (rsi_prediction == "SELL" and not is_price_up)
                        self._update_rsi_stats(rsi_index, is_correct, price_change)
                    
                    # 2. PHÂN TÍCH EMA
                    ema_fast = analyzer.calculate_ema(closes, analyzer.ema_fast)
                    ema_slow = analyzer.calculate_ema(closes, analyzer.ema_slow)
                    ema_trend = analyzer.calculate_ema(closes, analyzer.ema_trend)
                    
                    self._update_ema_stats(closes, ema_fast, ema_slow, ema_trend, is_price_up, price_change)
                    
                    # 3. PHÂN TÍCH VOLUME
                    if len(historical_klines) >= 20:
                        volumes = [float(candle[5]) for candle in historical_klines]
                        current_volume = volumes[-1] if volumes else 0
                        avg_volume = np.mean(volumes[-20:-1]) if len(volumes) >= 20 else 1.0
                        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                        
                        volume_index = self.get_volume_ratio_index(volume_ratio)
                        volume_prediction = self._get_volume_prediction(volume_ratio, current_close, ema_fast)
                        
                        if volume_prediction is not None:
                            is_correct = (volume_prediction == "BUY" and is_price_up) or (volume_prediction == "SELL" and not is_price_up)
                            self._update_volume_stats(volume_index, is_correct, price_change)
                            
                except Exception as e:
                    continue
            
            # Tính toán kỳ vọng và phương sai cuối cùng
            self._calculate_final_stats()
            
            self.last_update_time = current_time
            logger.info(f"✅ Đã cập nhật thống kê xác suất cho {symbol}")
            
            return self.probability_stats
            
        except Exception as e:
            logger.error(f"❌ Lỗi phân tích hiệu suất lịch sử: {str(e)}")
            return self.probability_stats
    
    def _get_rsi_prediction(self, rsi):
        """Dự đoán dựa trên RSI"""
        if rsi < 30:
            return "BUY"
        elif rsi > 70:
            return "SELL"
        return None
    
    def _get_volume_prediction(self, volume_ratio, price, ema_fast):
        """Dự đoán dựa trên volume"""
        if volume_ratio > 1.2:
            if price > ema_fast:
                return "BUY"
            else:
                return "SELL"
        return None
    
    def _update_rsi_stats(self, index, is_correct, price_change):
        """Cập nhật thống kê RSI"""
        self.probability_stats['rsi']['total_predictions'][index] += 1
        if is_correct:
            self.probability_stats['rsi']['correct_predictions'][index] += 1
        
        # Cập nhật cho tính toán kỳ vọng
        current_expectation = self.probability_stats['rsi']['expectations'][index]
        self.probability_stats['rsi']['expectations'][index] = current_expectation + price_change
    
    def _update_ema_stats(self, closes, ema_fast, ema_slow, ema_trend, is_price_up, price_change):
        """Cập nhật thống kê EMA"""
        current_price = closes[-1] if closes else 0
        
        # Điều kiện EMA cơ bản
        conditions = {
            'above_fast': current_price > ema_fast,
            'below_fast': current_price < ema_fast,
            'above_slow': current_price > ema_slow,
            'below_slow': current_price < ema_slow,
            'above_trend': current_price > ema_trend,
            'below_trend': current_price < ema_trend,
        }
        
        # Golden Cross/Death Cross
        if len(closes) >= 2:
            prev_ema_fast = analyzer.calculate_ema(closes[:-1], analyzer.ema_fast)
            prev_ema_slow = analyzer.calculate_ema(closes[:-1], analyzer.ema_slow)
            conditions['golden_cross'] = ema_fast > ema_slow and prev_ema_fast <= prev_ema_slow
            conditions['death_cross'] = ema_fast < ema_slow and prev_ema_fast >= prev_ema_slow
        
        for condition, is_true in conditions.items():
            if is_true:
                self.probability_stats['ema']['total_predictions'][condition] += 1
                
                # Đánh giá độ chính xác
                if condition in ['above_fast', 'above_slow', 'above_trend', 'golden_cross']:
                    is_correct = is_price_up
                else:  # below conditions và death cross
                    is_correct = not is_price_up
                
                if is_correct:
                    self.probability_stats['ema']['correct_predictions'][condition] += 1
                
                # Cập nhật kỳ vọng
                current_expectation = self.probability_stats['ema']['expectations'][condition]
                self.probability_stats['ema']['expectations'][condition] = current_expectation + price_change
    
    def _update_volume_stats(self, index, is_correct, price_change):
        """Cập nhật thống kê volume"""
        self.probability_stats['volume']['total_predictions'][index] += 1
        if is_correct:
            self.probability_stats['volume']['correct_predictions'][index] += 1
        
        current_expectation = self.probability_stats['volume']['expectations'][index]
        self.probability_stats['volume']['expectations'][index] = current_expectation + price_change
    
    def _calculate_final_stats(self):
        """Tính toán kỳ vọng và phương sai cuối cùng"""
        # RSI
        for i in range(5):
            total = self.probability_stats['rsi']['total_predictions'][i]
            if total > 0:
                self.probability_stats['rsi']['expectations'][i] /= total
                # Tính phương sai đơn giản (trong thực tế cần lưu tất cả giá trị)
                self.probability_stats['rsi']['variances'][i] = abs(self.probability_stats['rsi']['expectations'][i]) * 0.1
        
        # EMA
        for condition in self.probability_stats['ema']['conditions']:
            total = self.probability_stats['ema']['total_predictions'][condition]
            if total > 0:
                self.probability_stats['ema']['expectations'][condition] /= total
                self.probability_stats['ema']['variances'][condition] = abs(self.probability_stats['ema']['expectations'][condition]) * 0.1
        
        # Volume
        for i in range(4):
            total = self.probability_stats['volume']['total_predictions'][i]
            if total > 0:
                self.probability_stats['volume']['expectations'][i] /= total
                self.probability_stats['volume']['variances'][i] = abs(self.probability_stats['volume']['expectations'][i]) * 0.1
    
    def _reset_stats(self):
        """Reset thống kê"""
        for indicator in self.probability_stats:
            if 'correct_predictions' in self.probability_stats[indicator]:
                for key in self.probability_stats[indicator]['correct_predictions']:
                    self.probability_stats[indicator]['correct_predictions'][key] = 0
                    self.probability_stats[indicator]['total_predictions'][key] = 0
                    self.probability_stats[indicator]['expectations'][key] = 0.0
                    self.probability_stats[indicator]['variances'][key] = 0.0
    
    def get_historical_klines(self, symbol, interval, limit):
        """Lấy dữ liệu nến lịch sử"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': interval,
                'limit': limit
            }
            return binance_api_request(url, params=params)
        except Exception as e:
            logger.error(f"❌ Lỗi lấy nến lịch sử {symbol}: {str(e)}")
            return None
    
    def get_recommended_direction(self, symbol, current_analysis):
        """ĐỀ XUẤT HƯỚNG DỰA TRÊN KỲ VỌNG & PHƯƠNG SAI"""
        try:
            stats = self.analyze_historical_performance(symbol)
            if not stats:
                return "NEUTRAL"
            
            current_rsi = current_analysis.get('rsi', 50)
            current_volume_ratio = current_analysis.get('volume_ratio', 1.0)
            current_ema_condition = current_analysis.get('ema_condition', 'neutral')
            
            # Tính điểm kỳ vọng cho từng hướng
            buy_score = 0
            sell_score = 0
            total_confidence = 0
            
            # 1. ĐÁNH GIÁ RSI
            rsi_index = self.get_rsi_range_index(current_rsi)
            rsi_prob = self._get_probability(stats['rsi'], rsi_index)
            rsi_expectation = stats['rsi']['expectations'][rsi_index]
            rsi_variance = stats['rsi']['variances'][rsi_index]
            
            if current_rsi < 45:  # Vùng mua
                buy_score += rsi_expectation * rsi_prob * (1 - rsi_variance)
            elif current_rsi > 55:  # Vùng bán
                sell_score += abs(rsi_expectation) * rsi_prob * (1 - rsi_variance)
            
            # 2. ĐÁNH GIÁ EMA
            ema_conditions = []
            if current_ema_condition == 'bullish':
                ema_conditions = ['above_fast', 'above_slow', 'above_trend', 'golden_cross']
            elif current_ema_condition == 'bearish':
                ema_conditions = ['below_fast', 'below_slow', 'below_trend', 'death_cross']
            
            for condition in ema_conditions:
                ema_prob = self._get_probability(stats['ema'], condition)
                ema_expectation = stats['ema']['expectations'][condition]
                ema_variance = stats['ema']['variances'][condition]
                
                if 'above' in condition or 'golden' in condition:
                    buy_score += ema_expectation * ema_prob * (1 - ema_variance)
                else:
                    sell_score += abs(ema_expectation) * ema_prob * (1 - ema_variance)
            
            # 3. ĐÁNH GIÁ VOLUME
            volume_index = self.get_volume_ratio_index(current_volume_ratio)
            volume_prob = self._get_probability(stats['volume'], volume_index)
            volume_expectation = stats['volume']['expectations'][volume_index]
            volume_variance = stats['volume']['variances'][volume_index]
            
            if current_volume_ratio > 1.2:
                # Volume cao thường đi cùng xu hướng hiện tại
                if buy_score > sell_score:
                    buy_score += volume_expectation * volume_prob * (1 - volume_variance)
                else:
                    sell_score += abs(volume_expectation) * volume_prob * (1 - volume_variance)
            
            # QUYẾT ĐỊNH HƯỚNG
            logger.info(f"🎯 {symbol} - Điểm BUY: {buy_score:.3f}, SELL: {sell_score:.3f}")
            
            if buy_score > sell_score and buy_score > 0.1:
                return "BUY"
            elif sell_score > buy_score and sell_score > 0.1:
                return "SELL"
            else:
                return "NEUTRAL"
                
        except Exception as e:
            logger.error(f"❌ Lỗi đề xuất hướng: {str(e)}")
            return "NEUTRAL"
    
    def _get_probability(self, indicator_stats, key):
        """Lấy xác suất thắng của chỉ báo"""
        total = indicator_stats['total_predictions'].get(key, 0)
        if total == 0:
            return 0.5  # Mặc định 50% nếu không có dữ liệu
        
        correct = indicator_stats['correct_predictions'].get(key, 0)
        return correct / total

    def get_probability_report(self, symbol):
        """BÁO CÁO XÁC SUẤT CHI TIẾT"""
        try:
            stats = self.analyze_historical_performance(symbol)
            if not stats:
                return "❌ Không có dữ liệu thống kê"
            
            report = f"📊 <b>BÁO CÁO XÁC SUẤT - {symbol}</b>\n\n"
            
            # RSI
            report += "📈 <b>RSI PROBABILITIES:</b>\n"
            for i, (low, high) in enumerate(stats['rsi']['ranges']):
                prob = self._get_probability(stats['rsi'], i)
                exp = stats['rsi']['expectations'][i]
                var = stats['rsi']['variances'][i]
                report += f"   {low}-{high}: {prob:.1%} (E:{exp:.2f}%, V:{var:.3f})\n"
            
            # EMA
            report += "\n📉 <b>EMA PROBABILITIES:</b>\n"
            for condition in stats['ema']['conditions']:
                prob = self._get_probability(stats['ema'], condition)
                exp = stats['ema']['expectations'][condition]
                var = stats['ema']['variances'][condition]
                report += f"   {condition}: {prob:.1%} (E:{exp:.2f}%, V:{var:.3f})\n"
            
            # Volume
            report += "\n📊 <b>VOLUME PROBABILITIES:</b>\n"
            for i, ratio in enumerate(stats['volume']['ratios']):
                prob = self._get_probability(stats['volume'], i)
                exp = stats['volume']['expectations'][i]
                var = stats['volume']['variances'][i]
                report += f"   >{ratio}x: {prob:.1%} (E:{exp:.2f}%, V:{var:.3f})\n"
            
            return report
            
        except Exception as e:
            return f"❌ Lỗi báo cáo: {str(e)}"

# ========== HỆ THỐNG CHỈ BÁO XU HƯỚNG TÍCH HỢP ==========
class TrendIndicatorSystem:
    """HỆ THỐNG CHỈ BÁO XU HƯỚNG TÍCH HỢP - THAY THẾ ĐA KHUNG THỜI GIAN"""
    
    def __init__(self):
        self.ema_fast = 9
        self.ema_slow = 21
        self.ema_trend = 50
        self.rsi_period = 14
        self.lookback = 100
        self.probability_analyzer = ProbabilityAnalyzer()
        
    def calculate_ema(self, prices, period):
        """Tính EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0
            
        ema = [prices[0]]
        multiplier = 2 / (period + 1)
        
        for i in range(1, len(prices)):
            ema_value = (prices[i] * multiplier) + (ema[i-1] * (1 - multiplier))
            ema.append(ema_value)
            
        return ema[-1]
    
    def calculate_rsi(self, prices, period=14):
        """Tính RSI"""
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
    
    def get_volume_data(self, symbol):
        """Lấy dữ liệu volume"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': '15m',
                'limit': 20
            }
            data = binance_api_request(url, params=params)
            if not data:
                return 1.0
                
            volumes = [float(candle[5]) for candle in data]
            if len(volumes) < 2:
                return 1.0
                
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[:-1])
            
            return current_volume / avg_volume if avg_volume > 0 else 1.0
            
        except Exception as e:
            logger.error(f"Lỗi lấy volume {symbol}: {str(e)}")
            return 1.0
    
    def get_support_resistance(self, symbol):
        """Xác định hỗ trợ/kháng cự đơn giản"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                'symbol': symbol.upper(),
                'interval': '15m',
                'limit': 30
            }
            data = binance_api_request(url, params=params)
            if not data or len(data) < 20:
                return 0, 0
                
            highs = [float(candle[2]) for candle in data]
            lows = [float(candle[3]) for candle in data]
            
            resistance = max(highs[-20:])
            support = min(lows[-20:])
            
            return support, resistance
            
        except Exception as e:
            logger.error(f"Lỗi lấy S/R {symbol}: {str(e)}")
            return 0, 0
    
    def analyze_symbol(self, symbol):
        """PHÂN TÍCH TÍCH HỢP - TẤT CẢ CHỈ BÁO THÀNH 1 TÍN HIỆU DUY NHẤT"""
        try:
            klines = self.get_klines(symbol, '15m', self.lookback)
            if not klines or len(klines) < 50:
                return "NEUTRAL"
            
            closes = [float(candle[4]) for candle in klines]
            current_price = closes[-1]
            
            # 1. TÍN HIỆU EMA (Quan trọng nhất - 40%)
            ema_fast = self.calculate_ema(closes, self.ema_fast)
            ema_slow = self.calculate_ema(closes, self.ema_slow)
            ema_trend = self.calculate_ema(closes, self.ema_trend)
            
            ema_signal = "NEUTRAL"
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
            else:
                ema_strength = 0.3
            
            # 2. TÍN HIỆU RSI + VOLUME (30%)
            rsi = self.calculate_rsi(closes, self.rsi_period)
            volume_ratio = self.get_volume_data(symbol)
            
            rsi_signal = "NEUTRAL"
            rsi_strength = 0
            
            if rsi < 30 and volume_ratio > 1.2:
                rsi_signal = "BUY"
                rsi_strength = min((30 - rsi) / 30 * volume_ratio, 1.0)
            elif rsi > 70 and volume_ratio > 1.2:
                rsi_signal = "SELL" 
                rsi_strength = min((rsi - 70) / 30 * volume_ratio, 1.0)
            elif 40 < rsi < 60:
                rsi_strength = 0.2
            
            # 3. TÍN HIỆU SUPPORT/RESISTANCE (20%)
            support, resistance = self.get_support_resistance(symbol)
            sr_signal = "NEUTRAL"
            sr_strength = 0
            
            if support > 0 and resistance > 0:
                distance_to_resistance = (resistance - current_price) / current_price
                distance_to_support = (current_price - support) / current_price
                
                if current_price > resistance and volume_ratio > 1.3:
                    sr_signal = "BUY"
                    sr_strength = min(volume_ratio * 0.8, 1.0)
                elif current_price < support and volume_ratio > 1.3:
                    sr_signal = "SELL"
                    sr_strength = min(volume_ratio * 0.8, 1.0)
                elif distance_to_resistance < 0.01:
                    sr_signal = "SELL"
                    sr_strength = 0.6
                elif distance_to_support < 0.01:
                    sr_signal = "BUY" 
                    sr_strength = 0.6
            
            # 4. TÍN HIỆU MARKET STRUCTURE (10%)
            structure_signal = self.analyze_market_structure(closes)
            structure_strength = 0.5 if structure_signal != "NEUTRAL" else 0.2
            
            # 5. PHÂN TÍCH XÁC SUẤT THỐNG KÊ
            current_analysis = {
                'rsi': rsi,
                'volume_ratio': volume_ratio,
                'ema_condition': 'bullish' if ema_signal == "BUY" else 'bearish' if ema_signal == "SELL" else 'neutral'
            }
            
            probability_signal = self.probability_analyzer.get_recommended_direction(symbol, current_analysis)
            probability_strength = 0.8 if probability_signal != "NEUTRAL" else 0.2
            
            # TỔNG HỢP TẤT CẢ TÍN HIỆU
            signals = {
                "BUY": 0,
                "SELL": 0, 
                "NEUTRAL": 0
            }
            
            weights = {
                "EMA": 0.3,
                "RSI_VOLUME": 0.25, 
                "SR": 0.15,
                "STRUCTURE": 0.1,
                "PROBABILITY": 0.2
            }
            
            if ema_signal != "NEUTRAL":
                signals[ema_signal] += weights["EMA"] * ema_strength
                
            if rsi_signal != "NEUTRAL": 
                signals[rsi_signal] += weights["RSI_VOLUME"] * rsi_strength
                
            if sr_signal != "NEUTRAL":
                signals[sr_signal] += weights["SR"] * sr_strength
                
            if structure_signal != "NEUTRAL":
                signals[structure_signal] += weights["STRUCTURE"] * structure_strength
                
            if probability_signal != "NEUTRAL":
                signals[probability_signal] += weights["PROBABILITY"] * probability_strength
            
            max_signal = max(signals, key=signals.get)
            confidence = signals[max_signal]
            
            # LOG CHI TIẾT
            logger.info(f"🎯 {symbol} - Tín hiệu tổng hợp: {max_signal}")
            logger.info(f"   📊 EMA: {ema_signal}({ema_strength:.1f}) | RSI: {rsi_signal}({rsi_strength:.1f})")
            logger.info(f"   📈 S/R: {sr_signal}({sr_strength:.1f}) | Structure: {structure_signal}({structure_strength:.1f})")
            logger.info(f"   🎯 Probability: {probability_signal}({probability_strength:.1f})")
            logger.info(f"   💯 Confidence: {confidence:.1%}")
            
            if confidence >= 0.4:
                return max_signal
            else:
                logger.debug(f"⚪ {symbol} - Tín hiệu yếu (Confidence: {confidence:.1%})")
                return "NEUTRAL"
                
        except Exception as e:
            logger.error(f"❌ Lỗi phân tích {symbol}: {str(e)}")
            return "NEUTRAL"
    
    def analyze_market_structure(self, prices):
        """Phân tích cấu trúc thị trường đơn giản"""
        if len(prices) < 10:
            return "NEUTRAL"
            
        recent_highs = prices[-5:]
        recent_lows = prices[-5:]
        prev_highs = prices[-10:-5] 
        prev_lows = prices[-10:-5]
        
        if (max(recent_highs) > max(prev_highs) and 
            min(recent_lows) > min(prev_lows)):
            return "BUY"
        elif (max(recent_highs) < max(prev_highs) and 
              min(recent_lows) < min(prev_lows)):
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

    def get_probability_report(self, symbol):
        """Lấy báo cáo xác suất"""
        return self.probability_analyzer.get_probability_report(symbol)

# ========== SMART COIN FINDER - TỐI ƯU THEO 5 BƯỚC ==========
class SmartCoinFinder:
    """TÌM COIN THÔNG MINH THEO HỆ THỐNG 5 BƯỚC"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.analyzer = TrendIndicatorSystem()
        self.leverage_cache = {}
        self.cache_timeout = 300
        
    def get_symbol_leverage_info(self, symbol):
        """Lấy thông tin đòn bẩy tối đa cho symbol"""
        try:
            current_time = time.time()
            if symbol in self.leverage_cache:
                cached_data, timestamp = self.leverage_cache[symbol]
                if current_time - timestamp < self.cache_timeout:
                    return cached_data
            
            url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
            data = binance_api_request(url)
            if not data:
                return None
                
            for s in data['symbols']:
                if s['symbol'] == symbol.upper():
                    for f in s['filters']:
                        if f['filterType'] == 'LEVERAGE':
                            max_leverage = int(f.get('maxLeverage', 20))
                            self.leverage_cache[symbol] = (max_leverage, current_time)
                            return max_leverage
                    
                    self.leverage_cache[symbol] = (20, current_time)
                    return 20
                    
            return None
            
        except Exception as e:
            logger.error(f"❌ Lỗi lấy đòn bẩy {symbol}: {str(e)}")
            return None
    
    def is_leverage_supported(self, symbol, target_leverage):
        """Kiểm tra coin có hỗ trợ đòn bẩy mục tiêu không"""
        try:
            max_leverage = self.get_symbol_leverage_info(symbol)
            if max_leverage is None:
                return False
                
            supported = max_leverage >= target_leverage
            if not supported:
                logger.debug(f"⚠️ {symbol} không hỗ trợ {target_leverage}x (tối đa: {max_leverage}x)")
            return supported
            
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra đòn bẩy {symbol}: {str(e)}")
            return False
    
    def filter_symbols_by_leverage(self, symbols, target_leverage):
        """Lọc danh sách symbol theo đòn bẩy hỗ trợ"""
        if not symbols:
            return []
            
        logger.info(f"🔍 Đang lọc {len(symbols)} coin theo đòn bẩy {target_leverage}x...")
        
        valid_symbols = []
        
        for symbol in symbols:
            if self.is_leverage_supported(symbol, target_leverage):
                valid_symbols.append(symbol)
        
        logger.info(f"✅ Tìm thấy {len(valid_symbols)} coin hỗ trợ {target_leverage}x")
        return valid_symbols

    def get_market_position_balance(self):
        """BƯỚC 1: Kiểm tra số lượng vị thế mua/bán trên Binance"""
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            buy_count = 0
            sell_count = 0
            
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt > 0:
                    buy_count += 1
                elif position_amt < 0:
                    sell_count += 1
            
            logger.info(f"📊 VỊ THẾ BINANCE - BUY: {buy_count}, SELL: {sell_count}")
            
            # Xác định hướng ngược lại
            if buy_count > sell_count:
                recommended_direction = "SELL"
                reason = f"Nhiều BUY hơn ({buy_count} vs {sell_count}) → Ưu tiên SELL"
            elif sell_count > buy_count:
                recommended_direction = "BUY"
                reason = f"Nhiều SELL hơn ({sell_count} vs {buy_count}) → Ưu tiên BUY"
            else:
                # Cân bằng, chọn ngẫu nhiên
                recommended_direction = "BUY" if random.random() > 0.5 else "SELL"
                reason = f"Cân bằng ({buy_count} vs {sell_count}) → Random {recommended_direction}"
            
            logger.info(f"🎯 HƯỚNG ĐỀ XUẤT: {recommended_direction} - {reason}")
            return recommended_direction
            
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra vị thế: {str(e)}")
            return "BUY" if random.random() > 0.5 else "SELL"
    
    def find_coin_by_direction(self, target_direction, excluded_symbols=None, target_leverage=20):
        """BƯỚC 2 + 3: Tìm coin tốt nhất theo hướng đã xác định"""
        try:
            if excluded_symbols is None:
                excluded_symbols = set()
            
            logger.info(f"🔍 Bot đang tìm coin {target_direction} (đòn bẩy {target_leverage}x)...")
            
            # Lấy danh sách coin
            all_symbols = get_all_usdt_pairs(limit=600)
            if not all_symbols:
                logger.error("❌ Không lấy được danh sách coin từ Binance")
                return None
            
            # Lọc theo đòn bẩy
            valid_symbols = self.filter_symbols_by_leverage(all_symbols, target_leverage)
            if not valid_symbols:
                logger.error(f"❌ Không có coin nào hỗ tr trợ đòn bẩy {target_leverage}x")
                return None
            
            # BƯỚC 3: Trộn ngẫu nhiên
            random.shuffle(valid_symbols)
            logger.info(f"🔄 Đã trộn ngẫu nhiên {len(valid_symbols)} coin")
            
            # Lấy coin đang được quản lý
            coin_manager = CoinManager()
            managed_coins = coin_manager.get_managed_coins()
            excluded_symbols.update(managed_coins.keys())
            
            if excluded_symbols:
                logger.info(f"🚫 Tránh {len(excluded_symbols)} coin đang được trade")
            
            # BƯỚC 3: Duyệt từng coin
            found_coin = None
            for i, symbol in enumerate(valid_symbols):
                try:
                    # Bỏ qua các coin bị loại trừ
                    if symbol in excluded_symbols or symbol in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']:
                        continue
                    
                    # BƯỚC 2: Phân tích kỹ thuật
                    signal = self.analyzer.analyze_symbol(symbol)
                    
                    # Nếu cùng hướng với target thì chọn
                    if signal == target_direction:
                        logger.info(f"✅ Đã tìm thấy coin {symbol} - {target_direction} (coin thứ {i+1})")
                        found_coin = {
                            'symbol': symbol,
                            'direction': target_direction,
                            'signal_strength': 'high',
                            'found_at_index': i+1,
                            'qualified': True,
                            'leverage_supported': True
                        }
                        break
                    
                    # Log tiến trình mỗi 50 coin
                    if (i + 1) % 50 == 0:
                        logger.info(f"⏳ Đã quét {i+1} coin, đang tìm {target_direction}...")
                        
                except Exception as e:
                    logger.debug(f"❌ Lỗi phân tích {symbol}: {str(e)}")
                    continue
            
            if found_coin:
                return found_coin
            else:
                logger.warning(f"⚠️ Không tìm thấy coin {target_direction} sau {len(valid_symbols)} coin")
                return self._find_fallback_coin(target_direction, excluded_symbols, target_leverage)
            
        except Exception as e:
            logger.error(f"❌ Lỗi tìm coin: {str(e)}")
            return None
    
    def _find_fallback_coin(self, target_direction, excluded_symbols, target_leverage):
        """Phương pháp dự phòng"""
        logger.info(f"🔄 Sử dụng fallback cho {target_direction}")
        
        all_symbols = get_all_usdt_pairs(limit=600)
        if not all_symbols:
            return None
            
        # Lọc theo đòn bẩy
        valid_symbols = self.filter_symbols_by_leverage(all_symbols, target_leverage)
        if not valid_symbols:
            return None
            
        random.shuffle(valid_symbols)
        
        for symbol in valid_symbols:
            if symbol in ['BTCUSDT', 'ETHUSDT'] or symbol in excluded_symbols:
                continue
                
            try:
                change_24h = get_24h_change(symbol)
                if change_24h is None:
                    continue
                
                score = 0
                if target_direction == "BUY" and change_24h < -5:
                    score = abs(change_24h) / 15
                elif target_direction == "SELL" and change_24h > 5:
                    score = abs(change_24h) / 15
                
                if score > 0.2:
                    logger.info(f"🔄 Fallback: {symbol} - {target_direction} (điểm: {score:.2f})")
                    return {
                        'symbol': symbol,
                        'direction': target_direction,
                        'score': score,
                        'fallback': True,
                        'qualified': True,
                        'leverage_supported': True
                    }
                        
            except Exception as e:
                logger.debug(f"❌ Lỗi fallback {symbol}: {str(e)}")
                continue
        
        return None

# ========== QUẢN LÝ COIN CHUNG ==========
class CoinManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CoinManager, cls).__new__(cls)
                cls._instance.managed_coins = {}
                cls._instance.config_coin_count = {}
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

# ========== KHỞI TẠO GLOBAL INSTANCES ==========
coin_manager = CoinManager()

# ========== HÀM KHỞI ĐỘNG HỆ THỐNG ==========
def start_trading_system(api_key, api_secret, telegram_bot_token, telegram_chat_id):
    """Khởi động hệ thống trading hoàn chỉnh"""
    logger.info("🚀 Đang khởi động hệ thống Trading Bot...")
    
    bot_manager = BotManager(
        api_key=api_key,
        api_secret=api_secret,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id
    )
    
    logger.info("✅ Hệ thống Trading Bot đã khởi động thành công!")
    logger.info("📱 Truy cập Telegram để sử dụng menu điều khiển")
    
    return bot_manager

# ========== BASE BOT NÂNG CẤP - TÍCH HỢP HỆ THỐNG 5 BƯỚC ==========
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
        
        self.status = "searching"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self.prices = deque(maxlen=100)
        self.position_open = False
        self._stop = False
        
        self.last_trade_time = 0
        self.last_close_time = 0
        self.last_position_check = 0
        self.last_error_log_time = 0
        
        self.cooldown_period = 300
        self.position_check_interval = 30
        
        self._close_attempted = False
        self._last_close_attempt = 0
        
        self.should_be_removed = False
        
        self.position_balance_check = 0
        self.balance_check_interval = 60
        
        self.coin_manager = CoinManager()
        self.coin_finder = SmartCoinFinder(api_key, api_secret)
        
        self.current_target_direction = None
        self.last_find_time = 0
        self.find_interval = 60
        
        self.check_position_status()
        if self.symbol:
            self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
        
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        
        if self.symbol:
            self.log(f"🟢 Bot {strategy_name} khởi động | {self.symbol} | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%")
        else:
            self.log(f"🟢 Bot {strategy_name} khởi động | Đang tìm coin... | ĐB: {lev}x | Vốn: {percent}% | TP/SL: {tp}%/{sl}%")

    def _register_coin_with_retry(self, symbol):
        max_retries = 3
        for attempt in range(max_retries):
            success = self.coin_manager.register_coin(symbol, self.bot_id, self.strategy_name, self.config_key)
            if success:
                return True
            time.sleep(0.5)
        return False

    def log(self, message):
        bot_info = f"[Bot {self.bot_id}]" if hasattr(self, 'bot_id') else ""
        logger.info(f"{bot_info} [{self.symbol or 'NO_COIN'} - {self.strategy_name}] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            symbol_info = f"<b>{self.symbol}</b>" if self.symbol else "<i>Đang tìm coin...</i>"
            send_telegram(f"{symbol_info} ({self.strategy_name} - Bot {self.bot_id}): {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def _handle_price_update(self, price):
        if self._stop or not price or price <= 0:
            return
        try:
            self.prices.append(float(price))
        except Exception as e:
            self.log(f"❌ Lỗi xử lý giá: {str(e)}")

    def get_signal(self):
        raise NotImplementedError("Phương thức get_signal cần được triển khai")

    def get_target_direction(self):
        """BƯỚC 1: Xác định hướng giao dịch dựa trên số lượng vị thế"""
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            buy_count = 0
            sell_count = 0
            
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt > 0:
                    buy_count += 1
                elif position_amt < 0:
                    sell_count += 1
            
            self.log(f"🔍 VỊ THẾ BINANCE - LONG: {buy_count}, SHORT: {sell_count}")
            
            if buy_count > sell_count:
                self.log(f"⚖️ QUYẾT ĐỊNH: Nhiều LONG hơn → ƯU TIÊN SHORT")
                return "SELL"
            elif sell_count > buy_count:
                self.log(f"⚖️ QUYẾT ĐỊNH: Nhiều SHORT hơn → ƯU TIÊN LONG")
                return "BUY"
            else:
                direction = "BUY" if random.random() > 0.5 else "SELL"
                self.log(f"⚖️ QUYẾT ĐỊNH: Số lượng bằng nhau → RANDOM {direction}")
                return direction
                    
        except Exception as e:
            self.log(f"❌ Lỗi kiểm tra vị thế Binance: {str(e)}")
            self.log("🔄 Fallback: Dùng random direction do lỗi API")
            return "BUY" if random.random() > 0.5 else "SELL"

    def find_and_set_coin(self):
        """BƯỚC 2 + 3 + 4: Tìm và set coin mới với hệ thống 5 bước"""
        try:
            current_time = time.time()
            if current_time - self.last_find_time < self.find_interval:
                return False
            
            self.last_find_time = current_time
            
            self.current_target_direction = self.get_target_direction()
            
            self.log(f"🎯 Đang tìm coin {self.current_target_direction} (đòn bẩy {self.lev}x)...")
            
            managed_coins = self.coin_manager.get_managed_coins()
            excluded_symbols = set(managed_coins.keys())
            
            if excluded_symbols:
                self.log(f"🚫 Tránh {len(excluded_symbols)} coin đang được trade")
            
            coin_data = self.coin_finder.find_coin_by_direction(
                self.current_target_direction, 
                excluded_symbols,
                self.lev
            )
        
            if coin_data is None:
                self.log(f"⚠️ Không tìm thấy coin {self.current_target_direction} phù hợp, thử lại sau")
                return False
                
            if not coin_data.get('qualified', False):
                self.log(f"⚠️ Coin {coin_data.get('symbol', 'UNKNOWN')} không đủ tiêu chuẩn, thử lại sau")
                return False
            
            new_symbol = coin_data['symbol']
            
            if self._register_coin_with_retry(new_symbol):
                if self.symbol:
                    self.ws_manager.remove_symbol(self.symbol)
                    self.coin_manager.unregister_coin(self.symbol)
                
                self.symbol = new_symbol
                self.ws_manager.add_symbol(self.symbol, self._handle_price_update)
                
                self.log(f"🎯 Đã tìm thấy coin {new_symbol} - {self.current_target_direction}")
                
                self.status = "waiting"
                return True
            else:
                self.log(f"❌ Không thể đăng ký coin {new_symbol} - có thể đã có bot khác trade")
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi tìm coin: {str(e)}")
            return False

    def get_signal_with_balance(self, original_signal):
        """ĐIỀU CHỈNH TÍN HIỆU - CÂN BẰNG VỚI TẤT CẢ VỊ THẾ BINANCE"""
        try:
            current_time = time.time()
            if current_time - self.position_balance_check < self.balance_check_interval:
                return original_signal
            
            self.position_balance_check = current_time
            
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            if not all_positions:
                self.log(f"⚖️ CÂN BẰNG: Không có vị thế → GIỮ NGUYÊN {original_signal}")
                return original_signal
            
            buy_count = 0
            sell_count = 0
            total_value = 0
            buy_value = 0
            sell_value = 0
            
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                entry_price = float(pos.get('entryPrice', 0))
                leverage = float(pos.get('leverage', 1))
                
                if position_amt != 0:
                    position_value = abs(position_amt) * entry_price / leverage
                    total_value += position_value
                    
                    if position_amt > 0:
                        buy_count += 1
                        buy_value += position_value
                    else:
                        sell_count += 1
                        sell_value += position_value
            
            total = buy_count + sell_count
            buy_ratio = buy_value / total_value if total_value > 0 else 0.5
            sell_ratio = sell_value / total_value if total_value > 0 else 0.5
            
            self.log(f"⚖️ CÂN BẰNG TÍN HIỆU: {buy_count}L/${buy_value:.0f} vs {sell_count}S/${sell_value:.0f} | Tín hiệu gốc: {original_signal}")
            
            if original_signal == "BUY" and buy_ratio >= 0.6:
                self.log(f"⚖️ ĐIỀU CHỈNH: Nhiều LONG ({buy_ratio:.1%} giá trị) + tín hiệu BUY → CHUYỂN SHORT")
                return "SELL"
            elif original_signal == "SELL" and sell_ratio >= 0.6:
                self.log(f"⚖️ ĐIỀU CHỈNH: Nhiều SHORT ({sell_ratio:.1%} giá trị) + tín hiệu SELL → CHUYỂN LONG")
                return "BUY"
            elif original_signal == "BUY" and buy_ratio > sell_ratio + 0.2:
                self.log(f"⚖️ ĐIỀU CHỈNH: LONG nhiều hơn SHORT đáng kể → ƯU TIÊN SHORT")
                return "SELL"
            elif original_signal == "SELL" and sell_ratio > buy_ratio + 0.2:
                self.log(f"⚖️ ĐIỀU CHỈNH: SHORT nhiều hơn LONG đáng kể → ƯU TIÊN LONG")
                return "BUY"
            else:
                self.log(f"⚖️ GIỮ NGUYÊN: Tín hiệu {original_signal} phù hợp với cân bằng hệ thống")
                return original_signal
                
        except Exception as e:
            self.log(f"❌ Lỗi cân bằng với vị thế Binance: {str(e)}")
            return original_signal

    def check_position_status(self):
        """BƯỚC 4: Kiểm tra trạng thái vị thế"""
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
            if time.time() - self.last_error_log_time > 10:
                self.log(f"❌ Lỗi kiểm tra vị thế: {str(e)}")
                self.last_error_log_time = time.time()

    def _reset_position(self):
        """Reset trạng thái vị thế"""
        self.position_open = False
        self.status = "searching" if not self.symbol else "waiting"
        self.side = ""
        self.qty = 0
        self.entry = 0
        self._close_attempted = False
        self._last_close_attempt = 0

    def _run(self):
        """Vòng lặp chính của bot"""
        while not self._stop:
            try:
                current_time = time.time()
                
                if current_time - self.last_position_check > self.position_check_interval:
                    self.check_position_status()
                    self.last_position_check = current_time
                              
                if not self.position_open:
                    signal = self.get_signal()
                    
                    if signal and signal != "NEUTRAL":
                        balanced_signal = self.get_signal_with_balance(signal)
                        
                        if (balanced_signal and balanced_signal != "NEUTRAL" and
                            current_time - self.last_trade_time > 60 and
                            current_time - self.last_close_time > self.cooldown_period):
                            
                            if self.open_position(balanced_signal):
                                self.last_trade_time = current_time
                            else:
                                time.sleep(30)
                    else:
                        if signal == "NEUTRAL":
                            logger.debug(f"⚪ {self.symbol} - Tín hiệu NEUTRAL, bỏ qua")
                        time.sleep(5)
                
                if self.position_open and not self._close_attempted:
                    self.check_tp_sl()
                    
                time.sleep(1)
                
            except Exception as e:
                if time.time() - self.last_error_log_time > 10:
                    self.log(f"❌ Lỗi hệ thống: {str(e)}")
                    self.last_error_log_time = time.time()
                time.sleep(1)

    def stop(self):
        """Dừng bot"""
        self._stop = True
        if self.symbol:
            self.ws_manager.remove_symbol(self.symbol)
        if self.symbol:
            self.coin_manager.unregister_coin(self.symbol)
        if self.symbol:
            cancel_all_orders(self.symbol, self.api_key, self.api_secret)
        self.log(f"🔴 Bot dừng")

    def open_position(self, side):
        """BƯỚC 4: Mở vị thế với kiểm tra đầy đủ"""
        if side not in ["BUY", "SELL"]:
            self.log(f"❌ Side không hợp lệ: {side}")
            return False
            
        try:
            if not self.coin_finder.is_leverage_supported(self.symbol, self.lev):
                self.log(f"❌ Coin {self.symbol} không hỗ trợ đòn bẩy {self.lev}x, tìm coin mới")
                self.close_position("Coin không hỗ trợ đòn bẩy")
                self.symbol = None
                self.status = "searching"
                return False

            self.check_position_status()
            if self.position_open:
                self.log(f"⚠️ Đã có vị thế {self.side}, bỏ qua tín hiệu {side}")
                return False
    
            if self.should_be_removed:
                self.log("⚠️ Bot đã được đánh dấu xóa, không mở lệnh mới")
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
    
            self.log(f"📊 Đang đặt lệnh {side} - SL: {step_size}, Qty: {qty}, Giá: {current_price}")
            
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
                        f"✅ <b>ĐÃ MỞ VỊ THẾ {self.symbol}</b>\n"
                        f"🤖 Chiến lược: {self.strategy_name}\n"
                        f"📌 Hướng: {side}\n"
                        f"🏷️ Giá vào: {self.entry:.4f}\n"
                        f"📊 Khối lượng: {executed_qty:.4f}\n"
                        f"💵 Giá trị: {executed_qty * self.entry:.2f} USDT\n"
                        f"💰 Đòn bẩy: {self.lev}x\n"
                        f"🎯 TP: {self.tp}% | 🛡️ SL: {self.sl}%"
                    )
                    self.log(message)
                    return True
                else:
                    self.log(f"❌ Lệnh không khớp - Số lượng: {qty}")
                    return False
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đặt lệnh {side}: {error_msg}")
                    
                if result and 'code' in result:
                    self.log(f"📋 Mã lỗi Binance: {result['code']} - {result.get('msg', '')}")
                    
                return False
                    
        except Exception as e:
            self.log(f"❌ Lỗi mở lệnh: {str(e)}")
            return False

    def close_position(self, reason=""):
        """BƯỚC 4: Đóng vị thế và chuẩn bị tìm coin mới"""
        try:
            self.check_position_status()
            
            if not self.position_open or abs(self.qty) <= 0:
                self.log(f"⚠️ Không có vị thế để đóng: {reason}")
                if self.symbol:
                    self.coin_manager.unregister_coin(self.symbol)
                return False

            current_time = time.time()
            if self._close_attempted and current_time - self._last_close_attempt < 30:
                self.log(f"⚠️ Đang thử đóng lệnh lần trước, chờ...")
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
                    f"⛔ <b>ĐÃ ĐÓNG VỊ THẾ {self.symbol}</b>\n"
                    f"🤖 Chiến lược: {self.strategy_name}\n"
                    f"📌 Lý do: {reason}\n"
                    f"🏷️ Giá ra: {current_price:.4f}\n"
                    f"📊 Khối lượng: {close_qty:.4f}\n"
                    f"💰 PnL: {pnl:.2f} USDT"
                )
                self.log(message)
                
                if self.symbol:
                    self.coin_manager.unregister_coin(self.symbol)
                    self.ws_manager.remove_symbol(self.symbol)
                
                self._reset_position()
                self.last_close_time = time.time()
                self.symbol = None
                self.status = "searching"
                
                time.sleep(2)
                self.check_position_status()
                
                return True
            else:
                error_msg = result.get('msg', 'Unknown error') if result else 'No response'
                self.log(f"❌ Lỗi đóng lệnh: {error_msg}")
                self._close_attempted = False
                return False
                
        except Exception as e:
            self.log(f"❌ Lỗi đóng lệnh: {str(e)}")
            self._close_attempted = False
            return False

    def check_tp_sl(self):
        """BƯỚC 4: Kiểm tra TP/SL"""
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

# ========== BOT XU HƯỚNG ĐỘNG ==========
class DynamicTrendBot(BaseBot):
    """Bot động sử dụng hệ thống chỉ báo xu hướng tích hợp"""
    
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret, 
                 telegram_bot_token, telegram_chat_id, config_key=None, bot_id=None):
        
        super().__init__(symbol, lev, percent, tp, sl, ws_manager, api_key, api_secret,
                        telegram_bot_token, telegram_chat_id, "Dynamic Trend System", 
                        config_key, bot_id)
        
        self.analyzer = TrendIndicatorSystem()
        self.last_analysis_time = 0
        self.analysis_interval = 180
        
    def get_signal(self):
        """Lấy tín hiệu từ hệ thống chỉ báo tích hợp"""
        if not self.symbol:
            if self.find_and_set_coin():
                return None
            else:
                return None
            
        try:
            current_time = time.time()
            if current_time - self.last_analysis_time < self.analysis_interval:
                return None
            
            self.last_analysis_time = current_time
            
            signal = self.analyzer.analyze_symbol(self.symbol)
            
            if signal != "NEUTRAL":
                self.log(f"🎯 Nhận tín hiệu {signal} từ hệ thống chỉ báo tích hợp")
            
            return signal
            
        except Exception as e:
            self.log(f"❌ Lỗi phân tích chỉ báo: {str(e)}")
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
        
        if api_key and api_secret:
            self._verify_api_connection()
            self.log("🟢 HỆ THỐNG BOT XU HƯỚNG ĐÃ KHỞI ĐỘNG")
            self.log("🎯 Sử dụng hệ thống chỉ báo tích hợp: EMA + RSI + Volume + Support/Resistance")
            self.log("📊 Hệ thống thống kê xác suất: Phân tích 200 nến lịch sử")
            self.log("🔄 Hệ thống Rotation Coin: Tự động tìm coin mới sau khi đóng lệnh")
            
            self.telegram_thread = threading.Thread(target=self._telegram_listener, daemon=True)
            self.telegram_thread.start()
            
            if self.telegram_chat_id:
                self.send_main_menu(self.telegram_chat_id)
        else:
            self.log("⚡ BotManager khởi động ở chế độ không config")

    def _verify_api_connection(self):
        balance = get_balance(self.api_key, self.api_secret)
        if balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance API.")
        else:
            self.log(f"✅ Kết nối Binance thành công! Số dư: {balance:.2f} USDT")

    def get_detailed_statistics(self):
        """Thống kê chi tiết hệ thống"""
        try:
            all_positions = get_positions(api_key=self.api_key, api_secret=self.api_secret)
            
            system_positions = []
            external_positions = []
            total_pnl = 0
            
            for pos in all_positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    symbol = pos.get('symbol', 'UNKNOWN')
                    entry_price = float(pos.get('entryPrice', 0))
                    leverage = float(pos.get('leverage', 1))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    total_pnl += unrealized_pnl
                    
                    position_info = {
                        'symbol': symbol,
                        'side': 'LONG' if position_amt > 0 else 'SHORT',
                        'leverage': leverage,
                        'entry_price': entry_price,
                        'size': abs(position_amt),
                        'pnl': unrealized_pnl
                    }
                    
                    coin_manager = CoinManager()
                    if coin_manager.is_coin_managed(symbol):
                        system_positions.append(position_info)
                    else:
                        external_positions.append(position_info)
            
            report = "📊 **THỐNG KÊ CHI TIẾT HỆ THỐNG**\n\n"
            
            balance = get_balance(self.api_key, self.api_secret)
            report += f"💰 **Số dư khả dụng**: {balance:.2f} USDT\n"
            report += f"📈 **Tổng PnL chưa thực hiện**: {total_pnl:.2f} USDT\n\n"
            
            report += f"🤖 **VỊ THẾ HỆ THỐNG** ({len(system_positions)}):\n"
            for pos in system_positions:
                report += (
                    f"🔹 {pos['symbol']} | {pos['side']} | {pos['leverage']}x\n"
                    f"   📊 Size: {pos['size']:.4f} | Entry: {pos['entry_price']:.4f}\n"
                    f"   💰 PnL: {pos['pnl']:.2f} USDT\n\n"
                )
            
            if not system_positions:
                report += "   📭 Không có vị thế hệ thống\n\n"
            
            if external_positions:
                report += f"🌐 **VỊ THẾ NGOÀI HỆ THỐNG** ({len(external_positions)}):\n"
                for pos in external_positions:
                    report += f"🔸 {pos['symbol']} | {pos['side']} | {pos['leverage']}x\n"
                report += "\n"
            
            active_bots = len([b for b in self.bots.values() if b.position_open])
            searching_bots = len([b for b in self.bots.values() if b.status == "searching"])
            waiting_bots = len([b for b in self.bots.values() if b.status == "waiting"])
            
            report += f"🤖 **TRẠNG THÁI BOT**:\n"
            report += f"   🟢 Đang trade: {active_bots}\n"
            report += f"   🔍 Đang tìm coin: {searching_bots}\n"
            report += f"   🟡 Chờ tín hiệu: {waiting_bots}\n"
            report += f"   📈 Tổng số bot: {len(self.bots)}\n\n"
            
            coin_manager = CoinManager()
            managed_coins = coin_manager.get_managed_coins()
            if managed_coins:
                report += f"🔗 **COIN ĐANG QUẢN LÝ** ({len(managed_coins)}):\n"
                for symbol, info in list(managed_coins.items())[:10]:
                    report += f"   {symbol} ({info['strategy']})\n"
                if len(managed_coins) > 10:
                    report += f"   ... và {len(managed_coins) - 10} coin khác"
            
            return report
            
        except Exception as e:
            return f"❌ Lỗi thống kê: {str(e)}"

    def get_probability_report(self, symbol):
        """Lấy báo cáo xác suất cho symbol"""
        analyzer = TrendIndicatorSystem()
        return analyzer.get_probability_report(symbol)

    def get_position_summary(self):
        """Thống kê tổng quan"""
        return self.get_detailed_statistics()

    def log(self, message):
        logger.info(f"[SYSTEM] {message}")
        if self.telegram_bot_token and self.telegram_chat_id:
            send_telegram(f"<b>SYSTEM</b>: {message}", 
                         bot_token=self.telegram_bot_token, 
                         default_chat_id=self.telegram_chat_id)

    def send_main_menu(self, chat_id):
        welcome = (
            "🤖 <b>BOT GIAO DỊCH FUTURES ĐA LUỒNG</b>\n\n"
            "🎯 <b>HỆ THỐNG CHỈ BÁO XU HƯỚNG TÍCH HỢP</b>\n"
            "📊 <b>THỐNG KÊ XÁC SUẤT 200 NẾN</b>\n"
            "🔄 <b>ROTATION COIN TỰ ĐỘNG</b>"
        )
        send_telegram(welcome, chat_id, create_main_menu(),
                     bot_token=self.telegram_bot_token, 
                     default_chat_id=self.telegram_chat_id)

    def add_bot(self, symbol, lev, percent, tp, sl, strategy_type, bot_count=1, **kwargs):
        """Thêm bot với đầy đủ thông số"""
        bot_mode = kwargs.get('bot_mode', 'static')
        
        if sl == 0:
            sl = None
            
        if not self.api_key or not self.api_secret:
            self.log("❌ Chưa thiết lập API Key trong BotManager")
            return False
        
        test_balance = get_balance(self.api_key, self.api_secret)
        if test_balance is None:
            self.log("❌ LỖI: Không thể kết nối Binance")
            return False
        
        created_count = 0
        
        for i in range(bot_count):
            try:
                if bot_mode == 'static' and symbol:
                    bot_id = f"{symbol}_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = DynamicTrendBot
                    
                    if not bot_class:
                        continue
                    
                    bot = bot_class(symbol, lev, percent, tp, sl, self.ws_manager,
                                  self.api_key, self.api_secret, self.telegram_bot_token, 
                                  self.telegram_chat_id, bot_id=bot_id)
                    
                else:
                    bot_id = f"DYNAMIC_{strategy_type}_{i}_{int(time.time())}"
                    
                    if bot_id in self.bots:
                        continue
                    
                    bot_class = DynamicTrendBot
                    
                    if not bot_class:
                        continue
                    
                    bot = bot_class(None, lev, percent, tp, sl, self.ws_manager,
                                  self.api_key, self.api_secret, self.telegram_bot_token,
                                  self.telegram_chat_id, bot_id=bot_id)
                
                bot._bot_manager = self
                self.bots[bot_id] = bot
                created_count += 1
                
            except Exception as e:
                self.log(f"❌ Lỗi tạo bot {i}: {str(e)}")
                continue
        
        if created_count > 0:
            success_msg = (
                f"✅ <b>ĐÃ TẠO {created_count}/{bot_count} BOT XU HƯỚNG</b>\n\n"
                f"🎯 Hệ thống: Trend Indicator System\n"
                f"📊 Chỉ báo: EMA + RSI + Volume + Support/Resistance\n"
                f"📈 Thống kê: Phân tích xác suất 200 nến\n"
                f"💰 Đòn bẩy: {lev}x\n"
                f"📈 % Số dư: {percent}%\n"
                f"🎯 TP: {tp}%\n"
                f"🛡️ SL: {sl}%\n"
                f"🔧 Chế độ: {bot_mode}\n"
            )
            
            if bot_mode == 'static' and symbol:
                success_msg += f"🔗 Coin: {symbol}\n"
            else:
                success_msg += f"🔗 Coin: Tự động tìm kiếm\n"
            
            success_msg += (
                f"\n📊 <b>Hệ thống thống kê xác suất:</b>\n"
                f"• Phân tích 200 nến lịch sử\n"
                f"• Tính kỳ vọng & phương sai\n"
                f"• Đề xuất hướng tối ưu"
            )
            
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
        
        # Xử lý các lệnh menu chính
        if text == "➕ Thêm Bot":
            self._handle_add_bot(chat_id)
        elif text == "📊 Danh sách Bot":
            self._handle_bot_list(chat_id)
        elif text == "📊 Thống kê":
            self._handle_statistics(chat_id)
        elif text == "⛔ Dừng Bot":
            self._handle_stop_bot(chat_id)
        elif text == "💰 Số dư":
            self._handle_balance(chat_id)
        elif text == "📈 Vị thế":
            self._handle_positions(chat_id)
        elif text == "🎯 Chiến lược":
            self._handle_strategy(chat_id)
        elif text == "⚙️ Cấu hình":
            self._handle_config(chat_id)
        elif text.startswith("⛔ "):
            self._handle_stop_specific_bot(chat_id, text)
        elif text.startswith("📊 "):
            symbol = text.replace("📊 ", "").strip()
            report = self.get_probability_report(symbol)
            send_telegram(report, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        elif current_step:
            self._handle_bot_creation_steps(chat_id, text, user_state, current_step)
        elif text.strip():
            self.send_main_menu(chat_id)

    def _handle_add_bot(self, chat_id):
        """Xử lý thêm bot"""
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

    def _handle_bot_list(self, chat_id):
        """Xử lý danh sách bot"""
        if not self.bots:
            send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        else:
            message = "🤖 <b>DANH SÁCH BOT ĐỘC LẬP ĐANG CHẠY</b>\n\n"
            
            for bot_id, bot in self.bots.items():
                if bot.status == "searching":
                    status = "🔍 Đang tìm coin"
                elif bot.status == "waiting":
                    status = "🟡 Chờ tín hiệu"
                elif bot.status == "open":
                    status = "🟢 Đang trade"
                else:
                    status = "⚪ Unknown"
                
                symbol_info = bot.symbol if bot.symbol else "Đang tìm..."
                message += f"🔹 {bot_id}\n"
                message += f"   📊 {symbol_info} | {status}\n"
                message += f"   💰 ĐB: {bot.lev}x | Vốn: {bot.percent}%\n\n"
            
            message += f"📈 Tổng số: {len(self.bots)} bot"
            
            send_telegram(message, chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)

    def _handle_statistics(self, chat_id):
        """Xử lý thống kê"""
        summary = self.get_detailed_statistics()
        send_telegram(summary, chat_id,
                     bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)

    def _handle_stop_bot(self, chat_id):
        """Xử lý dừng bot"""
        if not self.bots:
            send_telegram("🤖 Không có bot nào đang chạy", chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        else:
            message = "⛔ <b>CHỌN BOT ĐỂ DỪNG</b>\n\n"
            keyboard = []
            
            for bot_id in self.bots.keys():
                keyboard.append([{"text": f"⛔ {bot_id}"}])
            
            keyboard.append([{"text": "⛔ DỪNG TẤT CẢ"}])
            keyboard.append([{"text": "❌ Hủy bỏ"}])
            
            send_telegram(
                message, 
                chat_id, 
                {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True},
                self.telegram_bot_token, self.telegram_chat_id
            )

    def _handle_stop_specific_bot(self, chat_id, text):
        """Xử lý dừng bot cụ thể"""
        bot_id = text.replace("⛔ ", "").strip()
        if bot_id == "DỪNG TẤT CẢ":
            self.stop_all()
            send_telegram("⛔ Đã dừng tất cả bot", chat_id, create_main_menu(),
                        self.telegram_bot_token, self.telegram_chat_id)
        elif self.stop_bot(bot_id):
            send_telegram(f"⛔ Đã dừng bot {bot_id}", chat_id, create_main_menu(),
                        self.telegram_bot_token, self.telegram_chat_id)
        else:
            send_telegram(f"⚠️ Không tìm thấy bot {bot_id}", chat_id, create_main_menu(),
                        self.telegram_bot_token, self.telegram_chat_id)

    def _handle_balance(self, chat_id):
        """Xử lý số dư"""
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

    def _handle_positions(self, chat_id):
        """Xử lý vị thế"""
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

    def _handle_strategy(self, chat_id):
        """Xử lý chiến lược"""
        strategy_info = (
            "🎯 <b>HỆ THỐNG BOT XU HƯỚNG TÍCH HỢP</b>\n\n"
            "📊 <b>Hệ Thống Thống Kê Xác Suất</b>\n"
            "• Phân tích 200 nến lịch sử\n"
            "• Tính xác suất thắng cho từng chỉ báo\n"
            "• Tính kỳ vọng & phương sai\n"
            "• Đề xuất hướng tối ưu\n\n"
            "🤖 <b>Chỉ Báo Sử Dụng</b>\n"
            "• EMA (9, 21, 50) - Trọng số 30%\n"
            "• RSI + Volume - Trọng số 25%\n"  
            "• Support/Resistance - Trọng số 15%\n"
            "• Market Structure - Trọng số 10%\n"
            "• Probability Analysis - Trọng số 20%"
        )
        send_telegram(strategy_info, chat_id,
                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)

    def _handle_config(self, chat_id):
        """Xử lý cấu hình"""
        balance = get_balance(self.api_key, self.api_secret)
        api_status = "✅ Đã kết nối" if balance is not None else "❌ Lỗi kết nối"
        
        searching_bots = sum(1 for bot in self.bots.values() if bot.status == "searching")
        trading_bots = sum(1 for bot in self.bots.values() if bot.status in ["waiting", "open"])
        
        config_info = (
            "⚙️ <b>CẤU HÌNH HỆ THỐNG ĐA LUỒNG</b>\n\n"
            f"🔑 Binance API: {api_status}\n"
            f"🤖 Tổng số bot: {len(self.bots)}\n"
            f"🔍 Đang tìm coin: {searching_bots} bot\n"
            f"📊 Đang trade: {trading_bots} bot\n"
            f"📈 Thống kê xác suất: Đã kích hoạt\n"
            f"🔄 Rotation Coin: Đã kích hoạt"
        )
        send_telegram(config_info, chat_id,
                    bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)

    def _handle_bot_creation_steps(self, chat_id, text, user_state, current_step):
        """Xử lý các bước tạo bot"""
        if text == '❌ Hủy bỏ':
            self.user_states[chat_id] = {}
            send_telegram("❌ Đã hủy thêm bot", chat_id, create_main_menu(),
                        self.telegram_bot_token, self.telegram_chat_id)
            return

        try:
            if current_step == 'waiting_bot_count':
                bot_count = int(text)
                if bot_count <= 0 or bot_count > 10:
                    send_telegram("⚠️ Số lượng bot phải từ 1 đến 10. Vui lòng chọn lại:",
                                chat_id, create_bot_count_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)
                    return

                user_state['bot_count'] = bot_count
                user_state['step'] = 'waiting_bot_mode'
                
                send_telegram(
                    f"🤖 Số lượng bot: {bot_count}\n\nChọn chế độ bot:",
                    chat_id,
                    create_bot_mode_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

            elif current_step == 'waiting_bot_mode':
                if text in ["🤖 Bot Tĩnh - Coin cụ thể", "🔄 Bot Động - Tự tìm coin"]:
                    user_state['bot_mode'] = 'static' if text == "🤖 Bot Tĩnh - Coin cụ thể" else 'dynamic'
                    user_state['step'] = 'waiting_strategy'
                    
                    mode_text = "BOT TĨNH - Coin cố định" if user_state['bot_mode'] == 'static' else "BOT ĐỘNG - Tự tìm coin"
                    
                    send_telegram(
                        f"🎯 <b>ĐÃ CHỌN: {mode_text}</b>\n\nChọn chiến lược:",
                        chat_id,
                        create_strategy_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )

            elif current_step == 'waiting_strategy':
                if text in ["⏰ Trend System"]:
                    user_state['strategy'] = "Multi-Timeframe"
                    user_state['step'] = 'waiting_leverage'
                    
                    send_telegram(
                        f"🎯 <b>ĐÃ CHỌN: Trend System</b>\n\nChọn đòn bẩy:",
                        chat_id,
                        create_leverage_keyboard(),
                        self.telegram_bot_token, self.telegram_chat_id
                    )

            elif current_step == 'waiting_leverage':
                lev_text = text[:-1] if text.endswith('x') else text
                leverage = int(lev_text)
                
                if leverage <= 0 or leverage > 100:
                    send_telegram("⚠️ Đòn bẩy phải từ 1 đến 100. Vui lòng chọn lại:",
                                chat_id, create_leverage_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)
                    return

                user_state['leverage'] = leverage
                user_state['step'] = 'waiting_percent'
                
                send_telegram(
                    f"💰 Đòn bẩy: {leverage}x\n\nChọn % số dư cho mỗi lệnh:",
                    chat_id,
                    create_percent_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

            elif current_step == 'waiting_percent':
                percent = float(text)
                if percent <= 0 or percent > 100:
                    send_telegram("⚠️ % số dư phải từ 0.1 đến 100. Vui lòng chọn lại:",
                                chat_id, create_percent_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)
                    return

                user_state['percent'] = percent
                user_state['step'] = 'waiting_tp'
                
                send_telegram(
                    f"📊 % Số dư: {percent}%\n\nChọn Take Profit (%):",
                    chat_id,
                    create_tp_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

            elif current_step == 'waiting_tp':
                tp = float(text)
                if tp <= 0:
                    send_telegram("⚠️ Take Profit phải lớn hơn 0. Vui lòng chọn lại:",
                                chat_id, create_tp_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)
                    return

                user_state['tp'] = tp
                user_state['step'] = 'waiting_sl'
                
                send_telegram(
                    f"🎯 Take Profit: {tp}%\n\nChọn Stop Loss (%):",
                    chat_id,
                    create_sl_keyboard(),
                    self.telegram_bot_token, self.telegram_chat_id
                )

            elif current_step == 'waiting_sl':
                sl = float(text)
                if sl < 0:
                    send_telegram("⚠️ Stop Loss phải lớn hơn hoặc bằng 0. Vui lòng chọn lại:",
                                chat_id, create_sl_keyboard(),
                                self.telegram_bot_token, self.telegram_chat_id)
                    return

                user_state['sl'] = sl
                
                # Tạo bot
                strategy = user_state.get('strategy')
                bot_mode = user_state.get('bot_mode', 'static')
                leverage = user_state.get('leverage')
                percent = user_state.get('percent')
                tp = user_state.get('tp')
                sl = user_state.get('sl')
                symbol = user_state.get('symbol')
                bot_count = user_state.get('bot_count', 1)
                
                success = self.add_bot(
                    symbol=symbol,
                    lev=leverage,
                    percent=percent,
                    tp=tp,
                    sl=sl,
                    strategy_type=strategy,
                    bot_mode=bot_mode,
                    bot_count=bot_count
                )
                
                if success:
                    success_msg = f"✅ <b>ĐÃ TẠO {bot_count} BOT THÀNH CÔNG</b>"
                    send_telegram(success_msg, chat_id, create_main_menu(),
                                self.telegram_bot_token, self.telegram_chat_id)
                else:
                    send_telegram("❌ Có lỗi khi tạo bot. Vui lòng thử lại.",
                                chat_id, create_main_menu(),
                                self.telegram_bot_token, self.telegram_chat_id)
                
                self.user_states[chat_id] = {}
                
        except ValueError as e:
            send_telegram("⚠️ Vui lòng nhập số hợp lệ:", chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
        except Exception as e:
            send_telegram(f"❌ Lỗi xử lý: {str(e)}", chat_id,
                        bot_token=self.telegram_bot_token, default_chat_id=self.telegram_chat_id)
            self.user_states[chat_id] = {}

# ========== KẾT THÚC FILE ==========
logger.info("✅ Trading Bot Library đã được tải hoàn chỉnh!")
logger.info("📊 Hệ thống thống kê xác suất đã sẵn sàng!")
logger.info("🎯 Hệ thống 5 bước thông minh đã tích hợp!")
