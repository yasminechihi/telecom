USE telecom_DWH;
GO

-- Exportation de la vue complète en format JSON
SELECT * FROM View_Export_Chatbot
FOR JSON PATH, ROOT('dataset'), INCLUDE_NULL_VALUES;