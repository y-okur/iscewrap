from iscewrap import geo_to_kml

result = geo_to_kml(
    input_file="./alos4_isce_work/run/insar/filt_201127-210122_8rlks_16alks_msk.unw.geo",
    output_file="./alos4_isce_work/run/insar/filt_201127-210122_8rlks_16alks_msk.unw.geo.kmz",
    value_mode="real",
    alpha=0.75,
)

print(result)
