-- 1. Clients
INSERT INTO Dim_Client (Nom_Client) 
SELECT DISTINCT [اسم_الحريف] FROM telecom_voicebot_v2.dbo.conversations_table WHERE [اسم_الحريف] IS NOT NULL;

-- 2. Géo
INSERT INTO Dim_Geographie (Wilaya, Delegation) 
SELECT DISTINCT [الولاية], [البلاصة] FROM telecom_voicebot_v2.dbo.conversations_table;

-- 3. Problèmes
INSERT INTO Dim_Probleme (Probleme, Service_Type, Action_Requise) 
SELECT DISTINCT [المشكل], [الخدمة], [اش_لازم_يتعمل] FROM telecom_voicebot_v2.dbo.conversations_table;

-- 4. Descriptions (CRUCIAL : AJOUT DU DISTINCT)
INSERT INTO Dim_Description (Texte_Plainte, Texte_Reponse) 
SELECT DISTINCT [الشكاية], [الجواب] FROM telecom_voicebot_v2.dbo.conversations_table;

-- 5. Sentiment et Temps (Garder le DISTINCT comme tu l'as fait)
INSERT INTO Dim_Sentiment (Label) SELECT DISTINCT [الشعور] FROM telecom_voicebot_v2.dbo.conversations_table;
INSERT INTO Dim_Temps (Date_Full) SELECT DISTINCT TRY_CAST([تاريخ] AS DATE) FROM telecom_voicebot_v2.dbo.conversations_table;
GO