import os
import json
import requests
import threading
import time
import hmac
import hashlib
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db

app = Flask(__name__)

# ==========================================
# 1. API Keys & Settings (Fixed with .strip() to remove hidden spaces)
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip() 
DELTA_API_KEY = os.environ.get("DELTA_API_KEY", "").strip()
DELTA_API_SECRET = os.environ.get("DELTA_API_SECRET", "").strip()
RULES_FILE = "golden_rules.txt"

# ==========================================
# 2. Firebase Database Setup
# ==========================================
try:
    key_path = "/etc/secrets/firebase-key.json"
    if not os.path.exists(key_path):
        key_path = "firebase-key.json" 
        
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://rahul-algo-pro-default-rtdb.firebaseio.com/'
    })
    print("🔥 Firebase Connected Successfully!")
except Exception as e:
    print(f"⚠️ Firebase Connection Error: {e}")

# ==========================================
# 3. Helper Functions
# ==========================================
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Request Error: {e}")

def update_trade_memory(new_trade_data):
    try:
        ref = db.reference('trade_memory')
        ref.push(new_trade_data) 
    except Exception as e:
        print(f"⚠️ Firebase Save Error: {e}")

def get_recent_trades(limit=20):
    try:
        ref = db.reference('trade_memory')
        recent_data = ref.order_by_key().limit_to_last(limit).get()
        if recent_data:
            return list(recent_data.values())
        return []
    except Exception as e:
        return []

cached_rules = None
def read_golden_rules():
    global cached_rules
    if cached_rules is not None:
        return cached_rules
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'r') as file:
            cached_rules = file.read()
            return cached_rules
    return "No rules found."

# ==========================================
# 4. TAVILY NEWS ENGINE
# ==========================================
def get_live_market_news(ticker):
    if not TAVILY_API_KEY:
        return "No live news available."
        
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": f"Latest breaking crypto news and market sentiment about {ticker} today",
        "search_depth": "basic",
        "include_answer": False,
        "max_results": 2
    }
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            news_text = " ".join([res.get('content', '') for res in results])
            return news_text[:500] if news_text else "No major recent news found."
        return f"Tavily Error: {resp.status_code}"
    except Exception:
        return "Failed to fetch internet news."

