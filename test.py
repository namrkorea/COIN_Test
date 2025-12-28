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
    curr_ip = requests.get("https://api.ipify.org", timeout=5).text
    st.info(f"🌐 현재 서버 IP: **{curr_ip}**")
    st.caption("위 주소를 업비트 API 관리 페이지 'IP 주소 등록'에 복사해 넣으세요.")
except:
    st.error("IP 확인 불가")

# ==========================================
# [2] 보안 설정 (Streamlit Secrets 연동)
# ==========================================
try:
    access = st.secrets["upbit_access"]
    secret = st.secrets["upbit_secret"]
    discord_url = st.secrets["discord_webhook"]

    upbit = pyupbit.Upbit(access, secret)
    st.success("✅ 보안 키 로드 완료")
except Exception:
    st.error("❌ Secrets 설정이 필요합니다. Streamlit 설정을 확인하세요.")
    st.stop()

# ------------------------------------------
# [전략 설정]
# ------------------------------------------
K_VALUE = 0.5            # 변동성 돌파 계수
STOP_LOSS_PCT = 0.03     # 손절매 기준 (-3%)
MAX_HOLDINGS = 5         # 최대 보유 종목 수
MAX_BUY_AMOUNT = 19000   # 1회 최대 매수 한도
CANDIDATE_SIZE = 20      # 감시 종목 수

RESET_HOUR = 9
RESET_WINDOW_MINUTES = 5     # 09:00~09:05 사이 1회 리셋
COOLDOWN_SECONDS = 180       # 주문 후 동일 코인 재주문 방지(3분)

MIN_ORDER_KRW = 5000

# ==========================================
# [3] 기능 함수 정의
# ==========================================

def send_discord(msg: str):
    try:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        requests.post(discord_url, json={"content": f"[{now}] {msg}"}, timeout=3)
    except:
        pass


def get_top_candidates(limit=20, fallback=None):
    """
    24h 누적 거래대금 상위 limit개 반환.
    실패 시: fallback(직전 후보)을 반환해서 전략이 갑자기 BTC/ETH로 바뀌지 않도록 함.
    """
    try:
        tickers = pyupbit.get_tickers("KRW")
        resp = requests.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(tickers)},
            timeout=7
        ).json()

        sorted_coins = sorted(resp, key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)
        top = [x['market'] for x in sorted_coins[:limit] if 'market' in x]
        return top if top else (fallback or ["KRW-BTC", "KRW-ETH"])
    except:
        return fallback or ["KRW-BTC", "KRW-ETH"]


def get_target_price(ticker: str):
    """
    변동성 돌파 목표가 = 오늘 시가 + (전일 고가-저가)*K
    """
    try:
        df = pyupbit.get_ohlcv(ticker, interval="day", count=2)
        if df is None or len(df) < 2:
            return None
        yesterday = df.iloc[-2]
        today_open = df.iloc[-1]['open']
        return float(today_open) + (float(yesterday['high']) - float(yesterday['low'])) * K_VALUE
    except:
        return None


def build_target_prices(candidates):
    """
    get_target_price를 코인당 1번만 호출하도록 정리.
    """
    targets = {}
    for coin in candidates:
        t = get_target_price(coin)
        if t:
            targets[coin] = t
    return targets


def get_my_coins():
    """
    보유 코인 목록(평가금액 5천원 이상)
    """
    try:
        balances = upbit.get_balances()
        if not balances:
            return []
        my = []
        for b in balances:
            if b.get('currency') == "KRW":
                continue
            avg_buy = float(b.get('avg_buy_price', 0))
            bal = float(b.get('balance', 0))
            if avg_buy * bal > MIN_ORDER_KRW:
                my.append(f"KRW-{b['currency']}")
        return my
    except:
        return []


