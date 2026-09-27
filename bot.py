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
# 1. API Keys & Settings (Secured)
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") 

DELTA_API_KEY = os.environ.get("DELTA_API_KEY")
DELTA_API_SECRET = os.environ.get("DELTA_API_SECRET")

RULES_FILE = "golden_rules.txt"

# ==========================================
# 2. Firebase Database Setup (Super Fast Memory)
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
# 3. Helper Functions & FIREBASE READING
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
        print("⚡ Data saved to Firebase!")
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
        print(f"⚠️ Error reading history: {e}")
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
    return "No rules found. Analyze purely based on technical signal."

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
# 5. HUNTER AI ENGINE (With 20-Trade Memory)
# ==========================================
def ask_gemini_for_decision(tv_signal):
    rules = read_golden_rules()
    ticker = tv_signal.get("ticker", "Crypto")
    live_news = get_live_market_news(ticker)
    
    past_trades = get_recent_trades(20)
    history_text = json.dumps(past_trades) if past_trades else "No past trades yet. This is the first trade."
    
    prompt = f"""
    You are an expert Crypto Trader. 
    
    1. CURRENT SIGNAL: {json.dumps(tv_signal)}
    2. LIVE NEWS: {live_news}
    3. YOUR PAST TRADES (Up to 20): {history_text}
    4. RULES: {rules}
    
    Task: Decide whether to approve (YES) or reject (NO) this current signal.
    - Read 'YOUR PAST TRADES'. If you notice a pattern of recent failed trades with similar signals, be extra cautious or reject.
    - If Live Market News says "No major recent news found", DO NOT reject the trade just because of missing news. Base your YES/NO decision on technical Signal Data and Past History.
    
    Reply strictly in this format:
    DECISION | One short sentence explaining why (mention past history if relevant).
    Example: YES | Strong buy signal and news is neutral, previous similar trades were successful.
    """
    
    url_models = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        resp = requests.get(url_models)
        data = resp.json()
        valid_models = [m['name'] for m in data.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', []) and 'gemma' not in m['name'].lower() and 'gemini' in m['name'].lower()]
    except Exception as e:
        return False, f"Failed to fetch models: {str(e)}"
        
    if not valid_models:
        return False, "Google API returned zero valid Gemini models."

    last_error = ""
    for model_name in valid_models:
        url_gen = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data_payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            response = requests.post(url_gen, headers=headers, json=data_payload)
            if response.status_code == 200:
                resp_json = response.json()
                candidates = resp_json.get('candidates', [])
                if candidates and 'content' in candidates[0] and 'parts' in candidates[0]['content']:
                    output = candidates[0]['content']['parts'][0].get('text', '')
                    if output:
                        output = output.replace('`', '').replace('*', '').strip()
                        if "|" in output:
                            decision, reason = output.split("|", 1)
                            reason = reason.strip().split('\n')[0]
                        else:
                            decision = output.split('\n')[0]
                            reason = "No specific reason provided."
                            
                        is_approved = "YES" in decision.upper() or "APPROVED" in decision.upper()
                        return is_approved, reason.strip()
                else:
                    last_error = f"{model_name}: AI blocked or empty response."
            else:
                last_error = f"{model_name}: {response.text[:60]}"
        except Exception as e:
            last_error = f"{model_name} crashed: {str(e)[:50]}"
            
    return False, f"All Gemini models failed. Last error: {last_error}"

# ==========================================
# 6. DELTA EXCHANGE REAL EXECUTION
# ==========================================
def place_delta_order(action, ticker, qty):
    url = "https://api.delta.exchange/v2/orders"
    method = 'POST'
    timestamp = str(int(time.time() * 1000))
    path = '/v2/orders'
    
    payload = {
        "product_symbol": ticker,
        "order_type": "market",
        "side": "buy" if action.lower() == "buy" else "sell",
        "size": int(float(qty))
    }
    
    payload_str = json.dumps(payload)
    signature_data = method + timestamp + path + payload_str
    
    if not DELTA_API_SECRET:
        return {"status": "failed", "error": "Delta Secret missing"}
        
    signature = hmac.new(DELTA_API_SECRET.encode('utf-8'), signature_data.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {'api-key': DELTA_API_KEY, 'timestamp': timestamp, 'signature': signature, 'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        resp_data = response.json()
        if response.status_code == 200 and resp_data.get('success'):
            return {"status": "success", "order_id": resp_data.get('result', {}).get('id', 'Unknown')}
        return {"status": "failed", "error": resp_data.get('error', {}).get('message', 'API Error')}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# ==========================================
# 7. SIGNAL PROCESSING (Smart Exit System)
# ==========================================
def process_signal_background(tv_data):
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    # अगर SELL सिग्नल है, तो AI को बाईपास करके तुरंत एग्जिट करें (Fast Exit)
    if action == "SELL":
        send_telegram_message(f"⚡ <b>Fast Exit Triggered</b>\nPair: {ticker}\nAction: {action}\n🚀 Skipping AI for instant profit booking/stop loss...")
        ai_approved = True
        ai_reason = "Auto-approved for fast exit (SELL signal)."
    
    # अगर BUY सिग्नल है, तभी AI 20 ट्रेड्स की हिस्ट्री पढ़ेगा
    else:
        send_telegram_message(f"⚡ <b>Turbo Signal Received</b>\nPair: {ticker}\nAction: {action}\n🧠 AI is reading past 20 trades and live news...")
        ai_approved, ai_reason = ask_gemini_for_decision(tv_data)

    if ai_approved:
        delta_response = place_delta_order(action, ticker, qty)
        tv_data["ai_decision"] = "YES"
        tv_data["ai_reason"] = ai_reason
        
        if delta_response.get("status") == "success":
            tv_data["order_id"] = delta_response['order_id']
            update_trade_memory(tv_data)
            send_telegram_message(f"✅ <b>TRADE EXECUTED</b>\nPair: {ticker}\nAction: {action}\nReason: {ai_reason}\nOrder ID: {delta_response['order_id']}")
        else:
            tv_data["error"] = delta_response.get("error")
            update_trade_memory(tv_data)
            send_telegram_message(f"⚠️ <b>TRADE FAILED ON DELTA</b>\nReason: {delta_response.get('error')}")
    else:
        tv_data["ai_decision"] = "NO"
        tv_data["ai_reason"] = ai_reason
        update_trade_memory(tv_data)
        send_telegram_message(f"🚫 <b>TRADE REJECTED</b>\nReason: {ai_reason}")

# ==========================================
# 8. Flask Routes
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        tv_data = request.json
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    if not tv_data:
        return jsonify({"error": "No data"}), 400

    thread = threading.Thread(target=process_signal_background, args=(tv_data,))
    thread.start()
    return jsonify({"status": "success", "message": "Signal processing in background ⚡"}), 200

@app.route('/', methods=['GET'])
def ping():
    return "Rahul Pro 7.0 Bot is alive and Self-Learning (Smart Exit Active)!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
