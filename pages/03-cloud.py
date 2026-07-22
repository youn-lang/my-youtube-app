import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from wordcloud import WordCloud


# ---------------------------------------------------------
# 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="유튜브 댓글 언어 분석기",
    page_icon="🗨️",
    layout="wide",
)

# ---------------------------------------------------------
# 화면 디자인
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 8% 8%, rgba(255, 0, 0, 0.08), transparent 24rem),
            radial-gradient(circle at 92% 18%, rgba(72, 84, 255, 0.08), transparent 26rem),
            linear-gradient(180deg, #fffdfd 0%, #f7f8fc 100%);
    }

    .block-container {
        max-width: 1250px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    .hero-card {
        position: relative;
        overflow: hidden;
        padding: 2.2rem 2.4rem;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(32, 38, 57, 0.09);
        border-radius: 26px;
        background: linear-gradient(135deg, #ffffff 0%, #fff5f5 52%, #f1f3ff 100%);
        box-shadow: 0 18px 50px rgba(31, 38, 70, 0.10);
    }

    .hero-card::after {
        content: "말 · 의미 · 빈도 · 담화";
        position: absolute;
        right: 1.5rem;
        top: 1rem;
        font-size: 0.88rem;
        letter-spacing: 0.12rem;
        color: rgba(55, 62, 92, 0.42);
    }

    .hero-title {
        margin: 0;
        font-size: clamp(2rem, 5vw, 3.3rem);
        font-weight: 850;
        line-height: 1.08;
        color: #202639;
    }

    .hero-title span {
        color: #ff0033;
    }

    .hero-copy {
        max-width: 760px;
        margin-top: 0.9rem;
        margin-bottom: 0;
        color: #596078;
        font-size: 1.03rem;
        line-height: 1.75;
    }

    .linguistic-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.6rem;
        margin-top: 1.2rem;
    }

    .linguistic-token {
        padding: 0.42rem 0.72rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(69, 78, 113, 0.12);
        color: #3e4663;
        font-size: 0.87rem;
        font-weight: 650;
    }

    div[data-testid="stMetric"] {
        padding: 1rem 1.1rem;
        border: 1px solid rgba(36, 44, 73, 0.09);
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.88);
        box-shadow: 0 10px 30px rgba(35, 43, 77, 0.06);
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(36, 44, 73, 0.09);
        border-radius: 16px;
        overflow: hidden;
    }

    .section-note {
        margin: -0.25rem 0 1rem 0;
        color: #697087;
        font-size: 0.93rem;
    }

    .analysis-card {
        padding: 1rem 1.1rem;
        border-radius: 18px;
        border: 1px solid rgba(36, 44, 73, 0.09);
        background: rgba(255, 255, 255, 0.80);
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 12px;
        font-weight: 700;
    }
    </style>

    <div class="hero-card">
        <h1 class="hero-title">YouTube 댓글 <span>언어 분석기</span></h1>
        <p class="hero-copy">
            영상 댓글을 수집하고, 어휘 빈도와 워드클라우드를 통해
            온라인 담화에 반복되는 표현과 관심사를 탐색합니다.
        </p>
        <div class="linguistic-strip">
            <span class="linguistic-token">형태 · word</span>
            <span class="linguistic-token">빈도 · frequency</span>
            <span class="linguistic-token">담화 · discourse</span>
            <span class="linguistic-token">댓글 · comment</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# 예시 영상 주소
# ---------------------------------------------------------
EXAMPLE_1 = "https://youtu.be/d95J8yzvjbQ?si=LfL5DLwCL8Pk077r"
EXAMPLE_2 = "https://youtu.be/I9vK5EVTt0U?si=NEZ8L7MRuNvrzINa"


# ---------------------------------------------------------
# 유튜브 링크에서 영상 ID를 추출하는 함수
# ---------------------------------------------------------
def extract_video_id(url: str) -> str | None:
    """유튜브 영상 주소에서 11자리 영상 ID를 추출합니다."""

    if not url:
        return None

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed_url = urlparse(url)
        host = parsed_url.netloc.lower()
        host = host.removeprefix("www.")
        host = host.removeprefix("m.")

        video_id = None

        if host == "youtu.be":
            video_id = parsed_url.path.lstrip("/").split("/")[0]

        elif host in {"youtube.com", "music.youtube.com"}:
            if parsed_url.path == "/watch":
                query = parse_qs(parsed_url.query)
                video_id = query.get("v", [None])[0]

            elif parsed_url.path.startswith(("/shorts/", "/embed/", "/live/")):
                path_parts = parsed_url.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    video_id = path_parts[1]

        if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return video_id

    except Exception:
        return None

    return None


