from iscewrap.alos2 import generate_dem

result = generate_dem(
    reference_input="133-7030-RF2_7-20201127.zip",
    secondary_input="133-7030-RF2_7-20210122.zip",
    work_dir="./isce_dem_test",
    use_gpu=False,
    do_ionosphere=False,
    apply_ionosphere=False,
    geocode_file_list=["diff*int", "filt*int*"],
    end_step="baseline",
)

print("Baseline run directory:", result["baseline_work_dir"])
print("Final XML:", result["xml_file"])
print("DEM for coregistration:", result["dem_coreg"])
print("DEM for geocoding:", result["dem_geocode"])
print("Water body:", result["water_body"])
print("Empty DEM metadata:", result["empty_dem"])
