USE telecom_voicebot_v2;
GO

-- 1. Traduction de 'intent_name'
UPDATE conversations_table
SET intent_name = CASE 
    WHEN intent_name = 'balance_inquiry'    THEN N'استفسار عن الرصيد'
    WHEN intent_name = 'coverage_inquiry'   THEN N'استفسار عن التغطية'
    WHEN intent_name = 'hardware_failure'   THEN N'عطب في الجهاز'
    WHEN intent_name = 'roaming_issue'      THEN N'مشكلة في التجوال'
    WHEN intent_name = 'installation_delay' THEN N'تأخير في التركيب'
    WHEN intent_name = 'offers_inquiry'     THEN N'استفسار عن العروض'
    WHEN intent_name = 'billing_dispute'    THEN N'اعتراض على الفاتورة'
    WHEN intent_name = 'network_failure'    THEN N'عطل في الشبكة'
    WHEN intent_name = 'service_migration'  THEN N'تغيير الخدمة'
    WHEN intent_name = 'slow_internet'      THEN N'بطء في الانترنات'
    WHEN intent_name = 'sim_replacement'    THEN N'تبديل شريحة'
    WHEN intent_name = 'payment_issue'      THEN N'مشكلة في الدفع'
    WHEN intent_name = 'internet_outage'    THEN N'انقطاع الانترنات'
    WHEN intent_name = 'wifi_signal_issue'  THEN N'مشكلة في إشارة الويفي'
    ELSE intent_name 
END
WHERE intent_name NOT LIKE N'%[أ-ي]%';

-- 2. Traduction de 'location_city' (Gouvernorats)
UPDATE conversations_table
SET location_city = CASE 
    WHEN location_city IN ('Tunis', 'tunis', 'tounes', N'تونس العاصمة') THEN N'تونس'
    WHEN location_city IN ('Ariana', 'ariana') THEN N'أريانة'
    WHEN location_city IN ('Ben Arous', 'ben arous') THEN N'بن عروس'
    WHEN location_city IN ('Manouba', 'manouba') THEN N'منوبة'
    WHEN location_city IN ('Sousse', 'sousse') THEN N'سوسة'
    WHEN location_city IN ('Monastir', 'monastir') THEN N'المنستير'
    WHEN location_city IN ('Mahdia', 'mahdia') THEN N'المهدية'
    WHEN location_city IN ('Bizerte', 'bizerte', 'benzart') THEN N'بنزرت'
    WHEN location_city IN ('Beja', 'beja') THEN N'باجة'
    WHEN location_city IN ('Jendouba', 'jendouba') THEN N'جندوبة'
    WHEN location_city IN ('Sfax', 'sfax', 'sfax_city') THEN N'صفاقس'
    WHEN location_city IN ('Kairouan', 'kairouan') THEN N'القيروان'
    WHEN location_city IN ('Gabes', 'gabes') THEN N'قابس'
    WHEN location_city IN ('Medenine', 'medenine') THEN N'مدنين'
    WHEN location_city IN ('Tozeur', 'tozeur') THEN N'توزر'
    ELSE TRIM(location_city) 
END;

-- 3. Traduction de 'neighborhood' (Quartiers)
UPDATE conversations_table
SET neighborhood = CASE 
    WHEN neighborhood IN ('Gomra', 'gomra') THEN N'ڨمرة'
    WHEN neighborhood IN ('Sahloul', 'sahloul') THEN N'سهلول'
    WHEN neighborhood IN ('Ennasr', 'ennasr') THEN N'النصر'
    WHEN neighborhood IN ('Hammam Sousse', 'حمّام سوسة') THEN N'حمّام سوسة'
    ELSE neighborhood 
END;

-- 4. Traduction de 'action_required' (Adapté si la colonne existe avec ce nom ou proche)
-- Note : Vérifie si ta colonne s'appelle bien action_required dans conversations_table
UPDATE conversations_table
SET execution_status = CASE -- J'utilise execution_status ici car c'est ce qu'on a mis dans le CREATE TABLE
    WHEN execution_status = 'Valid' THEN N'صحيح'
    WHEN execution_status = 'non valide' THEN N'غير صالح'
    ELSE execution_status 
END;

-- 5. Traduction de 'sentiment_analysis'
UPDATE conversations_table
SET sentiment_analysis = CASE 
    WHEN sentiment_analysis = 'Positive' THEN N'إيجابي'
    WHEN sentiment_analysis = 'Negative' THEN N'سلبي'
    WHEN sentiment_analysis = 'Neutral' THEN N'محايد'
    ELSE sentiment_analysis 
END;
UPDATE conversations_table
SET [اش_لازم_يتعمل] = CASE 
    WHEN [اش_لازم_يتعمل] = 'reactivate_line'          THEN N'إعادة تفعيل الخط'
    WHEN [اش_لازم_يتعمل] = 'provide_offer_info'       THEN N'تقديم معلومات عن العروض'
    WHEN [اش_لازم_يتعمل] = 'check_fiber_availability' THEN N'تثبت من تغطية الفيبر'
    WHEN [اش_لازم_يتعمل] = 'replace_modem'            THEN N'تبديل المودم'
    WHEN [اش_لازم_يتعمل] = 'provide_store_location'   THEN N'مد الحريف بموقع فرع'
    WHEN [اش_لازم_يتعمل] = 'process_migration_request' THEN N'تحويل نوع الخدمة'
    WHEN [اش_لازم_يتعمل] = 'retrieve_invoice_details' THEN N'استخراج تفاصيل الفاتورة'
    WHEN [اش_لازم_يتعمل] = 'check_roaming_status'     THEN N'تثبت من حالة التجوال'
    WHEN [اش_لازم_يتعمل] = 'track_order_status'       THEN N'متابعة حالة الطلب'
    WHEN [اش_لازم_يتعمل] = 'inform_ussd_code'         THEN N'تقديم كود USSD'
    WHEN [اش_لازم_يتعمل] = 'technical_advice'         THEN N'تقديم نصيحة تقنية'
    WHEN [اش_لازم_يتعمل] = 'technical_diagnosis'      THEN N'تشخيص تقني'
    WHEN [اش_لازم_يتعمل] = 'check_network_status'     THEN N'تثبت من حالة الشبكة'
    WHEN [اش_لازم_يتعمل] = 'speed_test_check'         THEN N'اختبار سرعة التدفق'
    ELSE [اش_لازم_يتعمل] 
END;
GO