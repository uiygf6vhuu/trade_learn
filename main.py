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

# [Keep all the existing configuration and helper functions...]

# ========== NEW FUNCTIONS FOR 24H CHANGE LOGIC ==========

def get_24h_ticker_data():
    """Get 24h ticker data for all symbols from Binance"""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        data = binance_api_request(url)
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting 24h ticker data: {str(e)}")
        return []

def get_high_volatility_coins(threshold=30):
    """
    Get coins with price change > threshold% in 24h
    Returns: List of symbols with their price change and direction
    """
    tickers = get_24h_ticker_data()
    volatile_coins = []
    
    for ticker in tickers:
        try:
            symbol = ticker['symbol']
            price_change_percent = float(ticker['priceChangePercent'])
            
            # Only include USDT pairs and filter by threshold
            if symbol.endswith('USDT') and abs(price_change_percent) >= threshold:
                direction = "UP" if price_change_percent > 0 else "DOWN"
                volatile_coins.append({
                    'symbol': symbol,
                    'change_percent': price_change_percent,
                    'direction': direction
                })
        except Exception as e:
            logger.error(f"Error processing ticker {ticker.get('symbol', 'unknown')}: {str(e)}")
    
    return volatile_coins

def get_signal(symbol):
    """
    NEW LOGIC: Get trading signal based on 24h price movement
    - If price UP > 30% in 24h -> SELL signal (expecting pullback)
    - If price DOWN > 30% in 24h -> BUY signal (expecting bounce)
    """
    tickers = get_24h_ticker_data()
    
    for ticker in tickers:
        if ticker['symbol'] == symbol.upper():
            price_change_percent = float(ticker['priceChangePercent'])
            
            # Check if movement meets threshold
            if abs(price_change_percent) >= 30:
                if price_change_percent > 0:
                    return "SELL", price_change_percent
                else:
                    return "BUY", abs(price_change_percent)
    
    return None, 0

# ========== MODIFIED BOT CLASS ==========

class IndicatorBot:
    def __init__(self, symbol, lev, percent, tp, sl, ws_manager):
        self.symbol = symbol.upper()
        self.lev = lev
        self.percent = percent
        self.tp = tp
        self.sl = sl
        self.ws_manager = ws_manager
        
        # Remove indicator weights/stats as they're no longer needed
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

# ========== MODIFIED BOT MANAGER ==========

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
        
        # Add function to show high volatility coins
        self.add_volatility_keyboard()
        
        if self.admin_chat_id:
            self.send_main_menu(self.admin_chat_id)

    def add_volatility_keyboard(self):
        """Add keyboard option to check high volatility coins"""
        self.volatility_keyboard = {
            "keyboard": [
                [{"text": "📊 Danh sách Bot"}],
                [{"text": "➕ Thêm Bot"}, {"text": "⛔ Dừng Bot"}],
                [{"text": "💰 Số dư tài khoản"}, {"text": "📈 Vị thế đang mở"}],
                [{"text": "🎯 Coins biến động >30%"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }

    def send_main_menu(self, chat_id):
        welcome = "🤖 <b>BINANCE FUTURES TRADING BOT</b>\n\n🎯 <b>Strategy: Reverse 24h Moves >30%</b>\n\nChoose an option below:"
        send_telegram(welcome, chat_id, self.volatility_keyboard)

    # [Keep all other BotManager methods the same...]

    def _handle_telegram_message(self, chat_id, text):
        user_state = self.user_states.get(chat_id, {})
        current_step = user_state.get('step')
        
        # [Keep all existing step handling code...]
        
        elif text == "🎯 Coins biến động >30%":
            self.send_high_volatility_coins(chat_id)
            
        elif text:
            self.send_main_menu(chat_id)

    def send_high_volatility_coins(self, chat_id):
        """Send list of coins with >30% 24h movement"""
        try:
            volatile_coins = get_high_volatility_coins(30)
            
            if not volatile_coins:
                send_telegram("📊 Không có coin nào biến động >30% trong 24h", chat_id)
                return
            
            message = "🎯 <b>COINS BIẾN ĐỘNG >30% (24H)</b>\n\n"
            
            for coin in volatile_coins[:15]:  # Show first 15 coins
                arrow = "🟢" if coin['direction'] == "UP" else "🔴"
                message += f"{arrow} {coin['symbol']}: {coin['change_percent']:.2f}%\n"
            
            if len(volatile_coins) > 15:
                message += f"\n...và {len(volatile_coins) - 15} coin khác"
            
            send_telegram(message, chat_id)
            
        except Exception as e:
            send_telegram(f"❌ Lỗi khi lấy danh sách coin biến động: {str(e)}", chat_id)

# [Keep the rest of the code the same...]

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
