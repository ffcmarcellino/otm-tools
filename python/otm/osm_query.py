import math
import time
import numpy as np
import geopandas as gpd
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
import requests
from statistics import mean

MilesToKilometers = 1.609344

default_lanes_each_direction = {
    'residential': 1,
    'tertiary': 1,
    'secondary': 1,
    'primary': 1,
    'unclassified': 1,
    'trunk' : 1,
    'motorway_link':1,
    'secondary_link':1,
    'trunk_link':1,
    'tertiary_link':1,
    'motorway':1,
    'primary_link':1,
    'road':1,
    'disused':1,
    'planned':1,
    'slide':1
}

# OSM QUERY ---------------------------------
def __overpass_request(data, timeout=180):
    url = 'http://overpass-api.de/api/interpreter'
    headers = {'User-Agent': 'Open Traffic Models (https://github.com/ggomes/otm-sim)', 'Accept-Encoding': 'gzip, deflate', 'Accept': '*/*', 'Connection': 'keep-alive', 'referer': 'Open Traffic Models (https://github.com/ggomes/otm-sim)', 'Accept-Language': 'en'}
    response = requests.post(url, data=data, timeout=timeout, headers=headers)
    response_json = response.json()
    return response_json

def __query_json(west=-122.2981,north=37.8790,east=-122.2547,south=37.8594,exclude_tertiary=True):

    infrastructure = 'way["highway"]'
    timeout = 180
    osm_filter = '["area"!~"yes"]["motor_vehicle"!~"no"]["motorcar"!~"no"]["access"!~"private"]["service"!~"parking|parking_aisle|driveway|private|emergency_access"]'

    if exclude_tertiary:
        osm_filter = osm_filter + '["highway"!~"footway|bridleway|steps|path|living_street|service|pedestrian|track|bus_guideway|escape|raceway|cycleway|proposed|construction|bus_stop|crossing|elevator|emergency_access_point|give_way|mini_roundabout|motorway_junction|passing_place|rest_area|speed_camera|street_lamp|services|corridor|abandoned|platform|tertiary|unclassified|residential|tertiary_link"]'
    else:
        osm_filter = osm_filter + '["highway"!~"footway|bridleway|steps|path|living_street|service|pedestrian|track|bus_guideway|escape|raceway|cycleway|proposed|construction|bus_stop|crossing|elevator|emergency_access_point|give_way|mini_roundabout|motorway_junction|passing_place|rest_area|speed_camera|street_lamp|services|corridor|abandoned|platform"]'

    maxsize = ''

    # turn bbox into a polygon and project to local UTM
    polygon = Polygon([(west, south), (east, south), (east, north), (west, north)])
    geometry, crs_proj = __project_geometry(polygon)

    if isinstance(geometry, Polygon):
        geometry_proj_consolidated_subdivided = MultiPolygon([geometry])

    geometry, _ = __project_geometry(geometry_proj_consolidated_subdivided, crs=crs_proj, to_latlong=True)

    response_jsons = []

    for poly in geometry:

        west, south, east, north = poly.bounds
        query_template = '[out:json][timeout:{timeout}]{maxsize};({infrastructure}{filters}({south:.6f},{west:.6f},{north:.6f},{east:.6f});>;);out;'
        query_str = query_template.format(north=north, south=south,
                                          east=east, west=west,
                                          infrastructure=infrastructure,
                                          filters=osm_filter,
                                          timeout=timeout, maxsize=maxsize)
        response_json = __overpass_request(data={'data': query_str}, timeout=timeout)
        response_jsons.append(response_json)

    return response_jsons

