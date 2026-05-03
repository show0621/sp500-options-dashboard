import yfinance as yf
import pandas as pd
import datetime
import os

# 1. 獲取 S&P 500 股票代碼
def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    table = pd.read_html(url)[0]
    tickers = table['Symbol'].tolist()
    # 替換掉 Yahoo Finance 不吃的特殊符號
    tickers = [t.replace('.', '-') for t in tickers]
    return tickers

# 2. 技術分析邏輯 (與我們網頁上的相同)
def check_buy_signal(df_daily, df_60m):
    if df_daily.empty or df_60m.empty or len(df_daily) < 20:
        return False, 0, 0
    
    # 計算日K指標
    df_daily['SMA_20'] = df_daily['Close'].rolling(window=20).mean()
    ema_12 = df_daily['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df_daily['Close'].ewm(span=26, adjust=False).mean()
    df_daily['MACD'] = ema_12 - ema_26
    df_daily['MACD_Signal'] = df_daily['MACD'].ewm(span=9, adjust=False).mean()
    
    # 計算60K指標
    ema_12_60 = df_60m['Close'].ewm(span=12, adjust=False).mean()
    ema_26_60 = df_60m['Close'].ewm(span=26, adjust=False).mean()
    df_60m['MACD'] = ema_12_60 - ema_26_60
    df_60m['MACD_Signal'] = df_60m['MACD'].ewm(span=9, adjust=False).mean()
    
    last_d = df_daily.iloc[-1]
    last_60 = df_60m.iloc[-1]
    
    # 多頭共振條件：日K MACD 大於訊號線 + 日K 站上月線 + 60K MACD 大於訊號線
    d_macd_bullish = last_d['MACD'] > last_d['MACD_Signal']
    h_macd_bullish = last_60['MACD'] > last_60['MACD_Signal']
    d_trend_up = last_d['Close'] > last_d['SMA_20']
    
    if d_macd_bullish and h_macd_bullish and d_trend_up:
        support = df_daily['Low'].rolling(window=20).min().iloc[-1]
        return True, last_d['Close'], support
    return False, 0, 0

# 3. 執行全市場掃描並存檔
def run_scanner():
    print("開始掃描 S&P 500...")
    tickers = get_sp500_tickers()
    
    # 為了避免被 Yahoo 封鎖，這裡先設定只抓前 50 檔做測試，你可以拿掉 [:50] 掃描全部
    tickers_to_scan = tickers[:50] 
    
    buy_list = []
    
    for ticker in tickers_to_scan:
        try:
            print(f"正在分析: {ticker}")
            data = yf.Ticker(ticker)
            df_daily = data.history(period="6mo", interval="1d")
            df_60m = data.history(period="1mo", interval="60m")
            
            # 這裡可以加入將 df_60m 存入本地 CSV 累積的邏輯
            # 例如: df_60m.to_csv(f"data/{ticker}_60m.csv", mode='a')
            
            is_buy, price, support = check_buy_signal(df_daily, df_60m)
            
            if is_buy:
                buy_list.append({
                    '代碼': ticker,
                    '當前價格': round(price, 2),
                    '支撐位 (建議 Sell Put 價)': round(support, 2),
                    '訊號': '多頭共振',
                    '日期': datetime.datetime.now().strftime('%Y-%m-%d')
                })
        except Exception as e:
            print(f"{ticker} 抓取失敗: {e}")
            
    # 將結果存成 CSV 給 Streamlit 讀取
    df_result = pd.DataFrame(buy_list)
    df_result.to_csv('signals.csv', index=False, encoding='utf-8-sig')
    print(f"掃描完成！共發現 {len(buy_list)} 檔符合條件標的，已儲存至 signals.csv")

if __name__ == "__main__":
    run_scanner()
