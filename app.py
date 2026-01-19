import os
import uuid
import time
import threading
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from yt_dlp import YoutubeDL
import mimetypes
import requests

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "your-secret-key-change-in-production"

# Configuration
DOWNLOAD_FOLDER = Path("downloads")
DOWNLOAD_FOLDER.mkdir(exist_ok=True)
MAX_FILE_AGE = 3600
CLEANUP_INTERVAL = 300
# YouTube cookies file - check Render's secret files location first, then local
COOKIES_FILE = Path("/etc/secrets/cookies.txt") if Path("/etc/secrets/cookies.txt").exists() else Path("cookies.txt")


def get_ydl_base_opts():
    """Get base yt-dlp options with cookie support"""
    opts = {
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    # Use cookies file if it exists
    if COOKIES_FILE.exists():
        opts['cookiefile'] = str(COOKIES_FILE)
        logger.info("Using cookies.txt for YouTube authentication")
    else:
        logger.warning("cookies.txt not found - YouTube may block requests")
    return opts

# Thread-safe storage
progress_lock = threading.Lock()
progress_data = {}
download_cache = {}


# ------------------------- CLEANUP -------------------------
def cleanup_old_files():
    """Remove old downloaded files"""
    while True:
        try:
            time.sleep(CLEANUP_INTERVAL)
            current_time = time.time()
            
            for filepath in DOWNLOAD_FOLDER.iterdir():
                if filepath.is_file():
                    try:
                        age = current_time - filepath.stat().st_mtime
                        if age > MAX_FILE_AGE:
                            filepath.unlink()
                            logger.info(f"Cleaned up: {filepath.name}")
                    except Exception as e:
                        logger.error(f"Cleanup error for {filepath.name}: {e}")
            
            with progress_lock:
                stale = [j for j, d in list(download_cache.items()) 
                        if current_time - d.get("timestamp", 0) > MAX_FILE_AGE]
                for job_id in stale:
                    del download_cache[job_id]
                    if job_id in progress_data:
                        del progress_data[job_id]
        
        except Exception as e:
            logger.error(f"Cleanup thread error: {e}")


threading.Thread(target=cleanup_old_files, daemon=True).start()


# ------------------------- HELPER FUNCTIONS -------------------------
def create_progress_hook(job_id):
    """Progress callback for yt-dlp"""
    def hook(d):
        try:
            status = d.get('status')
            
            with progress_lock:
                if job_id not in progress_data:
                    progress_data[job_id] = {}
                
                if status == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    percent = int((downloaded / total) * 100) if total > 0 else 0
                    
                    progress_data[job_id].update({
                        'status': 'downloading',
                        'percent': percent,
                        'speed': d.get('speed', 0),
                        'eta': d.get('eta', 0)
                    })
                
                elif status == 'finished':
                    progress_data[job_id].update({
                        'status': 'processing',
                        'percent': 99
                    })
        except Exception as e:
            logger.error(f"Progress hook error: {e}")
    
    return hook


def get_video_info(url):
    """Extract video information from URL"""
    logger.info(f"Getting info for: {url}")
    
    ydl_opts = {
        **get_ydl_base_opts(),
        'quiet': False,
        'no_warnings': False,
        'skip_download': True,
        'extract_flat': False,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise ValueError("No video information found")
            
            logger.info(f"Got info for: {info.get('title', 'Unknown')}")
            
            # Extract formats
            video_formats = []
            audio_formats = []
            
            for fmt in info.get('formats', []):
                format_id = fmt.get('format_id')
                vcodec = fmt.get('vcodec', 'none')
                acodec = fmt.get('acodec', 'none')
                ext = fmt.get('ext', 'mp4')
                height = fmt.get('height', 0)
                abr = fmt.get('abr', 0)
                filesize = fmt.get('filesize') or fmt.get('filesize_approx')
                
                # Video with audio
                if vcodec != 'none' and acodec != 'none' and height:
                    video_formats.append({
                        'format_id': format_id,
                        'quality': f"{height}p",
                        'ext': ext,
                        'filesize': filesize
                    })
                
                # Audio only
                elif acodec != 'none' and vcodec == 'none' and abr:
                    audio_formats.append({
                        'format_id': format_id,
                        'quality': f"{int(abr)}kbps",
                        'ext': ext,
                        'filesize': filesize
                    })
            
            # Remove duplicates and sort
            seen = set()
            unique_video = []
            for fmt in video_formats:
                key = fmt['quality']
                if key not in seen:
                    seen.add(key)
                    unique_video.append(fmt)
            
            seen = set()
            unique_audio = []
            for fmt in audio_formats:
                key = fmt['quality']
                if key not in seen:
                    seen.add(key)
                    unique_audio.append(fmt)
            
            unique_video.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
            unique_audio.sort(key=lambda x: int(x['quality'].replace('kbps', '')), reverse=True)
            
            result = {
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'channel': info.get('channel') or info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'video_formats': unique_video[:15],
                'audio_formats': unique_audio[:10]
            }
            
            logger.info(f"Returning {len(result['video_formats'])} video and {len(result['audio_formats'])} audio formats")
            return result
            
    except Exception as e:
        logger.error(f"Error getting video info: {e}", exc_info=True)
        raise


def download_video(url, format_id, mode, job_id, output_format=None):
    """Download video/audio with optional format conversion"""
    try:
        with progress_lock:
            progress_data[job_id] = {'status': 'starting', 'percent': 0}
        
        temp_file = DOWNLOAD_FOLDER / f"{job_id}.%(ext)s"
        
        ydl_opts = {
            **get_ydl_base_opts(),
            'outtmpl': str(temp_file),
            'progress_hooks': [create_progress_hook(job_id)],
            'quiet': False,
            'no_warnings': False,
        }
        
        if mode == 'audio':
            # Audio mode - support mp3, aac, ogg
            audio_format = output_format if output_format in ['mp3', 'aac', 'ogg', 'm4a'] else 'mp3'
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_format,
                'preferredquality': '192',
            }]
            ext = audio_format
        else:
            # Video mode - support mp4, mkv, webm
            video_format = output_format if output_format in ['mp4', 'mkv', 'webm'] else 'mp4'
            if format_id and format_id != 'best':
                ydl_opts['format'] = f"{format_id}+bestaudio/best"
            else:
                ydl_opts['format'] = 'best'
            
            # Add merge output format for video
            ydl_opts['merge_output_format'] = video_format
            ext = video_format
        
        logger.info(f"Starting download for job {job_id}")
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
        
        # Find downloaded file
        downloaded_file = None
        for f in DOWNLOAD_FOLDER.iterdir():
            if f.name.startswith(job_id):
                downloaded_file = f
                break
        
        if not downloaded_file:
            raise FileNotFoundError("Downloaded file not found")
        
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:100]
        filename = f"{clean_title}.{ext}"
        
        with progress_lock:
            download_cache[job_id] = {
                'filepath': downloaded_file,
                'filename': filename,
                'size': downloaded_file.stat().st_size,
                'timestamp': time.time(),
                'mimetype': mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            }
            progress_data[job_id] = {'status': 'completed', 'percent': 100}
        
        logger.info(f"Download completed: {job_id}")
        
    except Exception as e:
        logger.error(f"Download error for {job_id}: {e}", exc_info=True)
        with progress_lock:
            progress_data[job_id] = {'status': 'error', 'percent': 0, 'message': str(e)}


