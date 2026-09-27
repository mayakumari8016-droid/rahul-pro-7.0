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
# 3. HUNTER AI ENGINE (Pattern Completion Prompt)
# ==========================================
def ask_gemini_for_decision(tv_signal):
    rules = read_golden_rules()
    
    # 🚨 THE ULTIMATE PARROT-KILLER PROMPT (Few-Shot) 🚨
    # अब हम इसे इंस्ट्रक्शन नहीं दे रहे, बस एक पैटर्न दे रहे हैं जिसे इसे पूरा करना होगा।
    prompt = f"""Rules: {rules}

Example 1:
Signal: {{"action": "BUY", "ticker": "BTC", "rsi": "85"}}
Response: REJECTED - The RSI is 85, making the market highly overbought and risky for a buy.

Example 2:
Signal: {{"action": "BUY", "ticker": "ETH", "rsi": "40"}}
Response: APPROVED - The RSI is 40 and the trend is stable, offering a safe entry point.

Now analyze this actual signal:
Signal: {json.dumps(tv_signal)}
Response:"""
    
    url_models = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    try:
        resp = requests.get(url_models)
        data = resp.json()
        valid_models = [m['name'] for m in data.get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]
    except Exception as e:
        return False, f"Failed to fetch models: {str(e)}"
        
    if not valid_models:
        return False, "Google API returned zero valid models."

    last_error = ""
    for model_name in valid_models:
        url_gen = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {'Content-Type': 'application/json'}
        data_payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            response = requests.post(url_gen, headers=headers, json=data_payload)
            
            if response.status_code == 200:
                resp_json = response.json()
                output = resp_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                
                if output:
                    # सफाई
                    output = output.replace('`', '').replace('Response:', '').strip()
                    
                    if "-" in output:
                        parts = output.split("-", 1)
                        decision = parts[0].strip().upper()
                        reason = parts[1].strip()
                    else:
                        decision = "APPROVED" if "APPROVED" in output.upper() else "REJECTED"
                        reason = output
                        
                    is_approved = "APPROVED" in decision
                    return is_approved, f"[{model_name.replace('models/', '')}] {reason}"
            else:
                last_error = f"{model_name}: {response.text[:60]}"
        except Exception as e:
            last_error = f"{model_name} crashed: {str(e)[:50]}"
            
    return False, f"All {len(valid_models)} models failed. Last error: {last_error}"

def place_delta_order(action, ticker, qty):
    return {"status": "success", "order_id": "DLT-TURBO-999"}

def process_signal_background(tv_data):
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    send_telegram_message(f"⚡ <b>Turbo Signal Received</b>\nPair: {ticker}\nAction: {action}\nChecking with AI Hunter...")

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
