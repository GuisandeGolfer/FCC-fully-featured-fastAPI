import os
import re
import logging
from openai import OpenAI
import yt_dlp
from dotenv import load_dotenv
from .audio_utils import split_audio_file

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

AUDIO_FOLDER = os.path.join(os.getcwd(), "audio")

# OpenAI client
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def clean_title(title: str) -> str:
    # Regular expression to remove trailing periods, spaces, or special characters
    return re.sub(r'[^\w\d]+$', '', title.strip())


def download_video_audio(url: str):

    # yt-dlp options to download audio and convert to mp3
    ydl_opts = {
        'format': 'bestaudio/best',  # Get the best available audio format
        'quiet': False,              # Show download progress
        'outtmpl': './audio/%(title)s.%(ext)s',  # Template for the filename
        'postprocessors': [{  
            'key': 'FFmpegExtractAudio',  # Extract audio using FFmpeg
            'preferredcodec': 'mp3',      # Convert to mp3
            'preferredquality': '192',    # Set audio quality (optional)
        }],
        'merge_output_format': 'mp3',
        "keep_video" : False,
    }

    # Download the audio using yt-dlp
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        try:
            # Extract video information
            info = ydl.extract_info(url, download=False)
            # Get the title from the metadata
            title = info.get('title', 'Unknown Title')

            print(f"TITLE PRINTING: {title}")

            result = ydl.download([url])

            print(result)

            return f"{AUDIO_FOLDER}/{title}.mp3"

        except Exception as e:
            print(f"something went wrong with yt-dlp options & extracting information: {e}")


def transcribe_mp3_file(filename: str) -> str:
    try:
        # Split file into chunks if necessary
        chunk_files = split_audio_file(filename)
        
        # Transcribe each chunk
        transcriptions = []
        for chunk_file in chunk_files:
            with open(chunk_file, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                )
                transcriptions.append(transcription.text)
            
            # Clean up chunk file if it's not the original
            if chunk_file != filename:
                try:
                    os.remove(chunk_file)
                except Exception as e:
                    logger.warning(f"Failed to clean up chunk file {chunk_file}: {str(e)}")
        
        # Combine transcriptions
        return " ".join(transcriptions)
        
    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}")
        raise


def ask_gpt_for_summary(transcript: str, url: str) -> str:
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. You are helping me summarize and write actionable insights from transcriptions of youtube videos."},
                {"role": "user", "content": f"Hello! Can you help me summarize and write a detailed, yet concise document from this transcript? \n {transcript}, also at the bottom of the summary can you put this url: {url} underneath a h2 md heading like this ![](<insert-url-here>) "}
            ]
        )

        return completion.choices[0].message.content
    except Exception as e:
        print(f"something went wrong with chat completion: {e}")



async def process_youtube_summary(url: str, detail: str) -> str:

    # TODO:  add 'detail' as a summary argument
    try:
        print(detail)
        logging.info(f"Downloading audio for {url}")
        audio_file_path = download_video_audio(url)

        logging.info(f"Transcribing audio for {audio_file_path}")
        transcription = transcribe_mp3_file(audio_file_path)

        logging.info(f"Generating summary for {audio_file_path}")
        summary = ask_gpt_for_summary(transcription, url)

        # Clean up the audio file
        os.remove(audio_file_path)

        # TaskStatus?
        return summary

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return {"status": "failed", "error": str(e)}
