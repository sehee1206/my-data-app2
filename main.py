from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import pytz

# Page config & title
st.set_page_config(page_title="어제 박스오피스", page_icon="🎬", layout="wide")
st.title("🎬 어제 일별 박스오피스")


# API 데이터를 1시간 동안 메모리에 저장(캐싱)하는 함수
# 같은 날짜로 다시 요청하면 API를 호출하지 않고 저장된 결과를 사용합니다.
@st.cache_data(ttl=3600)
def fetch_box_office_data(target_date, api_key):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # HTTP 요청 자체가 실패한 경우
        if response.status_code != 200:
            return None, f"서버 응답 오류 (상태 코드: {response.status_code})"

        data = response.json()

        # 1. API 키 오류 등으로 faultInfo 상자가 온 경우 처리
        if "faultInfo" in data:
            message = data["faultInfo"].get("message", "알 수 없는 오류")
            return None, f"API 오류 발생: {message}"

        # 2. 결과 응답에서 dailyBoxOfficeList 추출
        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        # 3. 영화 목록이 비어있는 경우 처리
        if not daily_list:
            return None, "조회된 영화 목록이 없습니다. 날짜 또는 API 상태를 확인해 주세요."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {e}"


# --- 1. 한국 시간(KST) 기준 어제 날짜 계산 ---
# 배포 서버의 시계가 해외 기준이어도 한국 시간으로 계산합니다.
kst = pytz.timezone("Asia/Seoul")
yesterday = datetime.now(kst) - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")
formatted_date_display = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"기준일자: **{formatted_date_display}** (한국 시간 기준어제)")

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

# API 요청 중 문제가 발생한 경우 에러 안내 출력 후 중단
if error_message:
    st.error(
        f"❌ 데이터를 가져오지 못했습니다.\n\n"
        f"**오류 내용:** {error_message}\n\n"
        "**체크리스트:**\n"
        "- KOBIS API 키가 올바르게 입력되었는지 확인해 주세요.\n"
        "- API 일일 사용량 초과 여부를 확인해 주세요.\n"
        "- 네트워크 상태를 확인해 주세요."
    )
    st.stop()

# --- 4. 데이터 전처리 (문자열 -> 숫자 변환) ---
df = pd.DataFrame(raw_data)

# 숫자 데이터 변환 (정렬 및 그래프 출력용)
numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in numeric_columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 순위 기준 정렬
df = df.sort_values("rank")

# --- 5. 1위 영화 하이라이트 (지표 카드 3개) ---
top_1 = df.iloc[0]

st.subheader(f"🥇 1위: {top_1['movieNm']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        label="당일 관객수",
        value=f"{top_1['audiCnt']:,} 명",
        delta=f"전날 대비 순위 변동: {top_1['rankInten']}",
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
    x="movieNm",
    y="audiCnt",
    text="audiCnt",
    labels={"movieNm": "영화명", "audiCnt": "관객수(명)"},
    color="audiCnt",
    color_continuous_scale="Blues",
)

# 그래프 레이아웃 설정 (숫자에 천 단위 쉼표 추가)
fig.update_traces(texttemplate="%{text:,}명", textposition="outside")
fig.update_layout(xaxis_title="", yaxis_title="관객수", showlegend=False)

st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- 7. 전체 박스오피스 표 출력 ---
st.subheader("📋 박스오피스 순위 표")

# 표에 출력할 컬럼 선택 및 이름 변경
display_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 천 단위 쉼표가 들어간 깔끔한 표 형식으로 출력
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
