-- 1. Clients
INSERT INTO Dim_Client (Nom_Client) 
SELECT DISTINCT [اسم_الحريف] FROM telecom_db.dbo.final_data_table WHERE [اسم_الحريف] IS NOT NULL;

-- 2. Géo
INSERT INTO Dim_Geographie (Wilaya, Delegation) 
SELECT DISTINCT [الولاية], [البلاصة] FROM telecom_db.dbo.final_data_table;

-- 3. Problèmes
INSERT INTO Dim_Probleme (Probleme, Service_Type, Action_Requise) 
SELECT DISTINCT [المشكل], [الخدمة], [اش_لازم_يتعمل] FROM telecom_db.dbo.final_data_table;

-- 4. Temps
INSERT INTO Dim_Temps (Date_Full) 
SELECT DISTINCT [تاريخ] FROM telecom_db.dbo.final_data_table;

-- 5. Sentiment
INSERT INTO Dim_Sentiment (Label) 
SELECT DISTINCT [الشعور] FROM telecom_db.dbo.final_data_table;

-- 6. Descriptions (Une ligne par réclamation, donc pas de DISTINCT ici)
INSERT INTO Dim_Description (Texte_Plainte, Texte_Reponse) 
SELECT [الشكاية], [الجواب] FROM telecom_db.dbo.final_data_table;