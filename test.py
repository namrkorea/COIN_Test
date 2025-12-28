import streamlit as st
import pyupbit
import time
import datetime
import requests
from zoneinfo import ZoneInfo  # ✅ KST

# ✅ 한국시간(KST) 고정
KST = ZoneInfo("Asia/Seoul")

def now_kst():
    return datetime.datetime.now(KST)

def fmt_kst(dt: datetime.datetime):
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")

def parse_kst(s: str):
    # 저장 문자열은 KST로 기록한다고 가정
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)

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
# [전략 설정]  (✅ 기존 기준 유지)
# ------------------------------------------
TARGET_INTERVAL = "minute60"
K_VALUE = 0.15

STOP_LOSS_PCT = 0.02
TAKE_PROFIT_PCT = 0.02
MAX_HOLDINGS = 5
MAX_BUY_AMOUNT = 15000
CANDIDATE_SIZE = 20

RESET_HOUR = 9
RESET_WINDOW_MINUTES = 5
COOLDOWN_SECONDS = 180

MIN_ORDER_KRW = 5000

# ==========================================
# [거래 기록: 최근 24시간 매수 종목 요약] (✅ 기존 유지)
# ==========================================
if "buy_records" not in st.session_state:
    st.session_state.buy_records = []  # list[dict]

def add_buy_record(coin: str, buy_time: datetime.datetime, buy_amount_krw: float, buy_price: float):
    try:
        st.session_state.buy_records.append({
            "buy_time": fmt_kst(buy_time),  # ✅ KST 저장
            "coin": coin,
            "buy_amount_krw": int(buy_amount_krw),
            "buy_price": float(buy_price),
        })
    except:
        pass

buy_summary_box = st.empty()

# ==========================================
# ✅ [추가] 매수/매도 트레이드 로그 (12시간 표시용)
# ==========================================
if "trade_records" not in st.session_state:
    st.session_state.trade_records = []  # list[dict]

def add_trade_record(side: str, coin: str, price: float, reason: str = "-", amount_krw: float = None):
    """
    side: 'BUY' or 'SELL'
    """
    try:
        ts = fmt_kst(now_kst())  # ✅ KST 저장
        st.session_state.trade_records.append({
            "time": ts,
            "side": side,
            "coin": coin,
            "price": None if price is None else float(price),
            "amount_krw": None if amount_krw is None else int(amount_krw),
            "reason": reason
        })
    except:
        pass

start_trade_box = st.empty()     # ✅ 시작 시 12시간 내 보유종목 거래 내역 표시
status_box = st.empty()          # ✅ 정각/30분 모니터링/보유 표시
holdings_box = st.empty()        # ✅ 시작/정각/30분 보유손익 표시

# ==========================================
# [3] 기능 함수 정의
# ==========================================

