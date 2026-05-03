import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import os

# ==========================================
# 網頁與視覺風格設定 (日系文學風)
# ==========================================
st.set_page_config(page_title="Alpha 櫻・美股共振展望", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Serif TC', serif; background-color: #FAFAFA; color: #2C3E50; }
    h1, h2, h3 { color: #34495E; font-weight: 300; letter-spacing: 2px; }
    .stApp { background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); }
    .metric-card { background-color: rgba(255, 255, 255, 0.8); border-radius: 10px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border-left: 4px solid #85C1E9; }
    .profit-text { color: #E74C3C; font-weight: bold; }
    .loss-text { color: #27AE60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 核心運算與 RSI + 支撐策略模組
# ==========================================
@st.cache_data(ttl=3600)
def fetch_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    df_daily = ticker.history(period="2y", interval="1d") # 拉長到2年以利回測
    news = ticker.news[:3] if hasattr(ticker, 'news') else []
    inst_holders = ticker.institutional_holders
    return df_daily, news, inst_holders

def apply_technical_analysis(df):
    if df.empty or len(df) < 50: return df
    # 趨勢均線
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_60'] = df['Close'].rolling(window=60).mean()
    
    # RSI 計算
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # 尋找支撐與壓力 (近20週期的高低點)
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()
    return df

def run_rsi_support_backtest(df):
    """進階策略：RSI背離修復與支撐測試 & 選擇權收租回測"""
    trade_log = []
    holding = False
    buy_price = 0
    
    # 選擇權模擬參數
    put_strike = 0
    expected_premium = 0
    holding_min_price = 0
    
    for i in range(1, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        date = df.index[i].strftime('%Y-%m-%d')
        
        # 策略 1：多頭回檔至支撐且 RSI 進入超賣區後反彈 (勝率與盈虧比高)
        is_uptrend = current['Close'] > current['SMA_60']
        near_support = current['Close'] <= prev['Support'] * 1.03 # 距離支撐3%內
        rsi_oversold_bounce = prev['RSI_14'] < 40 and current['RSI_14'] > prev['RSI_14']
        
        if not holding:
            if is_uptrend and near_support and rsi_oversold_bounce:
                holding = True
                buy_price = current['Close']
                
                # 建立選擇權 Sell Put 部位：履約價設在現價下方 4% (價外4檔)
                put_strike = buy_price * 0.96
                expected_premium = buy_price * 0.012 # 預估收取 1.2% 的權利金
                holding_min_price = current['Low']
                
                trade_log.append({
                    'Date': date, 'Action': 'BUY', 'Stock Price': buy_price, 
                    'Reason': '回測支撐且RSI反彈', 'Stock PnL(%)': 0, 
                    'Opt Strike': round(put_strike, 2), 'Opt PnL(%)': 0, 'Opt Status': '建倉'
                })
        
        elif holding:
            holding_min_price = min(holding_min_price, current['Low'])
            
            # 賣出邏輯：RSI 超買(>70) 或是 跌破季線(停損)
            if current['RSI_14'] > 70 or current['Close'] < current['SMA_60'] * 0.98:
                holding = False
                sell_price = current['Close']
                stock_pnl = (sell_price - buy_price) / buy_price * 100
                
                # 計算選擇權 Sell Put 損益
                if holding_min_price >= put_strike:
                    opt_status = '安全收租'
                    opt_pnl = 1.2 # 完整賺取 1.2% 權利金
                else:
                    opt_status = '跌破履約 (虧損或接盤)'
                    # 若跌破，選擇權損失 = (現價 - 履約價) + 權利金。最高賺1.2%
                    opt_raw_pnl = ((sell_price - put_strike) / buy_price * 100) + 1.2
                    opt_pnl = min(1.2, opt_raw_pnl)
                
                trade_log.append({
                    'Date': date, 'Action': 'SELL', 'Stock Price': sell_price, 
                    'Reason': 'RSI超買或破線', 'Stock PnL(%)': round(stock_pnl, 2),
                    'Opt Strike': round(put_strike, 2), 'Opt PnL(%)': round(opt_pnl, 2), 'Opt Status': opt_status
                })
    
    # 若最後一天仍持有
    if holding:
        last_price = df.iloc[-1]['Close']
        stock_pnl = (last_price - buy_price) / buy_price * 100
        holding_min_price = min(holding_min_price, df.iloc[-1]['Low'])
        
        if holding_min_price >= put_strike:
            opt_status = '未實現 (安全區)'
            opt_pnl = 1.2
        else:
            opt_status = '未實現 (跌破履約)'
            opt_pnl = min(1.2, ((last_price - put_strike) / buy_price * 100) + 1.2)

        trade_log.append({
            'Date': df.index[-1].strftime('%Y-%m-%d'), 'Action': 'HOLDING', 'Stock Price': last_price, 
            'Reason': '持倉中', 'Stock PnL(%)': round(stock_pnl, 2),
            'Opt Strike': round(put_strike, 2), 'Opt PnL(%)': round(opt_pnl, 2), 'Opt Status': opt_status
        })
        
    return pd.DataFrame(trade_log)

def plot_chart(df, title, trade_log_df):
    """繪製極簡文青風 K線圖與買賣點"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])

    # K線與均線、支撐線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線',
                                 increasing_line_color='#E74C3C', decreasing_line_color='#27AE60'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_60'], line=dict(color='#9B59B6', width=1.5), name='60MA (趨勢線)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Support'], line=dict(color='#95A5A6', width=1, dash='dot'), name='20日支撐'), row=1, col=1)

    # 標示買賣點位
    if not trade_log_df.empty:
        buys = trade_log_df[trade_log_df['Action'] == 'BUY']
        sells = trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]
        
        fig.add_trace(go.Scatter(x=pd.to_datetime(buys['Date']), y=buys['Stock Price'] * 0.95, mode='markers+text', 
                                 marker=dict(symbol='triangle-up', size=12, color='#E74C3C'), name='進場', text="買", textposition="bottom center"), row=1, col=1)
        fig.add_trace(go.Scatter(x=pd.to_datetime(sells['Date']), y=sells['Stock Price'] * 1.05, mode='markers+text', 
                                 marker=dict(symbol='triangle-down', size=12, color='#27AE60'), name='出場', text="賣", textposition="top center"), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI_14'], line=dict(color='#3498DB', width=1.5), name='RSI(14)'), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1, annotation_text="超買區")
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1, annotation_text="超賣區")

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
    
    st.markdown("---")
    st.write("📖 **全新策略說明**")
    st.write("已升級為 **「RSI 背離與支撐確認策略」**。此策略專注於多頭趨勢(站上季線)中的回檔。當股價靠近20日支撐，且 RSI 從低檔反彈時，發出買進訊號並模擬 **Sell Put (賣出賣權)** 收取權利金。")

if ticker_input:
    with st.spinner('正在從喧囂的市場中擷取數據...'):
        df_daily_raw, news_data, inst_holders = fetch_data(ticker_input)
        
    if not df_daily_raw.empty:
        df_daily = apply_technical_analysis(df_daily_raw.copy())
        trade_log_df = run_rsi_support_backtest(df_daily)
        
        current_price = df_daily.iloc[-1]['Close']
        support = df_daily.iloc[-1]['Support']
        put_strike = current_price * 0.96 # 建議價外4%
        est_premium = current_price * 0.012 # 預估權利金
        
        # 儀表板
        st.markdown("### 🧭 今日決策與最佳收租配置")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h4>當前股價</h4><h2>${current_price:.2f}</h2>
                <p>近期強支撐: ${support:.2f}</p>
                <hr>
                <h4 style='color:#E74C3C;'>🛡️ 最佳收租策略 (Sell Put 賣出賣權)</h4>
                <p>建議履約價：<b>${put_strike:.0f} (價外 4%)</b></p>
                <p>單口預估收租：<b>${est_premium*100:.0f} 美金</b> (約 1.2% 報酬)</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            # 統計回測數據
            if not trade_log_df.empty and len(trade_log_df[trade_log_df['Action'] == 'SELL']) > 0:
                sells = trade_log_df[trade_log_df['Action'] == 'SELL']
                stock_wins = len(sells[sells['Stock PnL(%)'] > 0])
                opt_wins = len(sells[sells['Opt PnL(%)'] > 0])
                total_trades = len(sells)
                
                stock_win_rate = f"{(stock_wins / total_trades) * 100:.1f}%"
                opt_win_rate = f"{(opt_wins / total_trades) * 100:.1f}%"
                
                stock_pnl = sells['Stock PnL(%)'].sum()
                opt_pnl = sells['Opt PnL(%)'].sum()
            else:
                stock_win_rate, opt_win_rate = "N/A", "N/A"
                stock_pnl, opt_pnl = 0.0, 0.0
            
            st.markdown(f"""
            <div class="metric-card">
                <h4>近兩年策略回測表現</h4>
                <p><b>買現股波段：</b> 總利潤 <span class='profit-text'>{stock_pnl:.1f}%</span> (勝率 {stock_win_rate})</p>
                <p><b>Sell Put 收租：</b> 總利潤 <span class='profit-text'>{opt_pnl:.1f}%</span> (勝率 {opt_win_rate})</p>
                <p style="font-size:0.9em; color:#7F8C8D;">*Sell Put 勝率通常更高，因為即使盤整或小跌(未破履約價)，仍可完整收租。</p>
            </div>
            """, unsafe_allow_html=True)

        # 圖表
        st.markdown("---")
        st.markdown("### 📊 RSI 支撐共振圖表")
        # 只顯示近 200 天讓畫面乾淨
        st.plotly_chart(plot_chart(df_daily.tail(200), f"{ticker_input} - 進出場與動能分析", trade_log_df), use_container_width=True)

        # 交易明細
        st.markdown("### 📝 回測交易與收租明細")
        if not trade_log_df.empty:
            st.dataframe(trade_log_df, use_container_width=True)
            csv = trade_log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 下載交易明細 (CSV)", data=csv, file_name=f'{ticker_input}_rsi_options_log.csv', mime='text/csv')
        else:
            st.write("過去兩年無符合條件之交易訊號。")
