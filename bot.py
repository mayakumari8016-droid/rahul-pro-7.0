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
    except Exception as e:
        print("Telegram Error:", e)

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
# 3. AI & Background Processing (DIRECT BYPASS)
# ==========================================
def ask_gemini_for_decision(tv_signal):
    rules = read_golden_rules()
    prompt = f"""
    New Signal: {json.dumps(tv_signal)}
    Rules: {rules}
    Check signal against rules. 
    Reply strictly in this format: DECISION | REASON
    Example: NO | RSI is 75, indicating an overbought market.
    """
    
    # Direct Google API Call (No library needed)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        resp_json = response.json()
        
        if 'error' in resp_json:
            return False, f"API_Error: {resp_json['error']['message'][:100]}"
            
        output = resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
        
        if "|" in output:
            decision, reason = output.split("|", 1)
        else:
            decision = output
            reason = "AI didn't provide a specific reason."
            
        return "YES" in decision.upper(), reason.strip()
    except Exception as e:
        error_msg = str(e).replace('\n', ' ')
        return False, f"Request_Error: {error_msg[:100]}"

def place_delta_order(action, ticker, qty):
    return {"status": "success", "order_id": "DLT-TURBO-999"}

def process_signal_background(tv_data):
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    send_telegram_message(f"⚡ <b>Turbo Signal Received</b>\nPair: {ticker}\nAction: {action}\nChecking with AI...")

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
# 4. Agent 2: Self-Learning AI (DIRECT BYPASS)
# ==========================================
@app.route('/learn', methods=['GET'])
def trigger_agent_2():
    if not os.path.exists(MEMORY_FILE):
        return jsonify({"status": "error", "message": "No memory file found."})
        
    with open(MEMORY_FILE, 'r') as file:
        try:
            memory = json.load(file)
        except:
            return jsonify({"status": "error", "message": "Memory file empty."})

    if len(memory) < 2: 
        return jsonify({"status": "error", "message": f"Need more trades to learn. Current: {len(memory)}"})

    send_telegram_message("🧠 <b>Agent 2 Active:</b> Analyzing past trades...")

    prompt = f"""
    You are an expert Crypto Hedge Fund Manager. 
    Analyze my AI bot's recent trade memory: {json.dumps(memory)}
    Based on what failed or succeeded, write 3 strict, updated trading rules for the next trades.
    Format as plain text rules only. No greetings, no extra text.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        resp_json = response.json()
        
        if 'error' in resp_json:
            return jsonify({"status": "error", "message": resp_json['error']['message']}), 500
            
        new_rules = resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
        
        with open(RULES_FILE, 'w') as file:
            file.write(new_rules)
            
        send_telegram_message(f"✅ <b>Rules Updated Successfully!</b>\n\n{new_rules}")
        return jsonify({"status": "success", "message": "Golden Rules updated by Agent 2!"}), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 5. Main Webhook Route
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
