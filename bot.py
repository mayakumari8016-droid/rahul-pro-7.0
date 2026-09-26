from flask import Flask, request, jsonify
import time
import hmac
import hashlib
import requests
import json
import google.generativeai as genai

app = Flask(__name__)

# ==========================================
# 1. API CREDENTIALS SETUP
# ==========================================
# Google Gemini AI Setup
GEMINI_API_KEY = 'AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg'
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# Delta Exchange India Setup
DELTA_API_KEY = 'LVIouI7TsxkNoP2QHMJfDtpZBohTgA'
DELTA_API_SECRET = '5i3oA7VkiVezVlnGSeUgILhdTf7CeGZUYQn0F3AP6U6Z82bmZItOqysZIAYB'
BASE_URL = 'https://api.india.delta.exchange'

# Telegram Setup
TELEGRAM_TOKEN = '8195533390:AAGuYQWfmdTvmJBS9D3JyoZ6W3HbO3UoRxc'
TELEGRAM_CHAT_ID = '@poojasarkar88' # Username के आगे @ लगाना ज़रूरी है

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def generate_signature(secret, method, path, query_string='', payload=''):
    message = method + timestamp + path + query_string + payload
    signature = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
        print("✅ Telegram message sent!")
    except Exception as e:
        print("❌ Telegram send error:", e)

# ==========================================
# 3. MAIN WEBHOOK & AI ANALYSIS ENGINE
# ==========================================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"TradingView Alert Received: {data}")

    if not data:
        return jsonify({"error": "Koi data nahi mila"}), 400

    try:
        action = data.get('action') # 'buy', 'sell', या 'exit'
        ticker = data.get('ticker', 'BTC') 
        size = int(data.get('qty', 1))
        reason = data.get('reason', 'Unknown') # Exit होने का कारण

        # --- NAYA CODE: Agar alert EXIT (Profit/Loss Book) ka hai ---
        if action == 'exit':
            print(f"🚪 Exit Alert Received: {reason}")
            exit_msg = f"🔔 *Trade Update*\nCoin: {ticker}\nStatus: {reason}"
            send_telegram_message(exit_msg)
            
            # (अभी के लिए यह सिर्फ टेलीग्राम पर मैसेज भेजेगा। अगर आप चाहते हैं कि Delta Exchange पर भी आर्डर कट जाए, तो हम आगे उसका कोड भी जोड़ सकते हैं।)
            return jsonify({"status": "success", "message": "Exit alert sent to Telegram"}), 200

        # --- STEP A: Google Gemini AI Analysis (सिर्फ Buy/Sell के लिए) ---
        prompt = f"Market is currently signaling a {action.upper()} for {ticker}. Analyze if this is safe based on general crypto volatility rules and reply with ONLY ONE WORD: 'YES' or 'NO'."
        
        ai_response = ai_model.generate_content(prompt)
        ai_decision = ai_response.text.strip().upper()
        print(f"🤖 Gemini AI Decision: {ai_decision}")

        # Agar AI mana kar de, toh Telegram message bhej kar trade drop kar do
        if 'YES' not in ai_decision:
            print("❌ Trade rejected by Gemini AI analysis.")
            msg = f"🔴 *Gemini AI Status: NO*\n❌ Trade Rejected for {ticker}\nAction: {action.upper()}\nReason: Market not safe."
            send_telegram_message(msg)
            return jsonify({"status": "aborted", "reason": "AI sentiment check failed", "ai_decision": ai_decision}), 200

        # --- STEP B: Delta Exchange Order Execution ---
        path = '/v2/orders'
        url = BASE_URL + path
        method = 'POST'
        
        global timestamp
        timestamp = str(int(time.time()))

        order_payload = {
            "product_id": 27,  
            "size": size,
            "side": "buy" if action == 'buy' else "sell",
            "order_type": "market"
        }
        
        payload_str = json.dumps(order_payload)
        signature = generate_signature(DELTA_API_SECRET, method, path, '', payload_str)

        headers = {
            'api-key': DELTA_API_KEY,
            'timestamp': timestamp,
            'signature': signature,
            'Content-Type': 'application/json'
        }

        response = requests.post(url, headers=headers, data=payload_str)
        res_data = response.json()

        if response.status_code == 200 and res_data.get('success'):
            print("✅ AI Verified & Order Placed Successfully on Delta:", res_data)
            
            # Telegram Success Message
            msg = f"🟢 *Gemini AI Status: YES*\n✅ *Order Placed on Delta*\nCoin: {ticker}\nAction: {action.upper()}\nQty: {size}"
            send_telegram_message(msg)

            return jsonify({"status": "success", "ai_check": "passed", "ai_decision": ai_decision, "response": res_data}), 200
        else:
            print("❌ Delta Exchange Error:", res_data)
            # Telegram Error Message
            error_msg = f"⚠️ *Delta Order Failed*\nCoin: {ticker}\nAction: {action.upper()}\nError: Check Delta Logs."
            send_telegram_message(error_msg)
            return jsonify({"status": "failed", "error": res_data}), 400

    except Exception as e:
        print("❌ Server Error:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
