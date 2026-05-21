"""Example: convert retained topographic phase to height."""

from iscewrap.alos2 import convert_phase_to_height

result = convert_phase_to_height(
    phase_file="./run/insar/filt_201127-210122_8rlks_16alks.unw",
    los_file="./run/insar/201127-210122_8rlks_16alks.los",
    track_xml="./run/201127.track.xml",
    baseline_log="./run/alos2App_full_terminal.log",
    output_file="height_from_phase.dem",

    # Try sign=-1.0 if the DEM is inverted.
    sign=1.0,
)

print(result)
