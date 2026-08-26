"""
A small process-wide concurrency cap around the expensive pipeline
(pulling nflverse season data + scoring every free agent).

Streamlit serves each visitor's session in its own thread of the same
process, so a burst of people opening the app at once would otherwise try to
pull multiple full-season nflverse datasets simultaneously - several hundred
MB of parquet downloads and pandas groupbys at once. This semaphore just
makes bursts queue instead of all landing on the server at the same moment.
"""

import threading

# ~2 concurrent heavy pipeline runs, per the house standard. Cheap reads
# (Sleeper roster/FAAB calls) are NOT gated by this - only the nflverse pull
# + scoring pass in pipeline.run_for_league().
PIPELINE_SEMAPHORE = threading.Semaphore(2)