def __project_geometry(geometry, crs=None, to_crs=None, to_latlong=False):
    """
    Project a shapely Polygon or MultiPolygon from lat-long to UTM, or
    vice-versa

    Parameters
    ----------
    geometry : shapely Polygon or MultiPolygon
        the geometry to project
    crs : dict
        the starting coordinate reference system of the passed-in geometry,
        default value (None) will set settings.default_crs as the CRS
    to_crs : dict
        if not None, just project to this CRS instead of to UTM
    to_latlong : bool
        if True, project from crs to lat-long, if False, project from crs to
        local UTM zone

    Returns
    -------
    tuple
        (geometry_proj, crs), the projected shapely geometry and the crs of the
        projected geometry
    """
    default_crs = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    if crs is None:
        crs = default_crs

    gdf = gpd.GeoDataFrame()
    gdf.crs = crs
    gdf.gdf_name = 'geometry to project'
    gdf['geometry'] = None
    gdf.loc[0, 'geometry'] = geometry
    gdf_proj = __project_gdf(gdf, to_crs=to_crs, to_latlong=to_latlong)
    geometry_proj = gdf_proj['geometry'].iloc[0]
    return geometry_proj, gdf_proj.crs

def __project_gdf(gdf, to_crs=None, to_latlong=False):
    """
    Project a GeoDataFrame to the UTM zone appropriate for its geometries'
    centroid.

    The simple calculation in this function works well for most latitudes, but
    won't work for some far northern locations like Svalbard and parts of far
    northern Norway.

    Parameters
    ----------
    gdf : GeoDataFrame
        the gdf to be projected
    to_crs : dict
        if not None, just project to this CRS instead of to UTM
    to_latlong : bool
        if True, projects to latlong instead of to UTM

    Returns
    -------
    GeoDataFrame
    """

    default_crs = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    assert len(gdf) > 0, 'You cannot project an empty GeoDataFrame.'
    start_time = time.time()

    # if gdf has no gdf_name attribute, create one now
    if not hasattr(gdf, 'gdf_name'):
        gdf.gdf_name = 'unnamed'

    # if to_crs was passed-in, use this value to project the gdf
    if to_crs is not None:
        projected_gdf = gdf.to_crs(to_crs)

    # if to_crs was not passed-in, calculate the centroid of the geometry to
    # determine UTM zone
    else:
        if to_latlong:
            # if to_latlong is True, project the gdf to latlong
            latlong_crs = default_crs
            projected_gdf = gdf.to_crs(latlong_crs)
            # log('Projected the GeoDataFrame "{}" to default_crs in {:,.2f} seconds'.format(gdf.gdf_name, time.time()-start_time))
        else:
            # else, project the gdf to UTM
            # if GeoDataFrame is already in UTM, just return it
            if (gdf.crs is not None) and ('+proj=utm ' in gdf.crs):
                return gdf

            # calculate the centroid of the union of all the geometries in the
            # GeoDataFrame
            avg_longitude = gdf['geometry'].unary_union.centroid.x

            # calculate the UTM zone from this avg longitude and define the UTM
            # CRS to project
            utm_zone = int(math.floor((avg_longitude + 180) / 6.) + 1)
            utm_crs = '+proj=utm +zone={} +ellps=WGS84 +datum=WGS84 +units=m +no_defs'.format(utm_zone)

            # project the GeoDataFrame to the UTM CRS
            projected_gdf = gdf.to_crs(utm_crs)
            # log('Projected the GeoDataFrame "{}" to UTM-{} in {:,.2f} seconds'.format(gdf.gdf_name, utm_zone, time.time()-start_time))

    projected_gdf.gdf_name = gdf.gdf_name
    return projected_gdf

# PARSE JSONS ---------------------------------

def __parse_jsons(jsons,fixes):
    global max_link_id
    global max_node_id

    # make sure we got data back from the server requests
    elements = []
    for json in jsons:
        elements.extend(json['elements'])

    # extract nodes and paths from the downloaded osm data
    print('\t> extracting nodes and paths')
    links = {}
    nodes = {}
    for element in elements:

        if element['type'] == 'way':
            link = __read_way(element,fixes)
            links[link['id']] = link

        elif element['type'] == 'node':
            node = __read_node(element)
            nodes[node['id']] = node

        else:
            print('[ERROR] Unknown element type.')

    max_link_id = max([x for x in links.keys()])+1
    max_node_id = max([x for x in nodes.keys()])+1

    # set in and out links
    print('\t> setting in and out links')
    for link  in links.values():
        nodes[link['start_node_id']]['out_links'].add(link['id'])
        nodes[link['end_node_id']]['in_links'].add(link['id'])

    return links, nodes

