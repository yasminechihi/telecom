SELECT 
    F.id_fact AS [ID Source],
    C.Nom_Client AS [Client],
    G.Wilaya AS [Gouvernorat],
    P.Probleme AS [Type Problème],
    S.Label AS [Sentiment],
    D.Texte_Plainte AS [Message Client],
    D.Texte_Reponse AS [Réponse Bot]
FROM Fact_Reclamations F
JOIN Dim_Client C ON F.id_client = C.id_client
JOIN Dim_Geographie G ON F.id_geo = g.id_geo
JOIN Dim_Probleme P ON F.id_prob = P.id_prob
JOIN Dim_Sentiment S ON F.id_sent = S.id_sent
JOIN Dim_Description D ON F.id_desc = D.id_desc;