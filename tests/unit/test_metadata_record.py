import pytest

from ide_dataverse_integrator.models.metadata_record import SpatialInfo

POLYGON_COORDS = [
    [-60.79, -32.86],
    [-60.61, -32.86],
    [-60.61, -33.03],
    [-60.79, -33.03],
    [-60.79, -32.86],
]


def _bbox(spatial: SpatialInfo) -> tuple:
    return (
        spatial.west_longitude,
        spatial.east_longitude,
        spatial.north_latitude,
        spatial.south_latitude,
    )


@pytest.mark.parametrize(
    "spatial",
    [
        SpatialInfo(
            wkt="POLYGON((-60.79 -32.86,-60.61 -32.86,-60.61 -33.03,-60.79 -33.03))"
        ),
        SpatialInfo(
            wkt="MULTIPOLYGON(((-60.79 -32.86,-60.61 -32.86)),((-60.61 -33.03)))"
        ),
        SpatialInfo(geojson={"type": "Polygon", "coordinates": [POLYGON_COORDS]}),
        SpatialInfo(
            geojson={"type": "MultiPolygon", "coordinates": [[POLYGON_COORDS]]}
        ),
    ],
    ids=["wkt_polygon", "wkt_multipolygon", "geojson_polygon", "geojson_multipolygon"],
)
def test_bbox_from_geometry(spatial):
    assert _bbox(spatial) == ("-60.79", "-60.61", "-32.86", "-33.03")


def test_bbox_from_geojson_point():
    spatial = SpatialInfo(geojson={"type": "Point", "coordinates": [-60.7, -32.9]})
    assert _bbox(spatial) == ("-60.7", "-60.7", "-32.9", "-32.9")


def test_geojson_takes_precedence_over_wkt():
    spatial = SpatialInfo(
        wkt="POINT(0 0)",
        geojson={"type": "Point", "coordinates": [-60.7, -32.9]},
    )
    assert spatial.west_longitude == "-60.7"


def test_explicit_bbox_is_not_overwritten():
    spatial = SpatialInfo(
        wkt="POINT(0 0)",
        west_longitude="1",
        east_longitude="2",
        north_latitude="3",
        south_latitude="4",
    )
    assert _bbox(spatial) == ("1", "2", "3", "4")


def test_without_geometry_bbox_is_empty():
    assert _bbox(SpatialInfo()) == (None, None, None, None)
