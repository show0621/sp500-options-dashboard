import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# ==========================================
# 網頁與視覺風格設定 (日系文學、極簡留白)
# ==========================================
st.set_page_config(page_title="Alpha 櫻・美股共振展望", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@300;400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Serif TC', serif;
        background-color: #FAFAFA;
        color: #2C3E50;
    }
    h1, h2, h3 {
        color: #34495E;
        font-weight: 300;
        letter-spacing: 2px;
    }
    .stApp {
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
    }
    .metric-card {
        background-color: rgba(255, 255, 255, 0.8);
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
        border-left: 4px solid #85C1E9;
    }
    .signal-buy { color: #E74C3C; font-weight: bold; } /* 股市中紅色通常代表漲 */
    .signal-sell { color: #27AE60; font-weight: bold; }
    .signal-wait { color: #7F8C8D; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 核心運算模組
# ==========================================
@st.cache_data(ttl=3600)
def fetch_data(ticker_symbol):
    """抓取日K與60分K數據，以及基本面籌碼與新聞"""
    ticker = yf.Ticker(ticker_symbol)
    
    # 抓取日K (計算大趨勢與支撐壓力)
    df_daily = ticker.history(period="1y", interval="1d")
    # 抓取60分K (計算短線進場點)
    df_60m = ticker.history(period="1mo", interval="60m")
    
    # 新聞與籌碼 (若有)
    news = ticker.news[:3] if hasattr(ticker, 'news') else []
    inst_holders = ticker.institutional_holders
    
    return df_daily, df_60m, news, inst_holders

def apply_technical_analysis(df):
    """使用原生 Pandas 計算技術指標與形態 (避免雲端套件衝突)"""
    if df.empty or len(df) < 50:
        return df
    
    # 計算 SMA (簡單移動平均)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_60'] = df['Close'].rolling(window=60).mean()
    
    # 計算 MACD
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_12_26_9'] = ema_12 - ema_26
    df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean() # Signal Line
    df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9'] # Histogram
    
    # 計算 RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # 尋找支撐與壓力 (近20週期的高低點)
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()
    
    # 簡單形態辨識 (紅三兵 - 連續三根實體紅K且創新高)
    df['Red_Three_Soldiers'] = (
        (df['Close'] > df['Open']) & 
        (df['Close'].shift(1) > df['Open'].shift(1)) & 
        (df['Close'].shift(2) > df['Open'].shift(2)) &
        (df['Close'] > df['Close'].shift(1)) &
        (df['Close'].shift(1) > df['Close'].shift(2))
    )
    
    return df

def generate_signals(df_daily, df_60m):
    """60K與日K動能共振與策略建議"""
    if df_daily.empty or df_60m.empty:
        return "資料不足", 0, 0, 0, "無", ""

    last_d = df_daily.iloc[-1]
    last_60 = df_60m.iloc[-1]
    
    # 動能判斷
    d_macd_bullish = last_d['MACD_12_26_9'] > last_d['MACDs_12_26_9']
    h_macd_bullish = last_60['MACD_12_26_9'] > last_60['MACDs_12_26_9']
    d_trend_up = last_d['Close'] > last_d['SMA_20']
    
    # 形態判斷
    pattern_msg = "未偵測到特殊形態"
    if last_d['Red_Three_Soldiers']:
        pattern_msg = "出現多頭形態：紅三兵 (強勢看漲)"
    elif last_d['Close'] <= last_d['Support'] * 1.02:
        pattern_msg = "測試底部支撐 (雙底/箱型底潛力)"

    current_price = last_d['Close']
    support = last_d['Support']
    resistance = last_d['Resistance']

    # 綜合建議邏輯
    if d_macd_bullish and h_macd_bullish and d_trend_up:
        action = "多頭共振進場"
        reason = "日K與60K MACD均呈多頭排列，且站上月線。"
    elif not d_macd_bullish and current_price < last_d['SMA_60']:
        action = "空手觀望"
        reason = "長線動能轉弱，跌破季線，建議耐心等待。"
    elif d_macd_bullish and not h_macd_bullish:
        action = "回檔佈局 (Sell Put)"
        reason = "日K多頭但短線60K回檔，適合尋找支撐賣出選擇權收租。"
    else:
        action = "區間震盪"
        reason = "動能分歧，建議區間操作或觀望。"

    return action, current_price, support, resistance, pattern_msg, reason

def plot_chart(df, title):
    """繪製極簡文青風 K線圖"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, row_heights=[0.7, 0.3])

    # K線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name='K線',
                                 increasing_line_color='#E74C3C', decreasing_line_color='#27AE60'),
                  row=1, col=1)
    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#3498DB', width=1.5), name='20MA'), row=1, col=1)
    
    # 支撐壓力線
    fig.add_trace(go.Scatter(x=df.index, y=df['Support'], line=dict(color='#95A5A6', width=1, dash='dot'), name='支撐'), row=1, col=1)

    # MACD
    fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], name='MACD Histogram', marker_color='#BDC3C7'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], line=dict(color='#E74C3C', width=1), name='MACD'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], line=dict(color='#2980B9', width=1), name='Signal'), row=2, col=1)

    fig.update_layout(title=title, xaxis_rangeslider_visible=False,
                      plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                      font=dict(family="Noto Serif TC", size=12, color="#2C3E50"),
                      margin=dict(l=20, r=20, t=50, b=20))
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(200,200,200,0.2)')
    
    return fig

# ==========================================
# 前端 UI 渲染
# ==========================================
st.title("晨光與數據的交匯 ── S&P 500 波段與收租展望")
st.write("靜心觀察日K與60分K的共振脈絡，尋找市場呼吸的節奏。")

with st.sidebar:
    st.header("🔍 標的探索")
    ticker_input = st.text_input("輸入美股代碼 (如 AAPL, NVDA, SPY)", "AAPL").upper()
    st.markdown("---")
    st.write("📖 **策略說明**")
    st.write("本系統尋找大級別(日)與小級別(60分)的動能共振點。並結合賣方選擇權 (Bull Put Spread) 策略，在支撐位建立穩定的現金流。")

if ticker_input:
    with st.spinner('正在從喧囂的市場中擷取數據...'):
        df_daily_raw, df_60m_raw, news_data, inst_holders = fetch_data(ticker_input)
        
    if not df_daily_raw.empty:
        # 使用修正過的原生 Pandas 函數計算
        df_daily = apply_technical_analysis(df_daily_raw.copy())
        df_60m = apply_technical_analysis(df_60m_raw.copy())
        
        action, current_price, support, resistance, pattern_msg, reason = generate_signals(df_daily, df_60m)
        
        # 顯示核心建議儀表板
        st.markdown("### 🧭 今日觀點與決策")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h4>當前股價</h4>
                <h2>${current_price:.2f}</h2>
                <p>近期支撐: ${support:.2f} | 壓力: ${resistance:.2f}</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h4>系統判定</h4>
                <h2 style="color:{'#E74C3C' if '多頭' in action else ('#27AE60' if '空手' in action else '#D35400')}">{action}</h2>
                <p>{pattern_msg}</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            # 選擇權收租策略建議
            put_strike = support * 0.98 # 抓支撐位下方2%作為履約價
            st.markdown(f"""
            <div class="metric-card">
                <h4>現金流策略 (Sell Put)</h4>
                <h2>Strike: ${put_strike:.0f}</h2>
                <p>建議跌至 ${support:.2f} 附近時，賣出履約價 ${put_strike:.0f} 的 Put 建立多頭價差以收取權利金。</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.info(f"**分析語意：** {reason}")
        
        # 繪圖區
        st.markdown("---")
        st.markdown("### 📊 價格脈絡 (日 K 線)")
        st.plotly_chart(plot_chart(df_daily.tail(100), f"{ticker_input} - 日級別趨勢"), use_container_width=True)

        # 籌碼與題材區
        st.markdown("---")
        col_news, col_chips = st.columns([2, 1])
        
        with col_news:
            st.markdown("### 📰 近期題材與市場絮語")
            if news_data:
                for n in news_data:
                    # 使用 .get() 安全地取得資料，避免報錯
                    title = n.get('title', '市場快訊')
                    link = n.get('link', '#')
                    publisher = n.get('publisher', '財經新聞')
                    
                    # 安全處理時間戳記
                    pub_time_raw = n.get('providerPublishTime')
                    time_str = ""
                    if pub_time_raw:
                        formatted_time = datetime.datetime.fromtimestamp(pub_time_raw).strftime('%Y-%m-%d %H:%M')
                        time_str = f" - {formatted_time}"
                        
                    st.markdown(f"**[{title}]({link})**")
                    st.caption(f"{publisher}{time_str}")
            else:
                st.write("目前市場平靜，無特別新聞。")
                
        with col_chips:
            st.markdown("### 💼 籌碼分析 (機構動向)")
            if inst_holders is not None and not inst_holders.empty:
                st.dataframe(inst_holders[['Holder', 'Shares', '% Out']].head(5), hide_index=True)
            else:
                st.write("暫無機構籌碼資料。")
    else:
        st.error("無法尋獲該代碼的軌跡，請確認美股代碼是否正確。")
