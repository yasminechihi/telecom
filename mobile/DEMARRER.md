# 🚀 Mon Espace TT — Application Flutter

Application mobile **Tunisie Telecom** — identique à l'interface web `user_app.py`.
Même base de données Firebase Firestore, même logique de connexion.

---

## 📁 Structure du projet

```
mobile/
├── lib/
│   ├── main.dart                  ← Point d'entrée + navigation
│   ├── theme/
│   │   └── app_theme.dart         ← Couleurs TT (violet, teal)
│   ├── services/
│   │   └── api_service.dart       ← Appels vers Flask (port 5001)
│   ├── models/
│   │   └── user_model.dart        ← UserModel, ChatMessage, Stats
│   └── screens/
│       ├── login_screen.dart      ← Écran connexion
│       ├── register_screen.dart   ← Écran inscription
│       ├── dashboard_screen.dart  ← Tableau de bord
│       └── chat_screen.dart       ← Chat avec le bot
├── web/
│   ├── index.html                 ← Page HTML pour Chrome
│   └── manifest.json              ← PWA manifest
├── pubspec.yaml                   ← Dépendances Flutter
└── DEMARRER.md                    ← Ce guide
```

---

## ✅ Étape 1 — Prérequis

Assure-toi d'avoir installé :

- **Flutter SDK** → [flutter.dev/docs/get-started/install](https://flutter.dev/docs/get-started/install)
- **VS Code** avec les extensions **Flutter** + **Dart**
- **Google Chrome** (pour les tests web)

Vérifie l'installation :
```bash
flutter doctor
```

---

## ✅ Étape 2 — Installer les dépendances

Ouvre un terminal dans le dossier `mobile/` :

```bash
cd C:\Users\USER\Desktop\telecom\mobile
flutter pub get
```

---

## ✅ Étape 3 — Lancer le backend Flask

Avant de lancer l'app Flutter, **démarre d'abord le serveur Flask** :

```bash
cd C:\Users\USER\Desktop\telecom\PFE
python user_app.py
```

Le serveur démarre sur : **http://localhost:5001**

---

## ✅ Étape 4 — Lancer l'application dans Chrome

```bash
cd C:\Users\USER\Desktop\telecom\mobile
flutter run -d chrome
```

L'application s'ouvre dans Chrome à l'adresse `http://localhost:8080`

### ⚠️ Important — CORS déjà configuré
Le fichier `user_app.py` a été modifié pour accepter les requêtes
depuis Chrome (`localhost:8080`). Pas besoin de configuration supplémentaire.

---

## 🔗 Connexion — même base de données

| Plateforme | URL | Base |
|---|---|---|
| Web Flask | http://localhost:5001 | Firebase Firestore |
| Mobile Flutter | http://localhost:8080 | **même Firebase Firestore** |

Un compte créé sur le **web** fonctionne sur le **mobile** et inversement.

---

## 📱 Fonctionnalités

| Écran | Description |
|---|---|
| **Connexion** | Se connecter avec email + mot de passe |
| **Inscription** | Créer un compte (nom, prénom, email, téléphone) |
| **Dashboard** | Statistiques, actions rapides, historique |
| **Chat** | Discuter avec l'assistant IA en arabe/darija |
| **Historique** | Voir toutes les conversations passées |
| **Profil** | Informations personnelles |

---

## 🎨 Design

Couleurs identiques au site web :

| Couleur | Hex | Usage |
|---|---|---|
| Violet principal | `#5B1FBE` | Boutons, header, accents |
| Violet foncé | `#3D1484` | Gradient sidebar |
| Teal | `#00B4D8` | Badges, statut en ligne |
| Blanc | `#FFFFFF` | Cartes, fond formulaires |
| Gris clair | `#F4F5F7` | Fond de page |

---

## 🛠️ Tester sur téléphone Android (sans émulateur)

1. Active **Mode développeur** sur ton téléphone
2. Active **Débogage USB**
3. Connecte via câble USB
4. Lance :
```bash
flutter run
```

---

## ❓ Problèmes fréquents

**"No devices found"**
→ Lance `flutter run -d chrome` pour le web

**Erreur CORS**
→ Vérifie que `user_app.py` tourne sur le port 5001

**"flutter: command not found"**
→ Ajoute Flutter au PATH Windows :
`C:\Users\USER\flutter\bin` (selon où tu l'as installé)

**Erreur de connexion au backend**
→ Ouvre `lib/services/api_service.dart` et vérifie :
```dart
static const String baseUrl = 'http://localhost:5001';
```
