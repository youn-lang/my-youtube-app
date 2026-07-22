import re
from urllib.parse import urlparse, parse_qs

import pandas as pd
import requests
import streamlit as st


# ---------------------------------------------------------
# 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="유튜브 댓글 분석기",
    page_icon="💬",
    layout="wide",
)

st.title("💬 유튜브 댓글 분석기")
st.caption("1단계 · 유튜브 영상 링크에서 댓글 최대 100개 가져오기")


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
    """

    if not url:
        return None

    # 앞뒤 공백 제거
    url = url.strip()

    # 사용자가 프로토콜(http:// 또는 https://) 없이 입력한 경우를 처리합니다.
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed_url = urlparse(url)
        host = parsed_url.netloc.lower()

        # www. 또는 m. 같은 앞부분을 제거해 비교하기 쉽게 만듭니다.
        host = host.removeprefix("www.")
        host = host.removeprefix("m.")

        video_id = None

        # youtu.be 형식: 주소 경로의 첫 부분이 영상 ID입니다.
        if host == "youtu.be":
            video_id = parsed_url.path.lstrip("/").split("/")[0]

        # youtube.com/watch 형식: v 파라미터가 영상 ID입니다.
        elif host in {"youtube.com", "music.youtube.com"}:
            if parsed_url.path == "/watch":
                query = parse_qs(parsed_url.query)
                video_id = query.get("v", [None])[0]

            # 아래 형식도 함께 처리합니다.
            # https://www.youtube.com/shorts/영상ID
            # https://www.youtube.com/embed/영상ID
            elif parsed_url.path.startswith(("/shorts/", "/embed/", "/live/")):
                parts = parsed_url.path.strip("/").split("/")
                if len(parts) >= 2:
                    video_id = parts[1]

        # 유튜브 영상 ID는 일반적으로 11자리입니다.
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
    YouTube Data API v3의 commentThreads 창구를 이용해
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

    # 응답이 늦거나 멈추는 상황을 방지하기 위해 timeout을 지정합니다.
    response = requests.get(api_url, params=params, timeout=15)

    # HTTP 오류가 있으면 아래에서 상세 내용을 확인할 수 있도록 예외를 발생시킵니다.
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
# 입력창 상태 초기화
# ---------------------------------------------------------
if "youtube_url" not in st.session_state:
    st.session_state.youtube_url = EXAMPLE_1


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
    # 1. 링크에서 영상 ID를 추출합니다.
    video_id = extract_video_id(youtube_url)

    if not video_id:
        st.error(
            "유효한 유튜브 영상 링크를 확인하지 못했습니다. "
            "youtu.be 주소 또는 youtube.com/watch 주소를 입력해 주세요."
        )
        st.stop()

    # 2. Streamlit 비밀 금고에서 API 키를 읽습니다.
    try:
        api_key = st.secrets["YOUTUBE_API_KEY"]
    except KeyError:
        st.error(
            "YouTube API 키가 설정되지 않았습니다. "
            "Streamlit Cloud의 Secrets에 "
            '`YOUTUBE_API_KEY = "발급받은_API_키"` 형식으로 등록해 주세요.'
        )
        st.stop()

    # 3. API에 요청해 댓글을 가져옵니다.
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

        # API가 보내온 오류 메시지가 있으면 읽어 봅니다.
        api_message = ""
        try:
            error_data = error.response.json()
            api_message = (
                error_data.get("error", {})
                .get("message", "")
            )
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
                "요청 형식이 올바르지 않습니다. 유튜브 영상 링크를 다시 확인해 주세요."
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

    # 4. 댓글이 한 건도 없을 때 안내합니다.
    if not comments:
        st.warning(
            "가져올 수 있는 댓글이 없습니다. "
            "댓글이 없는 영상이거나 댓글 작성이 막혀 있을 수 있습니다."
        )
        st.stop()

    # 5. 데이터프레임으로 바꾸고 좋아요가 많은 순으로 정렬합니다.
    comments_df = pd.DataFrame(comments)
    comments_df = comments_df.sort_values(
        by="좋아요 수",
        ascending=False,
    ).reset_index(drop=True)

    # 표에 순번을 추가합니다.
    comments_df.index = comments_df.index + 1
    comments_df.index.name = "순번"

    st.success("댓글을 성공적으로 가져왔습니다.")

    # 가져온 댓글 개수를 큰 지표 카드로 표시합니다.
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

    st.subheader("댓글 목록")

    # 댓글 전체가 잘 보이도록 표의 높이를 넉넉하게 지정합니다.
    st.dataframe(
        comments_df,
        use_container_width=True,
        height=600,
        column_config={
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
