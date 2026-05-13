"""Example: convert retained topographic phase to height."""

from iscewrap.alos2 import convert_phase_to_height

result = convert_phase_to_height(
    phase_file="201127-210122_8rlks_16alks.topophase",
    los_file="201127-210122_8rlks_16alks.los",
    track_xml="201127.track.xml",
    baseline_log="alos2App_full_terminal.log",
    output_file="height_from_phase.dem",

    # Usually inferred from filename *_8rlks_16alks.*.
    # Provide manually if needed:
    # range_looks=8,

    # Try sign=-1.0 if the DEM is inverted.
    sign=1.0,
)

print(result)
