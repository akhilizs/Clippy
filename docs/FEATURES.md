# What an auto-clipping app needs for clip campaigns

This is the feature spec Clippy is built from. **✅ = in this version**, **🔜 = planned**.

## How clip campaigns work (Whop Content Rewards)

1. A brand or creator posts a campaign. It includes the footage you may clip, rules (hashtags, tags, length, banned styles), a pay rate per 1,000 views (often around $1, roughly $0.20–$6), and a budget.
2. You cut short vertical clips and post them from **your own** TikTok, Instagram Reels, YouTube Shorts or X account, linked to Whop.
3. You paste each post link into the campaign. Whop tracks the views for a few days and pays you from the budget.
4. Budgets are first come, first served, so the first ~48 hours of a fresh campaign matter.
5. Clips get rejected for:
   - missing hashtags, tags or credits
   - using the wrong source footage
   - banned edit styles
   - near-duplicate clips
   - posting from an account that isn't linked
6. Buying or botting views gets you permanently banned.

So the app has three jobs: **find the moments, make them grab attention, and keep you inside the rules.**

## A. Finding the moments

| Feature | Why it matters | Status |
|---|---|---|
| Transcription with word-level timestamps (Whisper, runs locally) | Everything else is built on knowing exactly what is said when | ✅ |
| AI moment scoring (Claude Opus 5.5) over overlapping 10-minute windows | Picks clips that open on a hook, stand alone without context and end on a payoff. Each pick gets a 0–100 score and a reason | ✅ |
| Loudness boost (laughing, yelling, hype) | A cheap signal that something is happening. It nudges the AI score, and replaces it when there's no API key | ✅ |
| Snap cuts to sentence boundaries | Never start mid-word or cut before the punchline | ✅ |
| Length targeting | Follows the campaign's min/max; otherwise aims for 20–45 s | ✅ |
| Remove overlapping duplicates and rank | You see the best clips first, not five copies of the same moment | ✅ |
| Chat-spike detection for Twitch/Kick VODs | Chat goes crazy at the best moments of a stream | 🔜 |
| Learning from your results | Weights moments toward what actually got views for you | 🔜 |

## B. Making it grab attention (retention editing)

| Feature | Why it matters | Status |
|---|---|---|
| Hook text on screen for the first ~3 s | Viewers decide in 1–2 seconds whether to keep watching | ✅ |
| Animated word-by-word captions, current word highlighted | Most people watch muted; moving words keep the eyes busy | ✅ |
| Captions kept out of TikTok/Reels buttons and tabs | Text hidden behind the UI is wasted | ✅ |
| Dead-air removal (jump cuts on pauses over ~0.45 s) | Silence is where people swipe away | ✅ |
| Auto-reframe to 9:16: face-tracked crop, or a blurred background when there's no face | Vertical is mandatory; the speaker has to stay in frame | ✅ |
| Loudness normalised to social-media level | Clips aren't quieter than everything around them in the feed | ✅ |
| Split-screen (facecam over gameplay), two-speaker stacked layout | Common formats for streams and podcasts | 🔜 |
| Punch-in zooms on emphasis, sound effects, background music, emoji, progress bar | Extra retention tricks | 🔜 |
| Loopable endings | Rewatches boost reach | 🔜 |

## C. Staying inside the campaign rules

| Feature | Why it matters | Status |
|---|---|---|
| Paste the Whop rules and the AI pulls out hashtags, @mentions, credit, length, platforms, banned styles and pay rate | Nobody re-reads the rules for every clip | ✅ |
| Auto-written post caption that always includes the required tags and credit | The most common rejection reason, fixed automatically | ✅ |
| Pre-post checklist (errors, warnings, notes) | Catch problems before posting, not after rejection | ✅ |
| Fresh variant per export (zoom, caption colour, trims) | Lowers the chance of "near-duplicate" or reused-content flags | ✅ |
| Rules parsing without AI (regex fallback) | Still works with no API key | ✅ |

## D. The iPhone workflow

| Feature | Status |
|---|---|
| Add a video from a link (YouTube/Twitch/Kick/Drive/direct), Photos or Files | ✅ |
| Live progress while the computer works | ✅ |
| TikTok-style vertical review feed with keep / skip | ✅ |
| Edit the hook, nudge start/end, edit the caption, re-render | ✅ |
| Export: save to Photos, share sheet, copy caption, open TikTok/Instagram/YouTube | ✅ |
| Submission tracker with views and estimated earnings | ✅ |
| Reminders to screenshot views at 24 h, 3 days and 7 days (screenshots settle disputes) | ✅ |
| Push notification when clips are ready | 🔜 |
| Post directly through the TikTok, YouTube and Instagram APIs, multiple accounts, scheduling | 🔜 (needs each platform's app review) |
| Signed TestFlight builds | 🔜 (needs the $99/year Apple Developer Program) |

## E. Rules to respect

- Only clip footage the campaign authorises. Downloading other people's videos may break the platform's terms and copyright.
- Never buy or bot views.
- Post from the account you linked to Whop, and submit the link right away. Views only count from when the post is trackable.
