# What Clippy costs to run

## Hosting: $0

The backend runs on **your own computer** (Mac or Windows). Your iPhone talks to it over home Wi‑Fi. It only works while the computer is on and the backend window is open.

To use it away from home, install the free [Tailscale](https://tailscale.com) app on both the phone and the computer. Then use the computer's Tailscale address in the app's Settings.

Prefer it always on? A small cloud server (4–8 CPU) costs roughly **$8–25/month** (Hetzner, DigitalOcean, Railway…). One catch: YouTube often blocks downloads from cloud servers.

## Speech-to-text: $0

Whisper runs locally on your computer. On a recent laptop, the default `small` model takes roughly **5–15 minutes per hour of video** (an estimate, not a benchmark). Set `WHISPER_MODEL=base` in `backend/.env` for faster, slightly less accurate transcripts.

## AI clip picking: about $0.30–0.50 per hour of video

Clippy uses **Claude Opus 5.5** (`claude-opus-5-5`), priced at $4 per million input tokens and $20 per million output tokens.

An hour of talking is about 9,000 words. Clippy sends it in overlapping 10-minute chunks, and the model thinks and writes back clip picks plus post captions. All told that's roughly 25–35K tokens in and 10–20K tokens out per hour of video, **so about $0.30–0.50**. These are estimates; check your real usage in the [Anthropic Console](https://console.anthropic.com).

| Model (`CLAUDE_MODEL` in `backend/.env`) | Price per million tokens (in / out) | ≈ per hour of video |
|---|---|---|
| `claude-opus-5-5` (default, best picks) | $4 / $20 | $0.30–0.50 |
| `claude-sonnet-5-5` | $2 / $10 | $0.15–0.25 |
| `claude-haiku-5-5` | $0.10 / $0.50 | $0.01–0.02 |

Without an API key, Clippy still works for free. It falls back to the loudest moments of the video.

Getting a key: create an account at [console.anthropic.com](https://console.anthropic.com), add a few dollars of prepaid credit, and create an API key. Paste it into `backend/.env` as `ANTHROPIC_API_KEY=...`. Never commit that file. This repo is public, and `.gitignore` already excludes it.

## The iPhone app: $0 or $99/year

GitHub builds `Clippy.ipa` for free, because this repo is public. To install it on your phone:

| Option | Cost | Catch |
|---|---|---|
| [Sideloadly](https://sideloadly.io) or [AltStore](https://altstore.io) with your free Apple ID | $0 | The app stops opening after **7 days** until you re-install it. AltStore can refresh it automatically over Wi‑Fi. Max 3 sideloaded apps. |
| Apple Developer Program | $99/year | Apps last a year, and you can use TestFlight. Needs signing certificates set up as GitHub secrets (not set up yet). |

## Example monthly totals

- Own computer + Opus 5.5, 20 hours of source video: **$0 hosting + about $6–10 AI**
- Own computer, no API key: **$0**
- Cloud server + Opus 5.5, 20 hours of video: **$8–25 + about $6–10**
