import streamlit as st
import requests
import re
import urllib.parse
from datetime import datetime, timedelta

# 1. 앱 페이지 설정 및 모바일 최적화 CSS 적용
st.set_page_config(
    page_title="대만 4박 5일 여행 가이드",
    page_icon="✈️",
    layout="centered"
)

# --- [UI/텍스트 가독성 강화를 위한 CSS] ---
st.markdown("""
    <style>
    /* 전체 배경색 및 기본 글자색 고정 */
    .stApp { 
        background-color: #F8F9FA;
    }
    
    /* 모든 텍스트의 가시성 확보 */
    h1, h2, h3, p, span, li, label, div {
        color: #202124 !important;
    }

    /* 박스 간 간격 및 내부 여백 최적화 */
    div[data-testid="stVerticalBlock"] > div:has(div.stMarkdown) {
        background-color: white !important; 
        padding: 8px 12px !important; 
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
        margin-bottom: -10px !important; 
        border: 1px solid #EEEEEE;
    }

    /* 버튼 모바일 최적화 */
    .stButton > button {
        width: 100%; border-radius: 12px; height: 3em; font-weight: bold;
        background-color: #4285F4 !important; 
        color: white !important;
        border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 5px !important;
    }
    
    .stButton > button p {
        color: white !important;
    }

    /* 탭 메뉴 가독성 강화 */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #E9ECEF !important; 
        border-radius: 8px 8px 0 0;
        padding: 8px 12px; 
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #4285F4 !important; 
    }
    .stTabs [aria-selected="true"] div {
        color: white !important;
    }

    h1 { color: #1A73E8 !important; font-size: 1.6rem !important; text-align: center; font-weight: bold; margin-bottom: 0px; }
    
    .stAlert {
        padding: 8px !important;
        margin-bottom: 5px !important;
    }
    .stAlert p {
        color: #155724 !important;
    }

    /* 선택 박스 가독성 수정 */
    div[data-baseweb="select"] > div {
        background-color: white !important;
        color: #202124 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- [함수 설정] ---
def get_secret(key_name):
    return st.secrets.get(key_name, None)

NAVER_CLIENT_ID = get_secret("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = get_secret("NAVER_CLIENT_SECRET")
WEATHER_API_KEY = get_secret("OPENWEATHER_API_KEY")

def get_realtime_weather(city_name):
    if not WEATHER_API_KEY: return "☀️ 키 미등록"
    city_map = {"타이중": "Taichung", "타이베이": "Taipei"}
    city_en = city_map.get(city_name, "Taipei")
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_en}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url, timeout=5).json()
        return f"{res['main']['temp']}°C, {res['weather'][0]['description']}"
    except: return "⚠️ 정보 수신 불가"

def search_naver_blog(query, count=10):
    if not NAVER_CLIENT_ID: return [], "API 키 미등록"
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    params = {"query": f"대만 {query}", "display": count, "sort": "date"}
    try:
        response = requests.get(url, headers=headers, params=params)
        return response.json().get('items', []), None
    except: return [], "연결 오류"

def clean_html(raw_html):
    return re.sub('<.*?>', '', raw_html)

def map_link_btn(place_name, btn_text=None):
    text = btn_text if btn_text else f"📍 {place_name} 지도보기"
    encoded_place = urllib.parse.quote(place_name)
    url = f"https://www.google.com/maps/search/{encoded_place}"
    st.markdown(f"""<a href="{url}" target="_blank" style="text-decoration: none;">
        <div style="display: block; background-color: #4285F4; color: white !important; padding: 8px; border-radius: 10px; font-size: 0.85em; font-weight: bold; margin-bottom: 5px; text-align: center;">{text}</div>
    </a>""", unsafe_allow_html=True)

def info_card(title, content, is_hotel=False):
    bg_color = "#f3e5f5" if is_hotel else "#e1f5fe"
    border_color = "#9c27b0" if is_hotel else "#0288d1"
    icon = "🏨" if is_hotel else "📌"
    st.markdown(f"""<div style="background-color: {bg_color}; padding: 8px 12px; border-radius: 10px; border-left: 5px solid {border_color}; margin-bottom: 5px;">
        <b style="color: {border_color} !important; font-size: 1.0em;">{icon} {title}</b><br>
        <span style="font-size: 0.9em; color: #202124 !important; line-height: 1.4;">{content}</span>
    </div>""", unsafe_allow_html=True)

def display_blogs(query):
    st.markdown(f"<h5 style='color:#202124 !important; margin-bottom:5px;'>🔍 '{query}' 최신 정보</h5>", unsafe_allow_html=True)
    items, _ = search_naver_blog(query, count=10)
    if items:
        for item in items:
            st.markdown(f"<div style='font-size:0.85em; margin-bottom:3px;'>- <a href='{item['link']}' target='_blank'>{clean_html(item['title'])}</a></div>", unsafe_allow_html=True)
    else: st.write("블로그 정보를 불러올 수 없습니다.")

# --- [메인 레이아웃] ---
st.title("대만 스마트 여행 가이드")
st.info("📅 12/31 ~ 1/4 부산 출발-타이베이-타이중-타이베이(창호와 성민의 함께하는 여행)")

# --- 우버 호출 섹션 ---
with st.container():
    st.markdown("<h4 style='margin-bottom:2px;'>🚖 우버(Uber) 호출</h4>", unsafe_allow_html=True)
    uber_dest = st.text_input("", placeholder="목적지 입력 후 엔터", key="uber_input", label_visibility="collapsed")
    if uber_dest:
        encoded_dest = urllib.parse.quote(uber_dest)
        uber_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[nickname]={encoded_dest}"
        st.markdown(f'<a href="{uber_url}" target="_blank" style="text-decoration:none; color:white !important; background-color:#000000; padding:8px; border-radius:10px; display:block; text-align:center; font-weight:bold;">🚕 우버 호출하기 ({uber_dest})</a>', unsafe_allow_html=True)

st.divider()

with st.container():
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<h4 style='margin-bottom:2px;'>실시간 날씨</h4>", unsafe_allow_html=True)
        target_city = st.selectbox("", ["타이중", "타이베이","가오슝"], label_visibility="collapsed")
        st.info(f"**{target_city}:** {get_realtime_weather(target_city)}")
    with col2:
        st.markdown("<h4 style='margin-bottom:2px;'>🚀 지도 검색</h4>", unsafe_allow_html=True)
        # 지명을 입력하면 바로 아래 버튼이 생기도록 수정
        search_place = st.text_input("", placeholder="지명 입력 후 엔터", key="map_input", label_visibility="collapsed")
        if search_place:
            encoded_search = urllib.parse.quote(search_place)
            map_url = f"https://www.google.com/maps/search/{encoded_search}"
            # 찾기 버튼 대신 클릭 시 바로 이동하는 '단일 버튼' 생성
            st.markdown(f"""<a href="{map_url}" target="_blank" style="text-decoration: none;">
                <div style="display: block; background-color: #1A73E8; color: white !important; padding: 8px; border-radius: 10px; font-size: 0.9em; font-weight: bold; text-align: center; margin-top: 5px;">📍 지도 열기: {search_place}</div>
            </a>""", unsafe_allow_html=True)

st.divider()

tabs = st.tabs(["📅 일정", "🔍 블로그", "✅ 체크"])

with tabs[0]:
    d_tabs = st.tabs(["1일", "2일", "3일", "4일", "5일"])
    
    with d_tabs[0]:
        st.subheader("1일차: 부산-타이중")
        st.success("🛫 10:50 김해 → 🛬 12:30 타오위안")
        info_card("이동", "버스 터미널로 이동하여 '타이중'행 버스 탑승 (약 2시간)")
        info_card("체크인: 타이중 린 호텔", "차오마 터미널 하차 후 도보 5분", is_hotel=True)
        map_link_btn("The Lin Hotel Taichung")
        info_card("타이중 국가 가극원", "야경이 아름다운 랜드마크")
        map_link_btn("National Taichung Theater")
        info_card("숙박: 타이중 린 호텔", "", is_hotel=True)
        display_blogs("타이중 국가가극원 린호텔")

    with d_tabs[1]:
        st.subheader("2일차: 타이중 관광")
        info_card("조식: 타이중 린 호텔", "", is_hotel=True)
        info_card("동해대 루체예배당", "택시 20분")
        map_link_btn("Luce Memorial Chapel")
        info_card("춘수당 본점", "버블티 원조, 택시 20분")
        map_link_btn("Chun Shui Tang Siwei")
        info_card("심계신촌", "프리마켓, 택시 15분")
        map_link_btn("Audit Village")
        info_card("궁원안과", "디저트 카페, 택시 10분")
        map_link_btn("Miyahara")
        info_card("숙박: 타이중 린 호텔", "", is_hotel=True)
        display_blogs("춘수당 심계신촌 궁원안과")

    with d_tabs[2]:
        st.subheader("3일차: 근교 투어")
        info_card("조식: 타이중 린 호텔", "", is_hotel=True)
        info_card("일월담 (선문레이크)", "대만 최대 호수 유람선")
        map_link_btn("Sun Moon Lake")
        info_card("고미습지", "환상적인 일몰 습지")
        map_link_btn("Gaomei Wetlands")
        info_card("펑지아 야시장", "타이중 최대 야시장")
        map_link_btn("Fengjia Night Market")
        info_card("숙박: 타이중 린 호텔", "", is_hotel=True)
        display_blogs("타이중 일월담 고미습지")

    with d_tabs[3]:
        st.subheader("4일차: 타이중-타이베이")
        info_card("이동", "HSR 타이중역 → 타이베이역 (1시간 10분)")
        info_card("체크인: 메트로폴리탄 타이베이", "난징푸싱역 앞, 택시 15분", is_hotel=True)
        map_link_btn("Hotel Metropolitan Premier Taipei")
        info_card("국립고궁박물관", "택시 20분")
        map_link_btn("National Palace Museum")
        info_card("랴오닝 야시장", "현지인 맛집, 택시 30분")
        map_link_btn("Liaoning Night Market")
        display_blogs("타이베이고궁박물관 랴오닝야시장")

    with d_tabs[4]:
        st.subheader("5일차: 귀국")
        info_card("이동", "공항 버스 1960번 탑승 (60분)")
        st.success("🛫 13:25 타오위안 → 김해행")
        map_link_btn("Taoyuan Airport Terminal 1")
        display_blogs("타오위안 공항 면세점")

with tabs[1]:
    user_q = st.text_input("장소 검색", placeholder="예: 타이중 맛집", key="search_tab_input", label_visibility="collapsed")
    if user_q:
        items, _ = search_naver_blog(user_q, count=10)
        if items:
            for i, item in enumerate(items, 1):
                st.markdown(f"<div style='font-size:0.9em; margin-bottom:5px;'><b>{i}.</b> <a href='{item['link']}'>{clean_html(item['title'])}</a></div>", unsafe_allow_html=True)

with tabs[2]:
    st.header("✅ 체크")
    st.checkbox("데이터(eSIM/유심) 확인")
    st.checkbox("110V 돼지코 어댑터")
    st.info("연말 대만은 일교차가 큽니다. 가벼운 외투 지참!")