# ---------------------------------------------------------
# YouTube Data API에서 댓글을 여러 페이지에 걸쳐 가져오는 함수
# ---------------------------------------------------------
def fetch_youtube_comments(
    video_id: str,
    api_key: str,
    requested_count: int,
) -> list[dict]:
    """
    commentThreads API를 반복 호출해 댓글을 최대 1,000개 가져옵니다.

    API 한 번에 최대 100개까지 받을 수 있으므로,
    nextPageToken이 있을 때 다음 페이지를 계속 요청합니다.
    """

    api_url = "https://www.googleapis.com/youtube/v3/commentThreads"
    comments = []
    next_page_token = None

    while len(comments) < requested_count:
        remaining_count = requested_count - len(comments)

        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, remaining_count),
            "order": "relevance",
            "textFormat": "plainText",
            "key": api_key,
        }

        if next_page_token:
            params["pageToken"] = next_page_token

        response = requests.get(
            api_url,
            params=params,
            timeout=20,
        )
        response.raise_for_status()

        data = response.json()

        for item in data.get("items", []):
            top_comment = item["snippet"]["topLevelComment"]["snippet"]

            comments.append(
                {
                    "댓글": top_comment.get("textOriginal", ""),
                    "좋아요 수": int(top_comment.get("likeCount", 0)),
                    "작성일": top_comment.get("publishedAt", ""),
                }
            )

            if len(comments) >= requested_count:
                break

        next_page_token = data.get("nextPageToken")

        # 더 가져올 페이지가 없으면 반복을 끝냅니다.
        if not next_page_token:
            break

    return comments


# ---------------------------------------------------------
# 댓글 전체를 단어로 나누는 함수
# ---------------------------------------------------------
def extract_words(comments: pd.Series) -> list[str]:
    """
    한국어와 영어 단어를 추출합니다.
    영어는 소문자로 통일하고 한 글자짜리 단어는 제외합니다.
    """

    all_words = []

    for comment in comments.fillna("").astype(str):
        normalized_comment = comment.lower()
        words = re.findall(r"[가-힣A-Za-z]+", normalized_comment)
        words = [word for word in words if len(word) >= 2]
        all_words.extend(words)

    return all_words


def count_top_words(comments: pd.Series, top_n: int = 20) -> pd.DataFrame:
    """자주 나온 단어 상위 n개를 표로 만듭니다."""

    word_counts = Counter(extract_words(comments)).most_common(top_n)

    return pd.DataFrame(
        word_counts,
        columns=["단어", "빈도"],
    )


# ---------------------------------------------------------
# 한글 폰트 파일 다운로드
# ---------------------------------------------------------
@st.cache_resource
def download_korean_font() -> str | None:
    """워드클라우드용 나눔고딕 폰트를 내려받습니다."""

    font_url = (
        "https://raw.githubusercontent.com/google/fonts/main/"
        "ofl/nanumgothic/NanumGothic-Regular.ttf"
    )

    font_dir = Path(".streamlit_fonts")
    font_path = font_dir / "NanumGothic-Regular.ttf"

    if font_path.exists() and font_path.stat().st_size > 0:
        return str(font_path)

    try:
        font_dir.mkdir(parents=True, exist_ok=True)

        response = requests.get(font_url, timeout=20)
        response.raise_for_status()
        font_path.write_bytes(response.content)

        if font_path.stat().st_size == 0:
            font_path.unlink(missing_ok=True)
            return None

        return str(font_path)

    except (requests.exceptions.RequestException, OSError):
        return None


def make_wordcloud_image(comments: pd.Series, font_path: str):
    """
    matplotlib 없이 WordCloud가 만든 PIL 이미지를 반환합니다.
    """

    words = extract_words(comments)

    if not words:
        return None

    word_frequencies = Counter(words)

    wordcloud = WordCloud(
        width=1200,
        height=650,
        background_color="white",
        font_path=font_path,
        max_words=200,
        collocations=False,
    ).generate_from_frequencies(word_frequencies)

    return wordcloud.to_image()


# ---------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------
if "youtube_url" not in st.session_state:
    st.session_state.youtube_url = EXAMPLE_1

if "comments_df" not in st.session_state:
    st.session_state.comments_df = None

if "result_video_id" not in st.session_state:
    st.session_state.result_video_id = None

if "requested_count" not in st.session_state:
    st.session_state.requested_count = 100