# ==========================================
# 5. HUNTER AI ENGINE
# ==========================================
def ask_gemini_for_decision(tv_signal):
    rules = read_golden_rules()
    ticker = tv_signal.get("ticker", "Crypto")
    live_news = get_live_market_news(ticker)
    
    past_trades = get_recent_trades(20)
    history_text = json.dumps(past_trades) if past_trades else "No past trades."
    
    prompt = f"""
    You are an expert Crypto Trader. 
    1. CURRENT SIGNAL: {json.dumps(tv_signal)}
    2. LIVE NEWS: {live_news}
    3. YOUR PAST TRADES: {history_text}
    4. RULES: {rules}
    
    Task: Decide whether to approve (YES) or reject (NO) this current signal.
    Reply strictly in this format:
    DECISION | One short sentence explaining why.
    Example: YES | Strong buy signal and news is neutral.
    """
    
    url_models = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        resp = requests.get(url_models)
        valid_models = [m['name'] for m in resp.json().get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', []) and 'gemma' not in m['name'].lower() and 'gemini' in m['name'].lower()]
    except Exception:
        return False, "Failed to fetch models."

    for model_name in valid_models:
        url_gen = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
        data_payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            response = requests.post(url_gen, headers={'Content-Type': 'application/json'}, json=data_payload)
            if response.status_code == 200:
                output = response.json()['candidates'][0]['content']['parts'][0]['text'].replace('`', '').replace('*', '').strip()
                if "|" in output:
                    decision, reason = output.split("|", 1)
                else:
                    decision = output.split('\n')[0]
                    reason = "No specific reason provided."
                    
                return "YES" in decision.upper(), reason.strip()
        except Exception:
            continue
            
    return False, "All Gemini models failed."

# ==========================================
# 6. DELTA EXCHANGE REAL EXECUTION (Final Perfect Fix)
# ==========================================
def place_delta_order(action, ticker, qty):
    url = "https://api.delta.exchange/v2/orders"
    
    # 10-DIGIT TIME: Because Delta explicitly demands 10 digits
    timestamp = str(int(time.time()))
    
    # Payload strictly without spaces
    payload_str = json.dumps({
        "product_symbol": ticker, 
        "order_type": "market", 
        "side": "buy" if action.lower() == "buy" else "sell", 
        "size": int(float(qty))
    }, separators=(',', ':'))
    
    signature_data = 'POST' + timestamp + '/v2/orders' + payload_str
    if not DELTA_API_SECRET:
        return {"status": "failed", "error": "Delta Secret missing"}
        
    signature = hmac.new(DELTA_API_SECRET.encode('utf-8'), signature_data.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        'api-key': DELTA_API_KEY, 
        'timestamp': timestamp, 
        'signature': signature, 
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload_str)
        resp_data = response.json()
        
        if response.status_code == 200 and resp_data.get('success'):
            return {"status": "success", "order_id": resp_data.get('result', {}).get('id', 'Unknown')}
        
        return {"status": "failed", "error": f"Raw Error: {str(resp_data)}"}
    except Exception as e:
        return {"status": "failed", "error": f"System Error: {str(e)}"}

# ==========================================
# 7. SIGNAL PROCESSING (Smart Exit System)
# ==========================================
def process_signal_background(tv_data):
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    if action == "SELL":
        send_telegram_message(f"⚡ <b>Fast Exit Triggered</b>\nPair: {ticker}\n🚀 Skipping AI for instant profit booking...")
        ai_approved, ai_reason = True, "Auto-approved for fast exit (SELL signal)."
    else:
        send_telegram_message(f"⚡ <b>Turbo Signal Received</b>\nPair: {ticker}\nAction: {action}\n🧠 AI is checking history & news...")
        ai_approved, ai_reason = ask_gemini_for_decision(tv_data)

    if ai_approved:
        delta_response = place_delta_order(action, ticker, qty)
        tv_data["ai_decision"], tv_data["ai_reason"] = "YES", ai_reason
        if delta_response.get("status") == "success":
            tv_data["order_id"] = delta_response['order_id']
            update_trade_memory(tv_data)
            send_telegram_message(f"✅ <b>TRADE EXECUTED</b>\nPair: {ticker}\nAction: {action}\nOrder ID: {delta_response['order_id']}")
        else:
            tv_data["error"] = delta_response.get("error")
            update_trade_memory(tv_data)
            send_telegram_message(f"⚠️ <b>TRADE FAILED ON DELTA</b>\nReason: {delta_response.get('error')}")
    else:
        tv_data["ai_decision"], tv_data["ai_reason"] = "NO", ai_reason
        update_trade_memory(tv_data)
        send_telegram_message(f"🚫 <b>TRADE REJECTED</b>\nReason: {ai_reason}")

# ==========================================
# 8. Webhook & Auto-IP Startup
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    tv_data = request.json
    if not tv_data:
        return jsonify({"error": "No data"}), 400
    threading.Thread(target=process_signal_background, args=(tv_data,)).start()
    return jsonify({"status": "success"}), 200

def notify_startup():
    time.sleep(5)
    try:
        ip = requests.get('https://api.ipify.org').text
        send_telegram_message(f"🚀 <b>Bot Restarted Successfully!</b>\n\n🖥️ <b>Render Server IP:</b> <code>{ip}</code>")
    except:
        pass

@app.route('/', methods=['GET'])
def ping():
    return "Rahul Pro 7.0 is Live!", 200

if __name__ == '__main__':
    threading.Thread(target=notify_startup).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
