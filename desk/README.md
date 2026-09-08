# Market Desk

Cross-product snapshot at `/desk/`: headline KPIs, PLD×CMO×CVU, POC vs ANP
Santos prices, TSO capacity vs realized flows, and a thermal spark-spread
calculator. Built from sibling/lake parquet when present; empty panels when not.

```bash
cd desk
pip install -r requirements.txt
python dashboard.py
```
