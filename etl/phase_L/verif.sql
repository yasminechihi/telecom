SELECT 'Source' as TableName, COUNT(*) as Total FROM telecom_db.dbo.final_data_table
UNION ALL
SELECT 'DWH_Fact' as TableName, COUNT(*) as Total FROM Fact_Reclamations;