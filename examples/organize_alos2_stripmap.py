"""Example: organize ALOS-2 stripmap ZIP products by processable date."""

from iscewrap.alos2 import organize_alos2_stripmap_zips

groups = organize_alos2_stripmap_zips(
    zip_files="raw_zips",
    output_dir="organized",
)

for group_name, group in groups.items():
    print(group_name)
    for date, date_info in group["dates"].items():
        print(f"  {date}: {date_info['date_dir']}")
