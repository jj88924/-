import FinanceDataReader as fdr
import pandas_ta as ta
import requests
import os
import time

# --- 1. 환경 설정 (GitHub Secrets 연동) ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

# --- 2. 관심 종목 리스트 ---
MY_STOCKS = [
    ('TSLA', '테슬라', True),
    ('RKLB', '로켓랩', True),
    ('LITE', '루멘텀', True),
    ('445680', '큐리옥스바이오', False)
]

def send_telegram_msg(message):
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except: pass

def get_ma_analysis(df, is_us=False):
    msgs = []
    last, prev = df.iloc[-1], df.iloc[-2]
    ma_list = [5, 10, 20, 50, 100] if is_us else [5, 20, 60, 120]
    ma_data = {p: df['Close'].rolling(p).mean() for p in ma_list}

    for p in ma_list:
        if len(ma_data[p]) < 2 or ma_data[p].isnull().iloc[-1]: continue
        m_val, p_m_val = ma_data[p].iloc[-1], ma_data[p].iloc[-2]
        if prev['Close'] > p_m_val and last['Close'] < m_val: msgs.append(f"⚠️{p}선이탈")
        elif abs(last['Close'] - m_val) / m_val < 0.012: msgs.append(f"⚓{p}선지지")

    fast, slow = (5, 20) if not is_us else (20, 50)
    if all(p in ma_data for p in [fast, slow]):
        f_l, f_p = ma_data[fast].iloc[-1], ma_data[fast].iloc[-2]
        s_l, s_p = ma_data[slow].iloc[-1], ma_data[slow].iloc[-2]
        if f_p < s_p and f_l > s_l: msgs.append(f"🚀골든({fast}/{slow})")
        elif f_p > s_p and f_l < s_l: msgs.append(f"💀데드({fast}/{slow})")
    return " | ".join(msgs) if msgs else ""

def get_signals(ticker, name, is_us=False):
    try:
        df = fdr.DataReader(ticker).tail(200)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['MFI'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
        adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
        df['ADX'] = adx_df['ADX_14']
        m = df['Close'].rolling(20).mean(); s = df['Close'].rolling(20).std()
        df['ZS'] = (df['Close'] - m) / s
        
        last = df.iloc[-1]
        r, m_val, z, a = round(last['RSI'],1), round(last['MFI'],1), round(last['ZS'],2), round(last['ADX'],1)
        price = round(float(last['Close']), 0) if not is_us else round(float(last['Close']), 2)
        ma_info = get_ma_analysis(df, is_us)

        res = ""
        if r < 35 and m_val < 30 and z < -1.5: res = f"🔵 BUY  | {name[:5]:<5} | {price:>8}"
        elif r > 70 and m_val > 80 and z > 1.8 and a > 30: res = f"🔴 SELL | {name[:5]:<5} | {price:>8}"
        
        prefix = res if res else f"⚪️ INFO | {name[:5]:<5} | {price:>8}"
        return f"{prefix} | {ma_info} (R:{r}/Z:{z})"
    except: return None

final_results = []
for ticker, name, is_us in MY_STOCKS:
    out = get_signals(ticker, name, is_us)
    if out: final_results.append(out)
    time.sleep(0.5)

if final_results:
    report = "📑 *관심 종목 정밀 리포트*\n" + "-"*30 + "\n" + "\n".join(final_results)
    send_telegram_msg(report)
