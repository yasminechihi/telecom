USE telecom_voicebot_v2;
GO

-- 1. On définit la CTE pour identifier les lignes en double
WITH CTE_Nettoyage AS (
    SELECT 
        id_conversation, 
        ROW_NUMBER() OVER (
            PARTITION BY client_name, full_context 
            ORDER BY id_conversation ASC
        ) AS Numero_Ligne
    FROM conversations_table
)
-- 2. On supprime toutes les lignes qui ont un Numero_Ligne supérieur à 1
DELETE FROM conversations_table
WHERE id_conversation IN (
    SELECT id_conversation 
    FROM CTE_Nettoyage 
    WHERE Numero_Ligne > 1
);
GO

-- 3. Vérification finale : relance ton script de comptage
SELECT 
    client_name, 
    full_context, 
    COUNT(*) AS Nombre_Occurrences
FROM conversations_table
GROUP BY client_name, full_context
HAVING COUNT(*) > 1;
GO