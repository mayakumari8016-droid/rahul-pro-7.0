import os
import json
import time
import requests
import google.generativeai as genai
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# 1. API Keys & Settings (यहाँ अपनी डिटेल्स डालें)
# ==========================================
# Telegram
TELEGRAM_BOT_TOKEN = "8195533390:AAGuYQWfmdTvmJBS9D3JyoZ6W3HbO3UoRxc"
TELEGRAM_CHAT_ID = "@poojasarkar88"

# Gemini AI
GEMINI_API_KEY = "AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg"
genai.configure(api_key=AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg)

# Delta Exchange (API Keys)
DELTA_API_KEY = "LVIouI7TsxkNoP2QHMJfDtpZBohTgA"
DELTA_API_SECRET = "5i3oA7VkiVezVlnGSeUgILhdTf7CeGZUYQn0F3AP6U6Z82bmZItOqysZIAYB"

# Files
MEMORY_FILE = "trade_memory.json"
RULES_FILE = "golden_rules.txt"
MAX_MEMORY = 50  

# ==========================================
# 2. Helper Functions (मेमोरी और टेलीग्राम)
# ==========================================
def send_telegram_message(message):
    """Telegram पर मैसेज भेजने का फंक्शन"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram Error:", e)

def update_trade_memory(new_trade_data):
    """50 ट्रेड की मेमोरी को अपडेट और फिल्टर करने का फंक्शन"""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as file:
            try:
                memory = json.load(file)
            except:
                memory = []
    else:
        memory = []

    # नया डेटा जोड़ें और पुराने को काटें (Sliding Window)
    memory.append(new_trade_data)
    if len(memory) > MAX_MEMORY:
        memory = memory[-MAX_MEMORY:]  

    with open(MEMORY_FILE, 'w') as file:
        json.dump(memory, file, indent=4)
        
def read_golden_rules():
    """Agent 1 के बनाए रूल्स को पढ़ने का फंक्शन"""
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'r') as file:
            return file.read()
    return "कोई पुराने रूल्स नहीं मिले। नॉर्मल लॉजिक से ट्रेड करो।"

# ==========================================
# 3. AI & Exchange Functions
# ==========================================
def ask_gemini_for_decision(tv_signal):
    """Gemini AI से पूछने का लॉजिक कि ट्रेड लेना है या नहीं"""
    rules = read_golden_rules()
    
    prompt = f"""
    तुम एक प्रो-लेवल AI ट्रेडिंग बॉट हो। 
    TradingView से यह नया सिग्नल आया है: {json.dumps(tv_signal)}
    
    मेरे पिछले ट्रेड्स के आधार पर मैंने ये Golden Rules बनाए हैं:
    {rules}
    
    सिग्नल और रूल्स को मैच करो। अगर ट्रेड सुरक्षित है तो सिर्फ 'YES' लिखो, और अगर रिस्क ज़्यादा है तो 'NO' लिखो। फालतू कुछ मत लिखना।
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        decision = response.text.strip().upper()
        return "YES" in decision
    except Exception as e:
        print("Gemini AI Error:", e)
        return False # अगर AI डाउन है, तो सेफ्टी के लिए ट्रेड मत लो

def place_delta_order(action, ticker, qty):
    """Delta Exchange पर आर्डर लगाने का फंक्शन"""
    # नोट: यह Delta Exchange का बेसिक API स्ट्रक्चर है। 
    # आपको इसे Delta के official documentation के हिसाब से Signature (HMAC) के साथ अपडेट करना पड़ सकता है।
    print(f"Executing {action} order for {qty} {ticker} on Delta Exchange...")
    
    # अभी टेस्टिंग के लिए यह डमी 'Success' रेस्पोंस देगा
    return {"status": "success", "order_id": "DLT-987654321"}

# ==========================================
# 4. Main Webhook Route (TradingView यहाँ सिग्नल भेजेगा)
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    # 1. TradingView से JSON डेटा लेना
    try:
        tv_data = request.json
    except Exception as e:
        return jsonify({"error": "Invalid JSON format"}), 400

    if not tv_data:
        return jsonify({"error": "No data received"}), 400

    # 2. सिग्नल डिटेल्स निकालना
    action = tv_data.get("action", "").upper()
    ticker = tv_data.get("ticker", "UNKNOWN")
    qty = tv_data.get("qty", "1")
    
    send_telegram_message(f"🔔 <b>New Signal Received</b>\nPair: {ticker}\nAction: {action}\nChecking with AI...")

    # 3. AI से पूछना (Golden Rules के साथ)
    ai_approved = ask_gemini_for_decision(tv_data)

    if ai_approved:
        # 4. अगर AI ने 'YES' कहा, तो डेल्टा पर ट्रेड लो
        delta_response = place_delta_order(action, ticker, qty)
        
        if delta_response.get("status") == "success":
            # 5. मेमोरी अपडेट करो और टेलीग्राम पर फाइनल मैसेज भेजो
            tv_data["ai_decision"] = "YES"
            update_trade_memory(tv_data)
            
            success_msg = f"✅ <b>TRADE EXECUTED</b>\nPair: {ticker}\nAction: {action}\nAI Approved: YES 🧠\nOrder ID: {delta_response['order_id']}"
            send_telegram_message(success_msg)
        else:
            send_telegram_message("❌ Delta Exchange Order Failed!")
    else:
        # अगर AI ने 'NO' कहा, तो ट्रेड छोड़ दो
        tv_data["ai_decision"] = "NO"
        update_trade_memory(tv_data)
        send_telegram_message(f"🚫 <b>TRADE REJECTED</b>\nPair: {ticker}\nAI found high risk based on Golden Rules.")

    return jsonify({"status": "success", "message": "Signal processed"}), 200

# ==========================================
# 5. Server Run (रेंडर के लिए)
# ==========================================
if __name__ == '__main__':
    # Render अपने आप PORT देता है, इसलिए os.environ का इस्तेमाल करना ज़रूरी है
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
