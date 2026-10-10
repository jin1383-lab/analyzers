import streamlit as st
import yt_dlp
from google import genai
import os

# 페이지 설정
st.set_page_config(
    page_title="유튜브 콘텐츠 & 채널 타겟 분석기",
    page_icon="🎯",
    layout="wide"
)

# 사이드바 설정
st.sidebar.header("설정")
api_key = st.sidebar.text_input("Google Gemini API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.markdown("💡 **팁:** `yt-dlp`를 이용해 유튜브 메타데이터를 수집합니다.")

# 메인 타이틀
st.title("🎯 유튜브 콘텐츠 & 채널 타겟 분석기")
st.markdown("유튜브 개별 영상 또는 채널 주소를 입력하면 AI가 시청자층(성별, 연령대, 시간대)과 글로벌 키워드를 분석합니다.")

# 탭 구성
tab1, tab2 = st.tabs(["🎬 개별 영상 분석", "📺 채널 일괄 분석"])

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
    # 최신 지원 모델 지정
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
    )
    return response.text

with tab1:
    st.subheader("개별 유튜브 영상 타겟 분석")
    video_url = st.text_input("유튜브 영상 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")
    
    if st.button("분석 시작", key="btn_single"):
        if not api_key:
            st.error("좌측 사이드바에 Google Gemini API Key를 입력해주세요.")
        elif not video_url:
            st.warning("유튜브 영상 URL을 입력해주세요.")
        else:
            try:
                with st.spinner("유튜브 메타데이터 수집 및 AI 분석 중..."):
                    meta = get_video_metadata(video_url)
                    
                    prompt = f"""
                    다음 유튜브 영상 정보를 바탕으로 주요 시청자층과 키워드를 분석해줘.
                    
                    [영상 정보]
                    - 제목: {meta['title']}
                    - 채널명: {meta['uploader']}
                    - 설명: {meta['description'][:500]}
                    - 태그: {meta['tags']}
                    - 조회수: {meta['view_count']}
                    
                    [요청 사항]
                    1
