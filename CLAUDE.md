# ai-booth-webhook — Claude Context

## Project Overview

Flask-based webhook server hosted on Render that processes guest photos from Breeze Booth iPads using Google's Gemini API directly (`gemini-3-pro-image-preview`, aka "NB Pro"). Multi-event architecture: `styles/<name>/` subdirectories define the look per event, routed via `?style=<name>` URL param.

**This is the ACTIVE production service.** The legacy `photobooth-webhook` repo is stale and uses Replicate, not direct Gemini. Don't confuse the two.

## Active Architecture

| | |
|---|---|
| **GitHub repo** | `sum-xp/ai-booth-webhook` |
| **Branch** | `main` (auto-deploy) |
| **Render service** | `ai-booth-webhook` |
| **URL** | `https://ai-booth-webhook.onrender.com` |
| **API provider** | Google Gemini (direct) — NOT Replicate |
| **Primary model** | `gemini-3-pro-image-preview` (NB Pro) |
| **Fallback model** | `gemini-2.5-flash-preview-image-generation` (Flash) |
| **Render plan** | Standard / bumped to higher tier as needed for memory headroom |

```
Guest takes photo → Breeze Booth → POST /process?style=<name> → Flask Server
  → Google Gemini API (NB Pro primary, Flash fallback) → Resize → Return image
```

Per-iPad Breeze profile post-processing URL determines style:
`https://ai-booth-webhook.onrender.com/process?style=<style>`

## Active Styles

Styles live under `styles/<name>/` with `prompt.txt` (required) and `config.json` (optional aspect ratio + output dims).

| Style | Prompt | Aspect | Output | Used For |
|---|---|---|---|---|
| `pixar` | `styles/pixar/prompt.txt` | 1:1 | 1600×1600 | MongoDB AI — Pixar character + futuristic London (Westminster) |
| `mtg` | `styles/mtg/prompt.txt` | 1:1 | 1600×1600 | MongoDB AI — Magic the Gathering fantasy character |
| `tron` | `styles/tron/prompt.txt` | 1:1 | 1600×1600 | MongoDB AI — Tron-style armored cyber-hero |
| `gold` | `styles/gold/prompt.txt` | 3:4 | 1200×1600 | Olympic kids — gold medal celebration |
| `gold-big` | `styles/gold-big/prompt.txt` | 3:4 | 1200×1600 | Olympic adults — gold medal |
| `torch` | `styles/torch/prompt.txt` | 3:4 | 1200×1600 | Olympic kids — torch / opening ceremony |
| `torch-big` | `styles/torch-big/prompt.txt` | 3:4 | 1200×1600 | Olympic adults — torch |
| `avatar-earth` | `styles/avatar-earth/prompt.txt` | 1:1 | 1080×1350 | Avatar Activation — Earth Kingdom (uses background composite, photo_window crops to top 80%) |

### Style folder anatomy

```
styles/<name>/
  prompt.txt          (required)
  config.json         (optional: aspect_ratio, output_width, output_height)
  *.jpg / *.png       (optional reference images, passed to AI in sort order)
  background.jpg      (RESERVED filename — triggers opt-in composite step;
                       NOT sent to AI as a reference)
```

`background.jpg` is the only reserved filename. Any other image (e.g. `avatar-samples.jpg`, `football_reference.jpg`) is loaded as an AI reference in alphabetical order.

## Key Files

| File | Purpose |
|---|---|
| `server.py` | Flask app — `/process`, `/health`, `/warmup`, `/debug`, `/styles` |
| `gunicorn.conf.py` | Gunicorn worker config (timeout, max_requests, etc.) |
| `render.yaml` | Render.com deployment config |
| `requirements.txt` | Python deps (flask, google-genai, gunicorn, pillow) |
| `BREEZE-NOTES.md` | Notes on Breeze Booth integration |
| `styles/<name>/prompt.txt` | Per-style prompt (often 5-10K chars after enforcement blocks) |
| `styles/<name>/config.json` | Per-style aspect ratio + output dimensions |

## Endpoints

- `POST /process?style=<name>` — main image processing endpoint. Accepts `fileToUpload` multipart from Breeze.
- `GET /health` — service status, loaded styles, model config.
- `GET /warmup` — sends a tiny prompt to NB Pro to warm the model. **Hit this 10-15 min before events.**
- `GET /debug` — last `/process` request fields (useful for Breeze troubleshooting).
- `GET /styles` — list of registered styles.

## Render Environment Variables

