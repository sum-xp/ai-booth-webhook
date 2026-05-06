"""
ai-booth-webhook — SumXP generic AI photo booth webhook
Serves multiple styles via dynamic discovery from styles/ subdirectories.

Style directory layout:
  styles/
    {style_name}/
      prompt.txt          (required)
      config.json         (optional — aspect_ratio, output_width, output_height)
      *.jpg / *.png       (optional reference images, passed to AI in sort order)

URL: POST /process?style={style_name}
"""

from flask import Flask, request, jsonify, send_file
from google import genai
from google.genai import types as genai_types
from PIL import Image, ImageFilter
import os
import glob
import json
import base64
import time
from io import BytesIO

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
GOOGLE_API_KEYS = [k.strip() for k in os.environ.get('GOOGLE_API_KEYS', GOOGLE_API_KEY).split(',') if k.strip()]
GOOGLE_MODEL = os.environ.get('GOOGLE_MODEL', 'gemini-3-pro-image-preview')
FALLBACK_MODEL = os.environ.get('FALLBACK_MODEL', 'gemini-2.5-flash-preview-image-generation')

# Default output dimensions (can be overridden per-style via config.json)
DEFAULT_OUTPUT_WIDTH = int(os.environ.get('OUTPUT_WIDTH', '1600'))
DEFAULT_OUTPUT_HEIGHT = int(os.environ.get('OUTPUT_HEIGHT', '960'))
DEFAULT_ASPECT_RATIO = os.environ.get('ASPECT_RATIO', '3:2')
DEFAULT_STYLE = os.environ.get('DEFAULT_STYLE', '')

STYLES_DIR = os.path.join(os.path.dirname(__file__), 'styles')

_google_key_index = 0


# ---------------------------------------------------------------------------
# Google client
# ---------------------------------------------------------------------------

def get_google_client():
    """Get a Google GenAI client with round-robin key rotation."""
    global _google_key_index
    if not GOOGLE_API_KEYS:
        return None
    key = GOOGLE_API_KEYS[_google_key_index % len(GOOGLE_API_KEYS)]
    _google_key_index += 1
    return genai.Client(api_key=key)


# ---------------------------------------------------------------------------
# Dynamic style discovery
# ---------------------------------------------------------------------------

def discover_styles():
    """
    Auto-discover styles from styles/ subdirectories.
    Each subdirectory must contain prompt.txt to be registered as a style.
    Reference images (*.jpg, *.png, *.jpeg) are loaded in alphabetical order.
    Optional config.json may set per-style output dimensions and aspect_ratio.
    """
    styles = {}
    if not os.path.isdir(STYLES_DIR):
        print(f"WARNING: styles/ directory not found at {STYLES_DIR}")
        return styles

    for style_name in sorted(os.listdir(STYLES_DIR)):
        full_path = os.path.join(STYLES_DIR, style_name)
        if not os.path.isdir(full_path):
            continue
        prompt_path = os.path.join(full_path, 'prompt.txt')
        if not os.path.exists(prompt_path):
            continue

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_text = f.read().strip()

        # Optional per-style config
        config = {}
        config_path = os.path.join(full_path, 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)

        # Reference images in alphabetical order
        refs = []
        img_files = sorted(
            glob.glob(os.path.join(full_path, '*.png')) +
            glob.glob(os.path.join(full_path, '*.jpg')) +
            glob.glob(os.path.join(full_path, '*.jpeg'))
        )
        for img_file in img_files:
            with open(img_file, 'rb') as f:
                img_bytes = f.read()
            ext = os.path.splitext(img_file)[1].lower()
            mime = 'image/png' if ext == '.png' else 'image/jpeg'
            refs.append((img_bytes, mime, os.path.basename(img_file)))

        styles[style_name] = {
            'prompt': prompt_text,
            'refs': refs,
            'config': config,
        }
        print(f"  Style '{style_name}': {len(prompt_text)} chars, {len(refs)} ref images"
              + (f", config: {config}" if config else ""))

    return styles


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

def resize_to_target(image_bytes, width, height):
    """Resize and center-crop image to exact target dimensions."""
    img = Image.open(BytesIO(image_bytes))
    print(f"RESIZE: AI output {img.width}x{img.height} → {width}x{height}")

    target_ratio = width / height
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        new_height = height
        new_width = int(img.width * (height / img.height))
    else:
        new_width = width
        new_height = int(img.height * (width / img.width))

    img = img.resize((new_width, new_height), Image.LANCZOS)

    left = (new_width - width) // 2
    top = (new_height - height) // 2
    img = img.crop((left, top, left + width, top + height))

    # Light sharpen after downscale — matches Orca's tuned value (0.8/80)
    img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=2))

    buf = BytesIO()
    img.save(buf, format='JPEG', quality=95)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Load styles at startup
