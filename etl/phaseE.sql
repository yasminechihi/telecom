-- 1. Créer la base de données
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'telecom_db')
BEGIN
    CREATE DATABASE telecom_db;
END
GO

USE telecom_db;
GO

-- 2. Créer la table avec la colonne garbage incluse
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'final_data_table')
BEGIN
    CREATE TABLE final_data_table (
        comment_id INT NULL, -- Autoriser NULL pour les lignes Trash
        user_name NVARCHAR(255),
        intent NVARCHAR(100),
        entity_location NVARCHAR(100),
        entity_neighborhood NVARCHAR(100),
        entity_service NVARCHAR(100),
        input_text NVARCHAR(MAX),
        output_text NVARCHAR(MAX),
        action_required NVARCHAR(100),
        sentiment NVARCHAR(50),
        comment_timestamp NVARCHAR(100),
        [status] NVARCHAR(50),
        extra_field_garbage NVARCHAR(MAX) -- AJOUTÉ ICI
    );
END
GO
-- On vide la table pour éviter les doublons si le script précédent a partiellement fonctionné
TRUNCATE TABLE final_data_table; 
GO

DECLARE @jsonContent NVARCHAR(MAX);

-- Chargement
SELECT @jsonContent = BulkColumn
FROM OPENROWSET (BULK 'C:\Users\USER\Desktop\pfe\data\final_data_utf16.json', SINGLE_NCLOB) as j;

-- Nettoyage du BOM
SET @jsonContent = SUBSTRING(@jsonContent, CHARINDEX('[', @jsonContent), LEN(@jsonContent));

-- Insertion
INSERT INTO final_data_table (
    comment_id, user_name, intent, entity_location, entity_neighborhood, 
    entity_service, input_text, output_text, action_required, 
    sentiment, comment_timestamp, [status], extra_field_garbage
)
SELECT 
    TRY_CAST(NULLIF(comment_id_raw, 'NULL') AS INT), 
    user_name, intent, entity_location, entity_neighborhood, 
    entity_service, input_text, output_text, action_required, 
    sentiment, timestamp_raw, status_raw, extra_field_garbage
FROM OPENJSON(@jsonContent)
WITH (
    comment_id_raw      NVARCHAR(100)  '$.comment_id',
    user_name           NVARCHAR(255)  '$.user_name',
    intent              NVARCHAR(100)  '$.intent',
    entity_location     NVARCHAR(100)  '$.entity_location',
    entity_neighborhood NVARCHAR(100)  '$.entity_neighborhood',
    entity_service      NVARCHAR(100)  '$.entity_service',
    input_text          NVARCHAR(MAX)  '$.input_text',
    output_text         NVARCHAR(MAX)  '$.output_text',
    action_required     NVARCHAR(100)  '$.action_required',
    sentiment           NVARCHAR(50)   '$.sentiment',
    timestamp_raw       NVARCHAR(100)  '$.timestamp',
    status_raw          NVARCHAR(50)   '$.status',
    extra_field_garbage NVARCHAR(MAX)  '$.extra_field_garbage'
);
GO

-- VÉRIFICATION LÉGÈRE (Ne fait pas planter la connexion)
SELECT * 
FROM final_data_table