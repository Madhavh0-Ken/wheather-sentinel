# Five-minute demonstration

Before the session, run `scripts\prepare_demo.py --no-download`, start Streamlit on
port 8501, and leave the replay at frame 9.

**0:00–0:40 — Establish evidence.** Open the Source readiness sidebar. Point out the
cached historical NOAA CPC CMORPH event, 12 frames, approximately 8 km source grid,
and explicit official-input-required states for MOSDAC and IMD.

**0:40–1:25 — Replay the observation.** Use Prev/Next and Play. Explain the cyan
grid as observed rain and the amber outlines as derived Intense Precipitation Cells.
Show that the timestamp banner allows only observations up to the selected cut.

**1:25–2:20 — Inspect a persistent cell.** Select `IPC-011`. Read maximum rain rate,
area, speed, bearing, intensity trend, and tracked history. Stress that the object is
rainfall-derived, not a confirmed thunderstorm.

**2:20–3:15 — Forecast and uncertainty.** Follow the magenta +30/+60/+120 movement
path and expanding uncertainty circles. Distinguish the evidence-quality estimate
from the separate per-lead track heuristic; neither is calibrated.

**3:15–4:00 — Risk and target.** Expand the target editor, keep or adjust Shimla,
then show Prototype Extreme Rain Risk, closest approach, and qualified ETA. State
that risk is an unvalidated heuristic and ETA is the closest discrete forecast time
inside an uncertainty corridor.

**4:00–4:35 — Evaluate honestly.** Show the real +30 and +60 position error/IoU
rows and the insufficient +120 row. Emphasize the sample count of one at each
available lead.

**4:35–5:00 — Extension boundary.** Expand sensor evidence and hazard availability.
Show that unavailable lightning, hail, and downburst evidence is not replaced by
zero. Mention the read-only API and the next step: authorized MOSDAC/IMD files plus
multi-event validation.

