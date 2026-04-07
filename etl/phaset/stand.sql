USE telecom_db;
GO

-- 1. Traduction de 'intent' (Les intentions)
UPDATE final_data_table
SET intent = CASE 
    -- Les manquants de tes images
    WHEN intent = 'balance_inquiry'    THEN N'استفسار عن الرصيد'
    WHEN intent = 'coverage_inquiry'   THEN N'استفسار عن التغطية'
    WHEN intent = 'hardware_failure'   THEN N'عطب في الجهاز'

    -- Les autres valeurs à traduire
    WHEN intent = 'roaming_issue'      THEN N'مشكلة في التجوال'
    WHEN intent = 'installation_delay' THEN N'تأخير في التركيب'
    WHEN intent = 'offers_inquiry'     THEN N'استفسار عن العروض'
    WHEN intent = 'billing_dispute'    THEN N'اعتراض على الفاتورة'
    WHEN intent = 'network_failure'    THEN N'عطل في الشبكة'
    WHEN intent = 'service_migration'  THEN N'تغيير الخدمة'
    WHEN intent = 'slow_internet'      THEN N'بطء في الانترنات'
    WHEN intent = 'sim_replacement'    THEN N'تبديل شريحة'
    WHEN intent = 'payment_issue'      THEN N'مشكلة في الدفع'
    WHEN intent = 'internet_outage'    THEN N'انقطاع الانترنات'
    WHEN intent = 'wifi_signal_issue'  THEN N'مشكلة في إشارة الويفي'

    ELSE intent -- Si c'est déjà en arabe, on ne touche à rien
END
WHERE intent NOT LIKE N'%[أ-ي]%';

-- 2. Traduction de 'entity_location' (Gouvernorats)
UPDATE final_data_table
SET entity_location = 
    CASE 
        -- 1. Harmonisation de Tunis (Grand Tunis)
        WHEN entity_location IN ('Tunis', 'tunis', 'tounes', N'تونس العاصمة') THEN N'تونس'
        WHEN entity_location IN ('Ariana', 'ariana', 'l''ariana') THEN N'أريانة'
        WHEN entity_location IN ('Ben Arous', 'ben arous', 'ben arouz') THEN N'بن عروس'
        WHEN entity_location IN ('Manouba', 'manouba', 'la manouba') THEN N'منوبة'

        -- 2. Harmonisation du Sahel (Sousse)
        WHEN entity_location IN ('Sousse', 'sousse', 'sosa') THEN N'سوسة'
        WHEN entity_location IN ('Monastir', 'monastir') THEN N'المنستير'
        WHEN entity_location IN ('Mahdia', 'mahdia') THEN N'المهدية'

        -- 3. Nord
        WHEN entity_location IN ('Bizerte', 'bizerte', 'benzart') THEN N'بنزرت'
        WHEN entity_location IN ('Beja', 'beja') THEN N'باجة'
        WHEN entity_location IN ('Jendouba', 'jendouba') THEN N'جندوبة'

        -- 4. Centre et Sud
        WHEN entity_location IN ('Sfax', 'sfax') THEN N'صفاقس'
        WHEN entity_location IN ('Kairouan', 'kairouan') THEN N'القيروان'
        WHEN entity_location IN ('Gabes', 'gabes') THEN N'قابس'
        WHEN entity_location IN ('Medenine', 'medenine', 'mednin') THEN N'مدنين'
        WHEN entity_location IN ('Tozeur', 'tozeur') THEN N'توزر'

        ELSE TRIM(entity_location) 
    END;
-- 3. Traduction de 'entity_neighborhood' (Les quartiers)
UPDATE final_data_table
SET entity_neighborhood = 
    CASE 
        WHEN entity_neighborhood IN ('Gomra', 'gomra') THEN N'ڨمرة'
        WHEN entity_neighborhood IN ('Sahloul', 'sahloul') THEN N'سهلول'
        WHEN entity_neighborhood IN ('Ennasr', 'ennasr') THEN N'النصر'
        WHEN entity_neighborhood IN ('Jorgis', 'jorgis') THEN N'جرجيس'
        WHEN entity_neighborhood IN ('Bouhajla', 'bouhajla') THEN N'بوحجلة'
        WHEN entity_neighborhood IN ('Hammam Sousse', 'حمّام سوسة') THEN N'حمّام سوسة'
        ELSE entity_neighborhood 
    END;

-- 4. Traduction de 'action_required' (Actions système)
UPDATE final_data_table
SET action_required = 
    CASE 
        -- Traductions basées sur ta capture d'écran
        WHEN action_required = 'reactivate_line'           THEN N'إعادة تفعيل الخط'
        WHEN action_required = 'provide_offer_info'        THEN N'تقديم معلومات العرض'
        WHEN action_required = 'replace_modem'             THEN N'تبديل المودم'
        WHEN action_required = 'provide_store_location'    THEN N'تقديم موقع المحل'
        WHEN action_required = 'process_migration_request' THEN N'معالجة طلب تغيير العرض'
        WHEN action_required = 'retrieve_invoice_details'  THEN N'استخراج تفاصيل الفاتورة'
        WHEN action_required = 'check_roaming_status'      THEN N'تثبت من حالة التجوال'
        WHEN action_required = 'track_order_status'        THEN N'تتبع حالة الطلب'
        WHEN action_required = 'technical_advice'          THEN N'تقديم نصيحة تقنية'
        WHEN action_required = 'technical_diagnosis'       THEN N'تشخيص تقني'
        WHEN action_required = 'check_network_status'      THEN N'تثبت من حالة الشبكة'
        WHEN action_required = 'speed_test_check'          THEN N'تثبت من سرعة الانترنات'
        
        -- Anciennes valeurs déjà listées
        WHEN action_required = 'inform_ussd_code'          THEN N'تقديم كود USSD'
        WHEN action_required = 'technical_support_escalation' THEN N'تحويل للدعم التقني'
        WHEN action_required = 'check_fiber_availability'  THEN N'تثبت من تغطية الفايبر'
        WHEN action_required = 'schedule_technician_visit' THEN N'برمجة زيارة تقني'
        WHEN action_required = 'provide_pricing_details'   THEN N'تقديم تفاصيل الأسعار'

        ELSE action_required 
    END;
    -- 5. Traduction de 'sentiment' (Analyse de sentiment)
UPDATE final_data_table
SET sentiment = 
    CASE 
        WHEN sentiment = 'Positive' THEN N'إيجابي'
        WHEN sentiment = 'Negative' THEN N'سلبي'
        WHEN sentiment = 'Neutral' THEN N'محايد'
        ELSE sentiment 
    END;

-- 6. Traduction de 'status' (État de la donnée)
UPDATE final_data_table
SET [status] = 
    CASE 
        WHEN [status] = 'Valid' THEN N'صحيح'
        WHEN [status] = 'Trash' THEN N'غير صالح'
        ELSE [status] 
    END;
GO