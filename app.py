import streamlit as st
import yfinance as yf
import pandas as pd

# 網頁基本設定 (設定為寬螢幕、網頁標題)
st.set_page_config(page_title="美股波段與收租展望", layout="wide")

# 這裡稍微注入一點文青風格的 CSS
st.markdown("""
    <style>
    .main { background-color: #F5F5F7; }
    h1, h2, h3 { color: #1D1D1F; font-family: 'serif'; }
    </style>
    """, unsafe_allow_html=True)

st.title("📈 美股投資展望與選擇權收租")
st.write("這是一個自動化分析 S&P500 波段動能與建構現金流的系統。")

st.divider()

# 測試：抓取股票資料功能
ticker = st.text_input("請輸入美股代號 (例如: AAPL, MSFT, TSLA)", value="AAPL")

if ticker:
    st.subheader(f"目前分析標的：{ticker.upper()}")
    
    # 透過 yfinance 抓取近一個月的日 K 線資料
    with st.spinner('正在從市場抓取最新數據...'):
        data = yf.Ticker(ticker)
        hist = data.history(period="1mo")
        
        if not hist.empty:
            # 只顯示收盤價與成交量，簡化視覺
            display_data = hist[['Close', 'Volume']].tail(5)
            st.write("近五日交易數據：")
            st.dataframe(display_data)
            
            # 畫一個簡單的折線圖
            st.line_chart(hist['Close'])
        else:
            st.error("找不到該股票資料，請確認代號是否正確。")
