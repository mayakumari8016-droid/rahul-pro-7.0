import json
import google.generativeai as genai

# अपनी Gemini API Key डालें
genai.configure(api_key="AQ.Ab8RN6Lp_QzqNR-tBhIOI5IYaOi9tUFYVMc7FXHllFPZA-FWFg")

MEMORY_FILE = "trade_memory.json"
RULES_FILE = "golden_rules.txt"

def generate_golden_rules():
    print("Agent 1: पुरानी यादें पढ़ रहा हूँ...")
    
    # 1. पुरानी मेमोरी (JSON) को लोड करना
    try:
        with open(MEMORY_FILE, 'r') as file:
            memory_data = json.load(file)
    except Exception as e:
        print("मेमोरी फाइल नहीं मिली या खाली है!", e)
        return

    # 2. AI को निर्देश (Prompt) देना कि उसे क्या करना है
    prompt = f"""
    तुम एक प्रो-लेवल AI ट्रेडिंग एनालिस्ट हो। नीचे मेरे पिछले कुछ ट्रेड्स का JSON डेटा दिया गया है।
    तुम्हें इसे एनालाइज़ करना है और देखना है कि किन कंडीशंस (RSI, Trend, Ticker) में प्रॉफिट हुआ और किनमें लॉस।
    
    Data: {json.dumps(memory_data)}
    
    इस डेटा के आधार पर, मुझे कल के ट्रेडिंग के लिए सिर्फ 3 सख्त 'Golden Rules' बनाकर दो (बुलेट पॉइंट्स में)। 
    कोई फालतू बात मत लिखना, सिर्फ रूल्स लिखना ताकि मेरा दूसरा AI बॉट उसे पढ़कर ट्रेड ले सके।
    """

    # 3. Gemini AI से रूल्स बनवाना
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    
    # 4. नए रूल्स को एक टेक्स्ट फाइल में सेव करना
    golden_rules = response.text
    with open(RULES_FILE, 'w') as file:
        file.write(golden_rules)
        
    print("Agent 1 ने काम पूरा कर लिया! नए Golden Rules सेव हो गए हैं:\n")
    print(golden_rules)

# टेस्ट करने के लिए फंक्शन चलाएं
# generate_golden_rules()