- `GOOGLE_API_KEY` — single API key (or use `GOOGLE_API_KEYS` for round-robin)
- `GOOGLE_API_KEYS` — comma-separated list for rotation across multiple keys
- `GOOGLE_MODEL` — primary model (default `gemini-3-pro-image-preview`)
- `FALLBACK_MODEL` — fallback (default `gemini-2.5-flash-preview-image-generation`); set to `""` to disable fallback entirely
- `ATTEMPT_TIMEOUT` — per-attempt API timeout in seconds (default `50`). Tune live without redeploying.
- `DEFAULT_STYLE` — fallback if no `?style=` provided
- `REMOVEBG_API_KEY` — remove.bg API key. **Required** for styles that include a `background.jpg`. If not set, the composite step fails soft and the raw AI output is returned instead.
- `REMOVEBG_SIZE` — remove.bg output size (default `auto`). Options: `preview` (low-res testing), `auto` (1MP free / higher paid), `full` (original resolution, paid plans only).
- `REMOVEBG_TIMEOUT` — HTTP timeout for the remove.bg call in seconds (default `30`)

---

## Prompt Engineering Lessons (the big one)

These are non-obvious lessons learned painfully through trial and error. Read this section before editing any `prompt.txt`.

### 1. Positive language beats negative for brand/object suppression

**Counter-intuitive but consistently true.** When you write `NO Superman insignia`, the model reads "Superman" and is *more* likely to produce one. Same with `NO Nike`, `NO Spider-Man`, etc. The brand name itself is the prime.

**Better pattern:** describe what the output *should* contain in positive terms, omitting the unwanted concept entirely. Example:

```
✗ BAD:  "Optional chest emblem (no Superman, no Spider-Man)"
✓ GOOD: "Chest is plain bodysuit, OR features only an abstract glowing
         geometric shape (triangle, hexagon, vertical light bar). The
         chest is NOT a billboard for any logo."
```

This applied today to: Superman insignias on tron chests, source-photo brand logos, comic-book franchise priming.

### 2. Section titles prime the entire generation

The header `SUPERHERO COSTUME TRANSFORMATION` consistently produced spandex/comic-hero outputs no matter what we wrote inside it. Renaming to `ARMORED CYBER-HERO COSTUME` dramatically improved armor adherence. The model attends heavily to section titles.

If a section is producing the wrong vibe, **rename the section** before tweaking the bullets inside it.

### 3. Source clothing patterns transfer if not explicitly stripped

If the guest's source photo has flowers/plaid/stripes/text, the AI will try to translate that motif onto the costume unless you explicitly forbid it. The default behavior is "preserve clothing patterns."

**Required block in any costume-generating prompt:**

```
✗ Source clothing PATTERNS DO NOT TRANSFER to the costume — only the
  color palette transfers
✗ If the source shirt has flowers/florals → costume has NO flowers
✗ If the source has plaid/checks/stripes/graphics/animal print → costume
  has NONE of those patterns
✗ The costume's only decoration is abstract geometric line work
```

Without this, expect floral catsuits, plaid armor, etc.

### 4. "MANDATORY" at the bullet level lands soft; multi-point enforcement lands hard

A single `MANDATORY shoulder pauldrons` bullet usually produces decorative trim, not chunky armor. To make armor actually appear:

1. Repeat the requirement in 3+ locations (top !!!! block, costume section, CRITICAL CONSTRAINTS)
2. Use concrete visual specs ("RAISED THREE-DIMENSIONAL SHELLS sitting clearly proud of the surface, casting their own shadows")
3. Add a "what would happen if you removed this" framing ("If you mentally removed the armor pieces, you'd be left with a bare bodysuit")
4. Include a visual reference list ("Tron Legacy lightsuit + Mass Effect N7 armor")

### 5. The TRADING CARD framing was producing borders

`COMPOSITION & FRAMING - TRADING CARD FORMAT:` as a section header was directly causing decorative borders around outputs. Trading cards have borders by definition. Removing that phrase + adding explicit `FULL-BLEED` enforcement fixed the issue across pixar, mtg, and tron.

### 6. Multiple !!!! enforcement blocks at the top of the prompt have priority

Big visible blocks at the top, before SUBJECT TRANSFORMATION, get strongly attended to. Don't bury critical constraints deep in the prompt. The top of the file is prime real estate.

---

## Background Compositing Pattern (opt-in, style-level)

Some activations need the AI character placed onto a fixed branded background instead of an AI-generated environment (e.g. the Avatar Earth Kingdom brushstroke layout). This is handled by an **opt-in compositing step** in `server.py` that runs only if a style folder contains `background.jpg`.

### Pipeline

```
AI generates character on PURE WHITE background (per prompt)
        │
        ▼
remove.bg API → transparent PNG (subject cut-out with alpha)
        │
        ▼
Pillow composite: subject scaled to ~90% bg height, centered H, slight
bottom-bias for grounded feel → JPEG at background's native dimensions
        │
        ▼
resize_to_target → return to Breeze
```

