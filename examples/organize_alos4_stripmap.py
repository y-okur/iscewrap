"""Example: organize ALOS-4 stripmap ZIP products by processable date."""

from iscewrap.alos4 import organize_alos4_stripmap_zips

groups = organize_alos4_stripmap_zips(
    zip_files="raw_zips",
    output_dir="organized",
    polarizations=["HH"],  # optional; omit to extract all polarizations
)

for group_name, group in groups.items():
    print(group_name)
    for date, date_info in group["dates"].items():
        print(f"  {date}: {date_info['date_dir']}")