def __read_way(element,fixes):
    # OSM tags considered:
    #     'name'
    #     'highway',
    #     'junction',
    #     'lanes',
    #     'lanes:forward',
    #     'lanes:backward',
    #     'lanes:both_ways',
    #     'turn',
    #     'turn:forward',
    #     'turn:backward',
    #     'turn:both_ways',
    #     'turn:lanes',
    #     'turn:lanes:forward',
    #     'turn:lanes:backward',
    #     'turn:lanes:both_ways',
    #     'maxspeed',
    #     'name',
    #     'oneway'

    if 'tags' not in element:
        print("[ERROR] OSM returned a tag-less link.")
        return None

    tags = element['tags']

    # apply fixes ..................................................
    if element['id'] in fixes:
        for fix in fixes[element['id']]:
            if fix[1]==None and fix[0] in element['tags']:
                del element['tags'][fix[0]]
            else:
                element['tags'][fix[0]] = fix[1]


    nodes = element['nodes']
    link = {
        'id': element['id'],
        'length': 0,
        'start_node_id': nodes[0],
        'end_node_id': nodes[-1],
        'roadparam': 0,
        'nodes': nodes
    }

    # name ..................
    if 'name' in tags:
        link['name'] = tags['name']
    else:
        link['name'] = ''

    # highway ..................
    if 'highway' in tags:
        link['highway'] = tags['highway']
    else:
        link['highway'] = 'default_highway'

    # junction
    if 'junction' in tags:
        link['junction'] = tags['junction']
    else:
        link['junction'] = 'none'

    # oneway ..................
    if 'oneway' in tags:
        if tags['oneway'] == 'yes':
            link['flip'] = False
            link['bidirectional'] = False

        if tags['oneway'] == 'no':
            link['flip'] = False
            link['bidirectional'] = True

        if tags['oneway'] == '-1':
            link['flip'] = True
            link['bidirectional'] = False
    else:
        link['flip'] = False
        if 'lanes:backward' in tags:
            link['bidirectional'] = True
        else:
            link['bidirectional'] = False

    # max speed ..................
    if 'maxspeed' in tags:
        x = tags['maxspeed'].split(" ")

        if len(x)<2:
            link['maxspeed_kph'] = float(x[0])*MilesToKilometers
        else:
            if x[1].lower()=='kph':
                link['maxspeed_kph'] = float(x[0])
            elif x[1].lower()=='mph':
                link['maxspeed_kph'] = float(x[0])*MilesToKilometers
            else:
                print("[ERROR] Unknown units.")
    else:
        link['maxspeed_kph'] = 50

    # lanes, lanes_backward ..........................
    if link['bidirectional']:

        # (T,T,T),(F,T,T)
        if 'lanes:forward' in tags and 'lanes:backward' in tags:
            link['lanes'] = int(tags['lanes:forward'])
            link['lanes_backward'] = int(tags['lanes:backward'])

        # (T,T,F)
        elif 'lanes' in tags and 'lanes:forward' in tags:
            link['lanes'] = int(tags['lanes:forward'])
            link['lanes_backward'] = int(tags['lanes']) - int(tags['lanes:forward'])

        # (T,F,T)
        elif 'lanes' in tags and 'lanes:backward' in tags:
            link['lanes_backward'] = int(tags['lanes:backward'])
            link['lanes'] = int(tags['lanes']) - int(tags['lanes:backward'])

        # (T,F,F)
        elif 'lanes' in tags:

            # stupid, but see https://wiki.openstreetmap.org/wiki/Key:lanes#Assumptions
            if (int(tags['lanes']) % 2) == 0:
                link['lanes'] = int(int(tags['lanes']) / 2)
            else:
                link['lanes'] = int(tags['lanes'])
            link['lanes_backward'] = link['lanes']

        # (F,T,F)
        elif 'lanes:forward' in tags:
            link['lanes'] = int(tags['lanes:forward'])
            link['lanes_backward'] = link['lanes']

        # (F,F,T)
        elif 'lanes:backward' in tags:
            link['lanes'] = int(tags['lanes:backward'])
            link['lanes_backward'] = link['lanes']

        # (F,F,F)
        else:
            link['lanes'] = np.nan
            link['lanes_backward'] = np.nan

    else:
        link['lanes_backward'] = 0
        if 'lanes' in tags:
            link['lanes'] = int(tags['lanes'])
        elif 'lanes:forward' in tags:
            link['lanes'] = int(tags['lanes:forward'])
        else:
            link['lanes'] = np.nan

    # turns_lanes, turns_lanes_backward ................

    # check no clash in turn, turn:forward, turn:backward, turn:both_ways
    if 'turn' in tags and 'turn:forward' in tags:
        print("[ERROR] Link", link['id'] , "'turn' in tags and 'turn:forward' in tags")

    if 'turn' in tags and 'turn:backward' in tags:
        print("[ERROR] Link", link['id'] , "'turn' in tags and 'turn:backward' in tags")

    if 'turn' in tags and 'turn:both_ways' in tags:
        print("[ERROR] Link", link['id'] , "'turn' in tags and 'turn:both_ways' in tags")

    if 'turn:both_ways' in tags and 'turn:forward' in tags:
        print("[ERROR] Link", link['id'] , "'turn:both_ways' in tags and 'turn:forward' in tags")

    if 'turn:both_ways' in tags and 'turn:backward' in tags:
        print("[ERROR] Link", link['id'] , "'turn:both_ways' in tags and 'turn:backward' in tags")

    # if no clash, copy turn and turn:both_ways to turn:forward and turn:backward
    if 'turn' in tags:
        tags['turn:forward'] = tags['turn']
        tags['turn:backward'] = tags['turn']

    if 'turn:both_ways' in tags:
        tags['turn:forward'] = tags['turn:both_ways']
        tags['turn:backward'] = tags['turn:both_ways']

    # check no clash turn:lanes, turn:lanes:forward, turn:lanes:backward, turn:lanes:both_ways
    if 'turn:lanes' in tags and 'turn:lanes:forward' in tags:
        print("[ERROR] Link", link['id'] , "'turn:lanes' in tags and 'turn:lanes:forward' in tags")

    if 'turn:lanes' in tags and 'turn:lanes:backward' in tags:
        print("[ERROR] Link", link['id'] , "'turn:lanes' in tags and 'turn:lanes:backward' in tags")

    if 'turn:lanes' in tags and 'turn:lanes:both_ways' in tags:
        print("[ERROR] Link", link['id'] , "'turn:lanes' in tags and 'turn:lanes:both_ways' in tags")

    if 'turn:lanes:both_ways' in tags and 'turn:lanes:forward' in tags:
        print("[ERROR] Link", link['id'] , "'turn:lanes:both_ways' in tags and 'turn:lanes:forward' in tags")

    if 'turn:lanes:both_ways' in tags and 'turn:lanes:backward' in tags:
        print("[ERROR] Link", link['id'] , "'turn:lanes:both_ways' in tags and 'turn:lanes:backward' in tags")

    # if no clash, copy turn and turn:lanes:both_ways to turn:lanes:forward and turn:lanes:backward
    if 'turn:lanes' in tags:
        tags['turn:lanes:forward'] = tags['turn:lanes']
        tags['turn:lanes:backward'] = tags['turn:lanes']

    if 'turn:lanes:both_ways' in tags:
        tags['turn:lanes:forward'] = tags['turn:lanes:both_ways']
        tags['turn:lanes:backward'] = tags['turn:lanes:both_ways']

    # check clash turn:lanes:* and turn:*
    if 'turn:lanes:forward' in tags and 'turn:forward' in tags:
        if tags['turn:lanes:forward'] != tags['turn:forward']:
            print("[ERROR] Link", link['id'] , "'turn:lanes:forward' in tags and 'turn:forward' in tags")

    if 'turn:lanes:backward' in tags and 'turn:backward' in tags:
        if tags['turn:lanes:backward'] != tags['turn:backward']:
            print("[ERROR] Link", link['id'] , "'turn:lanes:backward' in tags and 'turn:backward' in tags")

    # copy turn to turn lanes
    if 'turn:forward' in tags:
        if math.isnan(link['lanes']):
            tags['turn:lanes:forward'] = '*'  # undefined
        else:
            tags['turn:lanes:forward'] = "|".join([tags['turn:forward'] for i in range(0,link['lanes'])])

    if 'turn:backward' in tags:
        if math.isnan(link['lanes_backward']):
            tags['turn:lanes:backward'] = '*'  # undefined
        else:
            tags['turn:lanes:backward'] = "|".join([tags['turn:backward'] for i in range(0, link['lanes_backward'])])

    # now all of the information is in tags['turn:lanes:forward'] and tags['turn:lanes:backward']

    # copy to link
    if 'turn:lanes:forward' in tags:
        link['turn_lanes'] = tags['turn:lanes:forward']
    else:
        if math.isnan(link['lanes']):
            link['turn_lanes'] = '*'  # undefined
        else:
            link['turn_lanes'] = '|'*(link['lanes']-1)

    if link['bidirectional'] and 'turn:lanes:backward' in tags:
        link['turn_lanes_backward'] = tags['turn:lanes:backward']
    else:
        if math.isnan(link['lanes_backward']):
            link['turn_lanes_backward'] = '*'  # undefined
        else:
            link['turn_lanes_backward'] = '|'*(link['lanes_backward']-1)

    # resolve undefined number of lanes
    if math.isnan(link['lanes']):
        if link['turn_lanes'] == '*':
            if link['highway'] in default_lanes_each_direction:
                link['lanes'] = default_lanes_each_direction[link['highway']]
            else:
                link['lanes'] = 1
        else:
            link['lanes'] = len(link['turn_lanes'].split('|'))

    if math.isnan(link['lanes_backward']):
        if link['turn_lanes_backward'] == '*':
            if link['highway'] in default_lanes_each_direction:
                link['lanes_backward'] = default_lanes_each_direction[link['highway']]
            else:
                link['lanes_backward'] = 1
        else:
            link['lanes_backward'] = len(link['turn_lanes_backward'].split('|'))


    return link

