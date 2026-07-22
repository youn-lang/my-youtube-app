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
    page_title="유튜브 댓글 분석기",
    page_icon="💬",
    layout="wide",
)

st.title("💬 유튜브 댓글 분석기")
st.caption("3단계 · 댓글 수집, 단어 빈도 분석, 워드클라우드")


# ---------------------------------------------------------
# 예시 영상 주소
# ---------------------------------------------------------
EXAMPLE_1 = "https://youtu.be/d95J8yzvjbQ?si=LfL5DLwCL8Pk077r"
EXAMPLE_2 = "https://youtu.be/I9vK5EVTt0U?si=NEZ8L7MRuNvrzINa"


# ---------------------------------------------------------
# 유튜브 링크에서 영상 ID를 추출하는 함수
# ---------------------------------------------------------
def extract_video_id(url: str) -> str | None:
    """
    유튜브 영상 주소에서 11자리 영상 ID를 추출합니다.

    지원 예시
    - https://youtu.be/d95J8yzvjbQ?si=...
    - https://www.youtube.com/watch?v=d95J8yzvjbQ
    - https://youtube.com/watch?v=d95J8yzvjbQ&t=10s
    - https://www.youtube.com/shorts/d95J8yzvjbQ
    """

    if not url:
        return None

    url = url.strip()

    # 사용자가 https://를 빼고 입력한 경우 자동으로 붙입니다.
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed_url = urlparse(url)
        host = parsed_url.netloc.lower()

        # 주소 앞의 www. 또는 m.을 제거합니다.
        host = host.removeprefix("www.")
        host = host.removeprefix("m.")

        video_id = None

        # youtu.be/영상ID 형식
        if host == "youtu.be":
            video_id = parsed_url.path.lstrip("/").split("/")[0]

        # youtube.com 형식
        elif host in {"youtube.com", "music.youtube.com"}:
            # youtube.com/watch?v=영상ID 형식
            if parsed_url.path == "/watch":
                query = parse_qs(parsed_url.query)
                video_id = query.get("v", [None])[0]

            # shorts, embed, live 형식도 함께 처리합니다.
            elif parsed_url.path.startswith(("/shorts/", "/embed/", "/live/")):
                path_parts = parsed_url.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    video_id = path_parts[1]

        # 유튜브 영상 ID는 영문, 숫자, _, -로 이루어진 11자리입니다.
        if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return video_id

    except Exception:
        return None

    return None


# ---------------------------------------------------------
# YouTube Data API에서 댓글을 가져오는 함수
# ---------------------------------------------------------
def fetch_youtube_comments(video_id: str, api_key: str) -> list[dict]:
    """
    YouTube Data API v3의 commentThreads 창구에서
    상위 댓글을 최대 100개 가져옵니다.
    """

    api_url = "https://www.googleapis.com/youtube/v3/commentThreads"

    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 100,
        "order": "relevance",
        "textFormat": "plainText",
        "key": api_key,
    }

    response = requests.get(
        api_url,
        params=params,
        timeout=15,
    )

    # 400, 403, 404 등의 HTTP 오류가 있으면 예외를 발생시킵니다.
    response.raise_for_status()

    data = response.json()
    comments = []

    for item in data.get("items", []):
        top_comment = item["snippet"]["topLevelComment"]["snippet"]

        comments.append(
            {
                "댓글": top_comment.get("textOriginal", ""),
                "좋아요 수": int(top_comment.get("likeCount", 0)),
            }
        )

    return comments


# ---------------------------------------------------------
# 댓글 전체를 단어로 나누는 함수
# ---------------------------------------------------------
def extract_words(comments: pd.Series) -> list[str]:
    """
    댓글 전체에서 한국어와 영어 단어를 추출합니다.

    - 영어는 모두 소문자로 바꿉니다.
    - 한 글자짜리 단어는 제외합니다.
    """

    all_words = []

    for comment in comments.fillna("").astype(str):
        normalized_comment = comment.lower()

        # 한국어 또는 영어가 연속된 부분을 단어로 봅니다.
        words = re.findall(r"[가-힣A-Za-z]+", normalized_comment)

        # 한 글자짜리 단어는 제외합니다.
        words = [word for word in words if len(word) >= 2]

        all_words.extend(words)

    return all_words