def sell_all():
    try:
        balances = upbit.get_balances()
        if balances:
            for b in balances:
                if b.get('currency') == "KRW":
                    continue
                coin = f"KRW-{b['currency']}"
                amount = upbit.get_balance(coin)
                if not amount:
                    continue
                curr = pyupbit.get_current_price(coin)
                if curr and curr * amount > MIN_ORDER_KRW:
                    upbit.sell_market_order(coin, amount)
                    time.sleep(0.3)
        send_discord("🌅 09:00 리셋: 전량 매도 완료.")
    except Exception as e:
        send_discord(f"❗ 전량매도 에러: {e}")


def calculate_buy_amount(current_holding_count, krw_balance):
    if krw_balance is None:
        return 0
    remaining = MAX_HOLDINGS - current_holding_count
    if remaining <= 0:
        return 0
    amount = (float(krw_balance) * 0.999) / remaining
    return min(amount, MAX_BUY_AMOUNT) if amount >= MIN_ORDER_KRW else 0


def in_reset_window(now: datetime.datetime):
    if now.hour != RESET_HOUR:
        return False
    return 0 <= now.minute < RESET_WINDOW_MINUTES


def is_cooled_down(ticker: str, cooldown_map: dict, now_ts: float):
    last = cooldown_map.get(ticker)
    return (last is not None) and (now_ts - last < COOLDOWN_SECONDS)


# ==========================================
# [4] 실행 루프
# ==========================================
if st.button('🚀 자동매매 가동 시작'):
    send_discord("🤖 [V3.1] 자동매매 가동 시작")

    # 초기 세팅
    candidates = get_top_candidates(CANDIDATE_SIZE)
    target_prices = build_target_prices(candidates)

    # 리셋 1일 1회 플래그 (YYYY-MM-DD)
    last_reset_date = None

    # 주문 쿨다운(중복 주문 방지): { "KRW-BTC": last_order_ts, ... }
    cooldown = {}

    st.write("📊 모니터링 중... 디스코드 알림을 확인하세요.")

    while True:
        try:
            now = datetime.datetime.now()
            now_ts = time.time()

            # 09:00 리셋 (09:00~09:05 사이 '하루 1회'만)
            today_str = now.strftime("%Y-%m-%d")
            if in_reset_window(now) and last_reset_date != today_str:
                sell_all()
                last_reset_date = today_str

                candidates = get_top_candidates(CANDIDATE_SIZE, fallback=candidates)
                target_prices = build_target_prices(candidates)

                # 리셋 직후엔 주문 꼬임 방지
                cooldown.clear()
                time.sleep(2)

            my_coins = get_my_coins()
            krw_balance = upbit.get_balance("KRW")

            # A. 손절매 체크
            for coin in my_coins:
                if is_cooled_down(coin, cooldown, now_ts):
                    continue

                curr = pyupbit.get_current_price(coin)
                avg = upbit.get_avg_buy_price(coin)
                if curr and avg and avg > 0:
                    if (curr - avg) / avg <= -STOP_LOSS_PCT:
                        amt = upbit.get_balance(coin)
                        if amt and curr * amt > MIN_ORDER_KRW:
                            upbit.sell_market_order(coin, amt)
                            cooldown[coin] = now_ts
                            send_discord(f"⛔ {coin} 손절 완료 ({-STOP_LOSS_PCT*100:.1f}%)")
                            time.sleep(0.5)

            # B. 매수 체크
            if len(my_coins) < MAX_HOLDINGS:
                buy_amount = calculate_buy_amount(len(my_coins), krw_balance)
                if buy_amount >= MIN_ORDER_KRW:
                    for coin in candidates:
                        if coin in my_coins:
                            continue
                        if is_cooled_down(coin, cooldown, now_ts):
                            continue

                        target = target_prices.get(coin)
                        if not target:
                            continue

                        curr = pyupbit.get_current_price(coin)
                        if curr and curr >= target:
                            upbit.buy_market_order(coin, buy_amount)
                            cooldown[coin] = now_ts
                            send_discord(f"🚀 {coin} 돌파 매수 완료! (매수금액≈{int(buy_amount):,} KRW)")
                            time.sleep(0.5)
                            break

            time.sleep(2)

        except Exception as e:
            send_discord(f"❗ Loop Error: {e}")
            time.sleep(10)
