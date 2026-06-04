import os
import sys
import re
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi

# [필수 고도화] Streamlit Cloud 환경에서 내부 모듈(analyzers) 인식 오류 방지
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# ==========================================
# 1. 데이터 수집 및 유틸리티 함수 정의
# ==========================================

def extract_video_id(url):
    """유튜브 URL에서 11자리 Video ID 추출 (다양한 URL 포맷 대응)"""
    pattern = r'(?:v=|\/|be\/|embed\/)([0-9A-Za-z_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_video_transcript(video_id):
    """유튜브 영상에서 한국어 또는 영어 자막을 추출"""
    try:
        # 한국어 자막을 우선 시도하고, 없으면 영어 자막 자동 선택
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        full_text = " ".join([item['text'] for item in transcript_list])
        return full_text
    except Exception as e:
        return f"🚨 자막 추출 실패: {str(e)}\n(해당 영상에 추출 가능한 자막/자동생성 자막이 없을 수 있습니다.)"

def mock_ai_analysis(script_text):
    """
    [MVP 단계용 임시 함수] LLM API 연동 전 화면 출력을 확인하기 위한 가짜 데이터입니다.
    추후 이 부분에 OpenAI 또는 Gemini API 연동 코드를 삽입하시면 됩니다.
    """
    short_script = script_text[:100] + "..." if len(script_text) > 100 else script_text
    
    analysis_result = f"""
    ### 📊 AI가 분석한 이 영상의 떡상 포인트
    
    1. **⚡ 초반 이탈 방지 (Hooking) 분석**
       * 수집된 자막 초반부(`"{short_script}"`)를 분석한 결과, 시청자가 흥미를 느낄 만한 핵심 질문이나 자극적인 상황을 5초 이내에 배치하여 이탈률을 방지했습니다.
    
    2. **🎨 스토리라인 및 구성 특징**
       * 불필요한 서론을 과감히 생략하고 바로 본론으로 진입하는 '숏폼 스타일'의 빠른 템포를 가지고 있습니다.
       * 문제 제기 ➡️ 해결책 제시 ➡️ 행동 유도(구독/좋아요)의 기승전결이 명확합니다.
    
    3. **✍️ 카피라이팅 및 키워드**
       * 대중들이 검색창에 자주 입력할 만한 직관적이고 직설적인 어휘를 반복적으로 사용하여 알고리즘 추천 가능성을 높였습니다.
    
    > **💡 한 줄 총평:** 시청자의 시간을 낭비하지 않는 밀도 높은 정보 구성과 명확한 썸네일 카피가 시너지를 내어 성공한 케이스입니다.
    """
    return analysis_result

# ==========================================
# 2. Streamlit UI 메인 화면 구성
# ==========================================

st.set_page_config(page_title="유튜브 떡상 분석기", layout="wide", page_icon="🚀")

st.title("🚀 유튜브 떡상 요인 분석기")
st.caption("분석하고 싶은 성공한 유튜브 영상의 주소를 입력하면 AI가 핵심 흥행 포인트를 짚어줍니다.")
st.markdown("---")

# 사용자 URL 입력창
video_url = st.text_input(
    "유튜브 영상 URL을 입력하세요", 
    placeholder="https://www.youtube.com/watch?v=..."
)

# 분석 시작 버튼
if st.button("성공 포인트 분석하기 🔍", type="primary"):
    if video_url:
        video_id = extract_video_id(video_url)
        
        if video_id:
            # 로딩 애니메이션 시작
            with st.spinner("유튜브 데이터를 분석 중입니다. 잠시만 기다려 주세요..."):
                
                # 1. 자막 수집
                script = get_video_transcript(video_id)
                
                # 에러 발생 시 예외 처리
                if "🚨 자막 추출 실패" in script:
                    st.error
