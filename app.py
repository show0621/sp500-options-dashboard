請按這個程式碼去新增不要動到其他功能和程式碼還有框架，找不到的部分請幫我重新找回來，可以去尋找這個網頁重新找回來
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
    """三大執行策略平行回測引擎"""
    trade_log = []
    holding = False
    
    # 進場時的變數記錄
    buy_price = 0
    put_strike = 0
    call_strike = 0
    lowest_during_hold = 0
    
    # 權利金參數設定 (基於標的物價值的百分比)
    put_premium_pct = 1.2  # 賣出價外4% Put 約收 1.2%
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
            'Date': df.index[-1].strftime('%Y-%m-%d'), 'Action': 'HOLDING', 'Price': last_price, 'Reason': '目前持倉中 (未實現)', 
            '現股 PnL(%)': round(stock_pnl, 2), 'Sell Put PnL(%)': round(put_pnl, 2), 'Covered Call PnL(%)': round(cc_pnl, 2)
        })
        
    return pd.DataFrame(trade_log)

def plot_chart(df, title, trade_log_df):
    """繪製 K線圖與買賣點"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])

    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線',
                                 increasing_line_color='#E74C3C', decreasing_line_color='#27AE60'), row=1, col=1)
    
    # 繪製布林通道
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(52, 152, 219, 0.2)', width=1), name='布林上軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(52, 152, 219, 0.2)', width=1), fill='tonexty', fillcolor='rgba(52, 152, 219, 0.05)', name='布林下軌'), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#3498DB', width=1.5), name='20MA(中軌)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_60'], line=dict(color='#9B59B6', width=1.5), name='60MA'), row=1, col=1)

    # 標示買賣點位
    if not trade_log_df.empty:
        buys = trade_log_df[trade_log_df['Action'] == 'BUY']
        sells = trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]
        
        fig.add_trace(go.Scatter(x=pd.to_datetime(buys['Date']), y=buys['Price'] * 0.95, mode='markers+text', 
                                 marker=dict(symbol='triangle-up', size=12, color='#E74C3C'), name='買進點', text="買", textposition="bottom center"), row=1, col=1)
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
    
    st.markdown("---")
    st.header("⚙️ 選擇技術分析訊號")
    strategy_choice = st.selectbox(
        "選擇進出場判定邏輯：",
        ("布林通道極限收租", "VCP 形態突破", "MACD 動能共振")
    )
    
    # ---------------- 讀取機器人掃描的推薦名單 (動態過濾版) ----------------
    st.markdown("---")
    st.header("🎯 S&P 500 策略推薦清單")
    st.write(f"以下為符合【{strategy_choice}】條件之潛力標的：")
    
    try:
        if os.path.exists('signals.csv'):
            signals_df = pd.read_csv('signals.csv')
            if not signals_df.empty:
                # 根據下拉選單選擇的策略，動態過濾推薦清單
                if '符合策略' in signals_df.columns:
                    filtered_df = signals_df[signals_df['符合策略'] == strategy_choice]
                else:
                    filtered_df = signals_df
                    
                if not filtered_df.empty:
                    st.dataframe(filtered_df[['代碼', '當前價格', '支撐位 (建議 Sell Put 價)']], hide_index=True)
                    st.caption(f"最後更新日期：{filtered_df.iloc[0]['日期']}")
                    st.info("💡 提示：點擊上方代碼輸入框，即可查看該檔股票的詳細回測與圖表。")
                else:
                    st.write(f"今日無符合【{strategy_choice}】條件之標的。")
            else:
                st.write("今日市場無符合條件之標的。")
        else:
            st.warning("尚未偵測到 `signals.csv`。")
            st.caption("請確認 GitHub Actions 的掃描腳本是否已經成功執行並寫入資料庫。")
    except Exception as e:
        st.error(f"讀取推薦清單時發生錯誤: {e}")
    # --------------------------------------------------------------

# 以下為單檔股票詳細分析與圖表繪製邏輯
if ticker_input:
    with st.spinner('正在從喧囂的市場中擷取數據...'):
        df_daily_raw, df_60m_raw, news_data, inst_holders = fetch_data(ticker_input)
        
    if not df_daily_raw.empty:
        df_daily = apply_technical_analysis(df_daily_raw.copy())
        trade_log_df = run_daily_backtest(df_daily, strategy_choice)
        
        current_price = df_daily.iloc[-1]['Close']
        
        st.markdown(f"### 📊 【{strategy_choice}】訊號下的三大策略回測比較")
        st.write("當系統亮起買進訊號時，我們比較三種不同操作手法的總績效與勝率：")
        
        # 統計三大策略績效
        if not trade_log_df.empty and len(trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]) > 0:
            sells = trade_log_df[trade_log_df['Action'].isin(['SELL', 'HOLDING'])]
            
            # 純現股
            stock_total = sells['現股 PnL(%)'].sum()
            stock_win_rate = (len(sells[sells['現股 PnL(%)'] > 0]) / len(sells)) * 100
            
            # Sell Put
            put_total = sells['Sell Put PnL(%)'].sum()
            put_win_rate = (len(sells[sells['Sell Put PnL(%)'] > 0]) / len(sells)) * 100
            
            # Covered Call
            cc_total = sells['Covered Call PnL(%)'].sum()
            cc_win_rate = (len(sells[sells['Covered Call PnL(%)'] > 0]) / len(sells)) * 100
        else:
            stock_total, stock_win_rate, put_total, put_win_rate, cc_total, cc_win_rate = 0, 0, 0, 0, 0, 0

        # 三欄式呈現比較
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h4>📈 1. 純買現股 (Buy & Hold)</h4>
                <h2>總利潤: {stock_total:.2f}%</h2>
                <p>歷史勝率: <b>{stock_win_rate:.1f}%</b></p>
                <p style="font-size: 0.85em; color: gray;">完全承擔漲跌幅，大漲時利潤最高，下跌時無防護。</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h4>🛡️ 2. 賣出賣權 (Sell Put)</h4>
                <h2>總利潤: {put_total:.2f}%</h2>
                <p>歷史勝率: <b>{put_win_rate:.1f}%</b></p>
                <p style="font-size: 0.85em; color: gray;">空手收租。防禦力最強，只要不暴跌都能賺取固定權利金。</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h4>⚖️ 3. 掩護性買權 (Covered Call)</h4>
                <h2>總利潤: {cc_total:.2f}%</h2>
                <p>歷史勝率: <b>{cc_win_rate:.1f}%</b></p>
                <p style="font-size: 0.85em; color: gray;">持有股票並賣出買權。降低持股成本，但犧牲大漲時的尾部利潤。</p>
            </div>
            """, unsafe_allow_html=True)

        # K線圖
        st.markdown("---")
        st.markdown("### 📉 價格脈絡與買賣點標示")
        st.plotly_chart(plot_chart(df_daily.tail(150), f"{ticker_input} - 歷史交易點位", trade_log_df), use_container_width=True)

        # 交易明細
        st.markdown("### 📝 回測交易明細")
        if not trade_log_df.empty:
            st.dataframe(trade_log_df, use_container_width=True)
            csv = trade_log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 下載完整回測明細 (CSV)", data=csv, file_name=f'{ticker_input}_strategy_comparison.csv', mime='text/csv')
        else:
            st.write("過去一年無符合條件之交易訊號。")
            
        # 籌碼與題材區
        st.markdown("---")
        col_news, col_chips = st.columns([1, 1])
        
        with col_news:
            st.markdown("### 📰 近期題材與市場絮語")
            if news_data:
                for n in news_data:
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
                top_inst_pct = inst_holders['pctHeld'].sum()
                retail_pct = 1 - top_inst_pct
                sentiment = "偏多 (機構近期加碼)" if inst_holders['pctChange'].mean() > 0 else "偏空 (機構近期減碼)"
                st.info(f"📊 **籌碼推算：** 前幾大機構掌控約 **{top_inst_pct:.1%}**，散戶約佔 **{retail_pct:.1%}**。整體法人動向：**{sentiment}**")
                expected_cols = ['Holder', 'pctHeld', 'Shares', 'pctChange']
                display_df = inst_holders[expected_cols] if set(expected_cols).issubset(inst_holders.columns) else inst_holders
                st.dataframe(display_df.head(5), hide_index=True)
            else:
                st.write("暫無機構籌碼資料，或資料結構變更。")
    else:
        st.error("無法尋獲該代碼的軌跡，請確認美股代碼是否正確。")
