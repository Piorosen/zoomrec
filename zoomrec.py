import csv
import logging
import os
import psutil
import random
import schedule
import signal
import subprocess
import threading
import time
import atexit
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

# Turn DEBUG on:
#   - screenshot on error
#   - record joining
#   - do not exit container on error
DEBUG = True if os.getenv('DEBUG') == 'True' else False

# Get vars
BASE_PATH = os.getenv('HOME')
CSV_PATH = os.path.join(BASE_PATH, "meetings.csv")
IMG_PATH = os.path.join(BASE_PATH, "img")
REC_PATH = os.path.join(BASE_PATH, "recordings")
AUDIO_PATH = os.path.join(BASE_PATH, "audio")
DEBUG_PATH = os.path.join(REC_PATH, "screenshots")

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_RETRIES = 5

DISPLAY_NAME = os.getenv('DISPLAY_NAME')
if DISPLAY_NAME is None or len(DISPLAY_NAME) < 3:
    NAME_LIST = [
        'iPhone', 'iPad', 'Macbook', 'Desktop', 'Huawei',
        'Mobile', 'PC', 'Windows', 'Home', 'MyPC', 'Computer', 'Android'
    ]
    DISPLAY_NAME = random.choice(NAME_LIST)

TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
CSV_DELIMITER = ';'

ONGOING_MEETING = False
VIDEO_PANEL_HIDED = False

# ENV-based meeting config
ZOOM_URL = os.getenv('ZOOM_URL', '')
ENV_MEETING_ID = os.getenv('MEETING_ID', '')
ENV_MEETING_PWD = os.getenv('MEETING_PWD', '')
ENV_RECORD_DURATION = int(os.getenv('RECORD_DURATION', '60'))


def parse_zoom_url(url):
    """Parse a Zoom URL and extract meeting ID and password.

    Supports formats:
      - https://zoom.us/j/1234567890?pwd=XXXXX
      - https://us06web.zoom.us/j/1234567890?pwd=XXXXX
      - zoommtg://zoom.us/join?confno=1234567890&pwd=XXXXX
    """
    parsed = urlparse(url)
    meet_id = ''
    meet_pwd = ''

    if parsed.scheme in ('http', 'https'):
        # Extract meeting ID from path: /j/1234567890
        parts = parsed.path.strip('/').split('/')
        for i, part in enumerate(parts):
            if part == 'j' and i + 1 < len(parts):
                meet_id = parts[i + 1]
                break
        # Extract password from query string
        params = parse_qs(parsed.query)
        meet_pwd = params.get('pwd', [''])[0]
    elif parsed.scheme == 'zoommtg':
        params = parse_qs(parsed.query)
        meet_id = params.get('confno', [''])[0]
        meet_pwd = params.get('pwd', [''])[0]

    return meet_id, meet_pwd


def build_zoommtg_url(meet_id, meet_pwd='', uname=''):
    """Build a zoommtg:// URL for direct join."""
    url = f"zoommtg://zoom.us/join?action=join&confno={meet_id}"
    if meet_pwd:
        url += f"&pwd={meet_pwd}"
    if uname:
        url += f"&uname={uname}"
    return url


def build_zoom_https_url(meet_id, meet_pwd=''):
    """Build an https:// Zoom URL."""
    url = f"https://zoom.us/j/{meet_id}"
    if meet_pwd:
        url += f"?pwd={meet_pwd}"
    return url


class BackgroundThread:

    def __init__(self, interval=10):
        self.interval = interval
        thread = threading.Thread(target=self.run, args=())
        thread.daemon = True
        thread.start()

    def run(self):
        global ONGOING_MEETING
        ONGOING_MEETING = True
        logging.debug("Check continuously if meeting has ended..")
        while ONGOING_MEETING:
            time.sleep(self.interval)


