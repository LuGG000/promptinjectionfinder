# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 LuGG000
"""PromptInjectionFinder - deterministic prompt-injection scanner."""
import os as _os

# numpy is only used for small pixel-array operations; its BLAS thread pool would just burn CPU at start-up.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    _os.environ.setdefault(_var, "1")

__version__ = "1.3.3"
