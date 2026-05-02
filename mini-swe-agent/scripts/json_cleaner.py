import json

input_file = "../outputs/preds.json"
output_file = "../outputs/swt_bench_compatible.json"

with open(input_file) as f:
    data = json.load(f)

compatible_list = list(data.values())

with open(output_file, "w") as f:
    json.dump(compatible_list, f, indent=2)

print(f"Done! Use {output_file} for your --predictions_path")