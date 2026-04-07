# Pipeline VoiceBot Tunisie Telecom — Darija Tunisien

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────┐
│              VOICEBOT TUNISIE TELECOM — DARIJA                  │
│                   Centre d'appel virtuel                        │
└─────────────────────────────────────────────────────────────────┘

  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  🎙️ STT  │ →  │  🧠 NLU  │ →  │  🔍 RAG  │ →  │  🔊 TTS  │
  │ Whisper  │    │  Règles  │    │  FAISS   │    │  gTTS    │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
        ↑                               ↓
   Micro client                    Confiance ?
                                  /          \
                            ✅ Haute      ❌ Basse
                           Répondre      Transférer
                                             ↓
                                    ┌─────────────┐
                                    │ Agent Humain │
                                    └─────────────┘
                                             ↓
                                    ┌─────────────┐
                                    │ Apprentissage│
                                    │ Continu      │
                                    └─────────────┘
```

---

## Flux détaillé par étape

### Étape 1 — STT : Parole → Texte

**Module** : `modules/stt.py`
**Technologie** : `faster-whisper` (modèle medium, langue: ar)

Le client parle en darija tunisien. Whisper capte l'audio depuis le microphone via `sounddevice`, détecte automatiquement les silences (VAD filter), puis transcrit la parole en texte arabe. Un **prompt initial** guide Whisper vers le contexte télécom tunisien pour améliorer la précision.

---

### Étape 2 — NLU : Texte → Intention + Entités

**Module** : `modules/nlu.py`
**Technologie** : Règles regex multilingues (arabe + français)

Le texte darija est analysé pour détecter :
- **L'intention** : عطل شبكة, مشكلة دفع, استفسار رصيد, تجوال...
- **Les entités** : wilaya, numéro de téléphone, ID transaction
- **Le sentiment** : positif / négatif / neutre
- **Les mots de clôture** : باي, خلاص, يزي... (arrêt immédiat)

---

### Étape 3 — RAG : Recherche de réponse dans le dataset

**Module** : `modules/response_engine.py`
**Technologie** : `sentence-transformers` (MiniLM multilingue) + `FAISS`

Au premier démarrage, le moteur encode les **6 687 conversations** du dataset en vecteurs sémantiques et construit un index FAISS. À chaque requête :

1. La requête client est encodée en vecteur
2. FAISS cherche les K conversations les plus similaires
3. Le score de similarité décide :
   - `score ≥ 0.80` → réponse directe (haute confiance)
   - `0.55 ≤ score < 0.80` → réponse avec demande de confirmation
   - `score < 0.55` → transfert vers agent humain

---

### Étape 4 — TTS : Texte → Parole

**Module** : `modules/tts.py`
**Technologie** : `gTTS` (Google TTS, langue: ar)

La réponse darija est synthétisée en parole naturelle via Google TTS et jouée au client via les haut-parleurs.

---

### Étape 5 — Transfert agent humain

**Module** : `modules/human_transfer.py`

Déclenché si la confiance RAG est trop basse ou après N tentatives échouées. Un **ticket** est créé avec :
- Le résumé de la conversation
- L'intention détectée
- Le niveau de priorité (haute / moyenne / normale)
- L'historique complet

L'agent humain répond → le bot transmet la réponse au client.

---

### Étape 6 — Apprentissage continu

**Module** : `modules/learning.py`

La réponse de l'agent humain est sauvegardée dans `learned_interactions.jsonl` au **même format** que le dataset principal. Quand 50 nouvelles interactions sont apprises, l'index FAISS est **automatiquement reconstruit** pour intégrer les nouveaux cas.

---

## Structure des fichiers

```
agent_vocal/
├── voicebot_main.py                  ← Point d'entrée
├── config.py                         ← Configuration centrale
├── requirements.txt                  ← Dépendances Python
├── PIPELINE.md                       ← Ce document
│
├── modules/
│   ├── stt.py                        ← Speech-to-Text (Whisper)
│   ├── tts.py                        ← Text-to-Speech (gTTS)
│   ├── nlu.py                        ← Intention + entités
│   ├── response_engine.py            ← RAG (FAISS + embeddings)
│   ├── dialog_manager.py             ← Orchestration du dialogue
│   ├── human_transfer.py             ← Transfert agent humain
│   └── learning.py                   ← Apprentissage continu
│
├── utils/
│   ├── audio_utils.py                ← Enregistrement / lecture
│   └── text_utils.py                 ← Normalisation darija
│
├── models/                           ← Générés au premier démarrage
│   ├── faiss_index.bin               ← Index vectoriel
│   ├── embeddings.npy                ← Vecteurs encodés
│   └── dataset_cache.pkl             ← Cache du dataset
│
├── data/                             ← Données dynamiques
│   ├── learned_interactions.jsonl   ← Apprentissage continu
│   └── human_queue.jsonl             ← File d'attente agents
│
├── logs/                             ← Logs automatiques
│   ├── voicebot.log                  ← Log technique
│   └── conversations.jsonl           ← Historique sessions
│
└── dataset_final_nlp_v2_corrected.jsonl  ← Dataset principal
```

---

## Installation et démarrage

### 1. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 2. Premier démarrage (construction index RAG)
```bash
python voicebot_main.py --build-index
# Durée : ~5-10 min selon la machine
```

### 3. Lancer le voicebot en mode vocal
```bash
python voicebot_main.py
```

### 4. Mode debug (clavier, sans micro)
```bash
python voicebot_main.py --text
```

### 5. Statistiques d'apprentissage
```bash
python voicebot_main.py --stats
```

---

## Exemple de conversation

```
🤖 BOT : مرحبا بيك في تليكوم تونس! أنا المساعد الآلي، كيفاش نجم نعاونك اليوم؟

🧑 Client : [parle] عسلامة، الريزو عندي طايح من الصباح في صفاقس

🤖 BOT : سامحنا خويا، فما أشغال صيانة في صفاقس، تو يرجع مريغل إن شاء الله

🧑 Client : [parle] وقتاش بالضبط؟

🤖 BOT : متوقع يرجع قبل العشية، إذا ما رجعش اتصل بنا

🧑 Client : [parle] خلاص شكرن

🤖 BOT : شكرن على اتصالك بتليكوم تونس، يوم سعيد!
```

---

## Paramètres clés à ajuster

| Paramètre | Valeur défaut | Description |
|-----------|--------------|-------------|
| `STT_MODEL` | medium | Taille Whisper (tiny→large-v3) |
| `RAG_CONFIDENCE_THRESHOLD` | 0.55 | Seuil de confiance min |
| `ESCALATION_ATTEMPTS` | 2 | Essais avant transfert humain |
| `RETRAIN_THRESHOLD` | 50 | Interactions avant réentraînement |
| `MAX_TURNS` | 20 | Tours max par conversation |
| `STT_SILENCE_TIMEOUT` | 3.0s | Silence pour arrêter l'écoute |

---

## Technologies utilisées

| Composant | Technologie | Rôle |
|-----------|------------|------|
| STT | faster-whisper | Transcription darija |
| Embeddings | MiniLM multilingue | Encodage sémantique |
| Recherche | FAISS | Similarité vectorielle |
| TTS | gTTS (ar) | Synthèse vocale arabe |
| Audio | sounddevice | Capture microphone |
| NLU | Regex + règles | Intent / entités |
