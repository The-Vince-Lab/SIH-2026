"""SkillTrace AI internal ML modules.

These run inside the FastAPI backend (no separate microservice):
  - placement_risk.py   : explainable placement-risk prediction (scikit-learn)
  - identity_matching.py : fuzzy identity matching across programs (rapidfuzz)
  - text_classifier.py  : rule/keyword classification of free-text responses

Populated in later phases.
"""
