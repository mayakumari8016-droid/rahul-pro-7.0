from flask import Flask, request, jsonify
import time
import hmac
import hashlib
import requests
import json
import os
import google.generativeai as genai

app = Flask(__name__)

# ==========================================
# 1. API CREDENTIALS
# ==========================================
GEMINI_API_KEY = 'AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg'
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

DELTA_API_KEY = 'LVIouI7TsxkNoP2QHMJfDtpZBohTgA'
DELTA_API_SECRET = '5i3oA7VkiVezVlnGSeUgILhdTf7CeGZUYQn0F3AP6U6Z82bmZItOqysZIAYB'
BASE_URL = 'https://api.india.delta.exchange'

TELEGRAM_TOKEN = '8195533390:AAGuYQWfmdTvmJBS9D3JyoZ6W3HbO3UoRxc'
TELEGRAM_CHAT_ID = '@poojasarkar88'

MEMORY_FILE = 'trade_memory.json'
STATUS_FILE = 'bot_status.json'

# ==========================================
# 2. HELPER FUNCTIONS & MEMORY SYSTEM
# ==========================================
def generate_signature(secret, method, path, query_string='', payload=''):
    message = method + str(int(time.time())) + path + query_string + payload
    return hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except:
        pass

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f:
            return json.load(f)
    return []

def save_to_memory(ticker, outcome, reason, context):
    history = load_memory()
    history.append({"time": time.strftime("%Y-%m-%d %H:%M"), "ticker": ticker, "outcome": outcome, "context": context})
    if len(history) > 10: history = history[-10:] # Keep last 10 trades
    with open(MEMORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)

def check_bot_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            return json.load(f).get("status", "active")
    return "active"

def update_bot_status(status):
    with open(STATUS_FILE, 'w') as f:
        json.dump({"status": status}, f)

# ==========================================
# 3. TELEGRAM REMOTE CONTROL (Webhook)
# ==========================================
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    req = request.json
    if 'message' in req and 'text' in req['message']:
        text = req['message']['text'].lower()
        if text == '/pause':
            update_bot_status("paused")
            send_telegram_message("🛑 *BOT PAUSED* - No new trades will be taken.")
        elif text == '/resume':
            update_bot_status("active")
            send_telegram_message("▶️ *BOT RESUMED* - Ready for new trades.")
    return jsonify({"status": "ok"}), 200

# ==========================================
# 4. TRADINGVIEW WEBHOOK & AI ENGINE
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data: return jsonify({"error": "No data"}), 400

    action = data.get('action')
    ticker = data.get('ticker', 'BTC')
    base_qty = float(data.get('qty', 1))
    
    # TV se market context aayega
    rsi = data.get('rsi', 'N/A')
    adx = data.get('adx', 'N/A')
    trend = data.get('trend', 'N/A')
    ai_prob = data.get('ai_prob', 'N/A')
    
    market_context = f"RSI: {rsi}, ADX: {adx}, Trend: {trend}, SMC Prob: {ai_prob}%"

    # EXIT ALERT LOGIC
    if action == 'exit':
        reason = data.get('reason', 'Unknown')
        send_telegram_message(f"🔔 *Trade Closed*\nCoin: {ticker}\nStatus: {reason}")
        outcome = "PROFIT" if "Target Hit" in reason else "LOSS"
        save_to_memory(ticker, outcome, reason, market_context)
        return jsonify({"status": "exit logged"}), 200

    # CHECK PAUSE STATUS
    if check_bot_status() == "paused":
        send_telegram_message(f"⚠️ *Trade Ignored*\nAction: {action}\nReason: Bot is PAUSED via Telegram.")
        return jsonify({"status": "paused"}), 200

    # PREPARE AI MEMORY
    past_trades = load_memory()
    memory_txt = "No past trades." if not past_trades else "\n".join([f"- {t['outcome']} when {t['context']}" for t in past_trades])

    # ADVANCED AI PROMPT (God Mode)
    prompt = f"""
    You are an elite quantitative trading AI. Market is signaling a {action.upper()} for {ticker}.
    Current Market Context: {market_context}.
    Past 10 Trades History (Learn from this):
    {memory_txt}
    
    Analyze the current context vs past mistakes. Also consider current global crypto sentiment.
    If setup is perfect, reply 'YES_FULL'. 
    If setup is okay but slightly risky (e.g. low ADX or Choppy), reply 'YES_HALF' to reduce risk.
    If it looks like a trap based on your learning, reply 'NO'.
    Reply strictly with ONE WORD: YES_FULL, YES_HALF, or NO.
    """
    
    ai_decision = ai_model.generate_content(prompt).text.strip().upper()
    print(f"🤖 AI Decision: {ai_decision}")

    if 'NO' in ai_decision:
        send_telegram_message(f"🔴 *AI Status: NO*\n❌ Trade Rejected for {ticker}\nContext: {market_context}")
        return jsonify({"status": "aborted", "ai": ai_decision}), 200

    # DYNAMIC QUANTITY CALCULATION
    final_qty = base_qty
    if 'YES_HALF' in ai_decision:
        final_qty = max(1, int(base_qty / 2)) # Adhi quantity
        
    final_qty = int(final_qty) # Convert to integer for Delta Exchange

    # DELTA EXCHANGE EXECUTION
    path, method = '/v2/orders', 'POST'
    timestamp = str(int(time.time()))
    payload = json.dumps({"product_id": 27, "size": final_qty, "side": "buy" if action == 'buy' else "sell", "order_type": "market"})
    headers = {'api-key': DELTA_API_KEY, 'timestamp': timestamp, 'signature': generate_signature(DELTA_API_SECRET, method, path, '', payload), 'Content-Type': 'application/json'}
    
    res = requests.post(BASE_URL + path, headers=headers, data=payload).json()

    if res.get('success'):
        msg = f"🟢 *AI Status: {ai_decision}*\n✅ *Order Placed*\nCoin: {ticker}\nAction: {action.upper()}\nQty Executed: {final_qty}\nContext: {market_context}"
        send_telegram_message(msg)
        return jsonify({"status": "success", "ai": ai_decision}), 200
    else:
        send_telegram_message(f"⚠️ *Delta Error*\nCoin: {ticker}\nError: {res}")
        return jsonify({"error": res}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
