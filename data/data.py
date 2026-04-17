import json
import random
from datetime import datetime, timedelta

def generate_tunisian_raw_dataset(filename="telecom_raw_data_7000.json", num_total=7000):
    first_names = ["أمين", "فاطمة", "ياسين", "مريم", "أحمد", "ليلى", "سامي", "هند", "مراد", "إيناس", "هيثم", "خديجة", "نزار", "سلوى", "رؤوف", "نجلاء", "وليد", "ريم", "زياد", "سلمى"]
    last_names = ["الدريدي", "بن عرفة", "الورتاني", "المزيغي", "العياري", "الطرابلسي", "الجلاصي", "المنصوري", "الهمامي", "القروي", "بالقاسم", "الماجري"]
    
    cities_map = {
        "بنزرت": "منزل بورقيبة", "تونس": "حي الخضراء", "سوسة": "حمّام سوسة",
        "صفاقس": "طريق تنيور", "نابل": "الحمامات", "القيروان": "بوحجلة",
        "مدنين": "جرجيس", "باجة": "تستور", "جندوبة": "طبرقة", "توزر": "دقاش"
    }

    all_scenarios = [
        {"input": "لريزو طايح برشا في {addr}، {city}. مجمتش نخدم télétravail.", "output": "سامحنا خويا الغالي، فما ضغط كبير حالياً في {city} وقاعدين نصلحو في العطب، تو يرجع مريغل.", "intent": "network_failure", "action": "check_network_status", "net": "4G/Réseau", "sentiment": "Negative"},
        {"input": "الأنترنيت مقصوصة في {addr} عندها 3 أيام. كلمت الـ 1298 و حد ما جاوبني.", "output": "يا خويا سامحنا عالقلق، ثبتلي بربي في الموديم يشعل بالأحمر؟ أعطيني رقم الخط نثبتلك.", "intent": "internet_outage", "action": "technical_diagnosis", "net": "ADSL/Fixe", "sentiment": "Negative"},
        {"input": "الديبي في {city} يضحك، نخلص في برشا فلوس و الواصل شي يحشم.", "output": "واضح، بربي أعمل test de débit وابعثلنا capture d'écran، وجرب طفي الموديم و عاود شعلو.", "intent": "slow_internet", "action": "speed_test_check", "net": "VDSL", "sentiment": "Negative"},
        {"input": "الفاتورة جاتني غالية برشا الشهر هذا في {addr}، مش معقول قداش تسرقو.", "output": "مرحبا بيك، تنجم تثبت في ديتاي استهلاكك في MyTT، وإلا اعطيني رقمك نثبتلك كان فما غلطة.", "intent": "billing_dispute", "action": "retrieve_invoice_details", "net": "Billing", "sentiment": "Negative"},
        {"input": "خلصت الفاتورة عبر تطبيق MyTT و لتو الخط مقصوص في {city}.", "output": "سامحنا، ساعات السيستيم ياخذ شوية وقت. اعطيني رقم المعاملة تو نرجعلك الخط يخدم فوراً.", "intent": "payment_issue", "action": "reactivate_line", "net": "Administrative", "sentiment": "Negative"},
        {"input": "يا تليكوم لتو لا جيتو ركبتو الفيكس في {addr}. عندي شهر نستنى.", "output": "مرحبا بيك، نعتذرو عالـ retard. اعطيني رقم المطلب متاعك باش نثبتلك مع سرفيس تيكنيك.", "intent": "installation_delay", "action": "track_order_status", "net": "ADSL/Fixe", "sentiment": "Negative"},
        {"input": "وقتاش ناوين تسيبو الفايبر في {addr}؟ عيينا من الـ ADSL الضعيف.", "output": "الفايبر قاعدين نركبو فيه بالتدريج في {city}، خليلي رقمك تو نكلموك أول ما يوصل لحومتكم.", "intent": "coverage_inquiry", "action": "check_fiber_availability", "net": "Fibre Optique", "sentiment": "Neutral"},
        {"input": "نحب نعرف شنوما أحسن عروض الـ 4G عندكم توة في {city}؟", "output": "أهلا بيك، عندنا عروض خيالية توة، تنجم تطلب *140# وتختار الفورفي اللي يساعدك.", "intent": "offers_inquiry", "action": "provide_offer_info", "net": "4G/Réseau", "sentiment": "Neutral"},
        {"input": "موديم يطفى و يشعل وحدو في {addr}. بدلتو مرتين و ديما نفس المشكل.", "output": "واضح اللي فما مشكل في الـ alimentation. تنجم تبدلو بلاش فلوس من أقرب أجونس ليك.", "intent": "hardware_failure", "action": "replace_modem", "net": "ADSL/Fixe", "sentiment": "Negative"},
        {"input": "الويفي (Wifi) ميوصلش للبيت لداخل في {addr}، شنوة الحل؟", "output": "ينجم يكون المشكل من بلاصة الموديم، جرب حطو في بلاصة عالية وإلا ننصحك بـ répéteur Wifi.", "intent": "wifi_signal_issue", "action": "technical_advice", "net": "ADSL/Fixe", "sentiment": "Negative"},
        {"input": "السيم ضاعتلي في {city}، نحب نطلع وحدة أخرى بنفس الرقم.", "output": "مرحبا بيك، لازمك تمشي لأقرب بوتيك تليكوم ببطاقة التعريف باش تطلع سيم جديدة بنفس رقمك.", "intent": "sim_replacement", "action": "provide_store_location", "net": "Mobile", "sentiment": "Neutral"},
        {"input": "أنا لبرا وتوا الـ Roaming ميعملش كونيكسيون في {city}.", "output": "ثبت اللي الـ Données en itinérance مفعّلة في تليفونك، وإلا اعطيني رقمك نثبتلك في الفورفي.", "intent": "roaming_issue", "action": "check_roaming_status", "net": "Mobile", "sentiment": "Negative"},
        {"input": "نحب نعدي خطي من ADSL لـ VDSL في {addr}، قداش ياخذ وقت؟", "output": "المطلب ياخذ عادة بين 48 و 72 ساعة، اعطيني رقم المطلب نثبتلك وين وصل الدوسي.", "intent": "service_migration", "action": "process_migration_request", "net": "VDSL", "sentiment": "Neutral"},
        {"input": "كيفاش نجم نعرف قداش مازال عندي صولد في خطي في {city}؟", "output": "سهلة برشا، اطلب *122# تو يظهرلك الصولد متاعك والـ bonus الكل.", "intent": "balance_inquiry", "action": "inform_ussd_code", "net": "Mobile", "sentiment": "Neutral"}
    ]

    data = []

    # 1. GÉNÉRATION DES 6000 DONNÉES VALIDES
    for i in range(1, 6001):
        city = random.choice(list(cities_map.keys()))
        addr = cities_map[city]
        scene = random.choice(all_scenarios)
        data.append({
            "comment_id": i,
            "user_name": f"{random.choice(first_names)} {random.choice(last_names)}",
            "intent": scene["intent"],
            "entity_location": city,
            "entity_neighborhood": addr,
            "entity_service": scene["net"],
            "input_text": scene["input"].format(city=city, addr=addr),
            "output_text": scene["output"].format(city=city, addr=addr),
            "action_required": scene["action"],
            "sentiment": scene["sentiment"],
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=random.randint(0, 360))).strftime("%d-%m-%Y"),
            "status": "Valid"
        })

    # 2. GÉNÉRATION DES 1000 DONNÉES AVEC ANOMALIES RÉPARTIES
    for j in range(6001, 7001):
        city = random.choice(list(cities_map.keys()))
        addr = cities_map[city]
        scene = random.choice(all_scenarios)
        
        entry = {
            "comment_id": j,
            "user_name": f"{random.choice(first_names)} {random.choice(last_names)}",
            "intent": scene["intent"],
            "entity_location": city,
            "entity_neighborhood": addr,
            "entity_service": scene["net"],
            "input_text": scene["input"].format(city=city, addr=addr),
            "output_text": scene["output"].format(city=city, addr=addr),
            "action_required": scene["action"],
            "sentiment": scene["sentiment"],
            "timestamp": "20-10-2025",
            "status": "Trash" 
        }

        error_type = j % 5 

        if error_type == 0: 
            entry["comment_id"] = random.choice([None, "NULL", ""])
            
        elif error_type == 1: 
            entry["timestamp"] = random.choice(["2025.12.31", "01/02/25", "Feb 10, 2025", "2025-05-15"])
            
        elif error_type == 2: 
            entry["entity_location"] = random.choice(["TUNIS", "tunis", "تونس العاصمة", " Sousse "])
            
        elif error_type == 3: 
            entry["entity_service"] = random.choice(["adsl_fixe", "4g", "INTERNET", "fibreee"])
            
        elif error_type == 4: 
            entry["extra_field_garbage"] = "{" + f"id_tech: {random.randint(100,999)}" + "}"

        data.append(entry)

    random.shuffle(data)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Succès : {len(data)} lignes générées dans {filename}")

generate_tunisian_raw_dataset()