### To add a composite background to a new style

1. Drop `background.jpg` into the style folder (the only reserved filename).
2. Make sure the prompt explicitly requests a **pure white background** — the AI must produce a clean subject for remove.bg to cut accurately.
3. Set `config.json` `output_width`/`output_height` to match the background dimensions (e.g. `1080×1350` for a 4:5 Snappic background).
4. Choose `aspect_ratio` to match the **photo window's shape**, not the full background. If the layout reserves a caption area at the bottom, the usable window is often closer to square than the full background. See "Aspect ratio support" below.
5. Optionally add a `photo_window` block to constrain placement (see below).
6. Ensure `REMOVEBG_API_KEY` is set in the Render env vars.
7. Verify via `/health` — the style should show `has_composite_background: true`.

### `photo_window` config (optional)

When a background reserves caption/branding space (e.g. polaroid-style with a clear bottom strip), define the subject placement area:

```json
{
  "aspect_ratio": "1:1",
  "output_width": 1080,
  "output_height": 1350,
  "photo_window": {"x": 0, "y": 0, "width": 1080, "height": 1080}
}
```

Coordinates are absolute pixels in the background. The subject is scaled to fit ~95% of the window (preserving aspect) and centered inside it. Omit `photo_window` to use the full background.

### Aspect ratio support

`gemini-3-pro-image-preview` (NB Pro) supports these `aspect_ratio` values via `image_config`:

`match_input_image`, `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`

Pick the one that matches your **photo_window shape**, not the full background. E.g. a 4:5 background with a 1:1 photo window should use `aspect_ratio: "1:1"` — the AI composes the character for a square, which then fits the square window naturally.

### Subject autocrop

`composite_on_background()` runs an autocrop on the remove.bg PNG (via `Image.getbbox()`) before scaling. This ensures the scale math is based on the character's **actual silhouette bounding box**, not the full PNG dimensions (which include lots of transparent margin from the stripped white background). Without autocrop, characters appear small and narrow in the photo window.

### Failure modes (handled fail-soft)

- **`REMOVEBG_API_KEY` not set:** composite step raises, server falls back to returning the raw AI output. Visible as a `WARNING: composite step failed` log line.
- **remove.bg rate limit or API outage:** same fail-soft path. Guest gets the raw AI image (which has the pure white background per the prompt) instead of the composite.
- **Compositing math edge cases** (subject too wide for background, etc.): the helper falls back to a width-fit if height-fit overflows; y-position clamps to 0 if subject overruns the top.

### Subject positioning tweaks

The defaults (`90%` height, centered H, `2%` bottom margin) live in `composite_on_background()` in `server.py`. If a future style needs a different layout — e.g. character anchored upper-right with bottom-third reserved for branding — split those constants into per-style config in `config.json` rather than hardcoding multiple variants.

### Latency impact

`remove.bg` adds ~2-5 seconds on top of the normal AI call. Build that into any user-facing latency expectations. The Render gunicorn timeout (180s) and per-attempt API timeout (50s) already have plenty of headroom.

---

## Resolution & Sharpness Pipeline

The current pipeline that produces good results:

```
Google API (image_size='2K')  →  ~2048px on long edge
        │
        ▼
LANCZOS downscale to ~1600 (square) or ~1200×1600 (3:4)  ← provides natural sharpening
        │
        ▼
UnsharpMask(radius=0.4, percent=70, threshold=2)  ← tight-radius sharpen, no halos
        │
        ▼
JPEG quality 95  →  return to Breeze
```

### Tuning notes

- **Output dims = ~78% of native 2K.** This downscale ratio matches what the previous Orca event used. Going to native (no downscale) loses the natural sharpening from LANCZOS. Going aggressively smaller (50%) loses too much detail.
- **UnsharpMask radius is critical.** Higher radius (0.8+) creates halos around hair/beard edges against backgrounds. Tight radius (0.4) sharpens fine detail without visible halos. **Don't go above 0.5 unless you also reduce percent.**
- **Keep JPEG at 95.** Quality 90 or below shows compression artifacts at this resolution.

### What we tried that didn't work

