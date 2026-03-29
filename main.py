import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import requests
import os
import time

# --- 환경 설정 ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

MY_STOCKS = [
    ('TSLA', '테슬라', True),
    ('RKLB', '로켓랩', True),
    ('LITE', '루멘텀', True),
    ('445680', '큐리옥스바이오', False)
]

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_ma_analysis(df, is_us=False):
    msgs = []
    ma_list = [5, 10, 20, 50, 100] if is_us else [5, 20, 60, 120]
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    ma_values = {}
    for p in ma_list:
        ma = df['Close'].rolling(p).mean()
        m_val, p_m_val = ma.iloc[-1], ma.iloc[-2]
        ma_values[p] = (m_val, p_m_val)
        
        if prev['Close'] > p_m_val and last['Close'] < m_val: msgs.append(f"⚠️{p}선이탈")
        elif abs(last['Close'] - m_val) / m_val < 0.012: msgs.append(f"⚓{p}선지지")

    fast, slow = (5, 20) if not is_us else (20, 50)
    if fast in ma_values and slow in ma_values:
        f_l, f_p = ma_values[fast][0], ma_values[fast][1]
        s_l, s_p = ma_values[slow][0], ma_values[slow][1]
        if f_p < s_p and f_l > s_l: msgs.append(f"🚀골든({fast}/{slow})")
        elif f_p > s_p and f_l < s_l: msgs.append(f"💀데드({fast}/{slow})")
    return " | ".join(msgs) if msgs else ""

def get_signals(ticker, name, is_us=False):
    try:
        df = fdr.DataReader(ticker).tail(200)
        df['RSI'] = calculate_rsi(df['Close'])
        # Z-Score 직접 계산
        m20 = df['Close'].rolling(20).mean()
        s20 = df['Close'].rolling(20).std()
        df['ZS'] = (df['Close'] - m20) / s20
        
        last = df.iloc[-1]
        r, z = round(last['RSI'], 1), round(last['ZS'], 2)
        price = round(float(last['Close']), 2)
        ma_info = get_ma_analysis(df, is_us)

        res = ""
        if r < 35 and z < -1.5: res = f"🔵 BUY  | {name[:5]:<5} | {price:>8}"
        elif r > 70 and z > 1.8: res = f"🔴 SELL | {name[:5]:<5} | {price:>8}"
        
        prefix = res if res else f"⚪️ INFO | {name[:5]:<5} | {price:>8}"
        return f"{prefix} | {ma_info} (R:{r}/Z:{z})"
    except: return None

# --- 실행 및 전송 ---
final_results = []
for ticker, name, is_us in MY_STOCKS:
    out = get_signals(ticker, name, is_us)
    if out: final_results.append(out)
    time.sleep(0.5)

if final_results:
    report = "📑 *관심 종목 정밀 리포트*\n" + "-"*30 + "\n" + "\n".join(final_results)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": report, "parse_mode": "Markdown"})
