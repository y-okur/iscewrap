"""Example: process one ALOS-2 reference/secondary pair."""

from iscewrap.alos2.workflow import process_alos2_pair

result = process_alos2_pair(
    reference_input="reference.zip", # or path to unzipped folder where IMG* files are located
    secondary_input="secondary.zip", # or path to unzipped folder where IMG* files are located
    work_dir="isce_work",
    dem_coreg="dem.dem.wgs84", # leave None for auto-download SRTM DEM from ESA. dem_geocode will be created from downsampling this DEM. water_body will be generated in the same grid with valid pixels for all the grid
    dem_geocode="dem.dem.wgs84",
    water_body="waterBody.rdr",
    use_gpu=False,
    run=False,  # set True when ISCE2 is available to process the pair.
    geocode_file_list=["diff*int", "filt*int*"],
)

print(result["xml_file"])
