USE telecom_db;
GO

-- Renommer 'comment_id' -> 'id'
EXEC sp_rename 'final_data_table.comment_id', N'id', 'COLUMN';

-- Renommer 'user_name' -> 'اسم_الحريف'
EXEC sp_rename 'final_data_table.user_name', N'اسم_الحريف', 'COLUMN';

-- Renommer 'intent' -> 'المشكل' 
EXEC sp_rename 'final_data_table.intent', N'المشكل', 'COLUMN';

-- Renommer 'entity_location' -> 'الولاية' 
EXEC sp_rename 'final_data_table.entity_location', N'الولاية', 'COLUMN';

-- Renommer 'entity_neighborhood' -> 'البلاصة'
EXEC sp_rename 'final_data_table.entity_neighborhood', N'البلاصة', 'COLUMN';

-- Renommer 'entity_service' -> 'الخدمة'
EXEC sp_rename 'final_data_table.entity_service', N'الخدمة', 'COLUMN';

-- Renommer 'input_text' -> 'الشكاية'
EXEC sp_rename 'final_data_table.input_text', N'الشكاية', 'COLUMN';

-- Renommer 'output_text' -> 'الجواب'
EXEC sp_rename 'final_data_table.output_text', N'الجواب', 'COLUMN';

-- Renommer 'action_required' -> 'اش_لازم_يتعمل'
EXEC sp_rename 'final_data_table.action_required', N'اش_لازم_يتعمل', 'COLUMN';

-- Renommer 'sentiment' -> 'الشعور'
EXEC sp_rename 'final_data_table.sentiment', N'الشعور', 'COLUMN';

-- Renommer 'comment_timestamp' -> 'وقت_التعليق'
EXEC sp_rename 'final_data_table.comment_timestamp', N'وقت_التعليق', 'COLUMN';

-- Renommer 'status' -> 'الحالة'
EXEC sp_rename 'final_data_table.status', N'الحالة', 'COLUMN';

-- Renommer 'extra_field_garbage' -> 'عدد الاتصالات'
EXEC sp_rename 'final_data_table.extra_field_garbage', N'عدد الاتصالات', 'COLUMN';

-- Renommer 'comment_date_clean' -> 'تاريخ'
EXEC sp_rename 'final_data_table.comment_date_clean', N'تاريخ', 'COLUMN';
GO
