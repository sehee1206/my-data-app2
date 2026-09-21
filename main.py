from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import pytz

# Page config & title
st.set_page_config(page_title="일별 박스오피스", page_icon="🎬", layout="wide")
st.title("🎬 일별 박스오피스 조회")


# API 데이터를 1시간 동안 메모리에 저장(캐싱)하는 함수
@st.cache_data(ttl=3600)
def fetch_box_office_data(target_date, api_key):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            return None, f"서버 응답 오류 (상태 코드: {response.status_code})"

        data = response.json()

        # 1. API 키 오류 등으로 faultInfo 상자가 온 경우
        if "faultInfo" in data:
            message = data["faultInfo"].get("message", "알 수 없는 오류")
            return None, f"API 오류 발생: {message}"

        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        # 2. 영화 목록이 비어있는 경우
        if not daily_list:
            return None, "그날은 아직 집계 전입니다."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


# --- 1. 한국 시간(KST) 기준 날짜 계산 및 선택기 ---
kst = pytz.timezone("Asia/Seoul")
yesterday = (datetime.now(kst) - timedelta(days=1)).date()

# 사용자가 달력에서 날짜를 고를 수 있게 설정 (최대 날짜는 '어제')
selected_date = st.date_input(
    "조회할 날짜를 선택하세요 (오늘 날짜는 아직 집계 전입니다)",
    value=yesterday,
    max_value=yesterday,
)

target_dt = selected_date.strftime("%Y%m%d")
formatted_date_display = selected_date.strftime("%Y년 %m월 %d일")

st.caption(f"선택한 날짜: **{formatted_date_display}**")

# --- 2. Streamlit Secrets에서 API 키 불러오기 ---
if "KOBIS_KEY" not in st.secrets:
    st.error(
        "❌ 비밀 금고(Secrets)에 `KOBIS_KEY`가 설정되지 않았습니다.\n\n"
        "**확인 사항:**\n"
        "1. Streamlit Cloud 설정(Settings > Secrets)에 `KOBIS_KEY = '발급받은키'`를 입력했는지 확인하세요.\n"
        "2. 로컬 실행 시 `.streamlit/secrets.toml` 파일이 존재하는지 확인하세요."
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# --- 3. API 데이터 불러오기 ---
raw_data, error_message = fetch_box_office_data(target_dt, api_key)

# API 요청 중 문제가 발생하거나 목록이 비어있는 경우 안내 출력 후 중단
if error_message:
    if error_message == "그날은 아직 집계 전입니다.":
        st.warning(f"⚠️ {error_message}")
    else:
        st.error(
            f"❌ 데이터를 가져오지 못했습니다.\n\n"
            f"**오류 내용:** {error_message}\n\n"
            "**체크리스트:**\n"
            "- KOBIS API 키가 올바르게 입력되었는지 확인해 주세요.\n"
            "- API 일일 사용량 초과 여부를 확인해 주세요."
        )
    st.stop()

# --- 4. 데이터 전처리 ---
df = pd.DataFrame(raw_data)

# 숫자 데이터 변환 (정렬, 계산 및 그래프용)
numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 순위 기준 정렬
df = df.sort_values("rank")

# 1) 순위 증감(rankInten) 화살표 표시 텍스트 생성
def format_rank_inten(val):
    if val > 0:
        return f"🔺 {val}"
    elif val < 0:
        return f"🔹 {abs(val)}"
    else:
        return "-"

df["rankIntenDisplay"] = df["rankInten"].apply(format_rank_inten)

# 2) 누적 관객 100만 명 이상 영화명에 트로피(🏆) 추가
def format_movie_name(row):
    name = row["movieNm"]
    if row["audiAcc"] >= 1_000_000:
        return f"{name} 🏆"
    return name

df["movieNmDisplay"] = df.apply(format_movie_name, axis=1)

# --- 5. 1위 영화 하이라이트 (지표 카드 3개) ---
top_1 = df.iloc[0]

st.subheader(f"🥇 1위: {top_1['movieNmDisplay']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="당일 관객수",
        value=f"{top_1['audiCnt']:,} 명",
        delta=f"전날 대비 순위: {top_1['rankIntenDisplay']}",
    )
with col2:
    st.metric(label="누적 관객수", value=f"{top_1['audiAcc']:,} 명")
with col3:
    st.metric(label="스크린수", value=f"{top_1['scrnCnt']:,} 개")

st.divider()

# --- 6. 관객수 상위 5편 막대그래프 ---
st.subheader("📊 관객수 상위 5개 영화")
top_5_df = df.head(5)

fig = px.bar(
    top_5_df,
    x="movieNmDisplay",
    y="audiCnt",
    text="audiCnt",
    labels={"movieNmDisplay": "영화명", "audiCnt": "관객수(명)"},
    color="audiCnt",
    color_continuous_scale="Blues",
)

fig.update_traces(texttemplate="%{text:,}명", textposition="outside")
fig.update_layout(xaxis_title="", yaxis_title="관객수", showlegend=False)

st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- 7. 전체 박스오피스 표 출력 ---
st.subheader("📋 박스오피스 순위 표")

# 표에 출력할 컬럼 선택 및 이름 변경
display_df = df[
    [
        "rank",
        "rankIntenDisplay",
        "movieNmDisplay",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
    ]
].copy()

display_df.columns = [
    "순위",
    "순위 변동",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수",
]

st.dataframe(
    display_df,
    column_config={
        "순위": st.column_config.NumberColumn(format="%d위"),
        "관객수": st.column_config.NumberColumn(format="%d명"),
        "누적관객": st.column_config.NumberColumn(format="%d명"),
        "스크린수": st.column_config.NumberColumn(format="%d개"),
    },
    use_container_width=True,
    hide_index=True,
)