# ---------------------------------------------------------
# 입력 영역
# ---------------------------------------------------------
st.subheader("1. 분석할 영상과 댓글 수 설정")
st.markdown(
    '<p class="section-note">영상 주소를 넣고 수집할 댓글 수를 10개부터 1,000개까지 지정합니다.</p>',
    unsafe_allow_html=True,
)

button_col1, button_col2 = st.columns(2)

with button_col1:
    if st.button(
        "예시 1 · 딥마인드 다큐(영어 댓글)",
        use_container_width=True,
    ):
        st.session_state.youtube_url = EXAMPLE_1

with button_col2:
    if st.button(
        "예시 2 · 2002 월드컵 추억(한국어 댓글)",
        use_container_width=True,
    ):
        st.session_state.youtube_url = EXAMPLE_2

input_col1, input_col2 = st.columns([3, 1])

with input_col1:
    youtube_url = st.text_input(
        "유튜브 영상 링크",
        key="youtube_url",
        placeholder="https://www.youtube.com/watch?v=...",
    )

with input_col2:
    requested_count = st.number_input(
        "가져올 댓글 수",
        min_value=10,
        max_value=1000,
        step=10,
        key="requested_count",
        help="영상에 공개된 댓글이 적으면 지정한 수보다 적게 수집될 수 있습니다.",
    )

analyze_button = st.button(
    "댓글 수집 및 분석 시작",
    type="primary",
    use_container_width=True,
)


# ---------------------------------------------------------
# 댓글 가져오기 실행
# ---------------------------------------------------------
if analyze_button:
    video_id = extract_video_id(youtube_url)

    if not video_id:
        st.error(
            "유효한 유튜브 영상 링크를 확인하지 못했습니다. "
            "youtu.be 주소 또는 youtube.com/watch 주소를 입력해 주세요."
        )
        st.stop()

    try:
        api_key = st.secrets["YOUTUBE_API_KEY"]
    except KeyError:
        st.error(
            "YouTube API 키가 설정되지 않았습니다. "
            "Streamlit Cloud의 Secrets에 "
            '`YOUTUBE_API_KEY = "발급받은_API_키"` 형식으로 등록해 주세요.'
        )
        st.stop()

    try:
        with st.spinner(
            f"댓글을 최대 {requested_count:,}개까지 가져오고 있습니다..."
        ):
            comments = fetch_youtube_comments(
                video_id=video_id,
                api_key=api_key,
                requested_count=int(requested_count),
            )

    except requests.exceptions.Timeout:
        st.error(
            "유튜브 서버의 응답이 늦어 댓글을 가져오지 못했습니다. "
            "댓글 수를 줄이거나 잠시 후 다시 시도해 주세요."
        )
        st.stop()

    except requests.exceptions.HTTPError as error:
        status_code = error.response.status_code if error.response else None

        try:
            error_data = error.response.json()
            api_message = error_data.get("error", {}).get("message", "")
        except Exception:
            api_message = ""

        if status_code == 403:
            st.error(
                "댓글을 가져올 수 없습니다. 댓글이 비활성화된 영상이거나, "
                "API 키의 YouTube Data API 사용 권한 또는 할당량을 확인해 주세요."
            )
        elif status_code == 404:
            st.error(
                "영상을 찾을 수 없습니다. 링크가 올바른지, "
                "영상이 삭제되거나 비공개로 전환되지 않았는지 확인해 주세요."
            )
        elif status_code == 400:
            st.error(
                "요청 형식이 올바르지 않습니다. "
                "유튜브 영상 링크를 다시 확인해 주세요."
            )
        else:
            st.error(
                "유튜브 댓글을 가져오는 중 오류가 발생했습니다. "
                f"{api_message or '잠시 후 다시 시도해 주세요.'}"
            )

        st.stop()

    except requests.exceptions.RequestException:
        st.error(
            "네트워크 문제로 유튜브 댓글을 가져오지 못했습니다. "
            "인터넷 연결을 확인한 뒤 다시 시도해 주세요."
        )
        st.stop()

    except Exception:
        st.error(
            "댓글을 처리하는 중 예상하지 못한 오류가 발생했습니다. "
            "영상 링크와 API 키 설정을 확인해 주세요."
        )
        st.stop()

    if not comments:
        st.warning(
            "가져올 수 있는 댓글이 없습니다. "
            "댓글이 없는 영상이거나 댓글 작성이 막혀 있을 수 있습니다."
        )
        st.stop()

    comments_df = pd.DataFrame(comments)

    # UTC 형식의 API 날짜를 한국 시간 기준으로 바꾼 뒤 보기 쉬운 문자열로 저장합니다.
    comments_df["작성일"] = pd.to_datetime(
        comments_df["작성일"],
        utc=True,
        errors="coerce",
    ).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d %H:%M")

    comments_df = comments_df.sort_values(
        by="좋아요 수",
        ascending=False,
    ).reset_index(drop=True)

    comments_df.insert(
        0,
        "순번",
        range(1, len(comments_df) + 1),
    )

    st.session_state.comments_df = comments_df
    st.session_state.result_video_id = video_id

    if len(comments_df) < int(requested_count):
        st.info(
            f"{requested_count:,}개를 요청했지만 공개적으로 가져올 수 있는 댓글은 "
            f"{len(comments_df):,}개였습니다."
        )
    else:
        st.success(f"댓글 {len(comments_df):,}개를 성공적으로 가져왔습니다.")


