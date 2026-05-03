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
    news = ticker.news[:3] if hasattr(ticker, 'news') else []
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
    """三大執行策略平行回測引擎 (含多模式績效計算)"""
    trade_log = []
    holding = False
    buy_price = 0
    put_strike = 0
    call_strike = 0
    
    # 權利金參數設定
    put_premium_pct = 1.2  
    call_premium_pct = 1.5 
    
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
            is_uptrend = current['SMA_20'] > current['SMA_60']
            touch_lower = current['Low'] <= current['BB_Lower']
            if not holding and is_uptrend and touch_lower:
                buy_signal, reason = True, '多頭回檔觸及布林下軌'
            elif holding:
                if current['High'] >= current['BB_Upper']:
                    sell_signal, reason = True, '觸及布林上軌(過熱超買)'
                elif current['Close'] < current['SMA_60'] * 0.98:
                    sell_signal, reason = True, '跌破季線(趨勢轉弱停損)'

        # --- 交易執行計算 ---
        if buy_signal:
            holding = True
            buy_price = current['Close']
            put_strike = current['BB_Lower'] if current['BB_Lower'] > 0 else buy_price * 0.96
            call_strike = buy_price * 1.05
            trade_log.append({'Date': date, 'Action': 'BUY', 'Price': buy_price, 'Reason': reason, '現股 PnL(%)': 0, 'Sell Put PnL(%)': 0, 'Covered Call PnL(%)': 0})
            
        elif holding and sell_signal:
            holding = False
            sell_price = current['Close']
            stock_pnl = (sell_price - buy_price) / buy_price * 100
            put_pnl = ((sell_price - put_strike) / buy_price * 100) + put_premium_pct if sell_price < put_strike else put_premium_pct
            cc_pnl = ((call_strike - buy_price) / buy_price * 100) + call_premium_pct if sell_price > call_strike else stock_pnl + call_premium_pct 
            trade_log.append({'Date': date, 'Action': 'SELL', 'Price': sell_price, 'Reason': reason, '現股 PnL(%)': round(stock_pnl, 2), 'Sell Put PnL(%)': round(put_pnl, 2), 'Covered Call PnL(%)': round(cc_pnl, 2)})
    
    if holding:
        last_price = df.iloc[-1]['Close']
        stock_pnl = (last_price - buy_price) / buy_price * 100
        put_pnl = ((last_price - put_strike) / buy_price * 100) + put_premium_pct if last_price < put_strike else put_premium_pct
        cc_pnl = ((call_strike - buy_price) / buy_price * 100) + call_premium_pct if last_price > call_strike else stock_pnl + call_premium_pct
        trade_log.append({'Date': df.index[-1].strftime('%Y-%m-%d'), 'Action': 'HOLDING', 'Price': last_price, 'Reason': '目前持倉中 (未實現)', '現股 PnL(%)': round(stock_pnl, 2), 'Sell Put PnL(%)': round(put_pnl, 2), 'Covered Call PnL(%)': round(cc_pnl, 2)})
    return pd.DataFrame(trade_log)

def plot_chart(df, title, trade_log_df):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線', increasing_line_color='#E74C3C', decreasing_line_color='#27AE60'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(52, 152, 219, 0.2)', width=1), name='布林上軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(52, 152, 219, 0.2)', width=1), fill='tonexty', fillcolor='rgba(52, 152, 219, 0.05)', name='布林下軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#3498DB', width=1.5), name='20MA(中軌)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_60'], line=dict(color='#9B59B6', width=1.5), name='60MA'), row=1, col=1)
    
    if not trade_log_df.empty:
        buys = trade_log_df[trade_log_df['Action'] == 'BUY']
        sells = trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]
        fig.add_trace(go.Scatter(x=pd.to_datetime(buys['Date']), y=buys['Price'] * 0.95, mode='markers+text', marker=dict(symbol='triangle-up', size=12, color='#E74C3C'), name='買進', text="買", textposition="bottom center"), row=1, col=1)
        fig.add_trace(go.Scatter(x=pd.to_datetime(sells['Date']), y=sells['Price'] * 1.05, mode='markers+text', marker=dict(symbol='triangle-down', size=12, color='#27AE60'), name='賣出/現價', text="賣", textposition="top center"), row=1, col=1)
    
    fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name='MACD Hist', marker_color='#BDC3C7'), row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(family="Noto Serif TC", size=12), margin=dict(l=20, r=20, t=50, b=20))
    return fig

