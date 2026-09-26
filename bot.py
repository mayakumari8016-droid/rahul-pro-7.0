import os
import json
import time
import requests
import threading
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# 1. API Keys & Settings 
# ==========================================
# Telegram (यहाँ अपनी असली डिटेल्स डालें)
TELEGRAM_BOT_TOKEN = "8195533390:AAGuYQWfmdTvmJBS9D3JyoZ6W3HbO3UoRxc"
TELEGRAM_CHAT_ID = "6724287374"

# Gemini AI (यहाँ अपनी असली Key डालें)
GEMINI_API_KEY = "AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg"
genai.configure(api_key="AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg")

# Delta Exchange
DELTA_API_KEY = "LVIouI7TsxkNoP2QHMJfDtpZBohTgA"
DELTA_API_SECRET = "5i3oA7VkiVezVlnGSeUgILhdTf7CeGZUYQn0F3AP6U6Z82bmZItOqysZIAYB"

# Files
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
# 3. AI & Background Processing
# ==========================================
def ask_gemini_for_decision(tv_signal):
    rules = read_golden_rules()
    prompt = f"""
    New Signal: {json.dumps(tv_signal)}
    Rules: {rules}
    Check signal against rules. If safe reply 'YES', if risky reply 'NO'. Only 1 word.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        # TURBO SETTING: AI को सिर्फ 5 टोकन (1-2 शब्द) का आउटपुट देने को कहा है
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=5))
        decision = response.text.strip().upper()
        return "YES" in decision
    except Exception as e:
        print("Gemini AI Error:", e)
        return False

def place_delta_order(action, ticker, qty):
    print(f"Executing {action} order for {qty} {ticker}...")
    return {"status": "success", "order_id": "DLT-TURBO-999"}

def process_signal_background(tv_data):
    """यह पूरा फंक्शन बैकग्राउंड में चलेगा ताकि TradingView को इंतज़ार ना करना पड़े"""
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    send_telegram_message(f"⚡ <b>Turbo Signal Received</b>\nPair: {ticker}\nAction: {action}\nChecking with AI...")

    ai_approved = ask_gemini_for_decision(tv_data)

    if ai_approved:
        delta_response = place_delta_order(action, ticker, qty)
        if delta_response.get("status") == "success":
            tv_data["ai_decision"] = "YES"
            update_trade_memory(tv_data)
            send_telegram_message(f"✅ <b>TRADE EXECUTED</b>\nPair: {ticker}\nAI Approved: YES 🧠\nOrder ID: {delta_response['order_id']}")
    else:
        tv_data["ai_decision"] = "NO"
        update_trade_memory(tv_data)
# हम AI से कहेंगे कि वह अपना जवाब इस फॉर्मेट में दे:
prompt = f"""
New Signal: {json.dumps(tv_signal)}
Rules: {rules}
Check signal against rules. 
Reply strictly in this format: DECISION | REASON
Example: NO | RSI is 75, indicating an overbought market.
"""

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

    # TURBO MODE: सिग्नल को बैकग्राउंड थ्रेड में भेज दें 
    thread = threading.Thread(target=process_signal_background, args=(tv_data,))
    thread.start()

    # TradingView को तुरंत "200 OK" भेज दें (बिना AI का इंतज़ार किए)
    return jsonify({"status": "success", "message": "Signal processing in background ⚡"}), 200

# ==========================================
# 5. Server Run
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
# ==========================================
# 6. Agent 2: Self-Learning AI (Analytics)
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

    # टेस्टिंग के लिए लिमिट 2 रखी है, ताकि आप तुरंत चेक कर सकें
    if len(memory) < 2: 
        return jsonify({"status": "error", "message": f"Need more trades to learn. Current: {len(memory)}"})

    # टेलीग्राम पर अलर्ट भेजें कि AI अपना काम शुरू कर रहा है
    send_telegram_message("🧠 <b>Agent 2 Active:</b> Analyzing past trades to update Golden Rules...")

    prompt = f"""
    You are an expert Crypto Hedge Fund Manager. 
    Analyze my AI bot's recent trade memory: {json.dumps(memory)}
    
    Based on what failed or succeeded, write 3 strict, updated trading rules for the next trades.
    Format as plain text rules only. No greetings, no extra text.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        # यहाँ max_tokens नहीं लगाया है, क्योंकि रूल्स लिखने के लिए AI को सोचना पड़ेगा
        response = model.generate_content(prompt)
        new_rules = response.text.strip()
        
        # नई फाइल को पुराने रूल्स के ऊपर ओवरराइट (Overwrite) कर दें
        with open(RULES_FILE, 'w') as file:
            file.write(new_rules)
            
        send_telegram_message(f"✅ <b>Rules Updated Successfully!</b>\n\n{new_rules}")
        return jsonify({"status": "success", "message": "Golden Rules updated by Agent 2!"}), 200
        
    except Exception as e:
        print("Agent 2 Error:", e)
        return jsonify({"status": "error", "message": "Failed to update rules."}), 500
