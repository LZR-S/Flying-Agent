"""Explicit entry point for the isolated frozen v0 comparator."""
from .cli import ROOT,launch


def launch_baseline(config,directory):
    root=ROOT/'baseline/v0'
    if not (root/'runner.py').exists():raise RuntimeError('frozen baseline not prepared')
    return launch(config,directory,baseline_root=root)
