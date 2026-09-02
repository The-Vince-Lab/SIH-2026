"""Train all ML models and print metrics as JSON. Run: python -m ml.train_all"""
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from ml import placement_risk, response_classifier  # noqa: E402


def main():
    rc = response_classifier.train()
    pr = placement_risk.train()
    print(json.dumps({"response_classifier": rc, "placement_risk": pr}, indent=2))


if __name__ == "__main__":
    main()
