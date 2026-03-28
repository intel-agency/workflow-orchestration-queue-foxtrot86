# Local Development Setup

This guide explains how to set up local development for the Notifier Service with tunneling support, allowing you to receive GitHub webhooks on your local machine without deploying to a cloud environment.

## Overview

The Local-to-Cloud Tunneling feature enables developers to:
- Receive GitHub webhooks on their local machines
- Test webhook flows without cloud deployment
- Debug webhook handling in real-time
- Develop and test integrations quickly

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Developer Machine                          │
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │  start_dev_notifier │    │     FastAPI Notifier        │ │
│  │       .sh           │───▶│   (localhost:8000)          │ │
│  │                     │    │                             │ │
│  │  • Starts tunnel    │    │  • Webhook endpoint         │ │
│  │  • Starts FastAPI   │    │  • Signature validation     │ │
│  │  • Logs public URL  │    │  • Event processing         │ │
│  └─────────────────────┘    └─────────────────────────────┘ │
│                                        ▲                     │
└────────────────────────────────────────│─────────────────────┘
                                         │
                              ┌──────────┴──────────┐
                              │   Tunnel Service    │
                              │   (ngrok/Tailscale) │
                              │                     │
                              │  Public URL:        │
                              │  https://xxx.ngrok.io
                              └──────────┬──────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       GitHub Webhooks                        │
│                                                              │
│  • issues.opened                                            │
│  • issue_comment.created                                    │
│  • pull_request_review.submitted                            │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Required

