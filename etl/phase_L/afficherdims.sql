USE telecom_DWH_Final; -- Utilisation du nom exact de ta base finale
GO

-- 1. Voir tous les clients (7201 lignes ou moins si doublons de noms)
SELECT * FROM Dim_Client;

-- 2. Voir la segmentation géographique (Wilaya et Délégations en arabe)
SELECT * FROM Dim_Geographie;

-- 3. Voir les problèmes, services et les ACTIONS standardisées
-- C'est ici que tu verras tes traductions comme "تثبت من تغطية الفيبر"
SELECT * FROM Dim_Probleme;

-- 4. Voir les dates enregistrées (Format DATE SQL)
SELECT * FROM Dim_Temps;

-- 5. Voir les étiquettes de sentiments (إيجابي, سلبي, محايد)
SELECT * FROM Dim_Sentiment;

-- 6. Voir les textes complets des plaintes et réponses
SELECT TOP 10 * FROM Dim_Description; -- TOP 10 pour éviter de surcharger l'affichage avec le MAX
GO