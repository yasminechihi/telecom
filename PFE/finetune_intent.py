#!/usr/bin/env python3
# ============================================================
#  finetune_intent.py — Fine-tuning AraBERT pour classification d'intent
#  Tunisie Telecom VoiceBot — Darija tunisien
#
#  Utilise HuggingFace Transformers pour fine-tuner un modèle
#  BERT arabe sur le dataset de 6687 conversations.
#
#  Usage :
#    python finetune_intent.py
#    python finetune_intent.py --model aubmindlab/bert-base-arabertv02
#    python finetune_intent.py --epochs 10 --batch_size 8
#
#  Résultat :
#    models/finetuned_intent/       ← Modèle sauvegardé
#    models/finetuned_intent/label_map.json
#    models/finetuned_intent/metrics.json
# ============================================================

import os
import sys
import json
import re
import argparse
import logging
import numpy as np
from collections import Counter
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Chemins ──────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(BASE_DIR, "dataset_final_nlp_v2_corrected.jsonl")
OUTPUT_DIR   = os.path.join(BASE_DIR, "models", "finetuned_intent")

# ── Modèles disponibles (du plus performant au plus léger) ───
MODELS = {
    "arabert":      "aubmindlab/bert-base-arabertv02",
    "camelbert":    "CAMeL-Lab/bert-base-arabic-camelbert-mix",
    "multilingual": "bert-base-multilingual-cased",
    "distilbert":   "distilbert-base-multilingual-cased",   # Le plus léger/rapide
}

# ══════════════════════════════════════════════════════════════
#  1. CHARGEMENT ET PRÉPARATION DES DONNÉES
# ══════════════════════════════════════════════════════════════

