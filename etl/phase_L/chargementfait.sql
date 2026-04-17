USE telecom_DWH;
GO

-- 1. On vide la table au cas où il resterait des débris du test précédent
TRUNCATE TABLE Fact_Reclamations;
GO

-- 2. Insertion sécurisée avec gestion des doublons d'ID source
INSERT INTO Fact_Reclamations (id_fact, id_client, id_geo, id_prob, id_date, id_desc, id_sent)
SELECT 
    src.id, 
    MAX(c.id_client), 
    MAX(g.id_geo), 
    MAX(p.id_prob), 
    MAX(t.id_date), 
    MAX(d.id_desc), 
    MAX(s.id_sent)
FROM telecom_db.dbo.final_data_table src
LEFT JOIN Dim_Client c ON src.[اسم_الحريف] = c.Nom_Client
LEFT JOIN Dim_Geographie g ON src.[الولاية] = g.Wilaya AND src.[البلاصة] = g.Delegation
LEFT JOIN Dim_Probleme p ON src.[المشكل] = p.Probleme AND src.[الخدمة] = p.Service_Type
LEFT JOIN Dim_Temps t ON src.[تاريخ] = t.Date_Full
LEFT JOIN Dim_Sentiment s ON src.[الشعور] = s.Label
LEFT JOIN Dim_Description d ON src.[الشكاية] = d.Texte_Plainte AND src.[الجواب] = d.Texte_Reponse
GROUP BY src.id; 
GO