- **Native 2K output (no downscale):** lost natural LANCZOS sharpening, output looked soft.
- **UnsharpMask 1.0/100:** visible halos around hair/beard. Too aggressive.
- **UnsharpMask 0.8/80 (Orca's tuned value):** still slight halos at this resolution. 0.4/70 is better.

---

## Latency & Timeout Architecture

NB Pro at 2K typically takes **30-40s when warm**, but can spike to 60-90s+ on Google API jitter or 503 high-demand bursts.

### Critical config (post-event-tuned)

```python
# server.py
ATTEMPT_TIMEOUT = 50   # seconds, env-tunable
max_retries = 2        # primary AND fallback get 2 attempts each
retry_delays = [1, 2]  # seconds between retries

# gunicorn.conf.py
timeout = 180  # must exceed total in-app retry budget with margin
```

Worst-case wall-clock: 2 attempts × 50s + 1s delay = **101s on NB Pro alone**. With Flash fallback enabled, can extend to ~153s. Gunicorn at 180s gives comfortable margin.

### Why this matters

Without a per-attempt timeout, a single slow Google call can stall indefinitely. Without a gunicorn timeout buffer, the worker gets killed mid-retry, leaving Breeze hung.

The previous setup (`max_retries=3`, `delays=[2,5,10]`, `gunicorn timeout=120`) routinely killed workers during 503 bursts. Symptom: Breeze hangs forever, manual quit-and-retake required.

### Pre-event checklist

1. **Pre-warm the model** by hitting `/warmup` 10-15 min before doors open AND every 5-10 min during quiet periods. Eliminates cold-start spikes.
2. Verify all styles load via `/health`.
3. Confirm Render plan has memory headroom (see below).

---

## Memory & Worker Management

### What we know

- 2 gunicorn workers × ~1GB heap each = comfortable on a 2GB Render plan in steady state
- Each request transiently holds 2-3MB of AI image data
- **Memory drifts upward over hours** of continuous traffic — Python doesn't reliably release memory back to the OS, especially with HTTP connection pools
- OOMs (>2GB) showed up after several hours of an event

### Mitigations

```python
# gunicorn.conf.py — recycle workers periodically to prevent drift
max_requests = 100
max_requests_jitter = 10
```

Each worker handles ~90-110 requests then gracefully restarts. With 2 workers and jitter, one is always available — guests never see the restart.

### Bumping the Render plan

If OOMs continue under load, bump the plan in Render dashboard. The plan name in `render.yaml` may be `standard`; live plan can be set higher in the dashboard without changing the file.

---

## Known Issues / Tech Debt

### 1. `SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC` errors

**Symptom:** occasional log line `attempt 1 failed (30.8s): [SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC]`.

**Cause:** the `ATTEMPT_TIMEOUT` mechanism uses `ThreadPoolExecutor` + `shutdown(wait=False)`. When a timeout fires, the orphan thread is abandoned but its underlying httpx connection is still alive. Subsequent requests on the same worker can hit corrupted TLS state in the shared connection pool.

**Impact:** non-fatal. The retry loop catches it and the next attempt usually succeeds. User-invisible.

**Cleanup options for post-event:**
- **Preferred:** switch to httpx's native timeout (passed via `genai.Client(http_options=...)`) — proper cancellation, no orphan threads
- **Alternative:** use `signal.SIGALRM` for cancel (Linux-only, but Render is Linux)

### 2. Stale documentation in `photobooth-webhook` folder

The local `/Users/sumxp/Desktop/photobooth-webhook/` folder describes the old Replicate-based architecture. Its `CLAUDE.md` and `SESSION-HANDOFF.md` are stale. Don't trust them — this CLAUDE.md is the source of truth.

### 3. `mongodb-webhook/` and `olympic-webhook/` scaffold dirs in `photobooth-webhook`

Dead code. Were prototypes for the eventual `ai-booth-webhook` split. Can be deleted after the events.

### 4. Pixar prompt may transfer source-shirt graphics

Same root cause as the tron pattern issue. `OBEY` text was observed bleeding through from a guest's t-shirt onto a pixar character's shirt. If this becomes a problem, port the `NO LETTERS, NO LOGOS, NO PATTERNS FROM SOURCE PHOTO` block from `tron/prompt.txt` to `pixar/prompt.txt`.

---

## Iteration Tips for Future Prompt Tweaks

When a prompt isn't producing what you want:

1. **Look at the section titles first** — they prime more than bullet points.
2. **Search for any line that might encourage the unwanted behavior** before adding "no X" rules. Example: "traditional patterns as costume details" was actively producing the floral bleed-through.
3. **Add the constraint in 3+ places** — top !!!! block, the relevant section, and CRITICAL CONSTRAINTS at the bottom.
4. **Use positive descriptions** of what should appear, not just negative ones.
5. **Keep an eye on prompt length** — longer prompts add API latency. After several iterations, consolidate redundant blocks.

## Render dashboard quick links

- Service: https://dashboard.render.com → ai-booth-webhook
- Logs: Logs tab — search for "REQUEST from Breeze Booth" to find request boundaries
- Settings → Environment: live-tune `ATTEMPT_TIMEOUT` etc. without redeploying
- Events: deploy history, OOM events, restarts