# ------------------------- ROUTES -------------------------
@app.route('/')
def index():
    """Main page"""
    logger.info("Index page requested")
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process():
    """Process URL and get video info"""
    try:
        logger.info("Process endpoint called")
        data = request.get_json()
        logger.info(f"Request data: {data}")
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL required'}), 400
        
        url = data['url'].strip()
        logger.info(f"Processing URL: {url}")
        
        info = get_video_info(url)
        return jsonify(info)
        
    except Exception as e:
        logger.error(f"Process error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/download', methods=['POST'])
def download():
    """Stream download directly to browser (no disk save)"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'best')
        mode = data.get('mode', 'video')
        output_format = data.get('output_format', None)  # mp4, mkv, webm for video; mp3, aac, ogg for audio

        if not url:
            return jsonify({'error': 'URL required'}), 400

        # Extract format info (no download)
        ydl_opts = {
            **get_ydl_base_opts(),
            'skip_download': True,
            'quiet': True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # choose format
        chosen = None
        if format_id and format_id != 'best':
            for fmt in info.get('formats', []):
                if fmt.get('format_id') == format_id:
                    chosen = fmt
                    break

        if not chosen:
            # heuristics: prefer progressive (has both audio+video) for video, best audio for audio mode
            formats = info.get('formats', [])
            if mode == 'audio':
                # pick best audio
                formats = sorted([f for f in formats if f.get('acodec') and f.get('acodec') != 'none'],
                                 key=lambda x: x.get('abr') or 0, reverse=True)
            else:
                # pick best video with audio if possible
                formats = sorted([f for f in formats if f.get('vcodec') and f.get('vcodec') != 'none'],
                                 key=lambda x: (x.get('height') or 0, x.get('tbr') or 0), reverse=True)
            chosen = formats[0] if formats else info

        format_url = chosen.get('url') or info.get('url')
        if not format_url:
            return jsonify({'error': 'Could not get direct media URL (may require post-processing)'}), 400

        # decide filename and mimetype
        title = info.get('title', 'download')
        ext = chosen.get('ext') or output_format or 'bin'
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_'))[:100]
        filename = f"{clean_title}.{ext}"
        mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        filesize = chosen.get('filesize') or chosen.get('filesize_approx')

        # stream remote content to client
        remote = requests.get(format_url, stream=True, timeout=15)
        remote.raise_for_status()

        def generate():
            try:
                for chunk in remote.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            finally:
                try:
                    remote.close()
                except Exception:
                    pass

        headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
        if filesize:
            headers['Content-Length'] = str(filesize)

        return Response(stream_with_context(generate()), mimetype=mimetype, headers=headers)

    except Exception as e:
        logger.error(f"Download stream error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/progress/<job_id>')
def progress(job_id):
    """Get progress"""
    with progress_lock:
        data = progress_data.get(job_id, {'status': 'unknown', 'percent': 0})
    return jsonify(data)


@app.route('/file/<job_id>')
def file(job_id):
    """Download file"""
    try:
        with progress_lock:
            cache = download_cache.get(job_id)
        
        if not cache:
            return jsonify({'error': 'File not found'}), 404
        
        filepath = cache['filepath']
        if not filepath.exists():
            return jsonify({'error': 'File not found'}), 404
        
        def generate():
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk
        
        response = Response(stream_with_context(generate()), mimetype=cache['mimetype'])
        response.headers['Content-Disposition'] = f'attachment; filename="{cache["filename"]}"'
        response.headers['Content-Length'] = str(cache['size'])
        
        return response
        
    except Exception as e:
        logger.error(f"File serve error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'ok'})


# Error handlers
@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 error: {request.url}")
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 error: {e}")
    return jsonify({'error': 'Server error'}), 500


if __name__ == '__main__':
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
