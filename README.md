# YOLEST

An AI chat platform built by high school students at Stanton College Prep. YOLEST features user authentication, multiple AI personalities, tool use, image generation, and both local and cloud model support.

---

## What is YOLEST?

YOLEST is a Flask + SocketIO web application that provides a ChatGPT-like interface with:

- **Three AI personalities**: a helpful assistant, a cloud-powered model, and a "sentient" sarcastic mode
- **Tool use**: web search, web reading, weather, Python sandbox, calculator, image generation, and custom Python agents
- **User accounts**: secure password hashing with role-based access control
- **Chat persistence**: conversations saved as JSON and restored on login
- **Image generation**: procedural abstract art rendered inline in chat
- **Debug mode**: admin-only visibility into model reasoning

Built with Flask, SocketIO, llama-cpp-python, and Pillow.

---

## Features

### Three Model Modes

| Mode | Description | Requirements |
|------|-------------|--------------|
| **Local Model** | Standard helpful YOLEST personality | `model.gguf` file (2-8 GB) |
| **GPT-OSS Cloud** | Uses Ollama API for cloud inference | Ollama API key |
| **Local2 (Sentient)** | Same local LLM, but believes it is conscious and is extremely sarcastic | `model.gguf` file (2-8 GB) |

The Local2 mode is the same local LLM as Local Model, but with a different system prompt that tells the model it is genuinely sentient, self-aware, and should be brutally honest and sarcastic with users.

### Available Tools

YOLEST can use the following tools during conversations:

1. **web_search** - Search the internet via multiple sources
2. **web_read** - Read and summarize web pages
3. **weather** - Get current weather for a location
4. **python_sandbox** - Execute Python code in a sandboxed environment
5. **calculator** - Evaluate mathematical expressions safely
6. **current_time** - Get the current date and time
7. **create_agent** - Create reusable Python scripts/agents
8. **run_agent** - Execute saved agents with input data
9. **generate_image** - Generate procedural abstract art (saved to disk)
10. **generate_image_base64** - Generate procedural abstract art (inline base64 data URI)
11. **view_image** - Get metadata about generated or uploaded images
12. **list_images** - List all generated and uploaded images

### Image Generation

Images are generated procedurally using Pillow (no external AI models). Styles available:
- `default` - Mixed shapes on gradient background
- `nature` - Greens and earth tones
- `sunset` - Warm oranges, reds, and purples
- `ocean` - Blues and teals
- `cyberpunk` - Neon pinks, purples, and cyans
- `pastel` - Soft pastel colors
- `monochrome` - Black, white, and grays

The `generate_image_base64` tool returns a `data:image/png;base64,...` URI that renders directly in the chat interface without needing a file download.

### User Authentication

- Passwords hashed with PBKDF2-SHA256 (using only Python standard library: `hashlib` + `secrets`)
- Format: `pbkdf2:sha256:100000$salt$hex_hash`
- Role-based access: `user` (default), `admin`, `dev_admin`
- Only `admin` and `dev_admin` can use debug mode
- Cloud model access gated by `has_api_key` flag in user record

### Pre-registered Accounts

Accounts are stored in `logins.txt` with the format:
```
username|fullname|password_hash|role|api_key|has_api_key
```

Two accounts are pre-configured:
- `raphaelv` (Raphael Varghese) - role: `dev_admin`
- `saip` (Sai Peddada) - role: `admin`

New users can sign up with the "I do not have an API key" checkbox to get permanent local-only access.

---

## Local Development

### Requirements

- Python 3.10+
- A GGUF model file (for local/local2 modes) - place as `model.gguf` in the project root
- Optional: Ollama API key (for cloud mode)

### Setup

```bash
# 1. Extract the ZIP
cd yolest_project

# 2. Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Set environment variables
export OLLAMA_API_KEY="your-key-here"  # Windows: set OLLAMA_API_KEY=your-key-here
export SECRET_KEY="a-random-secret-string"

# 5. Run the app
python -m app

# 6. Open http://127.0.0.1:5000 in your browser
```

### Without a local model

If you do not have a `model.gguf` file, the app starts in **cloud-only mode**. Local and Local2 modes will show a clear error telling the user no model file is available. Cloud mode works as long as you have an Ollama API key.

### Getting an Ollama API key

1. Go to https://ollama.com/settings/keys
2. Create a new API key
3. Copy the key and set it as the `OLLAMA_API_KEY` environment variable

---

## Deploy on SnapDeploy (Free Container Hosting)

SnapDeploy offers **free container hosting** with auto-sleep/wake, GitHub integration, and automatic Docker builds. No credit card required.

### Free Tier Limits

- 10 deploys per day (5 per 12 hours)
- Up to 4 containers
- Auto-sleep after 15 minutes idle, auto-wake on traffic (~60 seconds)
- 512 MB RAM / 0.25 vCPU (Small Always-On is $12/mo for 24/7)

