# BO3 synthetic XGBoost demo

`bo3_synthetic_training_demo.csv` contains invented examples for demonstrating
the BO3 Learning-to-Rank pipeline. It represents 140 fictional user-context
scenarios and 840 candidate gaps. Its relevance labels were generated from a
handwritten scoring formula with noise, then graded relative to other
candidates in each scenario. No real user feedback was used.

The resulting model, `backend/models/bo3_gap_ranker_synthetic_demo.json`, is a
real XGBoost ranker file trained on that simulated data. It demonstrates the
training and inference format only; its scores do not establish real-world
accuracy and should not be treated as a validated DressMe model.

Recreate both files from the repository root in PowerShell:

```powershell
backend/.venv/Scripts/python.exe backend/generate_bo3_demo_data.py
backend/.venv/Scripts/python.exe backend/train_bo3_ranker.py `
  --data backend/data/bo3_synthetic_training_demo.csv `
  --output backend/models/bo3_gap_ranker_synthetic_demo.json
```
