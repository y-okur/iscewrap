"""Example: run ALOS-2 DEM-generation processing with empty DEM inputs.

This workflow is for preserving topographic phase. It first runs alos2App.py
through ``baseline``, creates zero-valued empty DEM files under
``work_dir/empty_dem``, inserts those empty DEM paths into the processing XML,
and then runs the requested ALOS-2 processing chain.

For ordinary InSAR processing with real SRTM DEM preparation, use
``process_alos2_pair`` instead.
"""

from iscewrap.alos2 import generate_dem

result = generate_dem(
    reference_input="133-7030-RF2_7-20201127.zip",
    secondary_input="133-7030-RF2_7-20210122.zip",
    work_dir="./isce_dem_test",
    use_gpu=False,
    do_ionosphere=False,
    apply_ionosphere=False,
    geocode_file_list=["diff*int", "filt*int*"],

    # Choose the final processing range after the empty DEM has been prepared.
    start_step=None,
    end_step=None,
)

print("Pair name:", result["pair_name"])
print("XML file:", result["xml_file"])
print("Run directory:", result["run_dir"])
print("DEM for coregistration:", result["dem_coreg"])
print("DEM for geocoding:", result["dem_geocode"])
print("Water body:", result["water_body"])
print("Empty DEM metadata:", result["empty_dem_result"])