# ---------------------------------------------------------------------------
print("=" * 50)
print("ai-booth-webhook — SumXP AI Photo Booth Service")
print(f"Primary model:  {GOOGLE_MODEL}")
print(f"Fallback model: {FALLBACK_MODEL}")
print(f"Default output: {DEFAULT_OUTPUT_WIDTH}x{DEFAULT_OUTPUT_HEIGHT} ({DEFAULT_ASPECT_RATIO})")
print(f"Discovering styles from: {STYLES_DIR}")
STYLES = discover_styles()
print(f"Loaded {len(STYLES)} style(s): {list(STYLES.keys())}")
if DEFAULT_STYLE and DEFAULT_STYLE not in STYLES:
    print(f"WARNING: DEFAULT_STYLE='{DEFAULT_STYLE}' not found in discovered styles")
print("=" * 50)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "ai-booth-webhook",
        "model": GOOGLE_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "default_output": f"{DEFAULT_OUTPUT_WIDTH}x{DEFAULT_OUTPUT_HEIGHT}",
        "default_style": DEFAULT_STYLE or "(none — must specify ?style=)",
        "styles": {
            name: {
                "prompt_chars": len(s['prompt']),
                "ref_images": len(s['refs']),
                "config": s['config'],
            }
            for name, s in STYLES.items()
        },
        "api_keys": len(GOOGLE_API_KEYS),
    }), 200


_last_request_data = {}

@app.route('/debug', methods=['GET'])
def debug():
    """Returns the last /process request's fields (for troubleshooting Breeze integration)."""
    return jsonify(_last_request_data), 200