def load_dataset(path: str) -> list:
    """Charge le dataset JSONL et extrait les textes + labels."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                issue_type  = normalize_issue(rec.get("issue_type", ""))
                instruction = rec.get("instruction", "")

                if not issue_type or not instruction:
                    continue

                # Extraire le message utilisateur (problème principal)
                user_text = extract_user_problem(instruction)
                if not user_text or len(user_text) < 5:
                    continue

                records.append({
                    "text":       user_text,
                    "label":      issue_type,
                    "full_text":  instruction,   # Pour debug
                })
            except json.JSONDecodeError:
                continue

    logger.info(f"Dataset chargé : {len(records)} exemples valides")
    return records


def normalize_issue(text: str) -> str:
    """Normalise les labels issue_type (corrige les typos dans le dataset)."""
    if not text or text == "None":
        return ""
    # Supprime les espaces parasites dans le texte
    text = re.sub(r'\s+', ' ', text.strip())
    # Normalise les caractères arabes
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    text = text.replace('ة', 'ة')  # Garder le ta marbuta ici
    return text


def extract_user_problem(instruction: str) -> str:
    """
    Extrait le message principal du client (le problème) de l'instruction multi-tour.

    Dataset format: USER: salut | BOT: salut | USER: problème | BOT: question | USER: réponse

    On extrait le 2ème USER turn (le problème), et le 3ème USER turn (la réponse
    à la clarification) pour avoir le contexte complet.
    """
    parts = instruction.split("|")
    user_turns = []
    for part in parts:
        part = part.strip()
        if part.upper().startswith("USER:"):
            user_turns.append(part[5:].strip())

    # Le premier USER turn est souvent juste "عسلامة" (salutation)
    # Le vrai problème est dans le 2ème et 3ème turn
    if len(user_turns) >= 3:
        # Combine problème + réponse clarification
        return f"{user_turns[1]} {user_turns[2]}"
    elif len(user_turns) >= 2:
        return user_turns[1]
    elif user_turns:
        return user_turns[0]
    return instruction


def create_label_mapping(records: list) -> dict:
    """Crée le mapping label → id et id → label."""
    labels = sorted(set(r["label"] for r in records))
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for i, label in enumerate(labels)}

    logger.info(f"Nombre de classes : {len(labels)}")
    for label in labels:
        count = sum(1 for r in records if r["label"] == label)
        logger.info(f"  {label}: {count} exemples")

    return label2id, id2label


# ══════════════════════════════════════════════════════════════
#  2. FINE-TUNING
# ══════════════════════════════════════════════════════════════

def finetune(model_name: str, records: list, label2id: dict, id2label: dict,
             epochs: int = 5, batch_size: int = 16, lr: float = 2e-5,
             max_len: int = 128):
    """Fine-tune un modèle HuggingFace pour la classification d'intent."""

    # Imports (ici pour ne pas planter si HF pas installé)
    try:
        import torch
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            TrainingArguments,
            Trainer,
        )
        from datasets import Dataset
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report, accuracy_score, f1_score
    except ImportError as e:
        logger.error(
            f"Module manquant : {e}\n"
            "Installe avec :\n"
            "  pip install transformers datasets torch scikit-learn --break-system-packages"
        )
        sys.exit(1)

    num_labels = len(label2id)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Device : {device}")
    logger.info(f"Modèle : {model_name}")
    logger.info(f"Classes : {num_labels}")

    # ── Tokenizer ────────────────────────────────────────────
    logger.info("Chargement du tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # ── Train / Val split ────────────────────────────────────
    texts  = [r["text"] for r in records]
    labels = [label2id[r["label"]] for r in records]

    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=0.15, random_state=42, stratify=labels
    )

    logger.info(f"Train : {len(train_texts)} | Val : {len(val_texts)}")

    # ── Tokenisation ─────────────────────────────────────────
    def tokenize_data(texts, labels):
        encodings = tokenizer(
            texts, truncation=True, padding=True,
            max_length=max_len, return_tensors="pt"
        )
        dataset = Dataset.from_dict({
            "input_ids":      encodings["input_ids"],
            "attention_mask": encodings["attention_mask"],
            "labels":         labels,
        })
        dataset.set_format("torch")
        return dataset

    logger.info("Tokenisation...")
    train_dataset = tokenize_data(train_texts, train_labels)
    val_dataset   = tokenize_data(val_texts, val_labels)

    # ── Modèle ───────────────────────────────────────────────
    logger.info("Chargement du modèle pré-entraîné...")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    )
    model.to(device)

    # ── Métriques ────────────────────────────────────────────
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = accuracy_score(labels, preds)
        f1  = f1_score(labels, preds, average="weighted")
        return {"accuracy": acc, "f1": f1}

    # ── Training Arguments ───────────────────────────────────
    training_args = TrainingArguments(
        output_dir=os.path.join(OUTPUT_DIR, "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=lr,
        weight_decay=0.01,
        warmup_ratio=0.1,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_dir=os.path.join(OUTPUT_DIR, "logs"),
        logging_steps=50,
        save_total_limit=2,
        fp16=(device == "cuda"),
        report_to="none",
        seed=42,
    )

    # ── Trainer ──────────────────────────────────────────────
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )

    # ── Entraînement ─────────────────────────────────────────
    logger.info("="*55)
    logger.info("  DÉBUT DU FINE-TUNING")
    logger.info("="*55)
    start_time = datetime.now()

    trainer.train()

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Fine-tuning terminé en {duration:.0f}s ({duration/60:.1f} min)")

    # ── Évaluation finale ────────────────────────────────────
    logger.info("Évaluation finale...")
    eval_results = trainer.evaluate()
    logger.info(f"  Accuracy : {eval_results['eval_accuracy']:.4f}")
    logger.info(f"  F1 Score : {eval_results['eval_f1']:.4f}")

    # Classification report détaillé
    preds_output = trainer.predict(val_dataset)
    preds = np.argmax(preds_output.predictions, axis=-1)
    report = classification_report(
        val_labels, preds,
        target_names=[id2label[i] for i in range(num_labels)],
        output_dict=True,
    )
    report_text = classification_report(
        val_labels, preds,
        target_names=[id2label[i] for i in range(num_labels)],
    )
    logger.info(f"\n{report_text}")

    # ── Sauvegarde ───────────────────────────────────────────
    logger.info(f"Sauvegarde du modèle dans {OUTPUT_DIR}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Sauvegarder modèle + tokenizer
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    # Sauvegarder le mapping des labels
    with open(os.path.join(OUTPUT_DIR, "label_map.json"), "w", encoding="utf-8") as f:
        json.dump({"label2id": label2id, "id2label": id2label}, f, ensure_ascii=False, indent=2)

    # Sauvegarder les métriques
    metrics = {
        "model_name":     model_name,
        "num_classes":    num_labels,
        "train_size":     len(train_texts),
        "val_size":       len(val_texts),
        "epochs":         epochs,
        "batch_size":     batch_size,
        "learning_rate":  lr,
        "accuracy":       eval_results["eval_accuracy"],
        "f1_score":       eval_results["eval_f1"],
        "duration_sec":   duration,
        "device":         device,
        "date":           datetime.now().isoformat(),
    }
    with open(os.path.join(OUTPUT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    logger.info("="*55)
    logger.info(f"  ✅ FINE-TUNING TERMINÉ")
    logger.info(f"  Accuracy : {eval_results['eval_accuracy']:.2%}")
    logger.info(f"  F1 Score : {eval_results['eval_f1']:.2%}")
    logger.info(f"  Modèle sauvegardé dans : {OUTPUT_DIR}")
    logger.info("="*55)

    return metrics


# ══════════════════════════════════════════════════════════════
#  3. MAIN
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Fine-tune AraBERT pour classification d'intent")
    parser.add_argument("--model", type=str, default="arabert",
                        choices=list(MODELS.keys()) + [v for v in MODELS.values()],
                        help="Nom du modèle (arabert, camelbert, multilingual, distilbert)")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max_len", type=int, default=128)
    args = parser.parse_args()

    # Résoudre le nom du modèle
    model_name = MODELS.get(args.model, args.model)

    logger.info("="*55)
    logger.info("  Fine-tuning Intent Classification — Tunisie Telecom")
    logger.info("="*55)

    # 1. Charger le dataset
    records = load_dataset(DATASET_PATH)
    if not records:
        logger.error("Dataset vide ou introuvable !")
        sys.exit(1)

    # 2. Créer le mapping des labels
    label2id, id2label = create_label_mapping(records)

    # 3. Fine-tuner
    metrics = finetune(
        model_name=model_name,
        records=records,
        label2id=label2id,
        id2label={int(k): v for k, v in id2label.items()},
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_len=args.max_len,
    )

    return metrics


if __name__ == "__main__":
    main()
