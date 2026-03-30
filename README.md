<h1 align="center">
    zoomrec
</h1>

<h4 align="center">
	A all-in-one solution to automatically join and record Zoom meetings.
</h4>

<p align="center">
	<a href="https://github.com/kastldratza/zoomrec/actions/workflows/docker-publish.yml"><img src="https://github.com/kastldratza/zoomrec/actions/workflows/docker-publish.yml/badge.svg" alt="GitHub Workflow Status"></a>
	<a href="https://github.com/kastldratza/zoomrec/actions/workflows/codeql.yml"><img src="https://github.com/kastldratza/zoomrec/actions/workflows/codeql.yml/badge.svg" alt="GitHub Workflow Status"></a>
	<a href="https://github.com/kastldratza/zoomrec/actions/workflows/snyk.yml"><img src="https://github.com/kastldratza/zoomrec/actions/workflows/snyk.yml/badge.svg" alt="GitHub Workflow Status"></a>
	<a href="https://github.com/kastldratza/zoomrec/actions/workflows/snyk-container-analysis.yml"><img src="https://github.com/kastldratza/zoomrec/actions/workflows/snyk-container-analysis.yml/badge.svg" alt="GitHub Workflow Status"></a>
    <br>
    <img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/kastldratza/zoomrec">
    <img alt="Docker Image Size (tag)" src="https://img.shields.io/docker/image-size/kastldratza/zoomrec/latest">
    <img alt="Github Stars" src="https://img.shields.io/github/stars/kastldratza/zoomrec.svg">
</p>

---

- **Zoom v7** - _Latest Zoom client with automatic meeting join_
- **Python3** - _Script to automatically join Zoom meetings and control FFmpeg_
- **FFmpeg** - _H.264/AAC MP4 recording_
- **Docker** - _Headless VNC Container based on Ubuntu 20.04 with Xfce window manager and TigerVNC_
- **Telegram** - _Get notified about your recordings_

---

## Quick Start

### Build

```bash
docker build --platform linux/amd64 -t zoomrec:latest .
```

### Join & Record with URL (simplest)

```bash
docker run -d --name zoomrec \
  --platform linux/amd64 \
  --security-opt seccomp=unconfined \
  --cap-add SYS_ADMIN \
  --cap-add NET_ADMIN \
  -e TZ=Asia/Seoul \
  -e ZOOM_URL="https://zoom.us/j/1234567890?pwd=XXXXXX" \
  -e DISPLAY_NAME="MyName" \
  -e RECORD_DURATION=60 \
  -v $(pwd)/recordings:/home/zoomrec/recordings \
  -p 5901:5901 \
  zoomrec:latest
```

### Join & Record with Meeting ID + Password

```bash
docker run -d --name zoomrec \
  --platform linux/amd64 \
  --security-opt seccomp=unconfined \
  --cap-add SYS_ADMIN \
  --cap-add NET_ADMIN \
  -e TZ=Asia/Seoul \
  -e MEETING_ID="1234567890" \
  -e MEETING_PWD="your_password" \
  -e DISPLAY_NAME="MyName" \
  -e RECORD_DURATION=60 \
  -v $(pwd)/recordings:/home/zoomrec/recordings \
  -p 5901:5901 \
  zoomrec:latest
```

### Schedule with CSV (original method)

```bash
docker run -d --name zoomrec \
  --platform linux/amd64 \
  --security-opt seccomp=unconfined \
  --cap-add SYS_ADMIN \
  --cap-add NET_ADMIN \
  -e TZ=Asia/Seoul \
  -e DISPLAY_NAME="MyName" \
  -v $(pwd)/recordings:/home/zoomrec/recordings \
  -v $(pwd)/example/meetings.csv:/home/zoomrec/meetings.csv:ro \
  -v $(pwd)/example/audio:/home/zoomrec/audio:ro \
  -p 5901:5901 \
  zoomrec:latest
```

---

## Environment Variables

Variable | Description | Default | Example
-------- | -------- | -------- | --------
`ZOOM_URL` | Full Zoom meeting URL (auto-parsed) | - | `https://zoom.us/j/123?pwd=XXX`
`MEETING_ID` | Meeting ID (alternative to URL) | - | `1234567890`
`MEETING_PWD` | Meeting password | - | `abc123`
`DISPLAY_NAME` | Name shown in Zoom | `ZoomRec` | `MyName`
`RECORD_DURATION` | Recording duration in minutes | `60` | `30`
`TZ` | Timezone | `Europe/Berlin` | `Asia/Seoul`
`DEBUG` | Enable debug mode | `False` | `True`
`TELEGRAM_BOT_TOKEN` | Telegram bot token for notifications | - | `123:ABC`
`TELEGRAM_CHAT_ID` | Telegram chat ID for notifications | - | `-100123`
`VNC_PW` | VNC password | `zoomrec` | `mypass`
`VNC_RESOLUTION` | Display resolution | `1024x576` | `1920x1080`

