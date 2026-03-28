#!/bin/bash
#
# Development Launcher Script for Notifier Service with Tunnel Support
#
# This script orchestrates the startup of both the tunnel service (ngrok or Tailscale)
# and the FastAPI notifier service for local webhook development.
#
# Story 3.1: Development Launcher Script
#
# Usage:
#   ./scripts/start_dev_notifier.sh [options]
#
# Options:
#   --ngrok          Use ngrok for tunneling (default)
#   --tailscale      Use Tailscale Funnel for tunneling
#   --port PORT      Local port for FastAPI (default: 8000)
#   --no-tunnel      Start only FastAPI without tunnel
#   --auto-configure Attempt to auto-configure GitHub webhook URL
#   --help           Show this help message
#
# Environment Variables:
#   TUNNEL_TYPE      Tunnel type to use (ngrok or tailscale)
#   FASTAPI_PORT     Local port for FastAPI server
#   GITHUB_WEBHOOK_SECRET  Secret for HMAC signature verification
#
# Prerequisites:
#   - ngrok: Install from https://ngrok.com and configure authtoken
#   - Tailscale: Install from https://tailscale.com and run `tailscale up`
#
# Examples:
#   # Start with ngrok (default)
#   ./scripts/start_dev_notifier.sh
#
#   # Start with Tailscale Funnel
#   ./scripts/start_dev_notifier.sh --tailscale
#
#   # Use custom port
#   ./scripts/start_dev_notifier.sh --port 3000
#
#   # Start without tunnel (for local testing only)
#   ./scripts/start_dev_notifier.sh --no-tunnel

set -euo pipefail

# ==============================================================================
# Configuration
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
TUNNEL_TYPE="${TUNNEL_TYPE:-ngrok}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
USE_TUNNEL=true
AUTO_CONFIGURE=false
NGROK_API_PORT=4040

# Process tracking
TUNNEL_PID=""
FASTAPI_PID=""
CLEANUP_DONE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ==============================================================================
# Helper Functions
# ==============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

log_url() {
    echo -e "${BLUE}[URL]${NC} $1"
}

show_help() {
    sed -n '/^# Usage:/,/^#$/p' "$0" | head -n -1 | tail -n +2 | sed 's/^# //'
    exit 0
}

cleanup() {
    if [[ "$CLEANUP_DONE" == "true" ]]; then
        return
    fi
    CLEANUP_DONE=true

    echo ""
    log_info "Shutting down services..."

    # Kill tunnel process first
    if [[ -n "$TUNNEL_PID" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        log_info "Stopping tunnel (PID: $TUNNEL_PID)..."
        kill "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi

    # Kill FastAPI process
    if [[ -n "$FASTAPI_PID" ]] && kill -0 "$FASTAPI_PID" 2>/dev/null; then
        log_info "Stopping FastAPI (PID: $FASTAPI_PID)..."
        kill "$FASTAPI_PID" 2>/dev/null || true
        wait "$FASTAPI_PID" 2>/dev/null || true
    fi

    log_info "Cleanup complete. Goodbye!"
}

# Set up signal handlers for graceful shutdown
trap cleanup SIGINT SIGTERM EXIT

# ==============================================================================
# Argument Parsing
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --ngrok)
            TUNNEL_TYPE="ngrok"
            shift
            ;;
        --tailscale)
            TUNNEL_TYPE="tailscale"
            shift
            ;;
        --port)
            FASTAPI_PORT="$2"
            shift 2
            ;;
        --no-tunnel)
            USE_TUNNEL=false
            shift
            ;;
        --auto-configure)
            AUTO_CONFIGURE=true
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# ==============================================================================
# Validation
# ==============================================================================

