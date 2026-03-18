import os
import asyncio
import uuid
import glob
import subprocess
from typing import Tuple, Optional, Any, cast
import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from app import config

class DownloadError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(self.message)


def _select_downloaded_file(job_temp_dir: str) -> Optional[str]:
    candidates = [
        path for path in glob.glob(os.path.join(job_temp_dir, "*"))
        if os.path.isfile(path) and not path.endswith(".part")
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _trim_video_with_ffmpeg(file_path: str, start_seconds: int, end_seconds: int) -> str:
    base_name, extension = os.path.splitext(os.path.basename(file_path))
    output_file_path = os.path.join(
        os.path.dirname(file_path),
        f"{base_name}_clip{extension or '.mp4'}"
    )

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-to",
        str(end_seconds),
        "-i",
        file_path,
        "-c",
        "copy",
        output_file_path,
    ]

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0 or not os.path.exists(output_file_path):
        raise DownloadError(
            "FFMPEG_TRIM_ERROR",
            (completed.stderr or completed.stdout or "ffmpeg failed while trimming").strip(),
        )

    try:
        os.remove(file_path)
    except Exception:
        pass

    return output_file_path

async def download_video(
    url: str,
    _job_id: int,
    audio_only: bool = False,
    clip_start_seconds: Optional[int] = None,
    clip_end_seconds: Optional[int] = None,
) -> Tuple[str, int]:
    """
    Downloads a video from the URL using yt-dlp.
    Returns the file path and size in bytes.
    Raises DownloadError on failure or size limit exceeded.
    """
    
    job_uuid = str(uuid.uuid4())
    job_temp_dir = os.path.join(config.TEMP_DOWNLOAD_DIR, job_uuid)
    os.makedirs(job_temp_dir, exist_ok=True)
    
    output_template = os.path.join(job_temp_dir, "%(id)s.%(ext)s")
    
    ydl_opts: dict[str, Any] = {
        'format': 'bestaudio/best' if audio_only else 'best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }

    if audio_only:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    if (clip_start_seconds is None) != (clip_end_seconds is None):
        raise DownloadError("INVALID_TRIM_RANGE", "Trim start and end must be provided together.")
    if clip_start_seconds is not None and clip_end_seconds is not None and clip_start_seconds >= clip_end_seconds:
        raise DownloadError("INVALID_TRIM_RANGE", "Trim start must be smaller than trim end.")
    if audio_only and clip_start_seconds is not None:
        raise DownloadError("INVALID_MODE", "Audio-only mode cannot be combined with trim mode.")

    try:
        # Run yt-dlp synchronously in an executor to not block the event loop
        loop = asyncio.get_running_loop()
        def _download():
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                ydl.extract_info(url, download=True)
                 
        await loop.run_in_executor(None, _download)
        
        # Find the downloaded file
        file_path = _select_downloaded_file(job_temp_dir)
        if not file_path:
            raise DownloadError("FILE_NOT_FOUND", "yt-dlp finished but no file was found.")

        if clip_start_seconds is not None and clip_end_seconds is not None:
            file_path = _trim_video_with_ffmpeg(file_path, clip_start_seconds, clip_end_seconds)

        file_size_bytes = os.path.getsize(file_path)
        
        if file_size_bytes > config.MAX_FILE_SIZE_BYTES:
            cleanup_job_files(job_temp_dir)
            raise DownloadError(
                config.STATUS_TOO_LARGE, 
                f"File size ({file_size_bytes / (1024*1024):.2f} MB) exceeds limit of {config.MAX_FILE_SIZE_MB} MB."
            )
            
        return file_path, file_size_bytes

    except YtDlpDownloadError as e:
        cleanup_job_files(job_temp_dir)
        raise DownloadError("YTDLP_ERROR", str(e))
    except DownloadError:
        raise
    except Exception as e:
        cleanup_job_files(job_temp_dir)
        raise DownloadError("UNKNOWN_ERROR", str(e))


def cleanup_job_files(job_temp_dir: str):
    """Deletes the job's temporary directory and all its contents."""
    if os.path.exists(job_temp_dir):
        for root, dirs, files in os.walk(job_temp_dir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except Exception:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except Exception:
                    pass
        try:
            os.rmdir(job_temp_dir)
        except Exception:
            pass
