from otm.OSMLoader import OSMLoader
import pickle

osmtool = OSMLoader()
osmtool.load_from_osm(
    north=25.9841,
    south=25.1923,
    east=-80.1107,
    west=-80.8593,
    fixes={
    }
)

osmtool.save_to_xml('miami.xml')
