USE telecom_db;
GO

-- 1. Réparer les IDs manquants en utilisant une numérotation automatique 
-- On commence à partir du dernier ID connu (ex: 7000) pour éviter les doublons
WITH CTE AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) + 7000 AS NewID
    FROM final_data_table
    WHERE id IS NULL
)
UPDATE CTE SET id = NewID;

-- 2. Remplir les autres vides potentiels par sécurité
UPDATE final_data_table
SET [الولاية] = ISNULL([الولاية], N'غير محدد'),
    [البلاصة] = ISNULL([البلاصة], N'غير محدد'),
    [الشعور] = ISNULL([الشعور], N'محايد');
GO