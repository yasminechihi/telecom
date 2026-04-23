USE telecom_DWH_Final;
GO

TRUNCATE TABLE Fact_Reclamations;
GO

INSERT INTO Fact_Reclamations (id_source_original, id_client, id_geo, id_prob, id_date, id_desc, id_sent)
SELECT 
    src.id_conversation,
    (SELECT MIN(id_client) FROM Dim_Client WHERE Nom_Client = src.[اسم_الحريف]) as id_client,
    (SELECT MIN(id_geo) FROM Dim_Geographie WHERE Wilaya = src.[الولاية] AND Delegation = src.[البلاصة]) as id_geo,
    (SELECT MIN(id_prob) FROM Dim_Probleme WHERE Probleme = src.[المشكل] AND Service_Type = src.[الخدمة] AND Action_Requise = src.[اش_لازم_يتعمل]) as id_prob,
    (SELECT MIN(id_date) FROM Dim_Temps WHERE Date_Full = TRY_CAST(src.[تاريخ] AS DATE)) as id_date,
    (SELECT MIN(id_desc) FROM Dim_Description WHERE Texte_Plainte = src.[الشكاية] AND Texte_Reponse = src.[الجواب]) as id_desc,
    (SELECT MIN(id_sent) FROM Dim_Sentiment WHERE Label = src.[الشعور]) as id_sent
FROM telecom_voicebot_v2.dbo.conversations_table src;
GO