# ---------------------------------------------------------
# 댓글 전체에서 자주 나온 단어를 세는 함수
# ---------------------------------------------------------
def count_top_words(comments: pd.Series, top_n: int = 20) -> pd.DataFrame:
    """
    모든 댓글을 단어로 나누고 자주 나온 단어를 셉니다.

    - 한국어와 영어 단어를 모두 찾습니다.
    - 영어는 대문자와 소문자를 같은 단어로 처리합니다.
    - 한 글자짜리 단어는 제외합니다.
    """

    all_words = extract_words(comments)
    word_counts = Counter(all_words).most_common(top_n)

    return pd.DataFrame(
        word_counts,
        columns=["단어", "빈도"],
    )


# ---------------------------------------------------------
# 한글 폰트 파일을 내려받는 함수
# ---------------------------------------------------------
@st.cache_resource
def download_korean_font() -> str | None:
    """
    워드클라우드에서 한글이 깨지지 않도록
    나눔고딕 폰트 파일을 내려받습니다.

    성공하면 폰트 파일 경로를 반환하고,
    실패하면 None을 반환합니다.
    """

    font_url = (
        "https://raw.githubusercontent.com/google/fonts/main/"
        "ofl/nanumgothic/NanumGothic-Regular.ttf"
    )

    font_dir = Path(".streamlit_fonts")
    font_path = font_dir / "NanumGothic-Regular.ttf"

    # 이미 폰트 파일이 있으면 다시 내려받지 않습니다.
    if font_path.exists() and font_path.stat().st_size > 0:
        return str(font_path)

    try:
        font_dir.mkdir(parents=True, exist_ok=True)

        response = requests.get(
            font_url,
            timeout=20,
        )
        response.raise_for_status()

        font_path.write_bytes(response.content)

        # 파일이 비어 있으면 다운로드 실패로 처리합니다.
        if font_path.stat().st_size == 0:
            font_path.unlink(missing_ok=True)
            return None

        return str(font_path)

    except (requests.exceptions.RequestException, OSError):
        return None


