USE telecom_DWH;
GO

-- On supprime l'ancienne vue si elle existe
IF OBJECT_ID('View_Export_Chatbot', 'V') IS NOT NULL
    DROP VIEW View_Export_Chatbot;
GO

CREATE VIEW View_Export_Chatbot AS
SELECT 
    F.id_fact AS [id_source],
    C.Nom_Client AS [client_name],
    G.Wilaya AS [location_wilaya],
    G.Delegation AS [location_delegation],
    P.Probleme AS [issue_type],
    P.Service_Type AS [service_type],
    P.Action_Requise AS [suggested_action],
    T.Date_Full AS [date_reclamation],
    S.Label AS [sentiment_label],
    D.Texte_Plainte AS [instruction], -- Champ principal pour le chatbot
    D.Texte_Reponse AS [response]      -- Réponse attendue
FROM Fact_Reclamations F
JOIN Dim_Client C ON F.id_client = C.id_client
JOIN Dim_Geographie G ON F.id_geo = G.id_geo
JOIN Dim_Probleme P ON F.id_prob = P.id_prob
JOIN Dim_Temps T ON F.id_date = T.id_date
JOIN Dim_Sentiment S ON F.id_sent = S.id_sent
JOIN Dim_Description D ON F.id_desc = D.id_desc;
GO