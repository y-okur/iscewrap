"""Example: process one ALOS-2 reference/secondary pair."""

from iscewrap.alos2.workflow import process_alos2_pair

result = process_alos2_pair(
    reference_input="reference.zip",
    secondary_input="secondary.zip",
    work_dir="isce_work",
    dem_coreg="dem.dem.wgs84",
    dem_geocode="dem.dem.wgs84",
    water_body="waterBody.rdr",
    use_gpu=False,
    run=False,  # set True when ISCE2 is available
    geocode_file_list=["diff*int", "filt*int*"],
)

print(result["xml_file"])