# ---------------------------------------------------------
# 워드클라우드 이미지를 만드는 함수
# ---------------------------------------------------------
def make_wordcloud_image(
    comments: pd.Series,
    font_path: str,
):
    """
    댓글 전체를 이용해 워드클라우드 이미지를 만듭니다.

    matplotlib은 사용하지 않고, WordCloud가 만든
    PIL 이미지 객체를 그대로 반환합니다.
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
# 입력창과 분석 결과의 세션 상태 초기화
# ---------------------------------------------------------
if "youtube_url" not in st.session_state:
    st.session_state.youtube_url = EXAMPLE_1

if "comments_df" not in st.session_state:
    st.session_state.comments_df = None

if "result_video_id" not in st.session_state:
    st.session_state.result_video_id = None


# ---------------------------------------------------------
# 예시 버튼
# ---------------------------------------------------------
st.subheader("영상 링크 입력")

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


# ---------------------------------------------------------
# 유튜브 링크 입력창
# ---------------------------------------------------------
youtube_url = st.text_input(
    "유튜브 영상 링크",
    key="youtube_url",
    placeholder="https://www.youtube.com/watch?v=...",
    label_visibility="collapsed",
)

analyze_button = st.button(
    "댓글 가져오기",
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

    # Streamlit Cloud의 비밀 금고에서 API 키를 읽습니다.
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
        with st.spinner("유튜브 댓글을 가져오는 중입니다..."):
            comments = fetch_youtube_comments(video_id, api_key)

    except requests.exceptions.Timeout:
        st.error(
            "유튜브 서버의 응답이 늦어 댓글을 가져오지 못했습니다. "
            "잠시 후 다시 시도해 주세요."
        )
        st.stop()

    except requests.exceptions.HTTPError as error:
        status_code = error.response.status_code if error.response else None

        api_message = ""

        try:
            error_data = error.response.json()
            api_message = error_data.get("error", {}).get("message", "")
        except Exception:
            pass

        if status_code == 403:
            st.error(
                "댓글을 가져올 수 없습니다. 댓글이 비활성화된 영상이거나, "
                "API 키 설정 또는 YouTube Data API 사용 권한을 확인해야 합니다."
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

    # 댓글을 데이터프레임으로 만들고 좋아요 수가 많은 순으로 정렬합니다.
    comments_df = pd.DataFrame(comments)

    comments_df = comments_df.sort_values(
        by="좋아요 수",
        ascending=False,
    ).reset_index(drop=True)

    # 순번 열을 따로 만들어 CSV 파일에도 포함되게 합니다.
    comments_df.insert(
        0,
        "순번",
        range(1, len(comments_df) + 1),
    )

    # 분석 결과를 세션 상태에 저장합니다.
    # 이렇게 하면 CSV 다운로드 버튼을 눌러도 결과가 유지됩니다.
    st.session_state.comments_df = comments_df
    st.session_state.result_video_id = video_id

    st.success("댓글을 성공적으로 가져왔습니다.")


# ---------------------------------------------------------
# 저장된 분석 결과 표시
# ---------------------------------------------------------
if st.session_state.comments_df is not None:
    comments_df = st.session_state.comments_df
    video_id = st.session_state.result_video_id

    metric_col1, metric_col2 = st.columns([1, 2])

    with metric_col1:
        st.metric(
            label="가져온 댓글 수",
            value=f"{len(comments_df):,}개",
        )

    with metric_col2:
        st.info(
            f"영상 ID: `{video_id}`  \n"
            "댓글은 YouTube API의 relevance 기준으로 가져온 뒤, "
            "좋아요 수가 많은 순으로 다시 정렬했습니다."
        )

    # -----------------------------------------------------
    # CSV 다운로드
    # -----------------------------------------------------
    st.subheader("댓글 데이터 내려받기")

    # utf-8-sig를 사용하면 엑셀에서도 한글이 깨질 가능성이 낮아집니다.
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

    # -----------------------------------------------------
    # 댓글 목록
    # -----------------------------------------------------
    st.subheader("댓글 목록")

    st.dataframe(
        comments_df,
        use_container_width=True,
        hide_index=True,
        height=600,
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
        },
    )

    # -----------------------------------------------------
    # 자주 나온 단어 분석
    # -----------------------------------------------------
    st.subheader("자주 나온 단어 상위 20개")
    st.caption(
        "댓글 전체를 한국어와 영어 단어로 나누어 집계했습니다. "
        "한 글자짜리 단어는 제외했습니다."
    )

    top_words_df = count_top_words(
        comments_df["댓글"],
        top_n=20,
    )

    if top_words_df.empty:
        st.warning(
            "두 글자 이상인 단어를 찾지 못했습니다."
        )
    else:
        # 가로 막대그래프에서는 작은 값부터 정렬하면
        # 가장 큰 값이 그래프의 맨 위에 표시됩니다.
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
            margin=dict(
                l=20,
                r=40,
                t=20,
                b=20,
            ),
            yaxis_title=None,
            xaxis_title="등장 횟수",
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

    # -----------------------------------------------------
    # 워드클라우드
    # -----------------------------------------------------
    st.subheader("댓글 워드클라우드")
    st.caption(
        "댓글 전체에서 두 글자 이상인 한국어와 영어 단어를 추출해 "
        "워드클라우드로 표시합니다."
    )

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
            # WordCloud가 만든 PIL 이미지를 화면에 바로 표시합니다.
            # matplotlib은 사용하지 않습니다.
            st.image(
                wordcloud_image,
                use_container_width=True,
            )
