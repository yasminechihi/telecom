import json

input_file = "dataset.jsonl"
output_file = "dataset_fixed.jsonl"

with open(input_file, "r", encoding="utf-8") as f_in, \
     open(output_file, "w", encoding="utf-8") as f_out:
    for line in f_in:
        # On remplace l'erreur spécifique trouvée par Hive
        fixed_line = line.replace("\\ /", "/").replace("\\/", "/")
        # On valide que c'est du bon JSON
        try:
            obj = json.loads(fixed_line)
            f_out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except:
            continue

print("✅ Fichier nettoyé : dataset_fixed.jsonl")