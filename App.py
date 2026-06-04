import os
import sys
import re
import json
import urllib.request
import streamlit as st
from googleapiclient.discovery import build
import google.generativeai as genai

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
    """유튜브 URL에서 11자리 Video ID 추출"""
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

def get_video_transcript_pure_python(video_id):
    """
    [🚨 문제 해결을 위한 완전 우회 기법]
    문제가 되던 외부 youtube-transcript-api 라이브러리를 완전히 제거했습니다.
    유튜브 영상의 껍데기 HTML에서 자막 파일 주소(Timedtext URL)를 정규식으로 직접 솎아낸 뒤,
    XML 자막 데이터를 순수 텍스트로 가공하여 가져옵니다.
    """
    try:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 봇 차단을 피하기 위해 흔한 브라우저 헤더를 세팅합니다.
        req = urllib.request.Request(
            video_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            
        # 유튜브가 숨겨놓은 자막 기본 데이터 주소 캡처
        if 'playerCaptionsTracklistRenderer' not in html:
            raise RuntimeError("이 영상은 자막(CC) 정보가 내장되어 있지 않거나 차단된 영상입니다.")
            
        # 정규식으로 자막 JSON 덩어리 추출
        captions_json_match = re.search(r'"playerCaptionsTracklistRenderer":\s*({.*?})\s*,\s*"videoDetails"', html)
        if not captions_json_match:
            captions_json_match = re.search(r'"playerCaptionsTracklistRenderer":\s*({.*?})\s*}', html)
            
        if captions_json_match:
            captions_json = json.loads(captions_json_match.group(1))
            caption_tracks = captions_json.get('captionTracks', [])
            
            if not caption_tracks:
                raise RuntimeError("추출 가능한 자막 트랙이 비어 있습니다.")
                
            # 한국어(ko) 자막 트랙 우선 매칭, 없으면 첫 번째 자막 사용
            target_track = caption_tracks[0]
            for track in caption_tracks:
                if 'ko' in track.get('languageCode', ''):
                    target_track = track
                    break
                    
            # 자막 XML 주소 획득 후 찌르기
            timedtext_url = target_track['baseUrl']
            
            # 포맷을 기본 XML 대신 텍스트 파싱이 쉬운 json 형태(fmt=json3)로 강제 변환 요청
            if 'fmt=' not in timedtext_url:
                timedtext_url += '&fmt=json3'
            else:
                timedtext_url = re.sub(r'fmt=[^&]+', 'fmt=json3', timedtext_url)
                
            req_text = urllib.request.Request(timedtext_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req_text) as res_text:
                caption_data = json.loads(res_text.read().decode('utf-8'))
                
            # JSON 데이터에서 대사(text)만 깔끔하게 뽑아서 합치기
            sentences = []
            for event in caption_data.get('events', []):
                if 'segs' in event:
                    text_segments = [seg['utf8'] for seg in event['segs'] if 'utf8' in seg]
                    clean_text = "".join(text_segments).strip()
                    if clean_text:
                        sentences.append(clean_text)
                        
            full_text = " ".join(sentences)
            # 불필요한 줄바꿈 및 다중 공백 정리
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            return full_text
            
        else:
            raise RuntimeError("유튜브 플레이어 자막 렌더러 데이터를 분석할 수 없습니다.")
            
    except Exception as e:
        raise RuntimeError(f"순수 파이썬 우회 자막 수집 중 최종 실패: {str(e)}")

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
                    # 1. 데이터 수집 (YouTube API + 순수 파이썬 내부 자막 스크래핑)
                    meta = get_video_details(video_id)
                    if not meta:
                        st.error("영상을 찾을 수 없습니다. URL을 다시 확인해 주세요.")
                        st.stop()
                        
                    script = get_video_transcript_pure_python(video_id)
                    
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