def __read_node(element):

    node = {}
    node['id'] = element['id']
    node['y'] = element['lat']
    node['x'] = element['lon']
    node['type'] = ''
    node['out_links'] = set()
    node['in_links'] = set()

    if 'tags' not in element:
        return node

    tags = element['tags']

    if 'highway' in tags:
        node['type']=tags['highway']

    return node

def __remove_P_shaped_links(links,nodes):
    p_links = set()
    for link in links.values():
        mynodes = link['nodes']
        if (mynodes[0] in mynodes[1:]) or mynodes[-1] in mynodes[:-1]:
            p_links.add(link['id'])
    for link_id in p_links:
        __delete_link(link_id,links,nodes)

# ROUNDABOUTS ---------------------------------

def __delete_link(link_id,links,nodes):
    if link_id not in links:
        return
    link = links[link_id]
    start_node = nodes[link['start_node_id']]
    start_node['out_links'].remove(link['id'])
    end_node = nodes[link['end_node_id']]
    end_node['in_links'].remove(link['id'])

    del links[link_id]

# SPLIT STREETS AND ELIMINATING NODES ---------------------------------

def __new_node_id():
    global max_node_id
    max_node_id = max_node_id + 1
    return max_node_id

def __new_link_id():
    global max_link_id
    max_link_id = max_link_id + 1
    return max_link_id

