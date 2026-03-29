import FinanceDataReader as fdr
import pandas as pd
import requests
import os
import time
import mplfinance as mpf
import matplotlib.pyplot as plt

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
    last, prev = df.iloc[-1], df.iloc[-2]
    
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

def generate_chart(df, ticker, name, is_us=False):
    try:
        # 이평선 계산은 전체 데이터(200일)에서 미리 해두고, 차트만 60일치를 그립니다.
        ma_list = [5, 10, 20, 50, 100] if is_us else [5, 20, 60, 120]
        
        # 각 이평선을 미리 계산해서 df에 넣습니다.
        for p in ma_list:
            df[f'MA{p}'] = df['Close'].rolling(window=p).mean()
            
        # 차트용 데이터는 마지막 60일만 사용 (하지만 이미 이평선은 계산된 상태)
        chart_df = df.tail(60)
        
        filename = f"{ticker}_chart.png"
        
        # 차트 스타일: 한국/미국 주식 구분을 위해 색상을 입힙니다.
        # [5일, 10/20일, 20/60일, 50/120일, 100일] 순서
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        s  = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)
        
        # 핵심: mav 옵션 대신 미리 계산한 컬럼을 넣거나, mav에 리스트를 정확히 전달합니다.
        mpf.plot(chart_df, type='candle', style=s, 
                 mav=tuple(ma_list), # 여기서 선들을 그립니다.
                 mavcolors=colors[:len(ma_list)], # 선 개수만큼 색상 배정
                 title=f"\n{name} ({ticker}) Daily Chart",
                 ylabel='Price', volume=True,
                 savefig=dict(fname=filename, dpi=100, bbox_inches='tight'))
        
        return filename
    except Exception as e:
        print(f"차트 생성 실패 ({ticker}): {e}")
        return None

def send_telegram_with_chart(message, chart_filename):
    """텔레그램으로 차트 이미지와 메시지를 함께 전송합니다."""
    if not TELEGRAM_TOKEN or not CHAT_ID: return
    
    # 1. 차트 이미지 전송 (이미지 먼저 보냄)
    if chart_filename and os.path.exists(chart_filename):
        try:
            url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            with open(chart_filename, 'rb') as photo:
                requests.post(url_photo, data={"chat_id": CHAT_ID}, files={"photo": photo})
            
            # 전송 후 파일 삭제 (서버 용량 관리)
            os.remove(chart_filename)
        except: pass
    
    # 2. 텍스트 메시지 전송 (Markdown 형식 지원)
    url_msg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url_msg, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except: pass

# --- 메인 실행부 ---
final_results = []
print("🔍 관심 종목 정밀 스캔 시작 (차트 생성 포함)...")

for ticker, name, is_us in MY_STOCKS:
    try:
        # 1. 데이터 다운로드
        df = fdr.DataReader(ticker).tail(200)
        
        # 2. 지표 계산
        df['RSI'] = calculate_rsi(df['Close'])
        m20 = df['Close'].rolling(20).mean()
        s20 = df['Close'].rolling(20).std()
        df['ZS'] = (df['Close'] - m20) / s20
        
        # 3. 신호 분석
        last = df.iloc[-1]
        r, z = round(last['RSI'], 1), round(last['ZS'], 2)
        price = round(float(last['Close']), 2)
        ma_info = get_ma_analysis(df, is_us)

        # 4. 차트 이미지 생성
        chart_file = generate_chart(df, ticker, name, is_us)

        # 5. 개별 종목 리포트 메시지 구성
        prefix = f"⚪️ INFO | *{name[:5]:<5}* | {price:>8}"
        if r < 35 and z < -1.5: prefix = f"🔵 BUY  | *{name[:5]:<5}* | {price:>8}"
        elif r > 70 and z > 1.8: prefix = f"🔴 SELL | *{name[:5]:<5}* | {price:>8}"
        
        single_report = f"{prefix} | {ma_info} (R:{r}/Z:{z})"
        
        # 6. 개별 종목 차트와 메시지 즉시 전송
        # (전체 리포트를 한꺼번에 보내는 대신, 차트와 메시지를 짝지어 종목별로 보냅니다.)
        send_telegram_with_chart(single_report, chart_file)
        
        time.sleep(1.0) # 전송 부하 방지
    except Exception as e:
        print(f"에러 발생 ({ticker}): {e}")

print("✅ 모든 관심 종목 스캔 및 전송 완료!")