# ---------------------------------------------------------
# 분석 결과 표시
# ---------------------------------------------------------
if st.session_state.comments_df is not None:
    comments_df = st.session_state.comments_df
    video_id = st.session_state.result_video_id

    st.divider()
    st.subheader("2. 수집 결과")

    metric_col1, metric_col2, metric_col3 = st.columns(3)

    with metric_col1:
        st.metric(
            label="수집된 댓글",
            value=f"{len(comments_df):,}개",
        )

    with metric_col2:
        st.metric(
            label="전체 좋아요",
            value=f"{comments_df['좋아요 수'].sum():,}개",
        )

    with metric_col3:
        date_values = pd.to_datetime(
            comments_df["작성일"],
            errors="coerce",
        ).dropna()

        date_range = (
            f"{date_values.min():%Y-%m-%d} ~ {date_values.max():%Y-%m-%d}"
            if not date_values.empty
            else "날짜 정보 없음"
        )

        st.metric(
            label="댓글 작성 기간",
            value=date_range,
        )

    st.info(
        f"영상 ID: `{video_id}` · API의 relevance 순서로 수집한 뒤 "
        "좋아요 수가 많은 순으로 다시 정렬했습니다."
    )

    st.subheader("댓글 데이터 내려받기")

    csv_data = comments_df.to_csv(
        index=False,
        encoding="utf-8-sig",
    ).encode("utf-8-sig")

    st.download_button(
        label="CSV 파일 다운로드",
        data=csv_data,
        file_name=f"youtube_comments_{video_id}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.subheader("댓글 목록")

    st.dataframe(
        comments_df,
        use_container_width=True,
        hide_index=True,
        height=620,
        column_config={
            "순번": st.column_config.NumberColumn(
                "순번",
                width="small",
            ),
            "댓글": st.column_config.TextColumn(
                "댓글",
                width="large",
            ),
            "좋아요 수": st.column_config.NumberColumn(
                "좋아요 수",
                format="%d",
            ),
            "작성일": st.column_config.TextColumn(
                "작성일",
                width="medium",
                help="한국 시간 기준입니다.",
            ),
        },
    )

    st.divider()
    st.subheader("3. 어휘 빈도 분석")
    st.markdown(
        '<p class="section-note">댓글 전체에서 두 글자 이상인 한국어·영어 단어를 추출합니다.</p>',
        unsafe_allow_html=True,
    )

    top_words_df = count_top_words(
        comments_df["댓글"],
        top_n=20,
    )

    if top_words_df.empty:
        st.warning("두 글자 이상인 단어를 찾지 못했습니다.")
    else:
        chart_df = top_words_df.sort_values(
            by="빈도",
            ascending=True,
        )

        fig = px.bar(
            chart_df,
            x="빈도",
            y="단어",
            orientation="h",
            text="빈도",
            labels={
                "빈도": "등장 횟수",
                "단어": "단어",
            },
        )

        fig.update_traces(
            textposition="outside",
            cliponaxis=False,
        )

        fig.update_layout(
            height=650,
            margin=dict(l=20, r=50, t=20, b=20),
            yaxis_title=None,
            xaxis_title="등장 횟수",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

        with st.expander("단어 빈도 표 보기"):
            st.dataframe(
                top_words_df,
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("댓글 워드클라우드")

    font_path = download_korean_font()

    if font_path is None:
        st.warning(
            "한글 폰트 파일을 내려받지 못해 워드클라우드를 만들 수 없습니다. "
            "인터넷 연결을 확인한 뒤 페이지를 새로고침해 주세요."
        )
    else:
        wordcloud_image = make_wordcloud_image(
            comments_df["댓글"],
            font_path,
        )

        if wordcloud_image is None:
            st.warning(
                "워드클라우드에 사용할 두 글자 이상의 단어를 찾지 못했습니다."
            )
        else:
            st.image(
                wordcloud_image,
                use_container_width=True,
            )
