"""
Script to generate the test data.
"""

import numpy as np

t = np.linspace(0, 10, num=5000)
one = np.full((5000,), 1)
two = np.random.normal(size=5000)
three = np.linspace(100, 10000, num=5000)

combined = np.column_stack([t, one, two, three])
np.savetxt("multichannel_data.csv", combined, delimiter=",", header="t, one, two, three", comments="")