# ==========================================
# 前端 UI 渲染
# ==========================================
st.title("晨光與數據的交匯 ── S&P 500 波段與收租展望")

with st.sidebar:
    st.header("🔍 標的探索")
    ticker_input = st.text_input("輸入美股代碼", "AAPL").upper()
    strategy_choice = st.selectbox("選擇進出場判定邏輯：", ("布林通道極限收租", "VCP 形態突破", "MACD 動能共振"))
    
    st.markdown("---")
    st.header("🎯 S&P 500 策略推薦清單")
    if os.path.exists('signals.csv'):
        try:
            signals_df = pd.read_csv('signals.csv')
            if not signals_df.empty and '符合策略' in signals_df.columns:
                filtered_df = signals_df[signals_df['符合策略'] == strategy_choice]
                if not filtered_df.empty:
                    st.dataframe(filtered_df[['代碼', '當前價格', '支撐位 (建議 Sell Put 價)']], hide_index=True)
                    st.caption(f"最後更新：{filtered_df.iloc[0]['日期']}")
                else: st.write(f"今日無符合標的。")
            else: st.write("無推薦數據。")
        except: st.error("清單讀取失敗")
    else: st.warning("等待訊號生成中...")

if ticker_input:
    with st.spinner('數據計算中...'):
        df_daily_raw, df_60m_raw, news_data, inst_holders = fetch_data(ticker_input)
        
    if not df_daily_raw.empty:
        df_daily = apply_technical_analysis(df_daily_raw.copy())
        trade_log_df = run_daily_backtest(df_daily, strategy_choice)
        
        st.markdown(f"### 📊 【{strategy_choice}】三大策略回測比較")
        if not trade_log_df.empty and len(trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]) > 0:
            sells = trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]
            c1, c2, c3 = st.columns(3)
            c1.metric("純買現股利潤", f"{sells['現股 PnL(%)'].sum():.2f}%")
            c2.metric("Sell Put 利潤", f"{sells['Sell Put PnL(%)'].sum():.2f}%")
            c3.metric("Covered Call 利潤", f"{sells['Covered Call PnL(%)'].sum():.2f}%")

        st.plotly_chart(plot_chart(df_daily.tail(150), f"{ticker_input} 圖表", trade_log_df), use_container_width=True)
        
        # --- 安全修復的新聞與籌碼區 ---
        st.markdown("---")
        col_news, col_chips = st.columns([1, 1])
        with col_news:
            st.markdown("### 📰 近期題材")
            if news_data:
                for n in news_data:
                    try:
                        # 這是修正 AttributeError 的關鍵安全路徑
                        title = n.get('title') or "市場新聞"
                        link = n.get('link')
                        if not link:
                            # 遍歷深層嵌套結構
                            content = n.get('content')
                            if isinstance(content, dict):
                                link = content.get('clickThroughUrl', {}).get('url')
                        st.markdown(f"**[{title}]({link or '#'})**")
                    except: continue
            else: st.write("暫無新聞。")
        
        with col_chips:
            st.markdown("### 💼 籌碼動向")
            if inst_holders is not None and not inst_holders.empty and 'pctHeld' in inst_holders.columns:
                st.info(f"機構掌控約 {inst_holders['pctHeld'].sum():.1%}")
                st.dataframe(inst_holders[['Holder', 'pctHeld']].head(5), hide_index=True)
            else: st.write("暫無數據。")
