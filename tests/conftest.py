import os
import sys

# repo root (contains the "frankAllSkyCam" package directory) needs to be on
# sys.path for "from frankAllSkyCam import ..." to resolve, same as it does
# for an installed package - tests/ lives at the repo root, one level up
# from here.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
