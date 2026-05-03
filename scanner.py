import yfinance as yf
import pandas as pd
import datetime
import os
import requests  # 用來處理偽裝瀏覽器的請求

# 1. 獲取 S&P 500 股票代碼
def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    
    # 加上 headers，偽裝成正常的 Windows Chrome 瀏覽器，避免被維基百科阻擋
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # 先用 requests 抓取網頁原始碼，再丟給 pandas 解析
    response = requests.get(url, headers=headers)
    table = pd.read_html(response.text)[0]
    
    tickers = table['Symbol'].tolist()
    # 替換掉 Yahoo Finance 不吃的特殊符號 (如 BRK.B 變成 BRK-B)
    tickers = [t.replace('.', '-') for t in tickers]
    return tickers

# 2. 技術分析邏輯 (升級：同時檢查三大策略)
def check_all_signals(df_daily, df_60m):
    signals = []
    
    if df_daily.empty or len(df_daily) < 25:
        return signals, 0, 0
    
    # --- 計算日K指標 ---
    df_daily['SMA_20'] = df_daily['Close'].rolling(window=20).mean()
    df_daily['SMA_60'] = df_daily['Close'].rolling(window=60).mean()
    df_daily['Vol_SMA_20'] = df_daily['Volume'].rolling(window=20).mean()
    
    # MACD
    ema_12 = df_daily['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df_daily['Close'].ewm(span=26, adjust=False).mean()
    df_daily['MACD'] = ema_12 - ema_26
    df_daily['MACD_Signal'] = df_daily['MACD'].ewm(span=9, adjust=False).mean()
    
    # 布林通道 (BB)
    df_daily['BB_Mid'] = df_daily['Close'].rolling(window=20).mean()
    df_daily['BB_Std'] = df_daily['Close'].rolling(window=20).std()
    df_daily['BB_Lower'] = df_daily['BB_Mid'] - (df_daily['BB_Std'] * 2)
    
    df_daily['Resistance'] = df_daily['High'].rolling(window=20).max()
    
    last_d = df_daily.iloc[-1]
    prev_d = df_daily.iloc[-2]
    current_price = last_d['Close']
    
    # 預設支撐點位
    support_price = last_d['BB_Lower'] if last_d['BB_Lower'] > 0 else current_price * 0.96

    # ---------------------------------------------
    # 策略 1：MACD 動能共振 (保留你原本的 日K + 60K 邏輯)
    # ---------------------------------------------
    if not df_60m.empty and len(df_60m) >= 26:
        # 計算60K指標
        ema_12_60 = df_60m['Close'].ewm(span=12, adjust=False).mean()
        ema_26_60 = df_60m['Close'].ewm(span=26, adjust=False).mean()
        macd_60 = ema_12_60 - ema_26_60
        macd_sig_60 = macd_60.ewm(span=9, adjust=False).mean()
        
        d_macd_bullish = last_d['MACD'] > last_d['MACD_Signal']
        h_macd_bullish = macd_60.iloc[-1] > macd_sig_60.iloc[-1]
        d_trend_up = current_price > last_d['SMA_20']
        
        if d_macd_bullish and h_macd_bullish and d_trend_up:
            signals.append("MACD 動能共振")

    # ---------------------------------------------
    # 策略 2：VCP 形態突破
    # ---------------------------------------------
    pivot = prev_d['Resistance']
    vcp_breakout = (current_price > pivot) and (last_d['Volume'] > 1.2 * last_d['Vol_SMA_20']) and (current_price > last_d['SMA_60'])
    
    if vcp_breakout:
        signals.append("VCP 形態突破")

    # ---------------------------------------------
    # 策略 3：布林通道極限收租
    # ---------------------------------------------
    is_uptrend = last_d['SMA_20'] > last_d['SMA_60']
    touch_lower = last_d['Low'] <= last_d['BB_Lower']
    
    if is_uptrend and touch_lower:
        signals.append("布林通道極限收租")

    return signals, current_price, support_price

# 3. 執行全市場掃描並存檔
def run_scanner():
    print("開始掃描 S&P 500 (三大策略)...")
    tickers = get_sp500_tickers()
    
    # 【注意】目前設定掃描全部 S&P500 股票。
    tickers_to_scan = tickers 
    
    buy_list = []
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    for ticker in tickers_to_scan:
        try:
            print(f"正在分析: {ticker}")
            data = yf.Ticker(ticker)
            df_daily = data.history(period="6mo", interval="1d")
            df_60m = data.history(period="1mo", interval="60m")
            
            signals, price, support = check_all_signals(df_daily, df_60m)
            
            # 只要有符合任何策略，就把它加入清單
            for strategy in signals:
                buy_list.append({
                    '代碼': ticker,
                    '符合策略': strategy,  # 這裡新增了策略欄位給網頁過濾用
                    '當前價格': round(price, 2),
                    '支撐位 (建議 Sell Put 價)': round(support, 2),
                    '日期': date_str
                })
        except Exception as e:
            print(f"{ticker} 抓取失敗: {e}")
            
    # 將結果存成 CSV
    df_result = pd.DataFrame(buy_list)
    df_result.to_csv('signals.csv', index=False, encoding='utf-8-sig')
    print(f"掃描完成！共發現 {len(buy_list)} 個符合條件的交易機會，已儲存至 signals.csv")

if __name__ == "__main__":
    run_scanner()
