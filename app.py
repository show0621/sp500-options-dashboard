import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import os

# ==========================================
# 網頁與視覺風格設定
# ==========================================
st.set_page_config(page_title="Alpha美股莊家策略", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Serif TC', serif; background-color: #FAFAFA; color: #2C3E50; }
    h1, h2, h3 { color: #34495E; font-weight: 300; letter-spacing: 2px; }
    .stApp { background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); }
    .metric-card { background-color: rgba(255, 255, 255, 0.8); border-radius: 10px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border-left: 4px solid #85C1E9; margin-bottom: 15px;}
    .highlight { color: #E74C3C; font-weight: bold; }
    .profit { color: #E74C3C; font-weight: bold; }
    .loss { color: #27AE60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 核心運算與回測模組
# ==========================================
@st.cache_data(ttl=3600)
def fetch_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    df_daily = ticker.history(period="1y", interval="1d")
    df_60m = ticker.history(period="1mo", interval="60m")
    # 確保 news 不會因為 None 而報錯
    news = (ticker.news or [])[:3] if hasattr(ticker, 'news') else []
    inst_holders = ticker.institutional_holders
    return df_daily, df_60m, news, inst_holders

def apply_technical_analysis(df):
    if df.empty or len(df) < 50: return df
    
    # 均線與成交量均線
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_60'] = df['Close'].rolling(window=60).mean()
    df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()
    
    # MACD
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema_12 - ema_26
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
    df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']
    
    # 布林通道 (Bollinger Bands)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()
    return df

def run_daily_backtest(df, strategy_type):
    """三大執行策略平行回測引擎"""
    trade_log = []
    holding = False
    
    # 進場時的變數記錄
    buy_price = 0
    put_strike = 0
    call_strike = 0
    lowest_during_hold = 0
    
    # 權利金參數設定 (基於標的物價值的百分比)
    put_premium_pct = 1.2  # 賣出價外4% Put 約收 1.2%
    call_premium_pct = 1.5 # 賣出價外5% Call 約收 1.5%
    
    for i in range(1, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        date = df.index[i].strftime('%Y-%m-%d')
        
        buy_signal = False
        sell_signal = False
        reason = ""
        
        # --- 進出場邏輯判定 ---
        if strategy_type == "MACD 動能共振":
            if not holding and (prev['MACD_12_26_9'] <= prev['MACDs_12_26_9']) and (current['MACD_12_26_9'] > current['MACDs_12_26_9']) and (current['Close'] > current['SMA_20']):
                buy_signal, reason = True, 'MACD金叉且站上20MA'
            elif holding and ((current['MACD_12_26_9'] < current['MACDs_12_26_9']) or (current['Close'] < current['SMA_60'])):
                sell_signal, reason = True, 'MACD死叉或跌破季線'
                
        elif strategy_type == "VCP 形態突破":
            pivot = prev['Resistance']
            if not holding and (current['Close'] > pivot) and (current['Volume'] > 1.2 * current['Vol_SMA_20']) and (current['Close'] > current['SMA_60']):
                buy_signal, reason = True, '帶量突破20日高點'
            elif holding and (current['Close'] < current['SMA_20']):
                sell_signal, reason = True, '跌破20MA趨勢線'

        elif strategy_type == "布林通道極限收租":
            # 趨勢濾網：只在季線與月線多頭排列時找買點 (避免接飛刀)
            is_uptrend = current['SMA_20'] > current['SMA_60']
            touch_lower = current['Low'] <= current['BB_Lower']
            
            if not holding and is_uptrend and touch_lower:
                buy_signal, reason = True, '多頭回檔觸及布林下軌'
            elif holding:
                # 賣出：價格衝至布林上軌 (過熱) 或 跌破季線停損
                if current['High'] >= current['BB_Upper']:
                    sell_signal, reason = True, '觸及布林上軌(過熱超買)'
                elif current['Close'] < current['SMA_60'] * 0.98:
                    sell_signal, reason = True, '跌破季線(趨勢轉弱停損)'

        # --- 交易執行與三大策略平行損益計算 ---
        if buy_signal:
            holding = True
            buy_price = current['Close']
            lowest_during_hold = current['Low']
            
            # 定義選擇權履約價
            put_strike = current['BB_Lower'] if current['BB_Lower'] > 0 else buy_price * 0.96
            call_strike = buy_price * 1.05
            
            trade_log.append({
                'Date': date, 'Action': 'BUY', 'Price': buy_price, 'Reason': reason, 
                '現股 PnL(%)': 0, 'Sell Put PnL(%)': 0, 'Covered Call PnL(%)': 0
            })
            
        elif holding:
            lowest_during_hold = min(lowest_during_hold, current['Low'])
            if sell_signal:
                holding = False
                sell_price = current['Close']
                
                # 1. 單純現股 (Buy & Hold)
                stock_pnl = (sell_price - buy_price) / buy_price * 100
                
                # 2. 賣出賣權 (Sell Put)
                if sell_price < put_strike:
                    put_pnl = ((sell_price - put_strike) / buy_price * 100) + put_premium_pct
                else:
                    put_pnl = put_premium_pct # 安穩收租
                    
                # 3. 掩護性買權 (Covered Call)
                if sell_price > call_strike:
                    cc_pnl = ((call_strike - buy_price) / buy_price * 100) + call_premium_pct
                else:
                    cc_pnl = stock_pnl + call_premium_pct 
                    
                trade_log.append({
                    'Date': date, 'Action': 'SELL', 'Price': sell_price, 'Reason': reason, 
                    '現股 PnL(%)': round(stock_pnl, 2), 
                    'Sell Put PnL(%)': round(put_pnl, 2), 
                    'Covered Call PnL(%)': round(cc_pnl, 2)
                })
    
    # 若最後一天仍持有，計算未實現損益
    if holding:
        last_price = df.iloc[-1]['Close']
        stock_pnl = (last_price - buy_price) / buy_price * 100
        
        put_pnl = ((last_price - put_strike) / buy_price * 100) + put_premium_pct if last_price < put_strike else put_premium_pct
        cc_pnl = ((call_strike - buy_price) / buy_price * 100) + call_premium_pct if last_price > call_strike else stock_pnl + call_premium_pct
        
        trade_log.append({
            'Date': df.index[-1].strftime('%Y-%m-%d'), 'Action': 'HOLDING', 'Price': last_price, 'Reason': '目前持倉中 (未實現我的设计用途只是处理和生成文本，所以没法在这方面帮到你。
