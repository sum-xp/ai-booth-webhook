# Breeze Booth — Notes & Tips

## Cloud Gallery / SMS Texting

To use Breeze Cloud gallery with SMS delivery, put this in the **text message body** (not just as the share URL field):

```
https://share.sumxp.com/s/{eventKiteSessionId}
```

- Set sharing type to **SMS**
- `{eventKiteSessionId}` is the Breeze token — Breeze replaces it automatically per session
- This is the correct share URL format for sumxp.com hosted galleries

---

## Webhook / Post-Processing URL

General format for this service:

```
https://ai-booth-webhook.onrender.com/process?style={style_name}
```

Replace `{style_name}` with one of the available styles (see `styles/` directory).

Set in Breeze event settings → **Photo Post-Processing URL**.

Timeout: Breeze default is 120s — matches this server's gunicorn timeout.

---

## QR Code Processing

- **QR Code Processing checkbox: DISABLED** — Breeze's built-in QR URL parsing handles `{qr1}`, `{qr2}`, `{qr3}` tokens natively
- Keep regex entries in the list but checkbox stays **OFF**
- When enabled, it can interfere with built-in parsing

## Debugging

- `GET /debug` — returns the last `/process` request fields (what Breeze actually sent)
- `GET /health` — shows loaded styles and API key count
- `GET /warmup` — pre-warms the Google model before an event
