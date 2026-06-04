import os
import sys
import re
import streamlit as st
from googleapiclient.discovery import build
import google.generativeai as genai
import youtube_transcript_api

# Streamlit Cloud 환경에서 내부 모듈 인식 오류 방지
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# ==========================================
# 0. API 키 인증 및 초기화
# ==========================================
try:
    # Streamlit Secrets에서 키 안전하게 로드
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    YOUTUBE_KEY = st.secrets["YOUTUBE_API_KEY"]
    
    # Gemini AI 설정
    genai.configure(api_key=GEMINI_KEY)
    # YouTube Data API 빌드
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_KEY)
except Exception as e:
    st.error("🚨 API 키 설정 오류: .streamlit/secrets.toml 파일이나 Streamlit Secrets 설정을 확인해 주세요.")
    st.stop()

# ==========================================
# 1. 핵심 비즈니스 로직 함수 정의
# ==========================================

def extract_video_id(url):
    """유튜브 URL에서 11자리 Video ID 추출 (주소 뒤 공백/파라미터 제거 보강)"""
    url = url.strip()
    pattern = r'(?:v=|\/|be\/|embed\/|shorts\/)([0-9A-Za-z_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_video_details(video_id):
    """YouTube API를 사용해 영상의 통계 정보 및 메타데이터 가져오기"""
    try:
        request = youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        )
        response = request.execute()
        
        if not response['items']:
            return None
            
        item = response['items'][0]
        metadata = {
            "title": item['snippet']['title'],
            "channel_title": item['snippet']['channelTitle'],
            "view_count": int(item['statistics'].get('viewCount', 0)),
            "like_count": int(item['statistics'].get('likeCount', 0)),
            "thumbnail": item['snippet']['thumbnails']['high']['url']
        }
        return metadata
    except Exception as e:
        raise RuntimeError(f"유튜브 메타데이터 로드 실패: {str(e)}")

def get_video_transcript(video_id):
    """
    [우회 로직 적용]has no attribute 'get_transcript' 에러를 완벽히 우회하기 위해 
    list_transcripts() 객체를 통해 내부 자막 딕셔너리를 직접 파싱합니다.
    """
    try:
        # 1. 영상에 등록된 모든 자막 리스트를 먼저 가져옵니다 (가장 안전한 메서드)
        transcript_list_obj = youtube_transcript_api.YouTubeTranscriptApi.list_transcripts(video_id)
        
        try:
            # 한국어 자막 탐색 수집
            srt = transcript_list_obj.find_transcript(['ko'])
        except:
            try:
                # 한국어가 없으면 영어 자막 탐색
                srt = transcript_list_obj.find_transcript(['en'])
            except:
                # 둘 다 없으면 자동으로 생성된 첫 번째 자막 강제 선택
                srt = transcript_list_obj.find_generated_transcript(['ko', 'en'])
                
        # 2. 선택된 자막 데이터를 텍스트로 합치기
        data = srt.fetch()
        full_text = " ".join([item['text'] for item in data])
        return full_text

    except Exception as e:
        error_msg = str(e)
        if "Subtitles are disabled" in error_msg or "TranscriptsDisabled" in error_msg:
            raise RuntimeError("이 영상은 크리에이터가 자막(CC) 기능을 완전히 비활성화한 영상입니다.")
        elif "No transcript found" in error_msg or "NoTranscriptFound" in error_msg:
            raise RuntimeError("이 영상에는 분석할 수 있는 한국어 또는 영어 자막이 존재하지 않습니다.")
        else:
            raise RuntimeError(f"자막 모듈 우회 수집 중 오류 발생: {error_msg}")

