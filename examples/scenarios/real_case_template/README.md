# Real Case Template

Place your real documents in this folder and then duplicate the JSON template below into `scenario.json`.

Expected files:

- `source.pdf` or `source.docx` or `source.txt`
- `response.pdf` or `response.docx` or `response.txt`
- Optional: `glossary.pdf` / `glossary.docx` / `glossary.txt`
- Optional: `prior_contract.pdf` / `prior_contract.docx` / `prior_contract.txt`
- Optional: `ground_truth.json` if you want evaluation against expected labels

Fastest way to run a real case:

```bash
./.venv/bin/python demo.py \
  --policy examples/scenarios/real_case_template/source.pdf \
  --response examples/scenarios/real_case_template/response.pdf \
  --output-dir output/demo_cases/real_case_run
```

Scenario-driven run:

1. Copy `scenario.template.json` to `scenario.json`
2. Update file names if needed
3. Run:

```bash
./.venv/bin/python demo.py \
  --scenario-dir examples/scenarios/real_case_template \
  --mode linear
```
