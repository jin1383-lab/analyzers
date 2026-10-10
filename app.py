import streamlit as st
from google import genai
import yt_dlp

# 페이지 설정
st.set_page_config(page_title="유튜브 타겟 및 키워드 통합 분석기", page_icon="🎯", layout="wide")

st.title("🎯 유튜브 콘텐츠 & 채널 타겟 분석기")
st.markdown("유튜브 개별 영상 또는 채널 주소를 입력하면 AI가 시청자층(성별, 연령대, 시간대)과 글로벌 키워드를 분석합니다.")

# 사이드바: API 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google Gemini API Key", type="password")
    st.markdown("---")
    st.markdown("💡 **팁:** `yt-dlp`를 이용해 유튜브 메타데이터를 수집합니다.")

# 탭 구성 (개별 영상 분석 vs 채널 일괄 분석)
tab1, tab2 = st.tabs(["🎬 개별 영상 분석", "📺 채널 일괄 분석"])

# --- TAB 1: 개별 영상 분석 ---
with tab1:
    st.subheader("개별 유튜브 영상 타겟 분석")
    video_url = st.text_input("유튜브 영상 URL을 입력하세요", placeholder="https://youtu.be/...", key="video_input")

    if st.button("영상 분석 시작", type="primary", key="btn_video"):
        if not api_key:
            st.error("Google Gemini API Key를 입력해주세요.")
        elif not video_url:
            st.error("유튜브 영상 URL을 입력해주세요.")
        else:
            with st.spinner("유튜브 영상 정보를 수집하고 AI가 분석 중입니다..."):
                try:
                    ydl_opts = {'extract_flat': False, 'skip_download': True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                        title = info.get('title', '')
                        description = info.get('description', '')
                        tags = info.get('tags', [])
                        channel_name = info.get('uploader', '')

                    client = genai.Client(api_key=api_key)
                    prompt = f"""
                    다음 유튜브 영상 정보를 바탕으로 상세한 타겟 분석과 키워드를 도출해줘.
                    
                    [영상 정보]
                    - 채널명: {channel_name}
                    - 영상 제목: {title}
                    - 설명: {description[:1000]}
                    - 태그: {', '.join(tags[:20]) if tags else '없음'}
                    
                    다음 항목에 맞춰 깔끔한 마크다운 형식으로 답변해줘:
                    1. 핵심 키워드 (한국어, 영어, 일본어)
                    2. 시청자 성별 비율 (예: 남성 85% / 여성 15% 추정 및 이유)
                    3. 주력 나이대 (예: 30대~50대 및 이유)
                    4. 주요 시청 시간대 (예: 평일 저녁, 주말 낮 등 및 이유)
                    5. 연관 키워드 (5개 이상)
                    6. 추천 연관 해시태그 (# 포함 5개 이상)
                    """

                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )

                    st.success("분석이 완료되었습니다!")
                    
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.subheader("📺 영상 기본 정보")
                        st.markdown(f"**채널명:** {channel_name}")
                        st.markdown(f"**제목:** {title}")
                    
                    with col2:
                        st.subheader("📊 AI 타겟 분석 결과")
                        st.markdown(response.text)

                except Exception as e:
                    st.error(f"분석 중 오류가 발생했습니다: {e}")

# --- TAB 2: 채널 일괄 분석 ---
with tab2:
    st.subheader("유튜브 채널 최근 영상 일괄 분석")
    channel_url = st.text_input("유튜브 채널 URL을 입력하세요", placeholder="https://www.youtube.com/@ChannelName", key="channel_input")
    max_videos = st.slider("분석할 최근 영상 개수", min_value=3, max_value=10, value=5)

    if st.button("채널 분석 시작", type="primary", key="btn_channel"):
        if not api_key:
            st.error("Google Gemini API Key를 입력해주세요.")
        elif not channel_url:
            st.error("유튜브 채널 URL을 입력해주세요.")
        else:
            with st.spinner("채널의 최근 영상 목록을 수집하고 AI가 분석 중입니다..."):
                try:
                    ydl_opts = {
                        'extract_flat': 'in_playlist',
                        'playlistend': max_videos,
                        'skip_download': True
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        channel_info = ydl.extract_info(channel_url, download=False)
                        entries = channel_info.get('entries', [])
                    
                    videos_data = []
                    for entry in entries:
                        v_title = entry.get('title', '')
                        v_url = entry.get('url', '')
                        videos_data.append(f"- 제목: {v_title} (URL: {v_url})")

                    client = genai.Client(api_key=api_key)
                    prompt = f"""
                    다음은 특정 유튜브 채널의 최근 업로드 영상 목록이야. 이 채널의 전체적인 성격과 타겟층을 종합적으로 분석해줘.
                    
                    [최근 영상 목록]
                    {'\n'.join(videos_data)}
                    
                    다음 항목에 맞춰 깔끔한 마크다운 형식으로 답변해줘:
                    1. 메인 타겟층 (성별 비율, 주력 나이대, 주요 시청 시간대 및 이유)
                    2. 채널 전반의 핵심 키워드 (한국어, 영어, 일본어)
                    3. 시청자들이 이 채널을 찾는 이유 및 공통 관심사
                    4. 추천 연관 해시태그 (# 포함 5개 이상)
                    """

                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )

                    st.success("채널 분석 완료!")
                    st.markdown(response.text)

                except Exception as e:
                    st.error(f"분석 중 오류가 발생했습니다: {e}")