def __split_link_at_node( link, node, links, nodes ):
    node_id = node['id']
    loc = link['nodes'].index(node_id)

    # create new link representing the upstream part of the link
    new_link = link.copy()
    new_link['id'] = __new_link_id()
    new_link['nodes']= link['nodes'][:loc+1].copy()
    new_link['end_node_id']= node_id
    new_link['turn_lanes'] = '|'*(link['lanes']-1)
    links[new_link['id']] = new_link

    # fix downstream part of the link
    link['nodes'] = link['nodes'][loc:]
    link['start_node_id']= node_id
    link['turn_lanes_backward'] = '|'*(link['lanes_backward']-1)

    # add to node inlinks and outlinks
    node['in_links'].add(new_link['id'])
    node['out_links'].add(link['id'])

    # fix start node outlinks
    start_node = nodes[new_link['start_node_id']]
    start_node['out_links'].remove(link['id'])
    start_node['out_links'].add(new_link['id'])

def __split_streets(links, nodes):

    # compute internal and external nodes
    print("\t> computing internal and external nodes")
    internal_nodes=set()
    external_nodes=set()
    for link_id,link in links.items():
        my_nodes=link['nodes']
        external_nodes.update([my_nodes[-1],my_nodes[0]])
        internal_nodes.update(my_nodes[1:-1])

    internal_and_external = internal_nodes.intersection(external_nodes)
    internal_signalized = set([node['id'] for node in nodes.values() if
                           (node['id'] in internal_nodes) and
                           (node['type']=='traffic_signals' or node['type']=='stop') ])

    split_nodes = internal_and_external.union(internal_signalized)

    # iterate through nodes that are both internal and external
    print("\t> iterating through", len(split_nodes), "internal && external nodes")
    for node_id in split_nodes:
        node = nodes[node_id]
        # for all links that have this as an internal node
        for link in [link for link in links.values() if node_id in link['nodes'][1:-1]]:
            __split_link_at_node( link, node, links, nodes )

        # move node from internal to external
        internal_nodes.remove(node_id)
        external_nodes.add(node_id)

    return internal_nodes, external_nodes

