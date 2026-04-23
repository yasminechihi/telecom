USE telecom_voicebot_v2;
GO

-- A. Ajout de la colonne propre
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('conversations_table') AND name = 'date_clean')
BEGIN
    ALTER TABLE conversations_table ADD date_clean DATE;
END
GO

-- B. Transformation
UPDATE conversations_table
SET date_clean = 
    CASE 
        -- 1. Format DD-MM-YYYY (Tirets) -> ex: 20-10-2025
        WHEN created_at LIKE '__-__-____' 
             THEN TRY_CONVERT(DATE, created_at, 105)

        -- 2. Format YYYY.MM.DD (Points) -> ex: 2025.12.31
        WHEN created_at LIKE '____.__.__' 
             THEN TRY_CONVERT(DATE, REPLACE(created_at, '.', '-'), 126)

        -- 3. Format DD/MM/YY (Slashs) -> ex: 01/02/25
        WHEN created_at LIKE '__/__/__' 
             THEN TRY_CONVERT(DATE, created_at, 3)

        -- 4. Format Texte Anglais -> ex: Feb 10, 2025
        WHEN created_at LIKE '%[a-zA-Z]%' 
             THEN TRY_PARSE(created_at AS DATE USING 'en-US')

        -- 5. Format ISO -> ex: 2025-01-01
        WHEN created_at LIKE '____-__-__' 
             THEN TRY_CAST(created_at AS DATE)

        ELSE NULL 
    END;
GO

-- C. Vérification : Voir si des dates n'ont pas pu être converties (NULL)
SELECT created_at, date_clean 
FROM conversations_table 
WHERE date_clean IS NULL AND created_at IS NOT NULL;
GO