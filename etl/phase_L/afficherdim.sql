USE telecom_DWH;
GO

-- Voir tous les clients
SELECT * FROM Dim_Client;

-- Voir la segmentation géographique (Wilaya et Délégations)
SELECT * FROM Dim_Geographie;

-- Voir les types de problèmes et les actions correctives
SELECT * FROM Dim_Probleme;

-- Voir les dates enregistrées
SELECT * FROM Dim_Temps;

-- Voir les étiquettes de sentiments (échantillon des labels)
SELECT * FROM Dim_Sentiment;

-- Voir les textes des plaintes et réponses (le cœur de ton futur chatbot)
SELECT * FROM Dim_Description;