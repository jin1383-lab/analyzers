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
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    YOUTUBE_KEY = st.secrets["YOUTUBE_API_KEY"]
    
    genai.configure(api_key=GEMINI_KEY)
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
    """YouTube API를 사용해 영상의 정보, 통계 및 설명(Description) 가져오기"""
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
            "description": item['snippet']['description'],
            "channel_title": item['snippet']['channelTitle'],
            "view_count": int(item['statistics'].get('viewCount', 0)),
            "like_count": int(item['statistics'].get('likeCount', 0)),
            "thumbnail": item['snippet']['thumbnails']['high']['url']
        }
        return metadata
    except Exception as e:
        raise RuntimeError(f"유튜브 메타데이터 로드 실패: {str(e)}")

def get_video_comments(video_id, max_results=30):
    """YouTube API를 사용해 시청자들의 실시간 인기 댓글 가져오기"""
    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=max_results
        )
        response = request.execute()
        
        comments = []
        for item in response.get('items', []):
            comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
            # html 태그 및 줄바꿈 가볍게 청소
            comment = re.sub(r'<[^>]*>', '', comment).strip()
            if comment:
                comments.append(comment)
        return comments
    except:
        # 🎯 에러가 났던 135번째 줄 부근입니다. 빈 리스트를 정상적으로 반환하도록 들여쓰기 블록을 맞췄습니다.
        return []

