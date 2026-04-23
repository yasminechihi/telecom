USE telecom_voicebot_v2;
GO

CREATE TABLE conversations_table (
    id_conversation INT IDENTITY(1,1) PRIMARY KEY,
    comment_id INT NULL,
    client_name NVARCHAR(255),
    intent_name NVARCHAR(100),
    service_type NVARCHAR(100),
    location_city NVARCHAR(100),
    neighborhood NVARCHAR(100),
    action_required NVARCHAR(255), 
    full_context NVARCHAR(MAX),    
    final_response NVARCHAR(MAX), 
    sentiment_analysis NVARCHAR(50),
    execution_status NVARCHAR(50),
    raw_turns_json NVARCHAR(MAX), 
    created_at NVARCHAR(100)
);
GO

DECLARE @jsonContent NVARCHAR(MAX);
SELECT @jsonContent = BulkColumn
FROM OPENROWSET (BULK 'C:\Users\USER\Desktop\dialogue\donneees\final_data_utf16.json', SINGLE_NCLOB) as j;

SET @jsonContent = SUBSTRING(@jsonContent, CHARINDEX('[', @jsonContent), LEN(@jsonContent));

INSERT INTO conversations_table (
    comment_id, client_name, intent_name, location_city, neighborhood, 
    service_type, action_required, full_context, final_response, 
    sentiment_analysis, created_at, execution_status, raw_turns_json
)
SELECT 
    TRY_CAST(NULLIF(comment_id_raw, 'NULL') AS INT), 
    user_name, intent, entity_location, entity_neighborhood, 
    entity_service, action_req, input_text, output_text, sentiment, 
    timestamp_raw, status_raw, turns_raw
FROM OPENJSON(@jsonContent)
WITH (
    comment_id_raw      NVARCHAR(100)  '$.comment_id',
    user_name           NVARCHAR(255)  '$.user_name',
    intent              NVARCHAR(100)  '$.intent',
    entity_location     NVARCHAR(100)  '$.entity_location',
    entity_neighborhood NVARCHAR(100)  '$.entity_neighborhood',
    entity_service      NVARCHAR(100)  '$.entity_service',
    action_req          NVARCHAR(255)  '$.action_required',
    input_text          NVARCHAR(MAX)  '$.input_text',
    output_text         NVARCHAR(MAX)  '$.output_text',
    sentiment           NVARCHAR(50)   '$.sentiment',
    timestamp_raw       NVARCHAR(100)  '$.timestamp',
    status_raw          NVARCHAR(50)   '$.status',
    turns_raw           NVARCHAR(MAX)  '$.turns' AS JSON
);
GO