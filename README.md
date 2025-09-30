# Amul Product Stock Monitor

Backend service that monitors product stock availability from Amul's product API JSON and sends Telegram alerts when a product transitions from OUT OF STOCK to IN STOCK.

## Features
- Parses API JSON response for product list
- Determines in-stock status using `available` flag + `inventory_quantity > 0`
- Suppresses duplicate alerts; only sends when stock transitions False -> True (or first seen already in stock)
- Telegram notifications using `python-telegram-bot`
- Simple loop runner with configurable polling interval
- Ready for Railway deployment (`Procfile` included)

## Project Structure
```
├── main.py              # Entrypoint with polling loop
├── bot_main.py          # Interactive Telegram bot that asks for pincode
├── fetcher.py           # Live/file fallback fetching with retries
├── persistent_state.py  # JSON-backed persistent stock status
├── stock_checker.py     # Parsing & stock transition logic
├── notifier.py          # Telegram notification helper
├── requirements.txt     # Dependencies
├── Procfile             # Railway worker definition
└── README.md            # Documentation
```

## Requirements
- Python 3.11+ (recommended; 3.9+ should work)
- Telegram Bot token & target Chat ID

## Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | (required for alerts) |
| `TELEGRAM_CHAT_ID` | Chat/channel/user ID to send messages to | (required for alerts) |
| `POLL_INTERVAL` | Seconds between checks | `60` |
| `PAYLOAD_FILE` | Optional path to JSON file containing latest API response | (uses sample) |
| `LOG_LEVEL` | Logging level | `INFO` |
| `API_ENDPOINT` | If set, use live HTTP fetch (GET) | (unset) |
| `FETCH_TIMEOUT` | Seconds per HTTP request | `15` |
| `FETCH_RETRIES` | Additional retry attempts | `2` |

Additional (interactive bot) notes: `bot_main.py` does not need `TELEGRAM_CHAT_ID` (it replies to users directly) unless you want to broadcast messages.

## How It Decides In-Stock
A product is considered in stock if:
1. `available` is truthy (1 / "1" / true) AND
2. `inventory_quantity` is an integer > 0.

You can modify this heuristic in `parse_products` if the real API rules differ.

## Local Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN = "123456:ABC..."
$env:TELEGRAM_CHAT_ID = "123456789"
python main.py
```

To test without Telegram credentials, simply omit them; the app will log warnings and skip sending messages.

## Simulating API Data
By default the service uses a built-in `SAMPLE_PAYLOAD` in `main.py`.
To use a real response:
1. Save the JSON to a file, e.g. `response.json`.
2. Set `PAYLOAD_FILE` env var:
```powershell
$env:PAYLOAD_FILE = "response.json"
python main.py
```
Update the file contents between cycles (e.g. via another script) and when a product transitions to in-stock an alert is sent.

## Telegram Setup
1. Talk to `@BotFather` to create a bot; get the token.
2. Add the bot to your group/channel (if using a group/channel) and optionally promote if needed.
3. Obtain chat ID:
   - Easiest: send a message to the bot, then call `https://api.telegram.org/bot<token>/getUpdates` in a browser and read the `chat.id`.
4. Set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.

### Interactive Bot (Pincode Flow)
You can run an interactive bot that asks each user for their pincode and lists currently in-stock products:
```powershell
python bot_main.py
```
Workflow:
1. User sends /start
2. Bot asks for pincode (4–6 digits)
3. User sends pincode
4. Bot responds with in-stock products (placeholder: all in-stock; extend logic for geo-filtering)
5. User can /check to re-check, /subscribe to get updates every 10 minutes, /unsubscribe to stop.

Pincode Filtering Extension:
Modify `product_available_for_pincode` in `bot_main.py` to implement real logic (e.g., mapping pincode -> serviceable product IDs).

You can optionally create a `pincode_products.json` file:
```json
{
   "122001": ["6636020d5c0420e92d79ebdd"],
   "560001": ["product_id_a", "product_id_b"]
}
```
If present, the bot and filtering will restrict results for those pincodes.

## Railway Deployment
1. Push this repo to GitHub.
2. In Railway: New Project -> Deploy from GitHub Repo.
3. Set Environment Variables in Railway project settings:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - (optional) `POLL_INTERVAL`
   - (optional) `PAYLOAD_FILE` if you plan to mount or fetch a file.
4. Railway detects `Procfile` and runs: `worker: python main.py`.
5. Confirm logs show "Starting stock monitor loop".

### Continuous Real API Fetching (Future Enhancement)
Currently the code loads from a static file or sample. To fetch live data:
```python
import requests

def fetch_live():
    url = "https://shop.amul.com/your/api/endpoint"  # Replace with real endpoint
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()
```
Then replace `load_payload()` contents with `return fetch_live()`.
Add `requests` to `requirements.txt`.

This project already includes `fetcher.py` which will use `API_ENDPOINT` automatically if set.

### Persistent State
`persistent_state.py` stores last known stock status in `stock_state.json` so restarts won't re-alert unless a new transition occurs.

### Polling Jitter
`main.py` adds a small random delay each cycle to reduce synchronized calls when multiple instances run.

## Extending
- Add persistence (e.g., Redis or simple JSON file) to retain state across restarts.
- Support multiple products: the current parser already handles arrays; just feed the full API response.
- Add rate limiting / jitter to avoid synchronized polling.
- Add health endpoint (FastAPI) if needed for uptime checks.

## Minimal Design Notes
- No external framework => lightweight & cheap to run.
- Async Telegram client is hidden behind sync wrapper for simplicity.
- State is in-memory; restarts will re-alert the first time if product is already in stock.

## License
MIT (add a LICENSE file if you need formal licensing).

---
Questions or need enhancements? Open an issue or extend directly.