def get_video_transcript_pure_python(video_id):
    """유튜브 HTML에서 자막 추출 시도 (실패 시 빈 문자열 반환)"""
    try:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(
            video_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            
        if 'playerCaptionsTracklistRenderer' not in html:
            return ""
            
        captions_json_match = re.search(r'"playerCaptionsTracklistRenderer":\s*({.*?})\s*,\s*"videoDetails"', html)
        if not captions_json_match:
            captions_json_match = re.search(r'"playerCaptionsTracklistRenderer":\s*({.*?})\s*}', html)
            
        if captions_json_match:
            captions_json = json.loads(captions_json_match.group(1))
            caption_tracks = captions_json.get('captionTracks', [])
            if not caption_tracks:
                return ""
                
            target_track = caption_tracks[0]
            for track in caption_tracks:
                if 'ko' in track.get('languageCode', ''):
                    target_track = track
                    break
                    
            timedtext_url = target_track['baseUrl']
            if 'fmt=' not in timedtext_url:
                timedtext_url += '&fmt=json3'
            else:
                timedtext_url = re.sub(r'fmt=[^&]+', 'fmt=json3', timedtext_url)
                
            req_text = urllib.request.Request(timedtext_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req_text) as res_text:
                caption_data = json.loads(res_text.read().decode('utf-8'))
                
            sentences = []
            for event in caption_data.get('events', []):
                if 'segs' in event:
                    text_segments = [seg['utf8'] for seg in event['segs'] if 'utf8' in seg]
                    sentences.append("".join(text_segments).strip())
                        
            full_text = " ".join(sentences)
            return re.sub(r'\s+', ' ', full_text).strip()
        return ""
    except:
        return ""

def analyze_with_gemini(title, description, script_text, comments_list):
    """자막 유무 및 다국어 댓글을 고려하여 Gemini 분석 수행 (한국어 답변 강제)"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        has_script = "있음" if script_text else "없음 (제공된 영상 설명과 댓글 위주로 분석 필요)"
        display_script = script_text if script_text else "자막 데이터가 제공되지 않은 영상입니다."
        comments_block = "\n".join(comments_list) if comments_list else "가져온 댓글이 없습니다."
        
        prompt = f"""
        당신은 글로벌 유튜브 알고리즘과 콘텐츠 마케팅 전문가입니다.
        제공된 유튜브 영상의 메타데이터와 데이터를 종합 분석하여 이 영상의 '떡상(흥행)' 핵심 성공 요인을 예리하게 분석해 주세요.
        
        [⚠️ 중요 지침]: 
        제공된 자막이나 댓글이 일본어, 영어 등 '외국어'로 되어 있더라도, 당신은 내용을 완벽히 파악한 뒤
        **최종 리포트는 무조건 이해하기 쉬운 깔끔한 '한국어'로만 작성**해야 합니다. 외국어 댓글 반응을 인용할 때도 한국어 번역을 곁들여 주세요.
        
        [영상 제목]: {title}
        [영상 설명]: {description[:1000]}
        [자막 유무]: {has_script}
        [영상 자막]: {display_script}
        [시청자 댓글 반응 샘플]:
        {comments_block}
        
        다음 구조에 맞춰 마크다운(Markdown) 형식으로 가독성 좋게 분석 리포트를 작성해 주세요:
        1. ⚡ **초반 시선 강탈(Hooking) 요인**: 제목, 썸네일 분위기, 그리고 영상 설명이나 자막 초반부를 토대로 시청자를 어떻게 유입시키고 붙잡았는지 분석해 주세요.
        2. 🎨 **콘텐츠 구성 및 포맷 특징**: 자막(대사) 혹은 댓글 흐름을 보아 유저들이 이 영상에 왜 몰입하고 끝까지 보는지 기승전결 구성을 설명해 주세요.
        3. 💬 **글로벌 시청자 반응 분석**: 제공된 댓글 반응을 분석하여(외국어인 경우 핵심 트렌드 번역 포함), 시청자들이 특히 어떤 포인트에 열광하거나 감동했는지 '참여 유도 요인'을 짚어주세요.
        4. 💡 **크리에이터를 위한 벤치마킹 한 줄 팁**: 이 영상의 성공 공식 중 내 채널에 바로 적용할 수 있는 가장 핵심적인 인사이트를 요약해 주세요.
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
st.caption("공식 YouTube API와 Gemini AI를 연동하여 다국어 자막과 글로벌 반응까지 실시간으로 정밀 분석합니다.")
st.markdown("---")

video_url = st.text_input(
    "분석할 유튜브 영상 URL을 입력하세요", 
    placeholder="https://www.youtube.com/watch?v=..."
)

if st.button("성공 포인트 정밀 분석하기 🔍", type="primary"):
    if video_url:
        video_id = extract_video_id(video_url)
        
        if video_id:
            with st.spinner("글로벌 데이터를 수집하고 Gemini AI가 번역 및 분석을 진행 중입니다..."):
                try:
                    # 1. 메타데이터 수집
                    meta = get_video_details(video_id)
                    if not meta:
                        st.error("영상을 찾을 수 없습니다. URL을 다시 확인해 주세요.")
                        st.stop()
                        
                    # 2. 데이터 수집 (자막 + 댓글)
                    script = get_video_transcript_pure_python(video_id)
                    comments_data = get_video_comments(video_id)
                    
                    # 3. Gemini AI 분석 수행 (다국어 처리 지침 포함)
                    analysis_report = analyze_with_gemini(meta['title'], meta['description'], script, comments_data)
                    
                    st.success("🎯 글로벌 트렌드 분석 완료!")
                    
                    col1, col2 = st.columns([1, 1.3])
                    
                    with col1:
                        st.subheader("📺 분석 대상 영상 정보")
                        st.image(meta['thumbnail'], use_container_width=True)
                        st.markdown(f"### **{meta['title']}**")
                        st.markdown(f"👤 **채널명:** {meta['channel_title']}")
                        st.markdown(f"👀 **조회수:** {meta['view_count']:,}회 | ❤️ **좋아요:** {meta['like_count']:,}개")
                        
                        st.video(video_url)
                        
                        # 자막 데이터 확인 창
                        with st.expander("📝 추출된 자막 데이터 상태"):
                            if script:
                                st.write(script)
                            else:
                                st.info("본 영상은 대사 자막이 추출되지 않아 영상 정보 및 댓글 기반으로 분석을 대체 진행했습니다.")
                                
                        # 수집된 원본 댓글 반응 확인 창
                        with st.expander("💬 수집된 시청자 댓글 반응 샘플"):
                            if comments_data:
                                for i, c in enumerate(comments_data, 1):
                                    st.markdown(f"**{i}.** {c}")
                            else:
                                st.info("댓글을 가져오지 못했거나 댓글 기능이 닫힌 영상입니다.")
                        
                    with col2:
                        st.subheader("💡 Gemini AI 흥행 요인 정밀 분석")
                        st.markdown(analysis_report)
                        
                except Exception as error:
                    st.error(f"🚨 작업 중 에러 발생: {str(error)}")
        else:
            st.error("올바른 형태의 유튜브 URL이 아닙니다.")
    else:
        st.warning("유튜브 URL을 입력해 주세요.")
