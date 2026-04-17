import re

input_file = "dataset.json"
output_file = "dataset.jsonl"

with open(input_file, "r", encoding="utf-8") as f:
    text = f.read()

# Extraire chaque objet JSON entre { ... }
objects = re.findall(r'\{[^{}]*"instruction"[^{}]*\}', text, re.DOTALL)

with open(output_file, "w", encoding="utf-8") as out:
    for obj in objects:
        # Nettoyage des retours à la ligne داخل النص
        clean_obj = obj.replace("\n", " ").replace("\r", " ")
        out.write(clean_obj.strip() + "\n")

print(f"✅ Conversion terminée : {len(objects)} lignes écrites dans dataset.jsonl")