def __eliminate_simple_external_nodes(links,nodes,internal_nodes, external_nodes):

    external_to_internal_nodes=set()
    for node_id in external_nodes:
        node=nodes[node_id]

        # dont eliminate signalized nodes
        if node['type']=='traffic_signals' or node['type']=='stop':
            continue

        # the two links should be almost identical
        if len(node['out_links'])==1 and len(node['in_links'])==1:
            in_link_id = next(iter(node['in_links']))
            out_link_id = next(iter(node['out_links']))
            in_link=links[in_link_id]
            out_link=links[out_link_id]
            if in_link['lanes']==out_link['lanes'] and\
                    in_link['lanes_backward']==out_link['lanes_backward'] and\
                    in_link['flip']==out_link['flip'] and\
                    in_link['bidirectional']==out_link['bidirectional'] and\
                    in_link['turn_lanes']==out_link['turn_lanes'] and\
                    in_link['turn_lanes_backward']==out_link['turn_lanes_backward'] and\
                    in_link['highway']==out_link['highway']:

                # extend the upstream link
                in_link['nodes'].extend(out_link['nodes'][1:])
                in_link['end_node_id']=in_link['nodes'][-1]

                # delete the downstream link
                del links[out_link_id]

                # transfer the node to internal
                external_to_internal_nodes.add(node_id)

                # update the in_links of the end node
                end_node = nodes[out_link['end_node_id']]
                end_node['in_links'].remove(out_link['id'])
                end_node['in_links'].add(in_link['id'])

    external_nodes.difference_update(external_to_internal_nodes)
    internal_nodes.update(external_to_internal_nodes)

# FLIP AND EXPAND LINKS ---------------------------------

def __flip_wrong_way_links(links):

    flip_links = [link for link in links.values() if link['flip']]

    if len(flip_links)>0:
        print("[WARNING] Flip links are not implemented. Ignoring this tag.")

    # remove flip_links attribute
    for link in links.values():
        del link['flip']