def send_telegram_message(text):
    if TELEGRAM_TOKEN is None or TELEGRAM_CHAT_ID is None:
        return
    if len(TELEGRAM_TOKEN) < 3 or len(TELEGRAM_CHAT_ID) < 3:
        return

    url_req = ("https://api.telegram.org/bot" + TELEGRAM_TOKEN +
               "/sendMessage?chat_id=" + TELEGRAM_CHAT_ID + "&text=" + text)
    tries = 0
    done = False
    while not done:
        results = requests.get(url_req)
        results = results.json()
        done = 'ok' in results and results['ok']
        tries += 1
        if not done and tries < TELEGRAM_RETRIES:
            logging.error("Sending Telegram message failed, retrying in 5s...")
            time.sleep(5)
        if not done and tries >= TELEGRAM_RETRIES:
            logging.error("Sending Telegram message failed %d times!", tries)
            done = True


def find_process_id_by_name(process_name):
    result = []
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name'])
            if process_name.lower() in pinfo['name'].lower():
                result.append(pinfo)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return result


def exit_process_by_name(name):
    procs = find_process_id_by_name(name)
    if len(procs) > 0:
        logging.info("%s process exists | killing..", name)
        for elem in procs:
            try:
                os.kill(elem['pid'], signal.SIGKILL)
            except Exception as ex:
                logging.error("Could not terminate %s[%d]: %s",
                              name, elem['pid'], str(ex))
    # Also kill by exact path to catch all Zoom child processes
    subprocess.run("pkill -9 -f '/opt/zoom/' 2>/dev/null", shell=True, capture_output=True)


def wait_for_zoom_process(timeout=60):
    """Wait until zoom process appears."""
    start = time.time()
    while time.time() - start < timeout:
        if len(find_process_id_by_name('zoom')) > 0:
            return True
        time.sleep(1)
    return False


def run_xdotool(cmd):
    """Run an xdotool command."""
    subprocess.run(
        f"DISPLAY=:1 xdotool {cmd}",
        shell=True, capture_output=True, timeout=5
    )


def hide_taskbar():
    """Hide the Xfce panel (taskbar) so it doesn't appear in recordings."""
    logging.info("Hiding Xfce taskbar...")
    subprocess.run(
        "DISPLAY=:1 xfce4-panel --quit",
        shell=True, capture_output=True
    )
    time.sleep(1)


def zoom_fullscreen():
    """Force Zoom to fullscreen mode."""
    logging.info("Setting Zoom to fullscreen...")
    w, h = [int(x) for x in os.getenv('VNC_RESOLUTION', '1920x1080').split('x')]

    # Find the main Zoom meeting window (largest one)
    result = subprocess.run(
        "DISPLAY=:1 xdotool search --name 'Zoom'",
        shell=True, capture_output=True, text=True
    )
    windows = [wid for wid in result.stdout.strip().split('\n') if wid]

    main_win = None
    max_area = 0
    for wid in windows:
        try:
            geom = subprocess.run(
                f"DISPLAY=:1 xdotool getwindowgeometry --shell {wid}",
                shell=True, capture_output=True, text=True, timeout=3
            )
            ww = hh = 0
            for line in geom.stdout.strip().split('\n'):
                if line.startswith('WIDTH='):
                    ww = int(line.split('=')[1])
                elif line.startswith('HEIGHT='):
                    hh = int(line.split('=')[1])
            if ww * hh > max_area:
                max_area = ww * hh
                main_win = wid
        except Exception:
            continue

    if not main_win:
        logging.warning("No Zoom window found for fullscreen")
        return

    logging.info("Main Zoom window: %s (area: %d)", main_win, max_area)

    # Activate the window
    run_xdotool(f"windowactivate --sync {main_win}")
    time.sleep(0.5)

    # Force window to cover entire screen (no decorations)
    subprocess.run(
        f"DISPLAY=:1 wmctrl -i -r {main_win} -b add,fullscreen 2>/dev/null || true",
        shell=True, capture_output=True
    )
    time.sleep(0.5)

    # Fallback: resize and move to cover screen
    run_xdotool(f"windowsize {main_win} {w} {h}")
    run_xdotool(f"windowmove {main_win} 0 0")
    time.sleep(1)

    # Double-click the meeting view to trigger Zoom's native fullscreen
    run_xdotool(f"mousemove {w // 2} {h // 2}")
    time.sleep(0.3)
    run_xdotool(f"click --repeat 2 1")
    time.sleep(2)


