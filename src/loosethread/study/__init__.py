"""The P3 evaluation study (docs/STUDY_PLAN.md).

Standard library only, like the core: model clients are imported only when a run asks for one, so
scoring and tables work offline without keys. Experiment rows go to `results/rows/study-*.jsonl`.
"""
