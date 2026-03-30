#!/bin/bash
set -e

# ============================================================
# zoomrec - Zoom Meeting Auto-Join & Record
# ============================================================
# Usage:
#   ./run.sh build                    - Build the Docker image
#   ./run.sh start                    - Start recording (uses .env)
#   ./run.sh stop                     - Stop recording
#   ./run.sh logs                     - View logs
#   ./run.sh status                   - Check container status
#   ./run.sh vnc                      - Show VNC connection info
# ============================================================

IMAGE_NAME="zoomrec:latest"
CONTAINER_NAME="zoomrec"
ENV_FILE=".env"
RECORDINGS_DIR="$(pwd)/recordings"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[zoomrec]${NC} $1"; }
warn() { echo -e "${YELLOW}[zoomrec]${NC} $1"; }
err() { echo -e "${RED}[zoomrec]${NC} $1"; }

# Create .env if not exists
create_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        cat > "$ENV_FILE" << 'ENVEOF'
# === zoomrec Configuration ===

# Zoom Meeting URL (full URL - easiest method)
ZOOM_URL=https://zoom.us/j/1234567890?pwd=XXXXXX

# Or use Meeting ID + Password instead of URL
# MEETING_ID=1234567890
# MEETING_PWD=password

# Display name shown in Zoom
DISPLAY_NAME=ZoomRec

# Timezone
TZ=Asia/Seoul

# Debug mode (True/False)
# DEBUG=True

# Telegram notifications (optional)
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=-100your_chat_id

# VNC password
VNC_PW=zoomrec
ENVEOF
        warn "Created ${ENV_FILE} - edit it with your meeting details before starting."
        return 1
    fi
    return 0
}

cmd_build() {
    log "Building Docker image..."
    docker build --platform linux/amd64 -t "$IMAGE_NAME" .
    log "Build complete: $IMAGE_NAME"
}

cmd_start() {
    # Check if already running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        err "Container '$CONTAINER_NAME' is already running. Use './run.sh stop' first."
        exit 1
    fi

    # Remove stopped container if exists
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

    # Check .env
    if ! create_env; then
        err "Please edit ${ENV_FILE} with your meeting details, then run again."
        exit 1
    fi

    # Create recordings directory
    mkdir -p "$RECORDINGS_DIR"

    # Load env vars
    source "$ENV_FILE"

    log "Starting zoomrec..."
    log "  URL: ${ZOOM_URL:-"(using MEETING_ID)"}"
    log "  Name: ${DISPLAY_NAME:-ZoomRec}"
    log "  Recording until meeting ends"
    log "  Timezone: ${TZ:-Asia/Seoul}"

    docker run -d --name "$CONTAINER_NAME" \
        --platform linux/amd64 \
        --security-opt seccomp=unconfined \
        --cap-add SYS_ADMIN \
        --cap-add NET_ADMIN \
        --env-file "$ENV_FILE" \
        -v "$RECORDINGS_DIR":/home/zoomrec/recordings \
        -p 5901:5901 \
        "$IMAGE_NAME"

    log "Container started!"
    log "  VNC: localhost:5901 (password: ${VNC_PW:-zoomrec})"
    log "  Logs: ./run.sh logs"
    log "  Recordings: $RECORDINGS_DIR"
}

cmd_stop() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log "Stopping zoomrec..."
        docker stop "$CONTAINER_NAME"
        docker rm "$CONTAINER_NAME"
        log "Stopped."
    else
        warn "Container '$CONTAINER_NAME' is not running."
    fi
}

cmd_logs() {
    docker logs -f "$CONTAINER_NAME" 2>&1
}

cmd_status() {
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log "Running"
        docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Status}}\t{{.Ports}}"
        echo ""
        # Show latest recording
        latest=$(ls -t "$RECORDINGS_DIR"/*.mp4 2>/dev/null | head -1)
        if [[ -n "$latest" ]]; then
            log "Latest recording: $(basename "$latest") ($(du -h "$latest" | cut -f1))"
        fi
    else
        warn "Not running."
    fi
}

cmd_vnc() {
    source "$ENV_FILE" 2>/dev/null
    log "VNC Connection:"
    log "  Host: localhost"
    log "  Port: 5901"
    log "  Password: ${VNC_PW:-zoomrec}"
}

# Main
case "${1:-}" in
    build)  cmd_build ;;
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    logs)   cmd_logs ;;
    status) cmd_status ;;
    vnc)    cmd_vnc ;;
    *)
        echo "Usage: $0 {build|start|stop|logs|status|vnc}"
        echo ""
        echo "  build   - Build the Docker image"
        echo "  start   - Start recording (configure .env first)"
        echo "  stop    - Stop recording"
        echo "  logs    - View live logs"
        echo "  status  - Check container status"
        echo "  vnc     - Show VNC connection info"
        ;;
esac
