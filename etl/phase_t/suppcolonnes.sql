USE telecom_voicebot_v2;
GO

ALTER TABLE [conversations_table]
DROP COLUMN 
    [وقت_التعليق], 
    [الحالة], 
    [التفاصيل_JSON], 
    [id]; -- Suppression de l'ancien ID ici, sans couper l'instruction
GO

-- Vérification de la structure finale
SELECT TOP 5 * FROM [conversations_table];
GO