@app.route('/warmup', methods=['GET'])
def warmup():
    """Pre-warm the Google GenAI model with a lightweight test call."""
    try:
        start = time.time()
        client = get_google_client()
        if not client:
            return jsonify({"status": "error", "message": "No API key configured"}), 500

        response = client.models.generate_content(
            model=GOOGLE_MODEL,
            contents=["A simple test: red circle on white background"],
            config=genai_types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE']
            )
        )
        elapsed = time.time() - start
        got_image = any(p.inline_data is not None for p in response.parts)
        return jsonify({
            "status": "READY" if got_image else "WARNING",
            "model": GOOGLE_MODEL,
            "time_seconds": round(elapsed, 1),
            "got_image": got_image,
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/styles', methods=['GET'])
def list_styles():
    """List all available styles."""
    return jsonify({
        "styles": list(STYLES.keys()),
        "default": DEFAULT_STYLE or None,
    }), 200


@app.route('/process', methods=['POST'])
def process_image():
    global _last_request_data
    try:
        print("=" * 50)
        print("REQUEST from Breeze Booth:")
        print(f"  Content-Type: {request.content_type}")
        print(f"  Form keys:    {list(request.form.keys())}")
        print(f"  File keys:    {list(request.files.keys())}")
        print(f"  Query args:   {dict(request.args)}")

        data = request.form.to_dict()

        _last_request_data = {
            "form": {k: v[:100] for k, v in data.items()},
            "args": request.args.to_dict(),
            "files": list(request.files.keys()),
            "content_type": request.content_type,
        }

        # ------------------------------------------------------------------
        # 1. Extract image from request
        # ------------------------------------------------------------------
        guest_img_bytes = None
        guest_img_mime = 'image/jpeg'

        if 'fileToUpload' in request.files or 'image' in request.files:
            file_key = 'fileToUpload' if 'fileToUpload' in request.files else 'image'
            image_file = request.files[file_key]
            guest_img_bytes = image_file.read()
            ext = os.path.splitext(image_file.filename or '')[1].lower()
            if ext == '.png':
                guest_img_mime = 'image/png'
            print(f"  Image: file upload '{image_file.filename}' ({len(guest_img_bytes)} bytes)")
        elif 'image' in data:
            image_data = data['image']
            if image_data.startswith('data:'):
                header, b64data = image_data.split(',', 1)
                guest_img_bytes = base64.b64decode(b64data)
                if 'png' in header:
                    guest_img_mime = 'image/png'
                print(f"  Image: base64 data URI ({len(guest_img_bytes)} bytes)")
            else:
                import requests as req
                resp = req.get(image_data, timeout=15)
                guest_img_bytes = resp.content
                print(f"  Image: downloaded from URL ({len(guest_img_bytes)} bytes)")
        elif 'image' in request.args:
            import requests as req
            resp = req.get(request.args['image'], timeout=15)
            guest_img_bytes = resp.content
            print(f"  Image: downloaded from args URL ({len(guest_img_bytes)} bytes)")

        if not guest_img_bytes:
            return jsonify({"status": "error", "message": "No image provided"}), 400

        # ------------------------------------------------------------------
        # 2. Resolve style
        # ------------------------------------------------------------------
        requested_style = (
            data.get('style') or request.args.get('style') or
            data.get('s3') or request.args.get('s3') or
            DEFAULT_STYLE or ''
        ).lower()

        if not requested_style:
            return jsonify({
                "status": "error",
                "message": "No style specified. Pass ?style=<name>. Available: " + str(list(STYLES.keys()))
            }), 400

        if requested_style not in STYLES:
            return jsonify({
                "status": "error",
                "message": f"Unknown style '{requested_style}'. Available: {list(STYLES.keys())}"
            }), 400

        style_data = STYLES[requested_style]
        prompt = style_data['prompt']
        refs = style_data['refs']
        config = style_data['config']

        out_width = config.get('output_width', DEFAULT_OUTPUT_WIDTH)
        out_height = config.get('output_height', DEFAULT_OUTPUT_HEIGHT)
        aspect_ratio = config.get('aspect_ratio', DEFAULT_ASPECT_RATIO)

        print(f"  Style: {requested_style} | Output: {out_width}x{out_height} ({aspect_ratio}) | Refs: {len(refs)}")

        # ------------------------------------------------------------------
        # 3. Build contents for Google GenAI
        # ------------------------------------------------------------------
        contents = [prompt]
        contents.append(genai_types.Part.from_bytes(data=guest_img_bytes, mime_type=guest_img_mime))

        for ref_bytes, ref_mime, ref_name in refs:
            contents.append(genai_types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime))
            print(f"  + ref: {ref_name}")

        # ------------------------------------------------------------------
        # 4. Call Google GenAI — primary model with fallback
        # ------------------------------------------------------------------
        models_to_try = [GOOGLE_MODEL]
        if FALLBACK_MODEL and FALLBACK_MODEL != GOOGLE_MODEL:
            models_to_try.append(FALLBACK_MODEL)

        response = None
        model_used = None

        for model_name in models_to_try:
            max_retries = 3 if model_name == GOOGLE_MODEL else 2
            retry_delays = [2, 5, 10]

            for attempt in range(max_retries):
                try:
                    api_start = time.time()
                    client = get_google_client()
                    if not client:
                        raise Exception("No Google API key configured")

                    print(f"  [{model_name}] attempt {attempt + 1}/{max_retries}...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=genai_types.GenerateContentConfig(
                            response_modalities=['TEXT', 'IMAGE'],
                            image_config=genai_types.ImageConfig(
                                image_size='2K',
                                aspect_ratio=aspect_ratio,
                            )
                        )
                    )
                    api_time = time.time() - api_start
                    model_used = model_name
                    print(f"  [{model_name}] done in {api_time:.1f}s")
                    break

                except Exception as retry_error:
                    api_time = time.time() - api_start
                    print(f"  [{model_name}] attempt {attempt + 1} failed ({api_time:.1f}s): {retry_error}")
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        print(f"  Retrying in {delay}s...")
                        time.sleep(delay)

            if model_used:
                break

        if not model_used:
            raise Exception(f"All models failed: {models_to_try}")

        # ------------------------------------------------------------------
        # 5. Extract generated image
        # ------------------------------------------------------------------
        if not response or not response.parts:
            msg = "Google API returned no parts"
            if response and hasattr(response, 'prompt_feedback'):
                msg += f" (feedback: {response.prompt_feedback})"
            return jsonify({"status": "error", "message": msg}), 500

        result_bytes = None
        for part in response.parts:
            if part.inline_data is not None:
                result_bytes = part.inline_data.data
                print(f"  Got image: {part.inline_data.mime_type}, {len(result_bytes)} bytes")
                break

        if not result_bytes:
            text_parts = [p.text for p in response.parts if p.text]
            return jsonify({
                "status": "error",
                "message": f"No image in response. Text: {text_parts}"[:500]
            }), 500

        # ------------------------------------------------------------------
        # 6. Resize → return
        # ------------------------------------------------------------------
        final_bytes = resize_to_target(result_bytes, out_width, out_height)
        print(f"  Final: {len(final_bytes)} bytes → returning to Breeze")
        print("=" * 50)

        return send_file(
            BytesIO(final_bytes),
            mimetype='image/jpeg',
            as_attachment=False
        )

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
