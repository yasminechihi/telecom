USE telecom_DWH_Final;
GO

-- On sélectionne tout depuis la vue et on transforme en format JSON
SELECT 
    id_source,
    client_name,
    location_wilaya,
    location_delegation,
    issue_type,
    service_type,
    suggested_action,
    sentiment_label,
    instruction,
    [response] -- On met entre crochets car 'response' peut être un mot réservé
FROM dbo.View_Export_Chatbot
FOR JSON PATH, ROOT('dataset_chatbot');
GO