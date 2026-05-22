import os
import re
import logging
import asyncio
from pathlib import Path
from openai import OpenAI
import yt_dlp
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create audio folder if it doesn't exist
AUDIO_FOLDER = os.path.join(os.getcwd(), "audio")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not os.getenv("OPENAI_API_KEY"):
    logger.warning("OPENAI_API_KEY not found in environment variables!")

def sanitize_filename(title: str) -> str:
    """Create a filesystem-safe filename from the video title"""
    # Remove invalid filename characters
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    # Trim to reasonable length
    if len(safe_title) > 100:
        safe_title = safe_title[:100]
    return safe_title.strip()

def download_video_audio(url: str) -> str:
    """Download audio from YouTube video and return the file path"""
    # Ensure audio directory exists
    if not os.path.exists(AUDIO_FOLDER):
        os.makedirs(AUDIO_FOLDER)
    
    # yt-dlp options to download audio and convert to mp3
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'outtmpl': os.path.join(AUDIO_FOLDER, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'merge_output_format': 'mp3',
        'keepvideo': False,
    }
    
    # Download the audio using yt-dlp
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Extract video information without downloading
            info = ydl.extract_info(url, download=False)
            
            # Get the title from the metadata
            raw_title = info.get('title', 'Unknown Title')
            safe_title = sanitize_filename(raw_title)
            
            logger.info(f"Downloading audio for: {safe_title}")
            
            # Download the video
            ydl.download([url])
            
            # Construct the expected file path
            # Note: yt-dlp may modify the filename slightly
            file_path = os.path.join(AUDIO_FOLDER, f"{safe_title}.mp3")
            
            # If the exact filename doesn't exist, try to find the file
            if not os.path.exists(file_path):
                # Look for files with similar names
                for file in os.listdir(AUDIO_FOLDER):
                    if file.endswith(".mp3") and raw_title.lower() in file.lower():
                        file_path = os.path.join(AUDIO_FOLDER, file)
                        break
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Downloaded file not found at expected location: {file_path}")
                
            return file_path
            
        except Exception as e:
            logger.error(f"Error downloading video audio: {str(e)}")
            raise

def transcribe_mp3_file(filename: str) -> str:
    """Transcribe an audio file using OpenAI's Whisper API"""
    logger.info(f"Transcribing file: {filename}")
    
    try:
        with open(filename, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        
        # Verify we got a text response
        if not hasattr(transcription, 'text') or not transcription.text:
            raise ValueError("Transcription response missing text field")
            
        logger.info(f"Transcription complete: {len(transcription.text)} characters")
        return transcription.text
        
    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}")
        raise

def ask_gpt_for_summary(transcript: str, url: str) -> str:
    """Generate a summary of the transcript using GPT"""
    logger.info("Generating summary with GPT")
    
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You are helping me summarize and write actionable insights from transcriptions of youtube videos."},
                {"role": "user", "content": f"Hello! Can you help me summarize and write a detailed, yet concise document from this transcript? \n {transcript}\n\nAlso at the bottom of the summary can you put this url: {url} underneath a h2 md heading like this ## Source\n![]({url})"}
            ]
        )
        
        # Verify we got a content response
        if not completion.choices or len(completion.choices) == 0:
            raise ValueError("No choices in completion response")
            
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("Empty content in completion response")
            
        logger.info(f"Summary generation complete: {len(content)} characters")
        return content
        
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        raise

async def process_youtube_summary(url: str, detail: str) -> str:
    """
    Process a YouTube video to generate a summary
    Returns the summary text or raises an exception on failure
    """
    audio_file_path = None
    
    try:
        logger.info(f"Processing YouTube summary for URL: {url} with detail level: {detail}")
        
        # Run download in a thread pool since it's a blocking operation
        audio_file_path = await asyncio.to_thread(download_video_audio, url)
        
        # Run transcription in a thread pool
        transcription = await asyncio.to_thread(transcribe_mp3_file, audio_file_path)
        
        # Run summary generation in a thread pool
        summary = await asyncio.to_thread(ask_gpt_for_summary, transcription, url)
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to process YouTube summary: {str(e)}")
        raise
        
    finally:
        # Clean up the audio file regardless of success/failure
        if audio_file_path and os.path.exists(audio_file_path):
            try:
                os.remove(audio_file_path)
                logger.info(f"Cleaned up audio file: {audio_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up audio file: {str(e)}")
