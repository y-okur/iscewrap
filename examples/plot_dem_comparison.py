from iscewrap.alos2 import plot_dem_comparison

out = plot_dem_comparison(
    generated_dem_file="./isce_dem_test/height_from_phase.dem",
    reference_dem_file="./isce_dem_test/crop.dem",
    remove_offset=True,
)
