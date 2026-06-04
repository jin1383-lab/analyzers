import re
from youtube_transcript_api import YouTubeTranscriptApi

def extract_video_id(url):
    """유튜브 URL에서 11자리 Video ID 추출"""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_video_transcript(video_id):
    """영상 자막(Script) 가져오기"""
    try:
        # 한국어 자막 우선 추출, 없으면 영어
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        # 텍스트만 하나로 합치기
        full_text = " ".join([item['text'] for item in transcript_list])
        return full_text
    except Exception as e:
        return f"자막을 가져올 수 없습니다: {str(e)}"
