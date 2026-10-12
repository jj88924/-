import os
import time
import requests
import pandas as pd
import FinanceDataReader as fdr

# Headless 환경 설정 (GUI 에러 방지)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf

# --- 환경 설정 ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

MY_STOCKS = [
    # 미국 주식
    ('GEV', 'GE버노바', True),
    ('SMR', '뉴스케일파워', True),
    ('SOXL', 'SOXL(3배레버리지)', True),
    ('NVDA', '엔비디아', True),
    ('INTC', '인텔', True),
    ('WDC', '웨스턴디지털', True),
    ('MU', '마이크론', True),
    ('LITE', '루멘텀', True),
    ('TSLA', '테슬라', True),
    # 한국 주식
    ('007660', '이수페타시스', False),
    ('141080', '리가켐바이오', False),
    ('402340', 'SK스퀘어', False),
    ('454910', '두산로보틱스', False),
    ('464190', '에스오에스랩', False),
    ('000660', 'SK하이닉스', False),
    ('035420', '네이버', False),
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
    last, prev = df.iloc[-1], df.iloc[-2]
    
    ma_values = {}
    for p in ma_list:
        ma = df['Close'].rolling(p).mean()
        m_val, p_m_val = ma.iloc[-1], ma.iloc[-2]
        ma_values[p] = (m_val, p_m_val)
        
        if prev['Close'] > p_m_val and last['Close'] < m_val:
            msgs.append(f"⚠️{p}선이탈")
        elif abs(last['Close'] - m_val) / m_val < 0.012:
            msgs.append(f"⚓{p}선지지")

    fast, slow = (5, 20) if not is_us else (20, 50)
    if fast in ma_values and slow in ma_values:
        f_l, f_p = ma_values[fast][0], ma_values[fast][1]
        s_l, s_p = ma_values[slow][0], ma_values[slow][1]
        if f_p < s_p and f_l > s_l:
            msgs.append(f"🚀골든({fast}/{slow})")
        elif f_p > s_p and f_l < s_l:
            msgs.append(f"💀데드({fast}/{slow})")
    return " | ".join(msgs) if msgs else ""

def generate_chart(df, ticker, name, is_us=False):
    try:
        ma_list = [5, 10, 20, 50, 100] if is_us else [5, 20, 60, 120]
        added_plots = []
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        for p in ma_list:
            df[f'MA{p}'] = df['Close'].rolling(window=p).mean()
        
        chart_df = df.tail(60)
        
        for i, p in enumerate(ma_list):
            ap = mpf.make_addplot(chart_df[f'MA{p}'], color=colors[i], width=1.0)
            added_plots.append(ap)
            
        filename = f"{ticker}_chart.png"
        
        mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)
        
        # 리눅스 한글 폰트 미설치 시 글자 깨짐 방지를 위해 ticker 위주 표시
        mpf.plot(chart_df, type='candle', style=s, 
                 addplot=added_plots,
                 title=f"\n{ticker} Daily Chart",
                 ylabel='Price', volume=True,
                 savefig=dict(fname=filename, dpi=100, bbox_inches='tight'))
        plt.close('all')  # 메모리 누수 방지
        return filename
    except Exception as e:
        print(f"차트 생성 실패 ({ticker}): {e}")
        return None

def send_telegram_with_chart(message, chart_filename):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram Token 또는 Chat ID가 설정되지 않았습니다.")
        return
    
    # 1. 차트 이미지 전송
    if chart_filename and os.path.exists(chart_filename):
        try:
            url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            with open(chart_filename, 'rb') as photo:
                res = requests.post(url_photo, data={"chat_id": CHAT_ID}, files={"photo": photo})
                if res.status_code != 200:
                    print(f"사진 전송 오류: {res.text}")
            os.remove(chart_filename)
        except Exception as e:
            print(f"사진 전송 예외 발생: {e}")
    
    # 2. 텍스트 메시지 전송 (마크다운 파싱 오류를 피하기 위해 일반 텍스트 전송)
    url_msg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url_msg, json={"chat_id": CHAT_ID, "text": message})
        if res.status_code != 200:
            print(f"메시지 전송 오류: {res.text}")
    except Exception as e:
        print(f"메시지 전송 예외 발생: {e}")

# --- 메인 실행부 ---
print("🔍 관심 종목 정밀 스캔 시작...")

for ticker, name, is_us in MY_STOCKS:
    try:
        df = fdr.DataReader(ticker).tail(200)
        if df.empty or len(df) < 60:
            print(f"데이터 부족으로 건너뜀: {ticker}")
            continue

        df['RSI'] = calculate_rsi(df['Close'])
        m20 = df['Close'].rolling(20).mean()
        s20 = df['Close'].rolling(20).std()
        df['ZS'] = (df['Close'] - m20) / s20
        
        last = df.iloc[-1]
        r, z = round(last['RSI'], 1), round(last['ZS'], 2)
        price = round(float(last['Close']), 2)
        ma_info = get_ma_analysis(df, is_us)

        chart_file = generate_chart(df, ticker, name, is_us)

        prefix = f"⚪️ INFO | {name} | {price}"
        if r < 35 and z < -1.5:
            prefix = f"🔵 BUY  | {name} | {price}"
        elif r > 70 and z > 1.8:
            prefix = f"🔴 SELL | {name} | {price}"
        
        single_report = f"{prefix} | {ma_info} (R:{r}/Z:{z})"
        send_telegram_with_chart(single_report, chart_file)
        
        time.sleep(1.0)
    except Exception as e:
        print(f"에러 발생 ({ticker}): {e}")

print("✅ 모든 관심 종목 스캔 및 전송 완료!")
