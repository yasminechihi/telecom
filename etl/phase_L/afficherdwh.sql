USE telecom_DWH_Final;
GO

SELECT 
    F.id_fact AS [ID Source],
    C.Nom_Client AS [Client],
    G.Wilaya AS [Gouvernorat],
    P.Probleme AS [Type Problème],
    S.Label AS [Sentiment],
    D.Texte_Plainte AS [Message Client],
    D.Texte_Reponse AS [Réponse Bot]
FROM Fact_Reclamations F
INNER JOIN Dim_Client C ON F.id_client = C.id_client
INNER JOIN Dim_Geographie G ON F.id_geo = G.id_geo
INNER JOIN Dim_Probleme P ON F.id_prob = P.id_prob
INNER JOIN Dim_Sentiment S ON f.id_sent = S.id_sent
INNER JOIN Dim_Description D ON F.id_desc = D.id_desc;
GO