validate_dependencies() {
    log_step "Validating dependencies..."

    # Check for Python/uv
    if ! command -v uv &>/dev/null; then
        log_error "uv is not installed. Please install it first."
        log_error "See: https://docs.astral.sh/uv/"
        exit 1
    fi

    # Check webhook secret
    if [[ -z "${GITHUB_WEBHOOK_SECRET:-}" ]]; then
        log_warn "GITHUB_WEBHOOK_SECRET is not set."
        log_warn "Webhook signature verification will fail."
        log_warn "Set it with: export GITHUB_WEBHOOK_SECRET=your-secret"
    fi

    if [[ "$USE_TUNNEL" == "true" ]]; then
        if [[ "$TUNNEL_TYPE" == "ngrok" ]]; then
            if ! command -v ngrok &>/dev/null; then
                log_error "ngrok is not installed."
                log_error "Install from: https://ngrok.com/download"
                exit 1
            fi

            # Check if ngrok is configured
            if ! ngrok config check &>/dev/null 2>&1; then
                log_error "ngrok is not configured."
                log_error "Run: ngrok config add-authtoken YOUR_TOKEN"
                exit 1
            fi
            log_info "ngrok is available and configured"
        elif [[ "$TUNNEL_TYPE" == "tailscale" ]]; then
            if ! command -v tailscale &>/dev/null; then
                log_error "Tailscale is not installed."
                log_error "Install from: https://tailscale.com/download"
                exit 1
            fi

            # Check if Tailscale is connected
            if ! tailscale status &>/dev/null; then
                log_error "Tailscale is not connected."
                log_error "Run: tailscale up"
                exit 1
            fi
            log_info "Tailscale is available and connected"
        fi
    fi

    log_info "All dependencies validated"
}

# ==============================================================================
# Tunnel Functions
# ==============================================================================

