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
st.set_page_config(page_title="Alpha 櫻・美股共振展望", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Serif TC', serif; background-color: #FAFAFA; color: #2C3E50; }
    h1, h2, h3 { color: #34495E; font-weight: 300; letter-spacing: 2px; }
    .stApp { background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); }
    .metric-card { background-color: rgba(255, 255, 255, 0.8); border-radius: 10px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border-left: 4px solid #85C1E9; }
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
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_60'] = df['Close'].rolling(window=60).mean()
    
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema_12 - ema_26
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
    df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']
    
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()
    return df

def run_daily_backtest(df):
    """日K波段回測引擎"""
    trade_log = []
    holding = False
    buy_price = 0
    
    for i in range(1, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        date = df.index[i].strftime('%Y-%m-%d')
        
        # 買進邏輯：MACD黃金交叉 且 站上月線
        if not holding:
            if (prev['MACD_12_26_9'] <= prev['MACDs_12_26_9']) and (current['MACD_12_26_9'] > current['MACDs_12_26_9']) and (current['Close'] > current['SMA_20']):
                holding = True
                buy_price = current['Close']
                trade_log.append({'Date': date, 'Action': 'BUY', 'Price': buy_price, 'Reason': 'MACD金叉且站上20MA', 'PnL (%)': 0})
        
        # 賣出邏輯：MACD死亡交叉 或 跌破季線
        elif holding:
            if (current['MACD_12_26_9'] < current['MACDs_12_26_9']) or (current['Close'] < current['SMA_60']):
                holding = False
                sell_price = current['Close']
                pnl = (sell_price - buy_price) / buy_price * 100
                trade_log.append({'Date': date, 'Action': 'SELL', 'Price': sell_price, 'Reason': 'MACD死叉或跌破60MA', 'PnL (%)': round(pnl, 2)})
    
    # 若最後一天仍持有，強制平倉計算未實現損益
    if holding:
        last_price = df.iloc[-1]['Close']
        pnl = (last_price - buy_price) / buy_price * 100
        trade_log.append({'Date': df.index[-1].strftime('%Y-%m-%d'), 'Action': 'HOLDING', 'Price': last_price, 'Reason': '目前持倉中 (未實現)', 'PnL (%)': round(pnl, 2)})
        
    return pd.DataFrame(trade_log)

def plot_chart(df, title, trade_log_df):
    """繪製 K線圖與買賣點"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])

    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線',
                                 increasing_line_color='#E74C3C', decreasing_line_color='#27AE60'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#3498DB', width=1.5), name='20MA'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_60'], line=dict(color='#9B59B6', width=1.5), name='60MA'), row=1, col=1)

    # 標示買賣點位
    if not trade_log_df.empty:
        buys = trade_log_df[trade_log_df['Action'] == 'BUY']
        sells = trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]
        
        # Buy Markers (向上三角形)
        fig.add_trace(go.Scatter(x=pd.to_datetime(buys['Date']), y=buys['Price'] * 0.95, mode='markers+text', 
                                 marker=dict(symbol='triangle-up', size=12, color='#E74C3C'), name='買進點', text="買", textposition="bottom center"), row=1, col=1)
        # Sell Markers (向下三角形)
        fig.add_trace(go.Scatter(x=pd.to_datetime(sells['Date']), y=sells['Price'] * 1.05, mode='markers+text', 
                                 marker=dict(symbol='triangle-down', size=12, color='#27AE60'), name='賣出/現價', text="賣", textposition="top center"), row=1, col=1)

    fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name='MACD Hist', marker_color='#BDC3C7'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], line=dict(color='#E74C3C', width=1), name='MACD'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], line=dict(color='#2980B9', width=1), name='Signal'), row=2, col=1)

    fig.update_layout(title=title, xaxis_rangeslider_visible=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                      font=dict(family="Noto Serif TC", size=12, color="#2C3E50"), margin=dict(l=20, r=20, t=50, b=20))
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.2)')
    return fig

# ==========================================
# 前端 UI 渲染
# ==========================================
st.title("晨光與數據的交匯 ── S&P 500 波段與收租展望")

with st.sidebar:
    st.header("🔍 標的探索")
    ticker_input = st.text_input("輸入美股代碼 (如 AAPL, NVDA, SPY)", "AAPL").upper()
    
    # ---------------- 讀取機器人掃描的推薦名單 ----------------
    st.markdown("---")
    st.header("🎯 S&P 500 共振推薦名單")
    st.write("以下為系統背景掃描，符合動能共振之潛力標的：")
    
    try:
        if os.path.exists('signals.csv'):
            signals_df = pd.read_csv('signals.csv')
            if not signals_df.empty:
                st.dataframe(signals_df[['代碼', '當前價格', '支撐位 (建議 Sell Put 價)']], hide_index=True)
                st.caption(f"最後更新日期：{signals_df.iloc[0]['日期']}")
                st.info("💡 提示：點擊上方代碼輸入框，即可查看該檔股票的詳細回測與圖表。")
            else:
                st.write("今日市場無符合多頭共振條件之標的。")
        else:
            st.warning("尚未偵測到 `signals.csv`。")
            st.caption("請確認 GitHub Actions 的掃描腳本是否已經成功執行並寫入資料庫。")
    except Exception as e:
        st.error(f"讀取推薦清單時發生錯誤: {e}")
    # --------------------------------------------------------------
        
    st.markdown("---")
    st.write("📖 **策略說明**")
    st.write("自動判定動能共振點，提供買賣回測點位，並結合賣方選擇權策略尋找收租支撐位。")

# 以下為單檔股票詳細分析與圖表繪製邏輯
if ticker_input:
    with st.spinner('正在從喧囂的市場中擷取數據...'):
        df_daily_raw, df_60m_raw, news_data, inst_holders = fetch_data(ticker_input)
        
    if not df_daily_raw.empty:
        df_daily = apply_technical_analysis(df_daily_raw.copy())
        
        # 執行歷史回測
        trade_log_df = run_daily_backtest(df_daily)
        
        current_price = df_daily.iloc[-1]['Close']
        support = df_daily.iloc[-1]['Support']
        put_strike = support * 0.98
        
        # 儀表板
        st.markdown("### 🧭 今日觀點與決策")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h4>當前股價</h4><h2>${current_price:.2f}</h2>
                <p>近期支撐: ${support:.2f} | 建議 Sell Put 履約價: ${put_strike:.0f}</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            # 計算歷史勝率
            win_rate = "無交易"
            if not trade_log_df.empty and len(trade_log_df[trade_log_df['Action'] == 'SELL']) > 0:
                sells = trade_log_df[trade_log_df['Action'] == 'SELL']
                wins = len(sells[sells['PnL (%)'] > 0])
                win_rate = f"{(wins / len(sells)) * 100:.1f}%"
                total_pnl = sells['PnL (%)'].sum()
            else:
                total_pnl = 0.0
            
            st.markdown(f"""
            <div class="metric-card">
                <h4>近一年日K波段回測表現</h4>
                <h2>總績效: {total_pnl:.2f}% (勝率: {win_rate})</h2>
                <p>純粹依賴 MACD 與 20MA/60MA 共振之機械化交易結果</p>
            </div>
            """, unsafe_allow_html=True)

        # K線圖 (帶買賣點)
        st.markdown("---")
        st.markdown("### 📊 價格脈絡與買賣點標示")
        st.plotly_chart(plot_chart(df_daily.tail(150), f"{ticker_input} - 歷史交易點位", trade_log_df), use_container_width=True)

        # 交易明細與下載
        st.markdown("### 📝 回測交易明細與原因")
        if not trade_log_df.empty:
            st.dataframe(trade_log_df, use_container_width=True)
            csv = trade_log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 下載交易明細 (CSV)", data=csv, file_name=f'{ticker_input}_trade_log.csv', mime='text/csv')
        else:
            st.write("過去一年無符合條件之交易訊號。")

        # 籌碼與題材區
        st.markdown("---")
        col_news, col_chips = st.columns([1, 1])
        
        with col_news:
            st.markdown("### 📰 近期題材與市場絮語")
            if news_data:
                for n in news_data:
                    # 暴力破解 Yahoo API 的各種巢狀結構
                    title = n.get('title') or n.get('content', {}).get('title') or '市場快訊'
                    link = n.get('link') or n.get('content', {}).get('clickThroughUrl', {}).get('url') or '#'
                    publisher = n.get('publisher') or n.get('content', {}).get('provider', {}).get('displayName') or '財經新聞'
                    
                    st.markdown(f"**[{title}]({link})**")
                    st.caption(f"{publisher}")
            else:
                st.write("目前市場平靜，無特別新聞。")
                
        with col_chips:
            st.markdown("### 💼 籌碼動向 (自動推算法人與散戶)")
            if inst_holders is not None and not inst_holders.empty and 'pctHeld' in inst_holders.columns:
                # 分析籌碼動向
                top_inst_pct = inst_holders['pctHeld'].sum()
                retail_pct = 1 - top_inst_pct
                sentiment = "偏多 (機構近期加碼)" if inst_holders['pctChange'].mean() > 0 else "偏空 (機構近期減碼)"
                
                st.info(f"📊 **籌碼推算：** 前幾大機構掌控約 **{top_inst_pct:.1%}**，散戶約佔 **{retail_pct:.1%}**。整體法人動向：**{sentiment}**")
                
                # 顯示表格
                expected_cols = ['Holder', 'pctHeld', 'Shares', 'pctChange']
                display_df = inst_holders[expected_cols] if set(expected_cols).issubset(inst_holders.columns) else inst_holders
                st.dataframe(display_df.head(5), hide_index=True)
            else:
                st.write("暫無機構籌碼資料，或資料結構變更。")
    else:
        st.error("無法尋獲該代碼的軌跡，請確認美股代碼是否正確。")
