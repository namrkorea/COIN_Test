import streamlit as st
import pyupbit
import time
import datetime
import requests

# ==========================================
# [1] Streamlit UI 및 IP 확인
# ==========================================
st.set_page_config(page_title="코인단타 자동매매", page_icon="📈")
st.title("📈 코인단타 자동매매 시스템")

try:
    # 현재 서버 IP 확인 (업비트 등록용)
    curr_ip = requests.get("https://api.ipify.org").text
    st.info(f"🌐 현재 서버 IP: **{curr_ip}**")
    st.caption("위 주소를 업비트 API 관리 페이지 'IP 주소 등록'에 복사해 넣으세요.")
except:
    st.error("IP 확인 불가")

# ==========================================
# [2] 보안 설정 (Streamlit Secrets 연동)
# ==========================================
# 설정 방법: Streamlit Cloud -> Settings -> Secrets에 아래 키값을 입력하세요.
try:
    access = st.secrets["upbit_access"]
    secret = st.secrets["upbit_secret"]
    discord_url = st.secrets["discord_webhook"]
    
    # 업비트 객체 생성
    upbit = pyupbit.Upbit(access, secret)
    st.success("✅ 보안 키 로드 완료")
except Exception as e:
    st.error("❌ Secrets 설정이 필요합니다. Streamlit 설정을 확인하세요.")
    st.stop()

# ------------------------------------------
# [전략 설정 변경]
# ------------------------------------------
K_VALUE = 0.5            # 변동성 돌파 계수
STOP_LOSS_PCT = 0.03     # 손절매 기준 (-3%)
MAX_HOLDINGS = 5         # 최대 보유 종목 수
MAX_BUY_AMOUNT = 19000   # 1회 최대 매수 한도
CANDIDATE_SIZE = 20      # 감시 종목 수

# ==========================================
# [3] 기능 함수 정의
# ==========================================

def send_discord(msg):
    try:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        requests.post(discord_url, json={"content": f"[{now}] {msg}"})
    except:
        pass

def get_top_candidates(limit=20):
    try:
        tickers = pyupbit.get_tickers("KRW")
        url = "https://api.ipify.org" # IP 체크용
        resp = requests.get("https://api.upbit.com/v1/ticker", params={"markets": ",".join(tickers)}).json()
        sorted_coins = sorted(resp, key=lambda x: x['acc_trade_price_24h'], reverse=True)
        return [x['market'] for x in sorted_coins[:limit]]
    except:
        return ["KRW-BTC", "KRW-ETH"]

def get_target_price(ticker):
    try:
        df = pyupbit.get_ohlcv(ticker, interval="day", count=2)
        if df is None or len(df) < 2: return None
        yesterday = df.iloc[-2]
        today_open = df.iloc[-1]['open']
        return today_open + ((yesterday['high'] - yesterday['low']) * K_VALUE)
    except:
        return None

def get_my_coins():
    try:
        balances = upbit.get_balances()
        if balances is None: return []
        return [f"KRW-{b['currency']}" for b in balances if b['currency'] != "KRW" and float(b['avg_buy_price']) * float(b['balance']) > 5000]
    except:
        return []

def sell_all():
    try:
        balances = upbit.get_balances()
        if balances:
            for b in balances:
                if b['currency'] != "KRW":
                    coin = f"KRW-{b['currency']}"
                    amount = upbit.get_balance(coin)
                    if pyupbit.get_current_price(coin) * amount > 5000:
                        upbit.sell_market_order(coin, amount)
                        time.sleep(0.2)
        send_discord("🌅 09:00 전량 매도 및 리셋 완료.")
    except Exception as e:
        send_discord(f"매도 에러: {e}")

def calculate_buy_amount(current_holding_count, krw_balance):
    if krw_balance is None: return 0
    remaining = MAX_HOLDINGS - current_holding_count
    if remaining <= 0: return 0
    amount = (float(krw_balance) * 0.999) / remaining
    return min(amount, MAX_BUY_AMOUNT) if amount >= 5000 else 0

# ==========================================
# [4] 실행 루프
# ==========================================
if st.button('🚀 자동매매 가동 시작'):
    send_discord("🤖 [V3.0] 보안 모드 가동 시작!")
    
    # 초기 세팅
    candidates = get_top_candidates(CANDIDATE_SIZE)
    target_prices = {coin: get_target_price(coin) for coin in candidates if get_target_price(coin)}
    
    st.write("📊 모니터링 중... 디스코드 알림을 확인하세요.")

    while True:
        try:
            now = datetime.datetime.now()

            # 09:00 리셋
            if now.hour == 9 and now.minute == 0 and now.second <= 10:
                sell_all()
                candidates = get_top_candidates(CANDIDATE_SIZE)
                target_prices = {coin: get_target_price(coin) for coin in candidates if get_target_price(coin)}
                time.sleep(11)

            my_coins = get_my_coins()
            krw_balance = upbit.get_balance("KRW")

            # A. 손절매 체크
            for coin in my_coins:
                curr = pyupbit.get_current_price(coin)
                avg = upbit.get_avg_buy_price(coin)
                if curr and avg and (curr - avg) / avg <= -STOP_LOSS_PCT:
                    upbit.sell_market_order(coin, upbit.get_balance(coin))
                    send_discord(f"⛔ {coin} 손절 완료 (-3%)")

            # B. 매수 체크
            if len(my_coins) < MAX_HOLDINGS:
                buy_amount = calculate_buy_amount(len(my_coins), krw_balance)
                if buy_amount >= 5000:
                    for coin in candidates:
                        if coin in my_coins: continue
                        target = target_prices.get(coin)
                        curr = pyupbit.get_current_price(coin)
                        if target and curr and curr >= target:
                            upbit.buy_market_order(coin, buy_amount)
                            send_discord(f"🚀 {coin} 돌파 매수 완료!")
                            break 
            
            time.sleep(2)

        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(10)
