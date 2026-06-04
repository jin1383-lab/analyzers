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
        return comments # 분석과 UI 출력을 위해 리스트 형태로 반환 변경
    except:
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
