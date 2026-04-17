#!/usr/bin/env python3
# ============================================================
#  migrate_dataset_to_firebase.py
#
#  Migre dataset_final_nlp_v2_corrected.jsonl → Firestore
#  collection "dataset_nlp".
#
#  USAGE :
#    python migrate_dataset_to_firebase.py            # migration complète
#    python migrate_dataset_to_firebase.py --check    # vérifie sans écrire
#    python migrate_dataset_to_firebase.py --clear    # vide la collection puis migre
#
#  PRÉREQUIS :
#    • serviceAccountKey.json présent dans ce dossier
#    • pip install firebase-admin
# ============================================================

import argparse
import json
import os
import sys
import time

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
JSONL_PATH   = os.path.join(BASE_DIR, "dataset_final_nlp_v2_corrected.jsonl")
BATCH_SIZE   = 499   # Firestore max = 500 ops/batch (on laisse 1 de marge)
COLLECTION   = "dataset_nlp"

# ── Couleurs console ──────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}✅ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}⚠️  {msg}{RESET}")
def err(msg):  print(f"{RED}❌ {msg}{RESET}")
def info(msg): print(f"{CYAN}ℹ  {msg}{RESET}")


# ── Chargement du JSONL ───────────────────────────────────
def load_jsonl(path: str) -> list:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("instruction") and rec.get("response"):
                    records.append(rec)
                else:
                    warn(f"Ligne {i} ignorée (champs manquants)")
            except json.JSONDecodeError as e:
                warn(f"Ligne {i} ignorée (JSON invalide) : {e}")
    return records


# ── Connexion Firebase ────────────────────────────────────
def get_firestore_client():
    cred_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
    if not os.path.exists(cred_path):
        err(f"serviceAccountKey.json introuvable dans : {BASE_DIR}")
        sys.exit(1)
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except ImportError:
        err("firebase-admin non installé. Lancez : pip install firebase-admin")
        sys.exit(1)


# ── Vider la collection ────────────────────────────────────
def clear_collection(db, dry_run: bool = False):
    info(f"Suppression de tous les documents de '{COLLECTION}'…")
    batch_count = 0
    deleted     = 0
    batch       = db.batch()
    docs        = db.collection(COLLECTION).stream()
    for doc in docs:
        batch.delete(doc.reference)
        batch_count += 1
        deleted     += 1
        if batch_count >= BATCH_SIZE:
            if not dry_run:
                batch.commit()
            batch       = db.batch()
            batch_count = 0
            info(f"  {deleted} supprimés…")
    if batch_count and not dry_run:
        batch.commit()
    ok(f"{deleted} documents supprimés de '{COLLECTION}'.")


# ── Migration principale ───────────────────────────────────
def migrate(records: list, db, dry_run: bool = False):
    total   = len(records)
    written = 0
    errors  = 0
    start   = time.time()

    info(f"Migration de {total} enregistrements vers '{COLLECTION}'…")
    info(f"Taille des batches : {BATCH_SIZE}")

    for batch_start in range(0, total, BATCH_SIZE):
        batch_records = records[batch_start : batch_start + BATCH_SIZE]
        batch = db.batch()

        for local_i, rec in enumerate(batch_records):
            global_i = batch_start + local_i
            doc_ref  = db.collection(COLLECTION).document()
            data     = {
                "_idx":               global_i,
                "client_name":        rec.get("client_name",        ""),
                "location_wilaya":    rec.get("location_wilaya",    ""),
                "location_delegation":rec.get("location_delegation",""),
                "issue_type":         rec.get("issue_type",         ""),
                "service_type":       rec.get("service_type",       ""),
                "suggested_action":   rec.get("suggested_action",   ""),
                "sentiment_label":    rec.get("sentiment_label",    ""),
                "instruction":        rec.get("instruction",        ""),
                "response":           rec.get("response",           ""),
            }
            batch.set(doc_ref, data)

        try:
            if not dry_run:
                batch.commit()
            written += len(batch_records)
            pct = written / total * 100
            print(f"\r  {written}/{total} ({pct:.1f}%)…", end="", flush=True)
        except Exception as e:
            errors += len(batch_records)
            err(f"\nErreur batch {batch_start}–{batch_start + len(batch_records)} : {e}")

    elapsed = time.time() - start
    print()  # newline après le \r
    return written, errors, elapsed


# ── Vérification post-migration ────────────────────────────
def verify(db, expected: int):
    info("Vérification du nombre de documents dans Firestore…")
    count = sum(1 for _ in db.collection(COLLECTION).stream())
    if count == expected:
        ok(f"Firestore : {count} documents — correspond au JSONL ({expected}). ✓")
    else:
        warn(f"Firestore : {count} documents, JSONL : {expected} — différence de {abs(count - expected)}")
    return count


# ── Point d'entrée ─────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migre le dataset JSONL vers Firebase Firestore")
    parser.add_argument("--check",  action="store_true", help="Vérifie sans écrire (dry-run)")
    parser.add_argument("--clear",  action="store_true", help="Vide la collection avant de migrer")
    parser.add_argument("--verify-only", action="store_true", help="Vérifie seulement le nombre de docs")
    args = parser.parse_args()

    print(f"\n{CYAN}═══════════════════════════════════════════════════{RESET}")
    print(f"{CYAN}   Migration dataset JSONL → Firebase Firestore   {RESET}")
    print(f"{CYAN}═══════════════════════════════════════════════════{RESET}\n")

    # 1. Charger le JSONL
    if not os.path.exists(JSONL_PATH):
        err(f"Fichier JSONL introuvable : {JSONL_PATH}")
        sys.exit(1)

    records = load_jsonl(JSONL_PATH)
    ok(f"JSONL chargé : {len(records)} enregistrements valides")

    # 2. Connexion Firebase
    db = get_firestore_client()
    ok("Firebase Firestore connecté")

    if args.verify_only:
        verify(db, len(records))
        sys.exit(0)

    if args.check:
        info("Mode --check : simulation sans écriture")
        written, errors, elapsed = migrate(records, db, dry_run=True)
        ok(f"Simulation terminée — {written} enregistrements auraient été écrits en {elapsed:.1f}s")
        sys.exit(0)

    # 3. Vider la collection si demandé
    if args.clear:
        warn("--clear : suppression de tous les documents existants…")
        clear_collection(db)

    # 4. Migration
    written, errors, elapsed = migrate(records, db, dry_run=False)

    if errors == 0:
        ok(f"Migration terminée : {written} enregistrements écrits en {elapsed:.1f}s")
    else:
        warn(f"Migration terminée avec {errors} erreurs sur {len(records)} enregistrements")

    # 5. Vérification automatique
    verify(db, len(records))

    print(f"\n{GREEN}La collection '{COLLECTION}' est prête.{RESET}")
    print(f"{CYAN}Supprimez ou gardez le fichier JSONL comme sauvegarde.{RESET}\n")
