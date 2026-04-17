CREATE DATABASE telecom_DWH;
GO
USE telecom_DWH;
GO

CREATE TABLE Dim_Client (id_client INT PRIMARY KEY IDENTITY(1,1), Nom_Client NVARCHAR(255));
CREATE TABLE Dim_Geographie (id_geo INT PRIMARY KEY IDENTITY(1,1), Wilaya NVARCHAR(100), Delegation NVARCHAR(100));
CREATE TABLE Dim_Probleme (id_prob INT PRIMARY KEY IDENTITY(1,1), Probleme NVARCHAR(MAX), Service_Type NVARCHAR(100), Action_Requise NVARCHAR(MAX));
CREATE TABLE Dim_Temps (id_date INT PRIMARY KEY IDENTITY(1,1), Date_Full DATE);
CREATE TABLE Dim_Description (id_desc INT PRIMARY KEY IDENTITY(1,1), Texte_Plainte NVARCHAR(MAX), Texte_Reponse NVARCHAR(MAX));
CREATE TABLE Dim_Sentiment (id_sent INT PRIMARY KEY IDENTITY(1,1), Label NVARCHAR(50));

CREATE TABLE Fact_Reclamations (
    id_fact INT PRIMARY KEY, -- On utilisera ton id de final_data_table
    id_client INT REFERENCES Dim_Client(id_client),
    id_geo INT REFERENCES Dim_Geographie(id_geo),
    id_prob INT REFERENCES Dim_Probleme(id_prob),
    id_date INT REFERENCES Dim_Temps(id_date),
    id_desc INT REFERENCES Dim_Description(id_desc),
    id_sent INT REFERENCES Dim_Sentiment(id_sent),
    Nombre_Recl INT DEFAULT 1
);
GO