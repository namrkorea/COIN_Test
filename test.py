import streamlit as st  # Streamlit 라이브러리 추가
import pyupbit
import time
import datetime
import requests
import schedule
import math

# ==========================================
# [1] Streamlit UI 및 IP 확인 (업비트 등록용)
# ==========================================
st.set_page_config(page_title="코인단타 자동매매", page_icon="📈")
st.title("📈 코인단타 자동매매 서버 정보")

try:
    # 현재 Streamlit 서버의 외부 IP 확인
    curr_ip = requests.get("https://api.ipify.org").text
    st.info(f"🌐 현재 서버 IP: **{curr_ip}**")
    st.write("위 IP 주소를 **업비트 API 관리 페이지**에 등록해야 매매가 가능합니다.")
except Exception as e:
    st.error(f"IP 확인 중 오류 발생: {e}")

# ==========================================
# [사용자 설정 구역] 본인의 키를 입력하세요
# ==========================================
# 보안을 위해 Secrets 사용 권장 (st.secrets["키이름"] 방식)
access = "UGnMADUZxRAuuA4MMLwMRUaEDOZ7xdgpBcDaDS8T"
secret = "UWJ1GYQQoNIWOgq5zuSR9OC7Q7t4ng6blp1bB8pe"
discord_url = "https://discord.com/api/webhooks/1446199475319079127/zf_qXtKYH04cCgVZYbPT5_J119B0a97pYzcm9bQucbSNfkGYKAnFAG_4d8Dmbm1roHP8"

# ------------------------------------------
# [전략 설정 변경]
# ------------------------------------------
K_VALUE = 0.5            # 변동성 돌파 계수
STOP_LOSS_PCT = 0.03     # 🚨 손절매 기준 (-3%)
MAX_HOLDINGS = 5         # ✅ 최대 보유 종목 수 (5개 꽉 채우기)
MAX_BUY_AMOUNT = 19000   # 1회 최대 매수 한도 금액
CANDIDATE_SIZE = 20      # 감시할 후보군 크기 (상위 20개)

# 업비트 객체 생성
upbit = pyupbit.Upbit(access, secret)

# ==========================================
# [기능 함수 정의]
# ==========================================

def send_discord(msg):
    try:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"[{now}] {msg}"
        print(message)
        requests.post(discord_url, json={"content": message})
    except Exception as e:
        print(f"디스코드 전송 실패: {e}")

def get_top_candidates(limit=20):
    try:
        tickers = pyupbit.get_tickers("KRW")
        url = "https://api.upbit.com/v1/ticker"
        params = {"markets": ",".join(tickers)}
        response = requests.get(url, params=params).json()
        
        sorted_coins = sorted(response, key=lambda x: x['acc_trade_price_24h'], reverse=True)
        top_coins = [x['market'] for x in sorted_coins[:limit]]
        return top_coins
    except Exception as e:
        send_discord(f"⚠️ 종목 선정 중 에러: {e}")
        return ["KRW-BTC"]

def get_target_price(ticker):
    try:
        df = pyupbit.get_ohlcv(ticker, interval="day", count=2)
        if df is None or len(df) < 2: return None
        yesterday = df.iloc[-2]
        today_open = df.iloc[-1]['open']
        
        volatility_range = yesterday['high'] - yesterday['low']
        target = today_open + (volatility_range * K_VALUE)
        return target
    except Exception as e:
        return None

def get_my_coins():
    try:
        balances = upbit.get_balances()
        if balances is None: return []
        my_coins = []
        for b in balances:
            if b['currency'] != "KRW":
                ticker = f"KRW-{b['currency']}"
                if float(b['avg_buy_price']) * float(b['balance']) > 5000:
                    my_coins.append(ticker)
        return my_coins
    except:
        return []

def sell_all():
    try:
        balances = upbit.get_balances()
        if balances is None: return
        for b in balances:
            if b['currency'] != "KRW":
                coin_name = f"KRW-{b['currency']}"
                amount = float(b['balance'])
                current_price = pyupbit.get_current_price(coin_name)
                
                if current_price and (current_price * amount > 5000):
                    upbit.sell_market_order(coin_name, amount)
                    time.sleep(0.2)
        send_discord("🌅 09:00 전량 매도 완료. 리셋.")
    except Exception as e:
        send_discord(f"매도 중 에러: {e}")

# [수정됨] 잔고 None 에러 방지 로직 추가
def calculate_buy_amount(current_holding_count, krw_balance):
    if krw_balance is None: # 업비트 서버 응답 지연 대비
        return 0
        
    remaining_slots = MAX_HOLDINGS - current_holding_count
    if remaining_slots <= 0:
        return 0
    
    amount_per_slot = (float(krw_balance) * 0.999) / remaining_slots
    final_amount = min(amount_per_slot, MAX_BUY_AMOUNT)
    
    if final_amount < 5100: 
        return 0
    return final_amount

# ==========================================
# [메인 로직]
# ==========================================
if st.button('🚀 봇 가동 시작'):
    send_discord(f"🤖 [봇 V2.8] 가동! (최대 {MAX_HOLDINGS}종목 / 후보군 20개 감시)")

    # 초기 리포트 및 세팅
    try:
        candidates = get_top_candidates(CANDIDATE_SIZE)
        target_prices = {coin: get_target_price(coin) for coin in candidates if get_target_price(coin)}
        send_discord(f"📌 상위 {CANDIDATE_SIZE}개 종목 모니터링 시작")
    except Exception as e:
        st.error(f"초기화 에러: {e}")

    #