> **Priority**: If `ZOOM_URL` or `MEETING_ID` is set, the meeting is joined immediately. Otherwise, the CSV schedule is used.

> **URL Parsing**: `ZOOM_URL` supports both `https://zoom.us/j/ID?pwd=PWD` and `zoommtg://` formats. The meeting ID and password are extracted automatically.

---

## Docker Run Options (Required)

Zoom v7 requires additional Docker permissions to function properly:

```
--platform linux/amd64          # Required on Apple Silicon (ARM)
--security-opt seccomp=unconfined   # Zoom namespace permissions
--cap-add SYS_ADMIN             # Zoom process isolation
--cap-add NET_ADMIN             # Zoom network access
```

---

## CSV Schedule

CSV must be formatted as in `example/meetings.csv`

- Delimiter: semicolon "**;**"
- Only meetings with "**record = true**" are joined and recorded
- "**description**" is used for the recording filename
- "**duration**" in minutes (+5 minutes buffer added)
- "**id**" can be a numeric meeting ID or a full Zoom URL

weekday | time | duration | id | password | description | record
-------- | -------- | -------- | -------- | -------- | -------- | --------
monday | 09:55 | 60 | 111111111111 | 741699 | Important_Meeting | true
monday | 14:00 | 90 | 222222222222 | 321523 | Unimportant_Meeting | false
tuesday| 17:00 | 90 | https://zoom.us/j/123456789?pwd=abc || Meeting_with_URL | true

---

## Recording

- Recordings are saved as **MP4** (H.264 video + AAC audio) at `/home/zoomrec/recordings`
- Filename format: `YYYY-MM-DD_HH-MM-SS-Description.mp4`
- Mount the recordings volume to access files on the host:
  ```
  -v $(pwd)/recordings:/home/zoomrec/recordings
  ```

### Preparation

```bash
mkdir -p recordings
chown -R 1000:1000 recordings
```

---

## VNC

Connect to zoomrec via VNC to see what is happening.

Hostname | Port | Password
-------- | -------- | --------
localhost | 5901 | zoomrec

---

## Telegram Notifications

Zoomrec can notify you via Telegram when recordings start/end or if joining fails.

1. [Create a new Telegram bot](https://core.telegram.org/bots#6-botfather) to get the bot token
2. Create a channel, add the bot with write permissions
3. [Get the chat ID](https://gist.github.com/mraaroncruz/e76d19f7d61d59419002db54030ebe35)

```bash
docker run -d --name zoomrec \
  --platform linux/amd64 \
  --security-opt seccomp=unconfined \
  --cap-add SYS_ADMIN --cap-add NET_ADMIN \
  -e TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN" \
  -e TELEGRAM_CHAT_ID="-100_YOUR_CHAT_ID" \
  -e ZOOM_URL="https://zoom.us/j/123?pwd=XXX" \
  -v $(pwd)/recordings:/home/zoomrec/recordings \
  -p 5901:5901 \
  zoomrec:latest
```

---

## Platform-specific Examples

### Linux / macOS

```bash
docker run -d --name zoomrec \
  --platform linux/amd64 \
  --security-opt seccomp=unconfined \
  --cap-add SYS_ADMIN --cap-add NET_ADMIN \
  -e TZ=Asia/Seoul \
  -e ZOOM_URL="https://zoom.us/j/123?pwd=XXX" \
  -v $(pwd)/recordings:/home/zoomrec/recordings \
  -p 5901:5901 \
  zoomrec:latest
```

### Windows / PowerShell

```powershell
docker run -d --name zoomrec `
  --platform linux/amd64 `
  --security-opt seccomp=unconfined `
  --cap-add SYS_ADMIN --cap-add NET_ADMIN `
  -e TZ=Asia/Seoul `
  -e ZOOM_URL="https://zoom.us/j/123?pwd=XXX" `
  -v ${PWD}/recordings:/home/zoomrec/recordings `
  -p 5901:5901 `
  zoomrec:latest
```

### Windows / cmd

```cmd
docker run -d --name zoomrec ^
  --platform linux/amd64 ^
  --security-opt seccomp=unconfined ^
  --cap-add SYS_ADMIN --cap-add NET_ADMIN ^
  -e TZ=Asia/Seoul ^
  -e ZOOM_URL="https://zoom.us/j/123?pwd=XXX" ^
  -v %cd%\recordings:/home/zoomrec/recordings ^
  -p 5901:5901 ^
  zoomrec:latest
```

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