def __expand_bidirectional_links(links, nodes):

    bi_links = [link for link in links.values() if link['bidirectional']]

    for link in bi_links:

        start_node_id = link['start_node_id']
        end_node_id = link['end_node_id']

        existing_backward_links = [link for link in links.values() if link['start_node_id']==end_node_id and link['end_node_id']==start_node_id]
        if len(existing_backward_links)>0:
            print("[WARNING] OSM returned a backwards link. I'm skipping this bi-directional link ", link['id'])
            continue

        backward_link = link.copy()

        backward_link['id'] = __new_link_id()
        backward_link['start_node_id'] = end_node_id
        backward_link['end_node_id'] = start_node_id
        backward_link['lanes'] = link['lanes_backward']
        backward_link['nodes'] = list(reversed(link['nodes']))
        backward_link['turn_lanes'] = link['turn_lanes_backward']

        # add to links
        links[backward_link['id']] = backward_link

        # add to nodes
        nodes[end_node_id]['out_links'].add(backward_link['id'])
        nodes[start_node_id]['in_links'].add(backward_link['id'])

    # remove backward attributes
    for link in links.values():
        del link['lanes_backward']
        del link['turn_lanes_backward']

# LINK AND NODE LOCATIONS ---------------------------------

def __latlong2meters(lat, lon, clat, clon):
    R = 6378137    # Radius of earth in meters

    lat = lat*math.pi / 180
    lon = lon*math.pi / 180

    clat = clat*math.pi / 180
    clon = clon*math.pi / 180

    dx = math.acos( 1 - math.pow(math.cos(clat), 2) * (1-math.cos(lon-clon)) ) * R
    if lon<clon:
        dx = -dx
    dy = (lat-clat) * R

    return dx, dy

def __compute_lengths(links,nodes):

    node_meters = {}

    centroid = np.mean([[v['x'], v['y']] for v in nodes.values()], axis=0)
    for node_id, node in nodes.items():
        dx, dy = __latlong2meters(node['y'], node['x'], centroid[1], centroid[0])
        node_meters[node_id] = (dx, dy)

    for link in links.values():
        total_length = 0
        for i in range(0,len(link['nodes'])-1):
            a = node_meters[link['nodes'][i]]
            b = node_meters[link['nodes'][i+1]]
            total_length += math.sqrt(math.pow(a[0]-b[0],2)+math.pow(a[1]-b[1],2))
        link['length'] = total_length

# ROAD CONNECTIONS ---------------------------------

def __find_direction(start_node,end_node):
    return math.atan2(end_node['y'] - start_node['y'], end_node['x'] - start_node['x']) * 180 / math.pi