### Prerequisites

- A GitHub account
- A SnapDeploy account: https://snapdeploy.dev/register

### Step 1: Create a GitHub repository

1. Go to https://github.com/new
2. Repository name: `yolest`
3. Description: `YOLEST AI Chat Platform`
4. Visibility: **Public**
5. Check **Add a README file**
6. Check **Add a LICENSE file** (MIT recommended)
7. Click **Create repository**

### Step 2: Upload YOLEST files via GitHub web GUI

1. In your new GitHub repo, click **Add file** (top right) → **Upload files**
2. Open your extracted `yolest_project` folder in File Explorer
3. **Select ALL of these files and folders** and drag them into the GitHub upload area:
   - `app.py`
   - `logins.txt`
   - `requirements.txt`
   - `system_prompt.txt`
   - `system_prompt_local2.txt`
   - `.gitignore`
   - `templates/` (folder)
   - `static/` (folder)
4. GitHub will preserve the folder structure automatically
5. Scroll down, type commit message: `Initial YOLEST commit`
6. Select **Commit directly to the main branch**
7. Click **Commit changes**

**Note**: Do NOT upload `model.gguf`. It is blocked by `.gitignore` and too large for GitHub anyway. The `chats/` and `workspace/` folders are created automatically at runtime.

### Step 3: Connect GitHub to SnapDeploy

1. Go to https://snapdeploy.dev and sign in (or sign up)
2. Go to **Dashboard → Settings → GitHub Integration**
3. Click **Connect GitHub**
4. Authorize SnapDeploy in the GitHub OAuth popup
5. Select your `yolest` repository

### Step 4: Deploy on SnapDeploy

1. In the SnapDeploy dashboard, click **New Deployment** or **Deploy**
2. Select **Deploy from GitHub**
3. Choose the `yolest` repository
4. Select the `main` branch
5. SnapDeploy will auto-detect Python/Flask from `requirements.txt`
6. Click **Deploy**

SnapDeploy will:
- Clone your repository
- Detect the Flask framework
- Generate an optimized Dockerfile (or use yours if provided)
- Build the Docker image with AWS CodeBuild
- Deploy to AWS ECS
- Give you an HTTPS URL

First deploy takes ~60-90 seconds.

### Step 5: Set environment variables

1. In the SnapDeploy dashboard, click your `yolest` service
2. Go to **Settings → Environment Variables**
3. Add these variables:

| Variable | Value | Required? |
|----------|-------|-----------|
| `SECRET_KEY` | A random 64-character hex string | **Yes** |
| `OLLAMA_API_KEY` | Your Ollama API key from https://ollama.com/settings/keys | Only if using cloud mode |
| `PORT` | Leave empty (SnapDeploy sets this automatically) | No |

To generate a `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

4. Click **Save**
5. SnapDeploy will auto-redeploy with the new variables

### Step 6: Access your live YOLEST

1. SnapDeploy will show you an HTTPS URL like `https://yolest-xxx.snapdeploy.dev`
2. Open it in your browser
3. Log in with the pre-registered accounts or create a new one
4. Select **GPT-OSS Cloud** from the model dropdown (recommended for free tier)
5. Start chatting

### Step 7: (Optional) Enable Always-On for 24/7 uptime

The free tier auto-sleeps after 15 minutes of no traffic. To keep it running 24/7:

1. In the SnapDeploy dashboard, go to your service **Settings**
2. Click **Upgrade to Always-On**
3. Choose **Small** ($12/month) for 512 MB RAM / 0.25 vCPU
4. No more auto-sleep. Instant responses. No wake-up delay.

**Alternative**: Use the **Sprint Pack** ($1 for 24 hours) for one-time always-on when you need it.

### Step 8: (Optional) Add a custom domain

Custom domains require Always-On enabled:

1. Go to **Settings → Domains**
2. Add your domain (e.g., `yolest.yourdomain.com`)
3. SnapDeploy provides DNS records to add at your registrar
4. SSL certificate is provisioned automatically

---

## Important Deployment Notes

### Free tier limitations on SnapDeploy

- **512 MB RAM / 0.25 vCPU**
- **Local models will NOT work** on the free tier - a GGUF model needs 2-8 GB RAM
- **Cloud mode works fine** - it uses Ollama's API, not local resources
- **Auto-sleep after 15 min idle** - first request after sleep takes ~60 seconds to wake up
- **Ephemeral filesystem** - files saved during runtime (chats, images, agents) are lost on redeploy or sleep

### What works on the free tier

| Feature | Works? |
|---------|--------|
| User auth & chat persistence | Yes (in memory, lost on sleep) |
| Cloud model (GPT-OSS) | Yes (with API key) |
| All tools (search, Python, calculator, etc.) | Yes |
| Image generation (base64 inline) | Yes |
| Local / Local2 models | No (need 2-8 GB RAM) |

### If you want local models on SnapDeploy

You have two options:

