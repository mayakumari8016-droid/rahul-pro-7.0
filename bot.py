import os
import json
import requests
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# 1. API Keys & Settings 
# ==========================================
TELEGRAM_BOT_TOKEN = "8195533390:AAGuYQWfmdTvmJBS9D3JyoZ6W3HbO3UoRxc"
TELEGRAM_CHAT_ID = "6724287374"

GEMINI_API_KEY = "AQ.Ab8RN6KzJPR07f7XhVPQYedI5NOuTGHU2ZuoZrOfhHzogLoOGA"

DELTA_API_KEY = "LVIouI7TsxkNoP2QHMJfDtpZBohTgA"
DELTA_API_SECRET = "5i3oA7VkiVezVlnGSeUgILhdTf7CeGZUYQn0F3AP6U6Z82bmZItOqysZIAYB"

MEMORY_FILE = "trade_memory.json"
RULES_FILE = "golden_rules.txt"
MAX_MEMORY = 50  

# ==========================================
# 2. Helper Functions
# ==========================================
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception:
        pass

def update_trade_memory(new_trade_data):
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as file:
            try:
                memory = json.load(file)
            except:
                memory = []
    else:
        memory = []

    memory.append(new_trade_data)
    if len(memory) > MAX_MEMORY:
        memory = memory[-MAX_MEMORY:]  

    with open(MEMORY_FILE, 'w') as file:
        json.dump(memory, file, indent=4)
        
def read_golden_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'r') as file:
            return file.read()
    return "No rules found."

# ==========================================
# 3. AUTO-DISCOVERY AI ENGINE
# ==========================================
def get_working_model():
    # यह फंक्शन Google से पूछता है कि इस Key के लिए कौन से मॉडल उपलब्ध हैं
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        resp = requests.get(url)
        data = resp.json()
        
        if 'error' in data:
            return None, f"Google Key Error: {data['error'].get('message', str(data))}"
            
        valid_models = []
        for m in data.get('models', []):
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                valid_models.append(m['name'])
                
        if not valid_models:
            return None, "Key is working, but Google says ZERO models are allowed for this key."
            
        # जो भी पहला मॉडल मिलेगा, हम उसी का इस्तेमाल करेंगे
        best_model = valid_models[0]
        for m in valid_models:
            if 'gemini-1.5-flash' in m:
                best_model = m
                break
                
        return best_model, "Success"
    except Exception as e:
        return None, f"Network Error: {str(e)}"

def ask_gemini_for_decision(tv_signal):
    model_name, status_msg = get_working_model()
    
    if not model_name:
        return False, status_msg  # असली एरर टेलीग्राम पर भेज देगा
        
    rules = read_golden_rules()
    prompt = f"""
    New Signal: {json.dumps(tv_signal)}
    Rules: {rules}
    Check signal against rules. 
    Reply strictly in this format: DECISION | REASON
    Example: NO | RSI is 75, indicating an overbought market.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            return False, f"API_Error ({response.status_code}) on {model_name}: {response.text[:100]}"
            
        resp_json = response.json()
        output = resp_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        if not output:
            return False, f"Empty Response from {model_name}"
            
        if "|" in output:
            decision, reason = output.split("|", 1)
        else:
            decision = output
            reason = f"No formatted reason. Output: {output[:50]}"
            
        return "YES" in decision.upper(), reason.strip()
        
    except Exception as e:
        return False, f"Crash Error: {str(e)[:100]}"

def place_delta_order(action, ticker, qty):
    return {"status": "success", "order_id": "DLT-TURBO-999"}

def process_signal_background(tv_data):
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    send_telegram_message(f"⚡ <b>Turbo Signal Received</b>\nPair: {ticker}\nAction: {action}\nChecking with Auto-Discovery AI...")

    ai_approved, ai_reason = ask_gemini_for_decision(tv_data)

    if ai_approved:
        delta_response = place_delta_order(action, ticker, qty)
        if delta_response.get("status") == "success":
            tv_data["ai_decision"] = "YES"
            tv_data["ai_reason"] = ai_reason
            update_trade_memory(tv_data)
            send_telegram_message(f"✅ <b>TRADE EXECUTED</b>\nPair: {ticker}\nAI Approved: YES 🧠\nReason: {ai_reason}\nOrder ID: {delta_response['order_id']}")
    else:
        tv_data["ai_decision"] = "NO"
        tv_data["ai_reason"] = ai_reason
        update_trade_memory(tv_data)
        send_telegram_message(f"🚫 <b>TRADE REJECTED</b>\nPair: {ticker}\nReason: {ai_reason}")

# ==========================================
# 4. Main Webhook Route
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
