# Clippy

Clippy turns long videos (podcasts, streams, interviews) into **short vertical clips built to grab attention**, made for paid clip campaigns such as **Whop Content Rewards**.

- 🔎 **Finds the moments:** AI (Claude Opus 5.5) reads the transcript and picks the moments that open on a hook, make sense on their own and end on a payoff.
- ✂️ **Edits them for you:** a hook title for the first 3 seconds, animated word-by-word captions, pauses cut out, auto-reframed to 9:16 with the speaker's face kept in frame.
- ✅ **Keeps you inside the rules:** paste the campaign's rules and Clippy adds the required hashtags, tags and credit, then checks length and platform before you post.
- 📱 **iPhone app:** swipe through clips, keep or skip, tweak the hook, save to Photos, copy the caption, and track your views and estimated earnings.

The full feature list is in [docs/FEATURES.md](docs/FEATURES.md) and the costs are in [docs/COSTS.md](docs/COSTS.md). In short: **$0 hosting**, plus about **$0.30–0.50 of AI per hour of source video** (or $0 with no AI).

```
 iPhone app  ── Wi-Fi ──►  backend on your computer  ──►  Claude API (picks moments)
 (review, export, track)    (download, transcribe,
                             cut, caption, render)
```

---

## Setup (about 15 minutes, once)

### 1. Get an Anthropic API key (optional but recommended)

1. Go to [console.anthropic.com](https://console.anthropic.com), create an account and add a few dollars of credit.
2. Create an API key and copy it.

Without a key, Clippy still works, but it picks the *loudest* moments instead of the most viral ones.

### 2. Run the backend on your computer

You need **Python 3.11 or 3.12** and **ffmpeg**.

**Mac**
```bash
brew install python@3.12 ffmpeg          # Homebrew: https://brew.sh
git clone https://github.com/akhilizs/Clippy.git
cd Clippy/backend
./run.sh
```

**Windows**
1. Install Python from [python.org](https://www.python.org/downloads/). Tick **"Add python.exe to PATH"**.
2. In a terminal run `winget install Gyan.FFmpeg`, then open a **new** terminal.
3. Download this repo (green **Code** button → **Download ZIP**) and unzip it.
4. Double-click `backend\run.bat`. If Windows Firewall asks, allow access on **private networks**.

The first start installs everything, which takes a few minutes. Then:

1. Open `backend/.env` (it's created on the first run), paste your key after `ANTHROPIC_API_KEY=`, and start it again.
2. The window shows something like this:

```
  In the iPhone app, open Settings and enter:
    Server address:  http://192.168.1.20:8000
    Access code:     7F3A9C
```

Keep that window open while you use the app.

### 3. Install the iPhone app

The app is built automatically by GitHub Actions. You don't need a Mac.

1. Open the [Actions tab](https://github.com/akhilizs/Clippy/actions/workflows/ios-ipa.yml), click the latest green run and download **Clippy-ipa** under *Artifacts*. You need to be logged in to GitHub. Unzip it to get `Clippy.ipa`.
2. Install it with **[Sideloadly](https://sideloadly.io)** (Windows/Mac) or **[AltStore](https://altstore.io)**, using your Apple ID.
3. On the iPhone, go to **Settings → General → VPN & Device Management**, trust your Apple ID, and turn on **Developer Mode** if iOS asks.
4. With a free Apple ID the app has to be re-installed every 7 days. AltStore can refresh it for you. The $99/year Apple Developer Program removes that limit.

### 4. Connect

In the app: **Settings** → enter the server address and access code → **Test connection**. Your phone must be on the same Wi‑Fi as the computer. To use it away from home, install [Tailscale](https://tailscale.com) on both devices.

---

## Using it for a Whop campaign

1. **Campaigns tab → +.** Name it and paste the campaign's rules from Whop. Clippy pulls out the hashtags, tags, credit, length and pay rate.
2. **Clips tab → +.** Pick the campaign, then paste the campaign's video link or choose a video from Photos or Files. The computer downloads, transcribes and edits it. A one-hour video takes several minutes.
3. **Review clips.** Swipe up and down. **Keep** the good ones and **Skip** the rest. Use **Edit** to change the hook text, nudge the start or end, or make a fresh variant.
4. **Export.**
   - Check the rules list.
   - Save the clip to Photos.
   - Copy the caption.
   - Post it from the account you linked to Whop.
5. **Submit on Whop immediately.** Paste the post link into the campaign. Also paste it in step 5 of Export so it shows up in **Tracker** and you get reminders to screenshot your views at 1, 3 and 7 days.

Tips that get more views:
- Post within the first 48 hours of a new campaign, before the budget runs out.
- Post several different moments rather than many copies of one.
- Use **Make a fresh variant** if you repost a moment.
- Only clip footage the campaign allows, and never buy views. Whop permanently bans accounts for fake engagement.

---

## Settings (`backend/.env`)

| Setting | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Turns on AI moment picking, rules reading and captions |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Use `claude-sonnet-5-5` or `claude-haiku-5-5` to spend less |
| `WHISPER_MODEL` | `small` | `base` is faster; `medium` is more accurate |
| `CLIPPY_MAX_CLIPS` | `8` | Clips made per video |
| `CLIPPY_DATA_DIR` | `backend/data` | Where videos and clips are stored. Delete old jobs in the app to free disk space |

Server-side fallback is on: if Claude's safety filter declines part of a transcript, the API retries it on Anthropic's recommended fallback model automatically.

## For developers

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest            # unit tests + real ffmpeg renders + API flow (no API key needed)
.venv/bin/python -m app     # start the server
```

- `backend/app/pipeline/`: ingest → transcribe → audio loudness → moments → silence cut → reframe → captions → render → compliance
- `backend/app/llm.py`: Claude prompts and structured outputs, plus an offline fallback
- `ios/`: SwiftUI app (iOS 17+). The Xcode project is generated from `ios/project.yml` with [XcodeGen](https://github.com/yonaskolb/XcodeGen).
- `.github/workflows/ios-ipa.yml`: builds the unsigned IPA. `backend-tests.yml` runs the tests.

The caption font is Inter Display Black, under the SIL Open Font License (see `backend/app/assets/fonts/OFL.txt`).
