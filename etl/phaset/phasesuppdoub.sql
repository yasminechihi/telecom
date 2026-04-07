USE telecom_db;
GO

WITH CTE_Nettoyage AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY user_name, input_text -- Les colonnes définissant le doublon
            ORDER BY comment_id ASC -- On garde la première occurrence (ID le plus petit)
        ) AS Numero_Ligne
    FROM final_data_table
)
-- CETTE LIGNE SUPPRIME LES COPIES
DELETE FROM CTE_Nettoyage WHERE Numero_Ligne > 1;
GO

-- Vérification : Le compte doit avoir diminué
SELECT COUNT(*) as Total_Apres_Suppression FROM final_data_table;