def __create_road_connections(links, nodes):

    all_road_conns = []

    for link in links.values():

        road_conns = []

        # get next links
        end_node = nodes[link['end_node_id']]
        next_links = [link for link in links.values() if link['id'] in end_node['out_links']]

        # ignore U turns
        next_links = [x for x in next_links if x['end_node_id']!=link['start_node_id']]

        # not needed when there are no turning options
        if len(next_links)<2:
            continue

        # trivial case
        if link['lanes']==1:
            for next_link in next_links:
                road_conns.append({ 'in_link': link['id'] ,
                                    'in_lanes' : [] ,
                                    'out_link' : next_link['id'] ,
                                    'out_lanes' : [] ,
                                    'direction' : 'through' })
            continue

        # compute angles
        d_in = __find_direction(nodes[link['nodes'][-2]],nodes[link['nodes'][-1]])

        relative_angle = []
        for next_link in next_links:
            from_node = nodes[next_link['nodes'][0]]
            to_node = nodes[next_link['nodes'][1]]
            d_out = __find_direction(from_node, to_node)
            relative_angle.append((next_link['id'], d_out-d_in))
        relative_angle = sorted(relative_angle, key=lambda x: x[1])

        # extract all of the turns we have
        turn_lanes = link['turn_lanes'].split('|')
        turn_to_lanes = {}
        for i in range(len(turn_lanes)):
            for t in turn_lanes[i].split(';'):
                if t=='':
                    continue
                if t in turn_to_lanes.keys():
                    turn_to_lanes[t].append(i+1)
                else:
                    turn_to_lanes[t] = [i+1]

        if 'left' in turn_to_lanes:
            road_conns.append({'in_link': link['id'],
                              'in_lanes': turn_to_lanes['left'],
                              'out_link': relative_angle[0][0],
                              'out_lanes': [],
                              'direction' : 'left'})
            next_links.remove(links[relative_angle[0][0]])
            del relative_angle[0]

        if 'right' in turn_to_lanes:
            road_conns.append({'in_link': link['id'],
                               'in_lanes': turn_to_lanes['right'],
                               'out_link': relative_angle[len(relative_angle)-1][0],
                               'out_lanes': [],
                              'direction' : 'right'})
            next_links.remove(links[relative_angle[len(relative_angle)-1][0]])
            del relative_angle[len(relative_angle)-1]


        if ('through' in turn_to_lanes) and len(relative_angle)==1:
            road_conns.append({'in_link': link['id'],
                               'in_lanes': turn_to_lanes['through'],
                               'out_link': relative_angle[0][0],
                               'out_lanes': [],
                              'direction' : 'through'})
            next_links.remove(links[relative_angle[0][0]])
            del relative_angle[0]

        if len(next_links)==0:
            continue

        unmarked_lanes = [i+1 for i in range(len(turn_lanes)) if turn_lanes[i]=='']

        for next_link in next_links:
            road_conns.append({'in_link':link['id'],
                               'in_lanes':unmarked_lanes,
                               'out_link':next_link['id'],
                               'out_lanes':[],
                               'direction' : 'unknown'})

        # check that all lanes are covered
        lanes_covered = set()
        for road_conn in road_conns:
            if len(road_conn['in_lanes'])==0:
                lanes_covered.update( range(1,link['lanes']+1) )
            else:
                lanes_covered.update(set(road_conn['in_lanes']))

        if lanes_covered != set(range(1,link['lanes']+1)):
            print('[WARNING] Link', link['id'], ': Not all lanes have outgoing road connections.')

        # check that all next_links are represented
        to_links = set([road_conn['out_link'] for road_conn in road_conns])
        next_links=set([x['id'] for x in links.values() if x['id'] in end_node['out_links'] and x['end_node_id']!=link['start_node_id']])
        if to_links!=next_links:
            print('[WARNING] Link', link['id'], ': Not all outgoing links are accessible by road connections')

        all_road_conns.extend(road_conns)

    return all_road_conns

################################################

def load_from_osm(west,north,east,south,exclude_tertiary,fixes={}):

    # 1. query osm
    print('> querying osm')
    jsons = __query_json(west, north, east, south, exclude_tertiary)

    # 2. parse osm
    print('> parsing osm')
    links, nodes = __parse_jsons(jsons, fixes)
    print('\t* num nodes =', len(nodes))
    print('\t* num links =', len(links))

    __remove_P_shaped_links(links, nodes)

    # 3. split links when
    #    a) they cross another street at an internal node,
    #    b) they contain an traffic signal at an internal node
    print('> splitting links')
    internal_nodes, external_nodes = __split_streets(links, nodes)

    # 4. eliminate simple external nodes
    print('> eliminating simple external nodes')
    __eliminate_simple_external_nodes(links, nodes, internal_nodes, external_nodes)

    # 5. flip and expand links
    print('> flipping and expand links')
    __flip_wrong_way_links(links)

    __expand_bidirectional_links(links, nodes)

    # 6. link lengths
    print('> computing link lengths')
    __compute_lengths(links, nodes)

    # 7. create road connections
    print('> creating road connections')
    road_conns = __create_road_connections(links, nodes)

    return {'links': links,
            'nodes': nodes,
            'road_conns': road_conns,
            'internal_nodes': internal_nodes,
            'external_nodes': external_nodes}

    # # demands
    # source_links = get_source_links(graph)
    #
    # # pathless demands
    # dt = 300
    # vph = [0, 4, 3, 2, 5]
    # convert.add_pathless_demand(scenario, veh_types[0], source_links[0], dt, vph)
    #
    # # splits
    # split_nodes = convert.get_split_nodes(graph)
    #
    # node_io = convert.get_node_io(split_nodes[0], graph)
    # link_out_to_split_profile = dict
    # convert.add_split(split_nodes[0], veh_types[0], node_io.link_in[0], dt, link_out_to_split_profile)

    # # pathfull demands
    # convert.add_pathfull_demand(scenario,)

    # to_xml(scenario)
    #
    # plot_graph(scenario)