start_ngrok_tunnel() {
    log_step "Starting ngrok tunnel on port $FASTAPI_PORT..."

    # Start ngrok in background
    ngrok http "$FASTAPI_PORT" --log=stdout > /dev/null 2>&1 &
    TUNNEL_PID=$!

    log_info "ngrok started (PID: $TUNNEL_PID)"

    # Wait for ngrok API to be ready
    log_info "Waiting for ngrok API to be ready..."
    local max_attempts=30
    local attempt=0

    while [[ $attempt -lt $max_attempts ]]; do
        if curl -s "http://localhost:$NGROK_API_PORT/api/tunnels" > /dev/null 2>&1; then
            break
        fi
        sleep 1
        ((attempt++))
    done

    if [[ $attempt -eq $max_attempts ]]; then
        log_error "ngrok API did not become ready in time"
        exit 1
    fi

    # Get the public URL
    local tunnel_info
    tunnel_info=$(curl -s "http://localhost:$NGROK_API_PORT/api/tunnels")

    # Extract HTTPS URL (prefer HTTPS over HTTP)
    local public_url
    public_url=$(echo "$tunnel_info" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tunnels = data.get('tunnels', [])
    for t in tunnels:
        url = t.get('public_url', '')
        if url.startswith('https://'):
            print(url)
            break
    else:
        for t in tunnels:
            url = t.get('public_url', '')
            if url.startswith('http://'):
                print(url)
                break
except Exception:
    pass
" 2>/dev/null)

    if [[ -z "$public_url" ]]; then
        log_error "Could not extract ngrok public URL"
        exit 1
    fi

    PUBLIC_URL="$public_url"
    log_info "ngrok tunnel established"
}

start_tailscale_tunnel() {
    log_step "Starting Tailscale Funnel on port $FASTAPI_PORT..."

    # Check if funnel is available
    if ! tailscale funnel status &>/dev/null 2>&1; then
        log_warn "Tailscale Funnel may not be enabled for this machine."
        log_warn "You may need to enable it in the Tailscale admin console."
    fi

    # Start tailscale funnel in background
    tailscale funnel "$FASTAPI_PORT" > /dev/null 2>&1 &
    TUNNEL_PID=$!

    log_info "Tailscale Funnel started (PID: $TUNNEL_PID)"

    # Get the funnel URL from tailscale status
    local dns_name
    dns_name=$(tailscale status --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    self_node = data.get('Self', {})
    dns_name = self_node.get('DNSName', '')
    print(dns_name.rstrip('.'))
except Exception:
    pass
" 2>/dev/null)

    if [[ -z "$dns_name" ]]; then
        log_error "Could not determine Tailscale DNS name"
        exit 1
    fi

    PUBLIC_URL="https://${dns_name}"
    log_info "Tailscale Funnel URL determined"
}

get_tunnel_url() {
    if [[ "$TUNNEL_TYPE" == "ngrok" ]]; then
        start_ngrok_tunnel
    elif [[ "$TUNNEL_TYPE" == "tailscale" ]]; then
        start_tailscale_tunnel
    fi
}

# ==============================================================================
# GitHub Webhook Configuration (Bonus - Story 3.3)
# ==============================================================================

configure_github_webhook() {
    if [[ "$AUTO_CONFIGURE" != "true" ]]; then
        return
    fi

    log_step "Attempting GitHub webhook auto-configuration..."

    local webhook_url="${PUBLIC_URL}/webhooks/github"
    local github_app_id="${GITHUB_APP_ID:-}"
    local github_app_pem="${GITHUB_APP_PEM:-}"

    if [[ -z "$github_app_id" ]] || [[ -z "$github_app_pem" ]]; then
        log_warn "GitHub App credentials not configured."
        log_warn "Set GITHUB_APP_ID and GITHUB_APP_PEM for auto-configuration."
        return
    fi

    # Note: Full implementation would use JWT authentication
    # This is a placeholder for the bonus feature
    log_warn "GitHub webhook auto-configuration is not yet fully implemented."
    log_warn "Please configure manually using the URL below."
}

# ==============================================================================
# FastAPI Service
# ==============================================================================

start_fastapi() {
    log_step "Starting FastAPI notifier service on port $FASTAPI_PORT..."

    # Export environment variables for the service
    export WEBHOOK_PUBLIC_URL="${PUBLIC_URL:-http://localhost:$FASTAPI_PORT}"

    cd "$PROJECT_ROOT"

    # Start uvicorn with uv
    uv run uvicorn src.notifier_service:app \
        --host 0.0.0.0 \
        --port "$FASTAPI_PORT" \
        --reload \
        > /dev/null 2>&1 &

    FASTAPI_PID=$!
    log_info "FastAPI started (PID: $FASTAPI_PID)"

    # Wait for FastAPI to be ready
    log_info "Waiting for FastAPI to be ready..."
    local max_attempts=30
    local attempt=0

    while [[ $attempt -lt $max_attempts ]]; do
        if curl -s "http://localhost:$FASTAPI_PORT/health" > /dev/null 2>&1; then
            break
        fi
        sleep 1
        ((attempt++))
    done

    if [[ $attempt -eq $max_attempts ]]; then
        log_error "FastAPI did not become ready in time"
        exit 1
    fi

    log_info "FastAPI is ready"
}

# ==============================================================================
# Main Execution
# ==============================================================================

main() {
    echo ""
    echo "=============================================="
    echo "  Notifier Development Launcher"
    echo "  Phase 2 - Local-to-Cloud Tunneling"
    echo "=============================================="
    echo ""

    validate_dependencies

    # Initialize PUBLIC_URL
    PUBLIC_URL="http://localhost:$FASTAPI_PORT"

    # Start tunnel if requested
    if [[ "$USE_TUNNEL" == "true" ]]; then
        get_tunnel_url
    else
        log_info "Running without tunnel (local access only)"
    fi

    # Attempt GitHub webhook configuration (bonus feature)
    configure_github_webhook

    # Start FastAPI
    start_fastapi

    # Display summary
    echo ""
    echo "=============================================="
    log_info "Services are running!"
    echo "=============================================="
    echo ""

    if [[ "$USE_TUNNEL" == "true" ]]; then
        echo -e "${GREEN}Public Webhook URL:${NC}"
        log_url "${PUBLIC_URL}/webhooks/github"
        echo ""
        echo -e "${YELLOW}Configure this URL in your GitHub webhook settings:${NC}"
        echo "  1. Go to your repository settings"
        echo "  2. Navigate to Webhooks"
        echo "  3. Add webhook with the URL above"
        echo "  4. Set Content type to 'application/json'"
        echo "  5. Set Secret to your GITHUB_WEBHOOK_SECRET"
        echo ""
    fi

    echo -e "${GREEN}Local Endpoints:${NC}"
    log_url "http://localhost:$FASTAPI_PORT/health"
    log_url "http://localhost:$FASTAPI_PORT/docs"
    log_url "http://localhost:$FASTAPI_PORT/webhooks/github"
    echo ""

    if [[ "$TUNNEL_TYPE" == "ngrok" ]] && [[ "$USE_TUNNEL" == "true" ]]; then
        echo -e "${GREEN}ngrok Web Interface:${NC}"
        log_url "http://localhost:$NGROK_API_PORT"
        echo ""
    fi

    echo "=============================================="
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
    echo "=============================================="
    echo ""

    # Keep script running and wait for processes
    wait
}

# Run main function
main