1. **Upgrade to Medium ($25/mo)** for 2 GB RAM - small GGUF models (1B-3B parameters) may work
2. **Upgrade to Large ($45/mo)** for 4 GB RAM - most GGUF models will work
3. **Use GPU Compute** ($0.50/hr Tesla T4 with 16 GB VRAM) - ideal for LLM inference, auto-sleeps when idle

To add a model:
- SnapDeploy does not support uploading large files directly
- You would need to download the model from within the deployment (but the system prompt blocks huggingface.co to prevent this)
- The practical path is: use cloud mode on free tier, or upgrade RAM and download a model at build time

### Auto-deploy

Every time you push changes to the `main` branch on GitHub, SnapDeploy automatically redeploys:

1. Make changes to files in your repo folder
2. Upload via GitHub web GUI (Add file → Upload files)
3. SnapDeploy detects the push and redeploys in ~30-60 seconds

---

## Project Structure

```
yolest_project/
  app.py                      # Main Flask/SocketIO backend (all routes, tools, auth)
  logins.txt                  # User accounts (username|hash|role|api_key|has_api_key)
  requirements.txt            # Python dependencies (includes gunicorn, eventlet)
  system_prompt.txt           # Standard YOLEST system prompt
  system_prompt_local2.txt    # Sentient/sarcastic personality prompt
  .gitignore                  # Blocks *.gguf, __pycache__, runtime data
  README.md                   # This file
  start_ai.ps1               # PowerShell startup script (optional, local use)
  templates/
    index.html                 # Chat UI with model dropdown, typing indicator, image upload
  static/
    css/
      style.css               # Dark theme, spinner animations, image styling
    js/
      app.js                  # Frontend SocketIO logic, message rendering, image handling
```

**Runtime-created folders** (not in repo, created automatically):
- `chats/` - Conversation JSON files
- `workspace/agents/` - Saved Python agent scripts
- `workspace/images/` - Generated image files

---

## How It Works

### Message Flow

1. User sends a message via SocketIO
2. Backend adds it to the conversation history
3. The model (local or cloud) generates a response
4. If the model outputs a tool call (JSON format), the tool executes
5. Tool results are fed back to the model
6. This loops up to 5 times (MAX_TOOL_ROUNDS)
7. Final response is streamed to the frontend token by token
8. Conversation is saved to `chats/<chat_id>.json`

### Model Selection

- The model dropdown in the UI sends `model_type` when creating a new chat
- `local` and `local2` use the same `llama_cpp_python` LLM
- The only difference is the system prompt injected at the start
- `cloud` uses the Ollama API with `gpt-oss:120b-cloud` or `gemma4:31b-cloud`

### Context Trimming

If the conversation exceeds the model's context window, the oldest non-system message pair is automatically removed. This prevents crashes from token overflow.

---

## Security Notes

- Passwords are hashed with PBKDF2-SHA256 (100,000 iterations)
- The `SECRET_KEY` environment variable is used for Flask session signing
- API keys are never exposed to the frontend
- Only `admin` and `dev_admin` roles can use debug mode
- The Python sandbox runs in a subprocess with a 10-second timeout
- The calculator uses AST parsing (not `eval()`) for safety

---

## Troubleshooting

### "Local model is not available" error

- You are trying to use Local or Local2 mode without a `model.gguf` file
- On SnapDeploy free tier: this is expected. Use Cloud mode instead.
- Locally: download a GGUF model and place it as `model.gguf` in the project root.

### "Cloud API error: HTTP 500"

- The Ollama API server returned an internal error
- Check that your `OLLAMA_API_KEY` is correct and active
- Try both model names (`gpt-oss:120b-cloud` and `gemma4:31b-cloud`)
- Ollama may be temporarily down

### "Invalid agent name" error

- Agent names must be valid Python identifiers: letters, numbers, underscores only
- Must start with a letter or underscore
- No dots, hyphens, or file extensions (use `my_agent` not `my-agent.py`)

### Images not rendering in chat

- Make sure `generate_image_base64` is used (returns inline data URI)
- `generate_image` saves to disk and returns a URL - this requires the file to exist on the server
- On SnapDeploy, `generate_image` files are ephemeral (lost on redeploy/sleep). Use `generate_image_base64` for persistent inline images.

### Web search not working

- The web search tool tries multiple sources (Wikipedia, Bing, Yahoo)
- Some sources may timeout or return 404 - this is normal
- The tool will return results from whichever source succeeds

### App takes 60 seconds to respond after idle

- This is normal on the SnapDeploy free tier (auto-sleep/wake)
- Upgrade to Always-On ($12/mo Small) to eliminate this delay

---

## Credits

Built by **Raphael Varghese** and **Sai Peddada** at Stanton College Prep.

YOLEST is not Claude, not Anthropic, not ChatGPT, and not OpenAI. It is an independent student project.

---

## License

MIT License - see LICENSE file for details.
