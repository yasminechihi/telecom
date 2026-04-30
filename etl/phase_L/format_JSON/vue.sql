-- 1. On force l'utilisation de la base de données DWH
USE telecom_DWH_Final; 
GO

-- 2. On vérifie et on supprime l'ancienne vue pour repartir à neuf
IF OBJECT_ID('dbo.View_Export_Chatbot', 'V') IS NOT NULL
    DROP VIEW dbo.View_Export_Chatbot;
GO

-- 3. Création de la vue avec DISTINCT pour nettoyer les 250k lignes
CREATE VIEW dbo.View_Export_Chatbot AS
SELECT DISTINCT 
    F.id_source_original AS [id_source], 
    C.Nom_Client AS [client_name],
    G.Wilaya AS [location_wilaya],
    G.Delegation AS [location_delegation],
    P.Probleme AS [issue_type],
    P.Service_Type AS [service_type],
    P.Action_Requise AS [suggested_action],
    S.Label AS [sentiment_label],
    D.Texte_Plainte AS [instruction],
    D.Texte_Reponse AS [response]
FROM dbo.Fact_Reclamations F
INNER JOIN dbo.Dim_Client C      ON F.id_client = C.id_client
INNER JOIN dbo.Dim_Geographie G  ON F.id_geo = G.id_geo
INNER JOIN dbo.Dim_Probleme P    ON F.id_prob = P.id_prob
INNER JOIN dbo.Dim_Sentiment S   ON F.id_sent = S.id_sent
INNER JOIN dbo.Dim_Description D ON F.id_desc = D.id_desc;
GO