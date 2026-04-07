USE telecom_db;
GO

ALTER TABLE final_data_table
DROP COLUMN 
    [وقت_التعليق], 
    [عدد الاتصالات], 
    [الحالة];
GO

-- Vérification de la nouvelle structure
SELECT TOP 5 * FROM final_data_table;