from iscewrap.alos2 import geocode_raster

result = geocode_raster(
    input_file="./isce_dem_test/height_from_phase.dem",
    lat_file="./isce_dem_test/final/run/201127-210122_8rlks_16alks.lat",
    lon_file="./isce_dem_test/final/run/201127-210122_8rlks_16alks.lon",
    output_file="./isce_dem_test/height_from_phase_geo.dem",
    resolution=1 / 3600,
    method="nearest",
)

print(result)
