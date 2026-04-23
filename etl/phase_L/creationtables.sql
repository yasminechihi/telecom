-- 1. Création de la nouvelle base de données
CREATE DATABASE telecom_DWH_Final;
GO

USE telecom_DWH_Final;
GO

-- 2. Création des Dimensions (Tables de référence)
CREATE TABLE Dim_Client (
    id_client INT PRIMARY KEY IDENTITY(1,1), 
    Nom_Client NVARCHAR(255)
);

CREATE TABLE Dim_Geographie (
    id_geo INT PRIMARY KEY IDENTITY(1,1), 
    Wilaya NVARCHAR(100), 
    Delegation NVARCHAR(100)
);

CREATE TABLE Dim_Probleme (
    id_prob INT PRIMARY KEY IDENTITY(1,1), 
    Probleme NVARCHAR(MAX), 
    Service_Type NVARCHAR(100), 
    Action_Requise NVARCHAR(MAX)
);

CREATE TABLE Dim_Temps (
    id_date INT PRIMARY KEY IDENTITY(1,1), 
    Date_Full DATE
);

CREATE TABLE Dim_Description (
    id_desc INT PRIMARY KEY IDENTITY(1,1), 
    Texte_Plainte NVARCHAR(MAX), 
    Texte_Reponse NVARCHAR(MAX)
);

CREATE TABLE Dim_Sentiment (
    id_sent INT PRIMARY KEY IDENTITY(1,1), 
    Label NVARCHAR(50)
);

-- 3. Création de la Table de Faits (Cœur du DWH)
CREATE TABLE Fact_Reclamations (
    id_fact INT PRIMARY KEY IDENTITY(1,1),
    id_source_original INT, -- Lien vers id_conversation de la base source
    id_client INT CONSTRAINT FK_Client REFERENCES Dim_Client(id_client),
    id_geo INT CONSTRAINT FK_Geo REFERENCES Dim_Geographie(id_geo),
    id_prob INT CONSTRAINT FK_Prob REFERENCES Dim_Probleme(id_prob),
    id_date INT CONSTRAINT FK_Date REFERENCES Dim_Temps(id_date),
    id_desc INT CONSTRAINT FK_Desc REFERENCES Dim_Description(id_desc),
    id_sent INT CONSTRAINT FK_Sent REFERENCES Dim_Sentiment(id_sent),
    Nombre_Recl INT DEFAULT 1
);
GO