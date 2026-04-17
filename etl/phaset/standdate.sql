USE telecom_db;
GO

-- A. Ajout de la colonne propre (si pas déjà fait)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('final_data_table') AND name = 'comment_date_clean')
BEGIN
    ALTER TABLE final_data_table ADD comment_date_clean DATE;
END
GO

-- B. Transformation intelligente avec CASE
UPDATE final_data_table
SET comment_date_clean = 
    CASE 
        -- 1. Format DD-MM-YYYY (Tirets) -> ex: 20-10-2025
        WHEN comment_timestamp LIKE '__-__-____' 
             THEN TRY_CONVERT(DATE, comment_timestamp, 105)

        -- 2. Format YYYY.MM.DD (Points) -> ex: 2024.12.31
        WHEN comment_timestamp LIKE '____.__.__' 
             THEN TRY_CONVERT(DATE, REPLACE(comment_timestamp, '.', '-'), 126)

        -- 3. Format DD/MM/YY (Slashs) -> ex: 01/02/25
        WHEN comment_timestamp LIKE '__/__/__' 
             THEN TRY_CONVERT(DATE, comment_timestamp, 3)

        -- 4. Format Texte Anglais -> ex: Feb 10, 2025
        WHEN comment_timestamp LIKE '%[a-zA-Z]%' 
             THEN TRY_PARSE(comment_timestamp AS DATE USING 'en-US')

        -- 5. Format ISO déjà propre -> ex: 2025-01-01
        WHEN comment_timestamp LIKE '____-__-__' 
             THEN TRY_CAST(comment_timestamp AS DATE)

        ELSE NULL 
    END;
GO