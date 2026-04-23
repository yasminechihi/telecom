import json
import random
import copy
from datetime import datetime, timedelta

def generate_voicebot_logical_dataset(filename="voicebot_telecom_final_7000.json"):
    # =======================
    # DONNÉES DE BASE
    # =======================
    first_names = [
        "أمين", "فاطمة", "ياسين", "مريم", "أحمد", "ليلى", "سامي", "هند", "مراد", "إيناس", 
        "هيثم", "خديجة", "نزار", "سلوى", "رؤوف", "نجلاء", "وليد", "ريم", "زياد",
        "سلمى", "مهدي", "سارة", "إسكندر", "ياسمين", "يوسف", "عبير", "كريم", "نور", "أنيس", "إيمان"
    ]

    last_names = [
        "الدريدي", "بن عرفة", "الورتاني", "المزيغي", "العياري", "الطرابلسي", "الجلاصي", 
        "المنصوري", "الهمامي", "القروي", "بالقاسم", "الماجري", "الزغيدي", "الشريف",
        "بن سالم", "العبيدي", "الغربي", "بن موسى", "المؤدب", "النفطي", "البجاوي", 
        "بن رمضان", "الرياحي", "الزواري"
    ]
    
    cities_map = {
        "بنزرت": "منزل بورقيبة", "تونس": "حي الخضراء", "سوسة": "حمّام سوسة",
        "صفاقس": "طريق تنيور", "نابل": "الحمامات", "القيروان": "بوحجلة",
        "مدنين": "جرجيس", "باجة": "تستور", "جندوبة": "طبرقة", "توزر": "دقاش",
        "أريانة": "سكرة", "بن عروس": "رادس", "منوبة": "طبربة", "زغوان": "الفحص",
        "المنستير": "قصر هلال", "المهدية": "الشابة", "سيدي بوزيد": "الرقاب",
        "القصرين": "سبيطلة", "قفصة": "المتلوي", "قابس": "مارث",
        "تطاوين": "غمراسن", "قبلي": "دوز", "الكاف": "السرس", "سليانة": "مكثر"
    }

    # ==========================================
    # SCÉNARIOS LOGIQUES
    # ==========================================
    all_scenarios = [
        {
            "intent": "network_failure", "net": "5G/Réseau", "sentiment": "Negative", "action": "check_network_status",
            "user_init": "الريزو طايح برشا في {addr}، {city}. مجمتش نخدم télétravail.",
            "bot_ask": "الخدمة موبيل ولا فيكس؟",
            "user_ans": "نحكي عالموبيل، التليفون ميفوتش شلطة وحدة.",
            "bot_final": "سامحنا خويا الغالي, فما ضغط كبير حالياً في {city} وقاعدين نصلحو في العطب، تو يرجع مريغل."
        },
        {
            "intent": "internet_outage", "net": "ADSL/Fixe", "sentiment": "Negative", "action": "technical_diagnosis",
            "user_init": "الأنترنت مقصوصة في {addr} عندها 3 أيام.",
            "bot_ask": "ثبتلي بربي في الموديم يشعل بالأحمر؟",
            "user_ans": "إي نعم، لومبة لوس (LOS) تشعل بالأحمر.",
            "bot_final": "يا خويا سامحنا، أعطيني رقم الخط نثبتلك وين واصل المشكل."
        },
        {
            "intent": "slow_internet", "net": "VDSL", "sentiment": "Negative", "action": "speed_test_check",
            "user_init": "الديبي في {city} يضحك، نخلص في برشا فلوس و الواصل شي يحشم.",
            "bot_ask": "عملت test de débit avant ما تطلبنا؟",
            "user_ans": "إي عملت، واصلني 4 ميغا برك وأنا عامل 20.",
            "bot_final": "واضح، بربي أعمل test de débit وابعثلنا capture، وجرب طفي الموديم و عاود شعلو."
        },
        {
            "intent": "billing_dispute", "net": "Billing", "sentiment": "Negative", "action": "retrieve_invoice_details",
            "user_init": "الفاتورة جاتني غالية برشا الشهر هذا في {addr}.",
            "bot_ask": "تحب نثبتولك في ديتاي الاستهلاك؟",
            "user_ans": "إي يرحم والديك، ثبتلي خاطر المبلغ مش عادي.",
            "bot_final": "مرحبا بيك، تنجم تثبت في MyTT، وإلا اعطيني رقمك نثبتلك كان فما غلطة."
        },
        {
            "intent": "payment_issue", "net": "Administrative", "sentiment": "Negative", "action": "reactivate_line",
            "user_init": "خلصت الفاتورة عبر تطبيق MyTT و لتو الخط مقصوص في {city}.",
            "bot_ask": "عندك رقم المعاملة (numéro de transaction)؟",
            "user_ans": "إي عندي، لحظة هاهو قدامي.",
            "bot_final": "سامحنا، ساعات السيستيم ياخذ شوية وقت. اعطيني الرقم تو نرجعلك الخط يخدم فوراً."
        },
        {
            "intent": "installation_delay", "net": "ADSL/Fixe", "sentiment": "Negative", "action": "track_order_status",
            "user_init": "يا تليكوم لتو لا جيتو ركبتو الفيكس في {addr}. عندي شهر نستنى.",
            "bot_ask": "عندك رقم المطلب (numéro de demande)؟",
            "user_ans": "عندي، المطلب تعدّى عندو برشا وما جاني حد.",
            "bot_final": "مرحبا بيك، نعتذرو عالـ retard. اعطيني رقم المطلب باش نثبتلك مع سرفيس تيكنيك."
        },
        {
            "intent": "coverage_inquiry", "net": "Fibre Optique", "sentiment": "Neutral", "action": "check_fiber_availability",
            "user_init": "وقتاش ناوين تسيبو الفيبر في {addr}؟ عيينا من الـ ADSL.",
            "bot_ask": "تحب نثبتولك في التغطية في نهجك؟",
            "user_ans": "إي ثبتلي يرحم والديك، رانا نستناو فيها بفارغ الصبر.",
            "bot_final": "الفيبر قاعدين نركبو فيه بالتدريج في {city}، خليلي رقمك تو نكلموك أول ما يوصل."
        },
        {
            "intent": "offers_inquiry", "net": "5G/Réseau", "sentiment": "Neutral", "action": "provide_offer_info",
            "user_init": "نحب نعرف شنوما أحسن عروض الـ 5G عندكم توة في {city}؟",
            "bot_ask": "تلوج على عرض يومي ولا شهري؟",
            "user_ans": "نلوج على forfait شهري يكون فيه برشا انترنت.",
            "bot_final": "أهلا بيك، عندنا عروض خيالية توة، تنجم تطلب *140# وتختار الفورفي اللي يساعدك."
        },
        {
            "intent": "hardware_failure", "net": "ADSL/Fixe", "sentiment": "Negative", "action": "replace_modem",
            "user_init": "موديم يطفى و يشعل وحدو في {addr}. بدلتو مرتين و ديما نفس المشكل.",
            "bot_ask": "ثبت في الخيوط و الـ prise؟",
            "user_ans": "إي ثبت في كل شي، حتى الخيوط جدد.",
            "bot_final": "واضح اللي فما مشكل في الـ alimentation. تنجم تبدلو بلاش فلوس من أقرب أجونس."
        },
        {
            "intent": "wifi_signal_issue", "net": "ADSL/Fixe", "sentiment": "Negative", "action": "technical_advice",
            "user_init": "الويفي (Wifi) ميوصلش للبيت لداخل في {addr}، شنوة الحل؟",
            "bot_ask": "الموديم محطوط في بلاصة مفتوحة؟",
            "user_ans": "إي حاطو في وسط الدار، أما لداخل ميوصلش.",
            "bot_final": "ينجم يكون من البلاصة، جرب حطو في بلاصة عالية وإلا ننصحك بـ répéteur Wifi."
        },
        {
            "intent": "sim_replacement", "net": "Mobile", "sentiment": "Neutral", "action": "provide_store_location",
            "user_init": "السيم ضاعتلي في {city}، نحب نطلع وحدة أخرى بنفس الرقم.",
            "bot_ask": "الرقم مسجل باسمك ببطاقة التعريف؟",
            "user_ans": "إي نعم، مسجل باسمي.",
            "bot_final": "مرحبا بيك، لازمك تمشي لأقرب بوتيك تليكوم ببطاقة التعريف باش تطلع سيم جديدة."
        },
        {
            "intent": "roaming_issue", "net": "Mobile", "sentiment": "Negative", "action": "check_roaming_status",
            "user_init": "أنا لبرا وتوا الـ Roaming ميعملش كونيكسيون.",
            "bot_ask": "ثبت اللي الـ Données en itinérance مفعّلة في تليفونك؟",
            "user_ans": "إي مفعلة، أما لتوا لا حب يمشي شي.",
            "bot_final": "ثبت في الـ réglages، وإلا اعطيني رقمك نثبتلك في سرفيس الـ Roaming."
        },
        {
            "intent": "service_migration", "net": "VDSL", "sentiment": "Neutral", "action": "process_migration_request",
            "user_init": "نحب نعدي خطي من ADSL لـ VDSL في {addr}، قداش ياخذ وقت؟",
            "bot_ask": "تحب نعدي المطلب توة؟",
            "user_ans": "باهي، عديه المطلب ونحب نعرف قداش نبقى نستنى.",
            "bot_final": "المطلب ياخذ عادة بين 48 و 72 ساعة، اعطيني رقم المطلب نثبتلك وين وصل."
        },
        {
            "intent": "balance_inquiry", "net": "Mobile", "sentiment": "Neutral", "action": "inform_ussd_code",
            "user_init": "كيفاش نجم نعرف قداش مازال عندي صولد في خطي في {city}؟",
            "bot_ask": "تلوج على الصولد الرئيسي ولا الـ bonus؟",
            "user_ans": "نحب نعرف الصولد الكل، متع المكالمات والانترنت.",
            "bot_final": "سهلة برشا، اطلب *122# تو يظهرلك الصولد متاعك والـ bonus الكل."
        }
    ]

    def build_turns(scene, city, addr):
        return [
            {"speaker": "user", "text": "عسلامة"},
            {"speaker": "bot", "text": "مرحبا بيك في تليكوم، كيفاش نجم نعاونك؟"},
            {"speaker": "user", "text": scene["user_init"].format(city=city, addr=addr)},
            {"speaker": "bot", "text": scene["bot_ask"]},
            {"speaker": "user", "text": scene["user_ans"]},
            {"speaker": "bot", "text": scene["bot_final"].format(city=city, addr=addr)}
        ]

    data = []

    # 1. GÉNÉRATION DES 6000 VALIDES
    for i in range(1, 6001):
        city = random.choice(list(cities_map.keys()))
        addr = cities_map[city]
        scene = random.choice(all_scenarios)
        turns = build_turns(scene, city, addr)
        
        # --- AJOUT DU FORMAT COMPATIBLE ---
        input_text = " | ".join([f"{t['speaker'].upper()}: {t['text']}" for t in turns[:-1]])
        output_text = turns[-1]["text"]

        data.append({
            "comment_id": i,
            "user_name": f"{random.choice(first_names)} {random.choice(last_names)}",
            "intent": scene["intent"],
            "entity_location": city,
            "entity_neighborhood": addr,
            "entity_service": scene["net"],
            "input_text": input_text,     # Nouveau champ
            "output_text": output_text,   # Nouveau champ
            "action_required": scene["action"],
            "sentiment": scene["sentiment"],
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 360))).strftime("%d-%m-%Y"),
            "status": "Valid",
            "turns": turns
        })

    # 2. GÉNÉRATION DES 1000 TRASH
    for j in range(6001, 7001):
        city = random.choice(list(cities_map.keys()))
        addr = cities_map[city]
        scene = random.choice(all_scenarios)
        turns = build_turns(scene, city, addr)
        
        # --- AJOUT DU FORMAT COMPATIBLE ---
        input_text = " | ".join([f"{t['speaker'].upper()}: {t['text']}" for t in turns[:-1]])
        output_text = turns[-1]["text"]

        entry = {
            "comment_id": j,
            "user_name": f"{random.choice(first_names)} {random.choice(last_names)}",
            "intent": scene["intent"],
            "entity_location": city,
            "entity_neighborhood": addr,
            "entity_service": scene["net"],
            "input_text": input_text,     # Nouveau champ
            "output_text": output_text,   # Nouveau champ
            "action_required": scene["action"],
            "sentiment": scene["sentiment"],
            "timestamp": "20-10-2025",
            "status": "non valide",
            "turns": turns
        }

        rand_val = random.randint(1, 100)
        if rand_val <= 20: 
            entry["comment_id"] = random.choice([None, "NULL", ""])
        elif rand_val <= 50: 
            entry["timestamp"] = random.choice(["2025.12.31", "01/02/25", "Feb 10, 2025", "2025-05-15"])
        elif rand_val <= 80: 
            entry["entity_location"] = random.choice(["TUNIS", "tunis", "تونس العاصمة", " Sousse ", "sfax_city"])
        else: 
            data.append(entry)
            data.append(copy.deepcopy(entry))
            continue
            
        data.append(entry)

    random.shuffle(data)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"✅ Succès : {len(data)} dialogues générés avec input_text/output_text dans {filename}")

# Exécution
generate_voicebot_logical_dataset()