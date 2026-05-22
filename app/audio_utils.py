import os
import math
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffmpeg"""
    try:
        cmd = [
            'ffmpeg', '-i', file_path,
            '-f', 'null', '-'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Parse the duration from ffmpeg output
        for line in result.stderr.split('\n'):
            if 'Duration:' in line:
                time_str = line.split('Duration:')[1].split(',')[0].strip()
                h, m, s = time_str.split(':')
                return float(h) * 3600 + float(m) * 60 + float(s)
        raise ValueError("Could not determine audio duration")
    except Exception as e:
        logger.error(f"Error getting audio duration: {str(e)}")
        raise

def split_audio_file(file_path: str, max_size_mb: int = 24) -> list[str]:
    """
    Split an audio file into chunks smaller than max_size_mb using ffmpeg
    Returns a list of paths to the chunk files
    """
    try:
        # Get file size in MB
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size <= max_size_mb:
            return [file_path]
            
        # Calculate number of chunks needed
        num_chunks = math.ceil(file_size / max_size_mb)
        
        # Get total duration
        total_duration = get_audio_duration(file_path)
        chunk_duration = total_duration / num_chunks
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        chunk_files = []
        for i in range(num_chunks):
            start_time = i * chunk_duration
            chunk_path = os.path.join(output_dir, f"{base_name}_chunk_{i}.mp3")
            
            # Use ffmpeg to split the audio
            cmd = [
                'ffmpeg', '-i', file_path,
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-acodec', 'libmp3lame',
                '-y',  # Overwrite output files if they exist
                chunk_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                chunk_files.append(chunk_path)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error splitting audio chunk {i}: {str(e)}")
                raise
                
        return chunk_files
        
    except Exception as e:
        logger.error(f"Error splitting audio file: {str(e)}")
        raise 