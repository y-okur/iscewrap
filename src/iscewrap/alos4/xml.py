"""XML writers for ALOS-4 workflows using ISCE2 Alos2Proc."""

from __future__ import annotations

from pathlib import Path

from iscewrap.alos2.xml import create_alos2app_xml


def create_alos4app_xml(
    reference_dir,
    secondary_dir,
    output_xml,
    **kwargs,
) -> Path:
    """Create an ISCE2 XML file for ALOS-4 data.

    ISCE2 does not currently expose a native ``Alos4Proc`` application in this
    environment. This writer intentionally emits an ``alos2App.py`` compatible
    XML because the processing engine being reused is still ``Alos2Proc``.
    """
    return create_alos2app_xml(
        reference_dir=reference_dir,
        secondary_dir=secondary_dir,
        output_xml=output_xml,
        **kwargs,
    )
