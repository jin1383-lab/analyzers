import streamlit as st
import yt_dlp
from google import genai
import os

# 페이지 설정
st.set_page_config(
    page_title="유튜브 콘텐츠 타겟 분석기",
    page_icon="🎯",
    layout="wide"
)

# st.secrets에서 API 키를 우선적으로 가져오고, 없으면 사이드바 입력창 표시
api_key = None
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
else:
    st.sidebar.header("설정")
    api_key = st.sidebar.text_input("Google Gemini API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.markdown("💡 **팁:** `yt-dlp`를 이용해 유튜브 메타데이터를 수집합니다.")

# 메인 타이틀
st.title("🎯 유튜브 콘텐츠 타겟 분석기")
st.markdown("유튜브 영상 주소를 입력하면 AI가 핵심 키워드와 해시태그를 분석합니다.")

def get_video_metadata(url):
    ydl_opts = {
        'extract_flat': False,
        'skip_download': True,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'title': info.get('title'),
            'description': info.get('description'),
            'tags': info.get('tags', []),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'uploader': info.get('uploader'),
            'duration': info.get('duration')
        }

def analyze_with_gemini(api_key, prompt_text):
    client = genai.Client(api_key=api_key)
    # 최신 권장 모델명으로 수정
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt_text,
    )
    return response.text

st.subheader("개별 유튜브 영상 분석")
video_url = st.text_input("유튜브 영상 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

if st.button("분석 시작", key="btn_single"):
    if not api_key:
        st.error("API Key가 설정되지 않았습니다. Streamlit Secrets 또는 사이드바에 키를 입력해주세요.")
    elif not video_url:
        st.warning("유튜브 영상 URL을 입력해주세요.")
    else:
        try:
            with st.spinner("유튜브 메타데이터 수집 및 AI 분석 중..."):
                meta = get_video_metadata(video_url)
                
                prompt = (
                    "다음 유튜브 영상 정보를 바탕으로 핵심 키워드와 해시태그를 분석해줘.\n\n"
                    f"[영상 정보]\n"
                    f"- 제목: {meta['title']}\n"
                    f"- 채널명: {meta['uploader']}\n"
                    f"- 설명: {str(meta['description'])[:500]}\n"
                    f"- 태그: {meta['tags']}\n"
                    f"- 조회수: {meta['view_count']}\n\n"
                    "[요청 사항]\n"
                    "1. 핵심 키워드 (한국어, 영어, 일본어 각 5개씩)\n"
                    "2. 추천 해시태그"
                )
                
                result = analyze_with_gemini(api_key, prompt)
                
                st.success("분석이 완료되었습니다!")
                st.markdown("### 📊 분석 결과")
                st.markdown(result)
                
        except Exception as e:
            st.error(f"분석 중 오류가 발생했습니다: {e}")