def dismiss_dialogs():
    """Dismiss 'AI Companion', 'transcribed' popups, and sidebar panels using mouse clicks."""
    logging.info("Dismissing popups and cleaning up UI...")
    w, h = [int(x) for x in os.getenv('VNC_RESOLUTION', '1920x1080').split('x')]

    # Click OK on "This meeting is being transcribed" dialog
    # The OK button is a blue button roughly center of screen
    # Try multiple positions to hit it
    ok_positions = [
        (w // 2 + 30, h // 2 + 80),
        (w // 2, h // 2 + 80),
        (w // 2 - 30, h // 2 + 80),
        (w // 2 + 30, h // 2 + 60),
        (w // 2, h // 2 + 60),
    ]
    for x, y in ok_positions:
        run_xdotool(f"mousemove {x} {y} click 1")
        time.sleep(0.5)

    time.sleep(2)

    # Close AI Companion side panel if visible
    # The X button to close it is at the top-right area of the panel
    # Panel typically occupies the right ~300px
    close_positions = [
        (w - 20, 50),   # top-right corner X
        (w - 30, 50),
        (w - 310, 50),  # left edge of panel header
    ]
    for x, y in close_positions:
        run_xdotool(f"mousemove {x} {y} click 1")
        time.sleep(0.5)

    time.sleep(1)


def join(meet_id, meet_pw, duration, description, extra_time=300, original_url=''):
    """Join a Zoom meeting and record it.
    original_url: if provided, use this URL directly instead of building one.
    """
    global ONGOING_MEETING
    ffmpeg_debug = None

    logging.info("Join meeting: %s (ID: %s, duration: %ds)",
                 description, meet_id, duration)

    if DEBUG:
        if not os.path.exists(DEBUG_PATH):
            os.makedirs(DEBUG_PATH, exist_ok=True)

    # Hide Xfce taskbar
    hide_taskbar()

    zoom_url = original_url if original_url else build_zoom_https_url(meet_id, meet_pw)
    logging.info("Zoom URL: %s", zoom_url)

    # Launch Zoom with URL using setsid (new session required for Zoom v7)
    logging.info("Launching Zoom with URL...")
    os.system(f'DISPLAY=:1 setsid zoom "--url={zoom_url}" &')

    if not wait_for_zoom_process(timeout=30):
        logging.error("Zoom did not start!")
        send_telegram_message(f"Failed to start Zoom for {description}!")
        return

    logging.info("Zoom started, entering name...")
    time.sleep(15)

    for char in DISPLAY_NAME:
        run_xdotool(f"key {char}")
        time.sleep(0.1)
    time.sleep(1)
    run_xdotool("key Return")

    logging.info("Waiting for meeting connection...")
    time.sleep(25)

    zoom_fullscreen()
    time.sleep(2)
    dismiss_dialogs()
    time.sleep(2)
    dismiss_dialogs()
    run_xdotool("mousemove 0 0")
    time.sleep(3)

    start_date = datetime.now()

    # Start BackgroundThread for meeting monitoring
    BackgroundThread()

    logging.info("Joined meeting, starting recording..")

    # Start FFmpeg recording
    width, height = [int(x) for x in os.getenv('VNC_RESOLUTION', '1920x1080').split('x')]
    disp = os.getenv('DISPLAY', ':1')
    filename = os.path.join(
        REC_PATH,
        time.strftime(TIME_FORMAT) + "-" + description + ".mp4"
    )

    # Crop out Zoom UI chrome: top title bar (~30px) and bottom toolbar (~56px)
    crop_top = 30
    crop_bottom = 56
    crop_h = height - crop_top - crop_bottom
    # H.264 requires even dimensions
    crop_h = crop_h - (crop_h % 2)

    command = (
        f"ffmpeg -nostats -loglevel error "
        f"-f pulse -ac 2 -i 1 "
        f"-f x11grab -r 30 -s {width}x{height} -i {disp} "
        f"-vf crop={width}:{crop_h}:0:{crop_top} "
        f"-acodec aac -b:a 128k -vcodec libx264 "
        f"-preset ultrafast -crf 23 -pix_fmt yuv420p -threads 0 "
        f"-async 1 -vsync 1 {filename}"
    )

    ffmpeg = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=True, preexec_fn=os.setsid
    )
    atexit.register(os.killpg, os.getpgid(ffmpeg.pid), signal.SIGQUIT)

    send_telegram_message(f"Joined meeting '{description}' and started recording.")

    end_date = start_date + timedelta(seconds=duration + extra_time)

    # Wait for meeting to end
    meeting_running = True
    while meeting_running:
        time_remaining = end_date - datetime.now()
        if time_remaining.total_seconds() < 0 or not ONGOING_MEETING:
            meeting_running = False
        else:
            print(f"Meeting ends in {time_remaining}", end="\r", flush=True)
        time.sleep(5)

    logging.info("Meeting ended at %s", datetime.now())
    logging.info("Recording saved: %s", filename)

    # Stop recording
    try:
        os.killpg(os.getpgid(ffmpeg.pid), signal.SIGQUIT)
        atexit.unregister(os.killpg)
    except Exception:
        pass
    # Stop Zoom
    exit_process_by_name("zoom")

    send_telegram_message(f"Meeting '{description}' ended.")


def play_audio(description):
    files = os.listdir(AUDIO_PATH)
    files = list(filter(lambda f: f.endswith(".wav"), files))
    if len(files) > 0:
        file = random.choice(files)
        path = os.path.join(AUDIO_PATH, file)
        command = "/usr/bin/paplay --device=microphone -p " + path
        play = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res, err = play.communicate()
        if play.returncode != 0:
            logging.error("Failed playing file! - %d - %s",
                          play.returncode, str(err))


def join_from_env():
    """Join a meeting using ENV variables (ZOOM_URL or MEETING_ID+MEETING_PWD)."""
    meet_id = ''
    meet_pwd = ''

    if ZOOM_URL:
        logging.info("Parsing ZOOM_URL: %s", ZOOM_URL)
        meet_id, meet_pwd = parse_zoom_url(ZOOM_URL)
        logging.info("Parsed -> ID: %s, PWD: %s", meet_id, meet_pwd[:4] + '...' if meet_pwd else '')

    # ENV vars override URL-parsed values
    if ENV_MEETING_ID:
        meet_id = ENV_MEETING_ID
    if ENV_MEETING_PWD:
        meet_pwd = ENV_MEETING_PWD

    if not meet_id:
        logging.info("No ZOOM_URL or MEETING_ID provided via ENV, skipping ENV join.")
        return

    duration = ENV_RECORD_DURATION * 60  # convert minutes to seconds
    description = "ENV_Meeting_" + meet_id

    # Pass original URL for direct use (preserves regional subdomain)
    orig_url = ZOOM_URL if ZOOM_URL and ZOOM_URL.startswith('http') else ''

    logging.info("Joining meeting from ENV: ID=%s, Duration=%d min",
                 meet_id, ENV_RECORD_DURATION)
    join(meet_id=meet_id, meet_pw=meet_pwd,
         duration=duration, description=description,
         extra_time=0, original_url=orig_url)


def join_ongoing_meeting():
    if not os.path.exists(CSV_PATH):
        logging.info("No meetings.csv found, skipping CSV schedule.")
        return

    with open(CSV_PATH, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=CSV_DELIMITER)
        for row in csv_reader:
            curr_date = datetime.now()

            if row["weekday"].lower() == curr_date.strftime('%A').lower():
                curr_time = curr_date.time()

                start_time_csv = datetime.strptime(row["time"], '%H:%M')
                start_date = curr_date.replace(
                    hour=start_time_csv.hour, minute=start_time_csv.minute)
                start_time = start_date.time()

                end_date = start_date + \
                    timedelta(seconds=int(row["duration"]) * 60 + 300)
                end_time = end_date.time()

                recent_duration = (end_date - curr_date).total_seconds()

                if start_time < end_time:
                    if start_time <= curr_time <= end_time and str(row["record"]) == 'true':
                        logging.info("Join meeting that is currently running..")

                        # Parse URL if id field is a URL
                        mid = row["id"]
                        mpw = row["password"]
                        if mid.startswith('http://') or mid.startswith('https://'):
                            mid, mpw_parsed = parse_zoom_url(mid)
                            if not mpw:
                                mpw = mpw_parsed

                        join(meet_id=mid, meet_pw=mpw,
                             duration=recent_duration,
                             description=row["description"])
                else:
                    if curr_time >= start_time or curr_time <= end_time and str(row["record"]) == 'true':
                        logging.info("Join meeting that is currently running..")
                        mid = row["id"]
                        mpw = row["password"]
                        if mid.startswith('http://') or mid.startswith('https://'):
                            mid, mpw_parsed = parse_zoom_url(mid)
                            if not mpw:
                                mpw = mpw_parsed

                        join(meet_id=mid, meet_pw=mpw,
                             duration=recent_duration,
                             description=row["description"])


def setup_schedule():
    if not os.path.exists(CSV_PATH):
        logging.info("No meetings.csv found, skipping CSV schedule setup.")
        return

    with open(CSV_PATH, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=CSV_DELIMITER)
        line_count = 0
        for row in csv_reader:
            if str(row["record"]) == 'true':
                # Parse URL if id field is a URL
                mid = row["id"]
                mpw = row["password"]
                if mid.startswith('http://') or mid.startswith('https://'):
                    mid, mpw_parsed = parse_zoom_url(mid)
                    if not mpw:
                        mpw = mpw_parsed

                sched_time = (datetime.strptime(row["time"], '%H:%M') -
                              timedelta(minutes=1)).strftime('%H:%M')
                dur = int(row["duration"]) * 60

                cmd_string = (
                    f'schedule.every().{row["weekday"]}'
                    f'.at("{sched_time}")'
                    f'.do(join, meet_id="{mid}"'
                    f', meet_pw="{mpw}"'
                    f', duration={dur}'
                    f', description="{row["description"]}")'
                )

                cmd = compile(cmd_string, "<string>", "eval")
                eval(cmd)
                line_count += 1
        logging.info("Added %d meetings to schedule.", line_count)


def main():
    try:
        if DEBUG and not os.path.exists(DEBUG_PATH):
            os.makedirs(DEBUG_PATH)
    except Exception:
        logging.error("Failed to create screenshot folder!")
        raise

    # Priority 1: ENV-based meeting (immediate join)
    if ZOOM_URL or ENV_MEETING_ID:
        join_from_env()
        return

    # Priority 2: CSV-based schedule
    setup_schedule()
    join_ongoing_meeting()


if __name__ == '__main__':
    main()

while True:
    schedule.run_pending()
    time.sleep(1)
    next_run = schedule.next_run()
    if next_run:
        remaining = next_run - datetime.now()
        print(f"Next meeting in {remaining}", end="\r", flush=True)
    else:
        print("No scheduled meetings. Waiting...", end="\r", flush=True)