def analyze_with_gemini(title, script_text):
    """Gemini API를 사용해 영상의 성공 포인트를 분석"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        당신은 유튜브 알고리즘과 콘텐츠 마케팅 전문가입니다.
        제공된 유튜브 영상의 제목과 자막(대사 전체)을 바탕으로 이 영상이 '떡상(흥행)'할 수 있었던 핵심 성공 요인을 예리하게 분석해 주세요.
        
        [영상 제목]: {title}
        [영상 자막]: {script_text}
        
        다음 구조에 맞춰 마크다운(Markdown) 형식으로 가독성 좋게 분석 리포트를 작성해 주세요:
        1. ⚡ **초반 이탈 방지(Hooking) 구조 분석**: 도입부(처음 30초~1분)에서 시청자를 어떻게 붙잡았는지 구체적인 대사나 흐름을 짚어주세요.
        2. 🎨 **스토리라인 및 구성 특징**: 본론 전개 방식과 시청자가 몰입하게 만드는 이 영상만의 플롯 구조를 설명해 주세요.
        3. ✍️ **카피라이팅 및 키워드 전략**: 제목과 대사에서 알고리즘의 선택을 유도하거나 대중의 심리를 자극 시킨 치트키 키워드를 분석해 주세요.
        4. 💡 **크리에이터를 위한 벤치마킹 한 줄 팁**: 이 영상에서 우리가 내 채널에 바로 적용할 수 있는 가장 핵심적인 인사이트를 요약해 주세요.
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"🚨 Gemini AI 분석 중 오류가 발생했습니다: {str(e)}"

# ==========================================
# 2. Streamlit UI 메인 화면 구성
# ==========================================

st.set_page_config(page_title="유튜브 떡상 분석기 PRO", layout="wide", page_icon="🚀")

st.title("🚀 유튜브 떡상 요인 분석기 PRO")
st.caption("공식 YouTube API와 Gemini AI를 연동하여 영상의 흥행 요인을 실시간으로 정밀 분석합니다.")
st.markdown("---")

# 사용자 URL 입력창
video_url = st.text_input(
    "분석할 유튜브 영상 URL을 입력하세요", 
    placeholder="https://www.youtube.com/watch?v=..."
)

# 분석 시작 버튼
if st.button("성공 포인트 정밀 분석하기 🔍", type="primary"):
    if video_url:
        video_id = extract_video_id(video_url)
        
        if video_id:
            with st.spinner("유튜브 데이터를 수집하고 Gemini AI가 떡상 요인을 도출하는 중입니다..."):
                try:
                    # 1. 데이터 수집 (YouTube API + 자막 API 우회기법)
                    meta = get_video_details(video_id)
                    if not meta:
                        st.error("영상을 찾을 수 없습니다. URL을 다시 확인해 주세요.")
                        st.stop()
                        
                    script = get_video_transcript(video_id)
                    
                    # 2. Gemini AI 분석 수행
                    analysis_report = analyze_with_gemini(meta['title'], script)
                    
                    st.success("🎯 분석이 완료되었습니다!")
                    
                    # 3. 화면 레이아웃 대시보드 구성
                    col1, col2 = st.columns([1, 1.3])
                    
                    with col1:
                        st.subheader("📺 분석 대상 영상 정보")
                        st.image(meta['thumbnail'], use_container_width=True)
                        st.markdown(f"### **{meta['title']}**")
                        st.markdown(f"👤 **채널명:** {meta['channel_title']}")
                        st.markdown(f"👀 **조회수:** {meta['view_count']:,}회 | ❤️ **좋아요:** {meta['like_count']:,}개")
                        
                        st.video(video_url)
                        
                        with st.expander("📝 원본 자막 텍스트 확인"):
                            st.write(script)
                        
                    with col2:
                        st.subheader("💡 Gemini AI 흥행 요인 정밀 분석")
                        st.markdown(analysis_report)
                        
                except Exception as error:
                    st.error(f"🚨 작업 중 에러 발생: {str(error)}")
        else:
            st.error("올바른 형태의 유튜브 URL이 아닙니다.")
    else:
        st.warning("유튜브 URL을 입력해 주세요.")