- **Python 3.12+** - Runtime environment
- **uv** - Python package manager ([install guide](https://docs.astral.sh/uv/))
- **Git** - Version control

### For Tunneling (choose one)

#### Option A: ngrok

1. **Install ngrok**
   ```bash
   # macOS
   brew install ngrok

   # Linux
   curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
   echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
   sudo apt update && sudo apt install ngrok

   # Windows (via Chocolatey)
   choco install ngrok
   ```

2. **Create a free account** at [ngrok.com](https://ngrok.com)

3. **Configure your authtoken**
   ```bash
   ngrok config add-authtoken YOUR_TOKEN
   ```

#### Option B: Tailscale

1. **Install Tailscale**
   ```bash
   # macOS
   brew install tailscale

   # Linux
   curl -fsSL https://tailscale.com/install.sh | sh

   # Windows
   # Download from https://tailscale.com/download
   ```

2. **Connect to Tailscale**
   ```bash
   tailscale up
   ```

3. **Enable Funnel** (requires admin approval)
   - Go to your [Tailscale Admin Console](https://login.tailscale.com/admin/dns)
   - Enable Funnel for your tailnet

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/intel-agency/workflow-orchestration-queue-foxtrot86.git
cd workflow-orchestration-queue-foxtrot86
```

### 2. Set Environment Variables

```bash
# Required: Webhook secret for HMAC verification
export GITHUB_WEBHOOK_SECRET="your-webhook-secret-here"

# Optional: Choose tunnel type (default: ngrok)
export TUNNEL_TYPE="ngrok"  # or "tailscale"

# Optional: Change FastAPI port
export FASTAPI_PORT="8000"
```

### 3. Start Development Environment

```bash
# Start with ngrok (default)
./scripts/start_dev_notifier.sh

# Or with Tailscale
./scripts/start_dev_notifier.sh --tailscale

# Or without tunnel (local testing only)
./scripts/start_dev_notifier.sh --no-tunnel
```

### 4. Configure GitHub Webhook

Once the service is running, you'll see output like:

```
==============================================
  Services are running!
==============================================

Public Webhook URL:
  https://abc123.ngrok.io/webhooks/github

Configure this URL in your GitHub webhook settings:
  1. Go to your repository settings
  2. Navigate to Webhooks
  3. Add webhook with the URL above
  4. Set Content type to 'application/json'
  5. Set Secret to your GITHUB_WEBHOOK_SECRET
```

## Configuration Options

### Command Line Options

| Option | Description |
|--------|-------------|
| `--ngrok` | Use ngrok for tunneling (default) |
| `--tailscale` | Use Tailscale Funnel for tunneling |
| `--port PORT` | Local port for FastAPI (default: 8000) |
| `--no-tunnel` | Start only FastAPI without tunnel |
| `--auto-configure` | Attempt to auto-configure GitHub webhook URL |
| `--help` | Show help message |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_WEBHOOK_SECRET` | Secret for HMAC signature verification | Required |
| `TUNNEL_TYPE` | Tunnel type to use (`ngrok` or `tailscale`) | `ngrok` |
| `FASTAPI_PORT` | Local port for FastAPI server | `8000` |
| `WEBHOOK_PUBLIC_URL` | Set by the launcher script | Auto-detected |

## Usage Examples

### Basic Usage

```bash
# Set webhook secret
export GITHUB_WEBHOOK_SECRET="my-super-secret-key"

# Start with default settings
./scripts/start_dev_notifier.sh
```

### Custom Port

```bash
# Use port 3000 instead of 8000
./scripts/start_dev_notifier.sh --port 3000
```

### Tailscale Funnel

```bash
# Use Tailscale instead of ngrok
./scripts/start_dev_notifier.sh --tailscale
```

### Local Testing (No Tunnel)

```bash
# Start without tunnel for local API testing
./scripts/start_dev_notifier.sh --no-tunnel

# Test locally
curl http://localhost:8000/health
```

## Local Endpoints

When running locally, these endpoints are available:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /ready` | Readiness check |
| `GET /docs` | OpenAPI documentation (Swagger UI) |
| `GET /redoc` | ReDoc documentation |
| `POST /webhooks/github` | GitHub webhook endpoint |

## Testing Webhooks

### Using curl

```bash
# Generate signature (requires webhook secret)
SECRET="your-webhook-secret"
PAYLOAD='{"action":"opened","issue":{"number":1,"title":"Test"}}'
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/.*= //')

# Send test webhook
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-GitHub-Delivery: test-123" \
  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
  -d "$PAYLOAD"
```

### Using ngrok Web Interface

When using ngrok, you can inspect requests at:
- `http://localhost:4040` - ngrok web interface

### Using GitHub Webhook Delivery

After configuring your webhook in GitHub:
1. Go to repository Settings > Webhooks
2. Click on your webhook
3. Scroll to "Recent Deliveries"
4. Click on a delivery to inspect the request/response

## Troubleshooting

### Common ngrok Issues

#### "ngrok is not configured"

**Problem:** ngrok authtoken not set.

**Solution:**
```bash
ngrok config add-authtoken YOUR_TOKEN
```

#### "Tunnel session expired" (Free Tier)

**Problem:** ngrok free tier sessions expire after 2 hours.

**Solution:**
- Restart the script to create a new tunnel
- Update the webhook URL in GitHub settings

#### "Account limited to 1 endpoint"

**Problem:** Free tier allows only one tunnel at a time.

**Solution:**
- Stop any other ngrok processes
- Check for stray processes: `ps aux | grep ngrok`
- Kill existing tunnels: `pkill ngrok`

#### "Rate limited"

**Problem:** Too many requests on free tier.

**Solution:**
- Upgrade to ngrok paid plan
- Use Tailscale as alternative

### Common Tailscale Issues

#### "Tailscale is not connected"

**Problem:** Tailscale daemon not running or not authenticated.

**Solution:**
```bash
# Check status
tailscale status

# Connect
tailscale up
```

#### "Funnel not enabled"

**Problem:** Funnel feature not enabled for your tailnet.

**Solution:**
1. Go to [Tailscale Admin Console](https://login.tailscale.com/admin/dns)
2. Enable Funnel in DNS settings
3. Wait for propagation (can take a few minutes)

#### "Permission denied"

**Problem:** Funnel requires specific permissions.

**Solution:**
- Contact your Tailscale admin
- Ensure your account has Funnel permissions

### General Issues

#### "Port already in use"

**Problem:** Another process is using port 8000.

**Solution:**
```bash
# Find process using port
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
./scripts/start_dev_notifier.sh --port 3000
```

#### "GITHUB_WEBHOOK_SECRET not set"

**Problem:** Environment variable not set.

**Solution:**
```bash
export GITHUB_WEBHOOK_SECRET="your-secret"
./scripts/start_dev_notifier.sh
```

#### "Signature verification failed"

**Problem:** Webhook secret doesn't match GitHub configuration.

**Solution:**
1. Verify `GITHUB_WEBHOOK_SECRET` matches GitHub webhook settings
2. Ensure no trailing whitespace in environment variable
3. Restart the service after changing the secret

#### "uv not found"

**Problem:** uv package manager not installed.

**Solution:**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pip
pip install uv
```

## Security Considerations

### Webhook Secret

- Always use a strong, unique webhook secret
- Never commit secrets to version control
- Use environment variables or secure secret storage

### Tunnel Security

- **ngrok:** Free tier tunnels are publicly accessible
- **Tailscale:** Requires authentication to your tailnet
- Consider using Tailscale for enhanced security

### Local Development

- The `--no-tunnel` option is for local testing only
- Do not expose local development servers to the internet
- Use proper authentication in production

## Advanced Configuration

### Programmatic Tunnel URL Discovery

You can use the tunnel manager programmatically:

```python
import asyncio
from src.notifier.tunnel_manager import (
    TunnelType,
    get_tunnel_manager,
    discover_tunnel_url,
)

async def get_webhook_url():
    # Simple discovery
    url = await discover_tunnel_url(TunnelType.NGROK)
    print(f"Tunnel URL: {url}")

    # With manager
    manager = get_tunnel_manager(TunnelType.NGROK)
    if manager.is_available():
        url = await manager.get_public_url()
        webhook_url = manager.get_webhook_url("/webhooks/github")
        print(f"Webhook URL: {webhook_url}")

asyncio.run(get_webhook_url())
```

### Custom Tunnel Configuration

```python
from src.notifier.tunnel_manager import NgrokTunnelManager

# Custom ngrok API endpoint
manager = NgrokTunnelManager(
    api_host="custom-host",
    api_port=8080,
    timeout=30.0,
)
```

## Related Documentation

- [Notifier Service Documentation](../src/notifier_service.py)
- [Tunnel Manager Module](../src/notifier/tunnel_manager.py)
- [GitHub Webhooks Documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [ngrok Documentation](https://ngrok.com/docs/)
- [Tailscale Funnel Documentation](https://tailscale.com/kb/1223/tailscale-funnel/)