def send_discord(msg: str):
    try:
        now = fmt_kst(now_kst())  # ✅ KST 표기
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
    60분봉 기준 변동성 돌파 목표가(민감)
    목표가 = 이번 봉 시가 + (직전 봉 고가-저가)*K
    """
    try:
        df = pyupbit.get_ohlcv(ticker, interval=TARGET_INTERVAL, count=2)
        if df is None or len(df) < 2:
            return None

        prev = df.iloc[-2]
        curr_open = df.iloc[-1]["open"]
        return float(curr_open) + (float(prev["high"]) - float(prev["low"])) * K_VALUE
    except:
        return None


def build_target_prices(candidates):
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


def get_holdings_pnl_rows(my_coins):
    """
    ✅ 보유종목의 매수금액(평단*수량), 평가금액(현재가*수량), 차이(평가-매수)
    """
    rows = []
    try:
        balances = upbit.get_balances() or []
        bal_map = {}
        for b in balances:
            cur = b.get("currency")
            if cur and cur != "KRW":
                bal_map[f"KRW-{cur}"] = b

        for coin in my_coins:
            b = bal_map.get(coin)
            if not b:
                continue

            qty = float(b.get("balance", 0))
            avg = float(b.get("avg_buy_price", 0))
            buy_amt = avg * qty

            curr = pyupbit.get_current_price(coin)
            eval_amt = (float(curr) * qty) if curr else None
            diff = (eval_amt - buy_amt) if eval_amt is not None else None

            if buy_amt >= MIN_ORDER_KRW:
                rows.append({
                    "종목": coin,
                    "매수금액(KRW)": int(buy_amt),
                    "평가금액(KRW)": None if eval_amt is None else int(eval_amt),
                    "차이(KRW)": None if diff is None else int(diff),
                })
    except:
        return []

    return rows


def render_holdings_pnl(my_coins, title="📦 보유종목 손익(매수/평가/차이)"):
    rows = get_holdings_pnl_rows(my_coins)
    with holdings_box.container():
        st.subheader(title)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("표시할 보유종목이 없습니다.")


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
                    add_trade_record("SELL", coin, price=curr, reason="SELL_ALL")
                    time.sleep(0.3)
        send_discord("🌅 전량 매도 완료.")
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


def render_recent_buys_24h():
    cutoff = now_kst() - datetime.timedelta(hours=24)
    rows = []

    recent = []
    for r in st.session_state.buy_records[::-1]:
        try:
            t = parse_kst(r["buy_time"])
            if t >= cutoff:
                recent.append(r)
            else:
                break
        except:
            continue
    recent = list(reversed(recent))

    coins = sorted({r["coin"] for r in recent})
    price_map = {}
    if coins:
        for c in coins:
            price_map[c] = pyupbit.get_current_price(c)

    for r in recent:
        coin = r["coin"]
        buy_amount = float(r["buy_amount_krw"])
        buy_price = float(r["buy_price"])
        curr_price = price_map.get(coin)

        qty_est = (buy_amount / buy_price) if (buy_price and buy_amount) else 0.0
        curr_value = (qty_est * curr_price) if (curr_price and qty_est) else None
        profit = (curr_value - buy_amount) if (curr_value is not None) else None

        rows.append({
            "매수시간(KST)": r["buy_time"],
            "종목": coin,
            "매수금액(KRW)": int(buy_amount),
            "현재평가금액(KRW)": None if curr_value is None else int(curr_value),
            "이익(KRW)": None if profit is None else int(profit),
        })

    with buy_summary_box.container():
        st.subheader("🧾 최근 24시간 매수 종목 요약 (KST)")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("최근 24시간 내 매수 기록이 없습니다.")


def liquidate_on_start(cooldown: dict):
    try:
        now_ts = time.time()
        my_coins = get_my_coins()
        if not my_coins:
            return

        for coin in my_coins:
            curr = pyupbit.get_current_price(coin)
            avg = upbit.get_avg_buy_price(coin)
            if curr and avg and avg > 0:
                rate = (curr - avg) / avg

                if rate >= TAKE_PROFIT_PCT or rate <= -STOP_LOSS_PCT:
                    amt = upbit.get_balance(coin)
                    if amt and curr * amt > MIN_ORDER_KRW:
                        upbit.sell_market_order(coin, amt)
                        cooldown[coin] = now_ts
                        send_discord(f"🧹 [시작청산] {coin} 매도 (수익률 {rate*100:.2f}%)")
                        add_trade_record("SELL", coin, price=curr, reason=f"START_LIQUIDATE({rate*100:.2f}%)")
                        time.sleep(0.5)

    except Exception as e:
        send_discord(f"❗ 시작청산 에러: {e}")


def render_trades_12h_for_holdings(my_coins):
    cutoff = now_kst() - datetime.timedelta(hours=12)
    rows = []
    for r in st.session_state.trade_records:
        try:
            t = parse_kst(r["time"])
            if t < cutoff:
                continue
            if r["coin"] not in my_coins:
                continue
            rows.append({
                "시간(KST)": r["time"],
                "구분": r["side"],
                "종목": r["coin"],
                "가격": r["price"],
                "금액(KRW)": r["amount_krw"],
                "사유": r["reason"]
            })
        except:
            continue

    with start_trade_box.container():
        st.subheader("🕒 시작 시점: 보유종목 최근 12시간 매수/매도 내역 (KST)")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("최근 12시간 내(보유종목 기준) 매수/매도 기록이 없습니다.")


def render_status_with_targets(candidates, target_prices, my_coins):
    """
    ✅ 정각/30분마다:
    - 모니터링 종목
    - 종목별 변동기준(목표가)
    - 보유종목 매수금액/평가금액/차이
    """
    rows = []
    for c in candidates:
        rows.append({
            "종목": c,
            "변동기준(목표가)": None if target_prices.get(c) is None else float(target_prices.get(c)),
        })

    with status_box.container():
        st.subheader("📌 모니터링/보유 현황 (KST 기준, 정각/30분 업데이트)")
        st.write("✅ 모니터링 종목 + 종목별 변동기준(목표가):")
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("모니터링 종목이 없습니다.")

    # 보유손익 표도 같이 갱신
    render_holdings_pnl(my_coins, title="📦 보유종목 손익(매수금액/평가금액/차이) (KST)")


def send_status_to_discord(candidates, target_prices, my_coins):
    # 디스코드는 길이 제한 고려해서 요약 형태로
    mon = ", ".join([f"{c}(T={int(target_prices[c])})" for c in candidates if c in target_prices]) if candidates else "-"
    hold = ", ".join(my_coins) if my_coins else "-"
    send_discord(
        "📌 [정각/30분 리포트/KST]\n"
        f"- 모니터링: {mon}\n"
        f"- 보유: {hold}"
    )

# ==========================================
# ✅ [추가] 일괄 강제 매도 버튼 (✅ 기존 유지)
# ==========================================
if st.button("🧨 일괄 강제 매도 (전량)"):
    sell_all()
    st.warning("✅ 전량 시장가 매도를 실행했습니다. (디스코드 알림 확인)")
    st.stop()

# ==========================================
# [4] 실행 루프
# ==========================================
if st.button('🚀 자동매매 가동 시작'):
    send_discord("🤖 [V3.4] 자동매매 가동 시작 (KST)")

    candidates = get_top_candidates(CANDIDATE_SIZE)
    target_prices = build_target_prices(candidates)

    last_reset_date = None
    cooldown = {}

    # 시작 시 보유 정리(전략 유지)
    liquidate_on_start(cooldown)

    # ✅ 시작 시: 보유종목 매수금액/평가금액/차이 표시
    my_coins_start = get_my_coins()
    render_holdings_pnl(my_coins_start, title="🚀 시작 시 보유종목 손익(매수금액/평가금액/차이) (KST)")

    # ✅ 시작 시 보유 종목 기준 최근 12시간 매수/매도 내역 표시(기존 유지)
    render_trades_12h_for_holdings(my_coins_start)

    st.write("📊 모니터링 중... 디스코드 알림을 확인하세요.")
    render_recent_buys_24h()

    # ✅ 정각/30분 리포트 중복 전송 방지 키 (YYYY-MM-DD HH:MM)
    last_report_key = None

    while True:
        try:
            now = now_kst()          # ✅ KST
            now_ts = time.time()

            # 기존 본문(24시간 매수 요약) 유지
            render_recent_buys_24h()

            # 09:00 리셋 (기존 전략 유지)
            today_str = now.strftime("%Y-%m-%d")
            if in_reset_window(now) and last_reset_date != today_str:
                sell_all()
                last_reset_date = today_str

                candidates = get_top_candidates(CANDIDATE_SIZE, fallback=candidates)
                target_prices = build_target_prices(candidates)

                cooldown.clear()
                time.sleep(2)

            my_coins = get_my_coins()
            krw_balance = upbit.get_balance("KRW")

            # ✅ 매시 정각(00분)과 30분에:
            # - 모니터링 종목/변동기준(목표가)
            # - 보유종목 매수금액/평가금액/차이
            # - 디스코드 전송
            if now.minute in (0, 30):
                report_key = now.strftime("%Y-%m-%d %H:%M")
                if last_report_key != report_key:
                    render_status_with_targets(candidates, target_prices, my_coins)
                    send_status_to_discord(candidates, target_prices, my_coins)
                    last_report_key = report_key

            # A. 매도 체크 (손절 -2% / 익절 +2% : 매수가(평단) 기준) - 기존 전략 유지
            for coin in my_coins:
                if is_cooled_down(coin, cooldown, now_ts):
                    continue

                curr = pyupbit.get_current_price(coin)
                avg = upbit.get_avg_buy_price(coin)

                if curr and avg and avg > 0:
                    rate = (curr - avg) / avg

                    # 익절(+2%)
                    if rate >= TAKE_PROFIT_PCT:
                        amt = upbit.get_balance(coin)
                        if amt and curr * amt > MIN_ORDER_KRW:
                            upbit.sell_market_order(coin, amt)
                            cooldown[coin] = now_ts
                            send_discord(f"✅ {coin} 익절 완료 (+{TAKE_PROFIT_PCT*100:.1f}%) (현재 {rate*100:.2f}%)")
                            add_trade_record("SELL", coin, price=curr, reason=f"TAKE_PROFIT({rate*100:.2f}%)")
                            time.sleep(0.5)
                        continue

                    # 손절(-2%)
                    if rate <= -STOP_LOSS_PCT:
                        amt = upbit.get_balance(coin)
                        if amt and curr * amt > MIN_ORDER_KRW:
                            upbit.sell_market_order(coin, amt)
                            cooldown[coin] = now_ts
                            send_discord(f"⛔ {coin} 손절 완료 (-{STOP_LOSS_PCT*100:.1f}%) (현재 {rate*100:.2f}%)")
                            add_trade_record("SELL", coin, price=curr, reason=f"STOP_LOSS({rate*100:.2f}%)")
                            time.sleep(0.5)

            # B. 매수 체크 (기존 전략 유지)
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
                        if target and curr and curr >= target:
                            upbit.buy_market_order(coin, buy_amount)
                            cooldown[coin] = now_ts
                            send_discord(f"🚀 {coin} 돌파 매수 완료! (매수금액≈{int(buy_amount):,} KRW)")

                            add_buy_record(
                                coin=coin,
                                buy_time=now_kst(),
                                buy_amount_krw=buy_amount,
                                buy_price=curr
                            )
                            add_trade_record("BUY", coin, price=curr, amount_krw=buy_amount, reason="BREAKOUT_BUY")

                            time.sleep(0.5)
                            break

            time.sleep(2)

        except Exception as e:
            send_discord(f"❗ Loop Error: {e}")
            time.sleep(10)

