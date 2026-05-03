# Styles

Each subdirectory here is a style available at `POST /process?style={name}`.

## Directory structure

```
styles/
  {style-name}/
    prompt.txt        ← required — the transformation prompt sent to Google GenAI
    config.json       ← optional — per-style output settings
    *.jpg / *.png     ← optional — reference images (passed to AI in alphabetical order)
```

## config.json fields

```json
{
  "output_width": 1600,
  "output_height": 960,
  "aspect_ratio": "3:2"
}
```

All fields optional. Falls back to server defaults (`OUTPUT_WIDTH`, `OUTPUT_HEIGHT`, `ASPECT_RATIO` env vars, or built-in `1600×960 / 3:2`).

## Common aspect ratios

| Ratio | Notes |
|-------|-------|
| `3:2` | Default — landscape (1600×960) |
| `1:1` | Square |
| `4:3` | Standard landscape |
| `9:16` | Vertical / portrait (social) |

## Adding a new style

1. Create `styles/{style-name}/`
2. Add `prompt.txt` with your transformation prompt
3. Optionally add reference images (e.g. `01_suit.png`, `02_background.jpg`)
4. Optionally add `config.json` for custom dimensions
5. Commit and push → Render redeploys automatically
6. New style is live at `?style={style-name}` after deploy

## Example

```
styles/
  mongodb/
    prompt.txt
    config.json        ← {"output_width": 1600, "output_height": 960, "aspect_ratio": "3:2"}
    01_background.jpg
  olympic/
    prompt.txt
    01_athlete.png
```
