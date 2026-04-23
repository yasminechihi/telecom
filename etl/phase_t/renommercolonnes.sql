USE telecom_voicebot_v2;
GO

-- 1. On utilise le format 'Schema.Table.Colonne' pour éviter l'ambiguïté
EXEC sp_rename 'dbo.conversations_table.comment_id', N'id', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.client_name', N'اسم_الحريف', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.intent_name', N'المشكل', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.location_city', N'الولاية', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.neighborhood', N'البلاصة', 'COLUMN';

-- Correction ici : On pointe bien sur conversations_table
EXEC sp_rename 'dbo.conversations_table.action_required', N'اش_لازم_يتعمل', 'COLUMN';

EXEC sp_rename 'dbo.conversations_table.service_type', N'الخدمة', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.full_context', N'الشكاية', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.final_response', N'الجواب', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.sentiment_analysis', N'الشعور', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.created_at', N'وقت_التعليق', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.execution_status', N'الحالة', 'COLUMN';
EXEC sp_rename 'dbo.conversations_table.raw_turns_json', N'التفاصيل_JSON', 'COLUMN';

-- Note: Assure-toi que la colonne 'date_clean' existe bien avant de lancer celle-ci
-- Si tu ne l'as pas créée, tu peux renommer 'وقت_التعليق' en 'تاريخ' plus tard.
GO