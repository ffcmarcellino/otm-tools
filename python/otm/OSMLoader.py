from . import osm_query
from lxml import etree

road_param_types = {
    'residential':      {'id': 0, 'capacity': 2000, 'speed': 100, 'jam_density': 100},
    'tertiary':         {'id': 1, 'capacity': 2001, 'speed': 101, 'jam_density': 101},
    'tertiary_link':    {'id': 2, 'capacity': 2002, 'speed': 102, 'jam_density': 102},
    'unclassified':     {'id': 3, 'capacity': 2003, 'speed': 103, 'jam_density': 103},
    'secondary':        {'id': 4, 'capacity': 2004, 'speed': 104, 'jam_density': 104},
}

class OSMLoader:

    def __init__(self, cfg=''):
        self.config_file = cfg
        self.scenario = {}
        self.model = {'name':''}

    def load_from_osm(self,west=-122.2981,north=37.8790,east=-122.2547,south=37.8594,exclude_tertiary=True,fixes={}):
        self.scenario = osm_query.load_from_osm(west=west,north=north,east=east,south=south,exclude_tertiary=exclude_tertiary,fixes=fixes)

    def join_links_shorter_than(self, min_length_meters):

        while True:

            # find a candidate link
            short_links = [link for (linkid, link) in self.scenario['links'].items() if
                           link['length'] < min_length_meters and
                           ( len(self.scenario['nodes'][link['start_node_id']]['in_links']) == 1 or
                           len(self.scenario['nodes'][link['end_node_id']]['out_links']) == 1)]

            if len(short_links) == 0:
                break

            foundone = False
            for short_link in short_links:

                start_node = self.scenario['nodes'][short_link['start_node_id']]
                end_node = self.scenario['nodes'][short_link['end_node_id']]

                # check the upstream link
                if len(start_node['in_links']) == 1 and len(start_node['out_links']) == 1:
                    merge_link = self.scenario['links'][next(iter(start_node['in_links']))]

                    # merge if they have the same number of lanes
                    merge_ok = merge_link['lanes']==short_link['lanes']

                    if merge_ok:

                        # adjust attributes of the upstream (merge) link
                        merge_link['length'] = merge_link['length'] + short_link['length']
                        merge_link['end_node_id'] = short_link['end_node_id']
                        merge_link['nodes'] = merge_link['nodes'] + short_link['nodes'][1:]

                        # delete the short link
                        self.__delete_link(short_link['id'])

                        # add upstream (merge) link to end node
                        end_node['in_links'].add(merge_link['id'])

                        # clear inputs and outputs of start node
                        start_node['in_links'] = set()
                        start_node['out_links'] = set()

                        # start node goes from external to internal
                        if start_node['id'] in self.scenario['external_nodes']:
                            self.scenario['external_nodes'].remove(start_node['id'])
                        self.scenario['internal_nodes'].add(start_node['id'])

                        foundone = True
                        break

                # check the downstream link
                if len(end_node['in_links']) == 1 and len(end_node['out_links']) == 1:
                    merge_link = self.scenario['links'][next(iter(end_node['out_links']))]

                    # merge if they have the same number of lanes
                    merge_ok = merge_link['lanes']==short_link['lanes']

                    if merge_ok:

                        # adjust attributes of the downstream (merge) link
                        merge_link['length'] = merge_link['length'] + short_link['length']
                        merge_link['start_node_id'] = short_link['start_node_id']
                        merge_link['nodes'] = short_link['nodes'] + merge_link['nodes'][1:]

                        # delete the short link
                        self.__delete_link(short_link['id'])

                        # add downstream (merge) link to end node
                        start_node['out_links'].add(merge_link['id'])

                        # clear inputs and outputs of end node
                        end_node['in_links'] = set()
                        end_node['out_links'] = set()

                        # end node goes from external to internal
                        if end_node['id'] in self.scenario['external_nodes']:
                            self.scenario['external_nodes'].remove(end_node['id'])
                        self.scenario['internal_nodes'].add(end_node['id'])

                        foundone = True
                        break

            # if you go through all short_links and find nothing, then quit
            if not foundone:
                break

        print(len(self.scenario['links']))

    # model is a dictionary with minimal structure {'type':TYPE
    # Here TYPE can be one of these strings: 'ctm','spaceq','micro','none'
    # If it is ctm or micro, then model must also include an entry 'sim_dt' with the simulation time step in seconds (as a string).
    def set_model(self,model):
        self.model = {'type':model['type'],'name':'default','is_default':'true'}
        if(model['type']=='ctm' or model['type']=='micro'):
            self.model['sim_dt']=model['sim_dt']

        if(model['type']=='ctm'):
            self.model['sim_dt']=model['sim_dt']
            self.model['max_cell_length']=model['max_cell_length']

        if(model['type']=='mciro'):
            self.model['sim_dt']=model['sim_dt']

    def set_demands_per_commodity_and_source_vph(self,demand):
        self.scenario['demand_per_commodity_source'] = demand

    def __delete_link(self,link_id):

        link = self.scenario['links'][link_id]

        # remove link from start node
        node = self.scenario['nodes'][link['start_node_id']]
        if link_id in node['out_links']:
            node['out_links'].remove(link_id)

        # remove link from end node
        node = self.scenario['nodes'][link['end_node_id']]
        if link_id in node['in_links']:
            node['in_links'].remove(link_id)

        # remove exiting road connections
        self.scenario['road_conns'] = [rc for rc in self.scenario['road_conns'] if rc['in_link']!=link_id and rc['out_link']!=link_id]

        del self.scenario['links'][link_id]

    def save_to_xml(self, outfile):

        scenario=etree.Element('scenario')
        scenario.set('xmlns','opentrafficmodels')
        etree.SubElement(scenario,'commodities')

        # model .......................................
        models = etree.SubElement(scenario, 'models')

        if 'type' not in self.model:
            self.model['type'] = 'spaceq'

        model = etree.SubElement(models,'model',{'type':self.model['type'],'name':'default','is_default':'true'})

        if(self.model['type']=='ctm'):
            model_params = etree.SubElement(model, 'model_params',{'sim_dt':self.model['sim_dt'],'max_cell_length':self.model['max_cell_length']})

        if(self.model['type']=='mciro'):
            model_params = etree.SubElement(model, 'model_params',{'sim_dt':self.model['sim_dt']})

        # vehicle types ............................
        commodities = next(scenario.iter('commodities'))
        etree.SubElement(commodities, 'commodity', {'id': '0', 'name': 'type0', 'pathfull': 'false'})

        # network ..................................
        network = etree.SubElement(scenario, 'network')

        # road params ..............................
        road_params = etree.SubElement(network, 'roadparams')
        for road_type_name,road_type_params in road_param_types.items():
            etree.SubElement(road_params, 'roadparam', {
                'id': str(road_type_params['id']),
                'name': road_type_name,
                'capacity': str(road_type_params['capacity']),
                'speed': str(road_type_params['speed']),
                'jam_density': str(road_type_params['jam_density'])
            })

        # get all node positions ......................
        node_set = etree.SubElement(network, 'nodes', {'gps_or_meters': 'gps'})
        node_id = 0
        for node_osmid in self.scenario['external_nodes']:
            node = self.scenario['nodes'][node_osmid]
            # node_id_map[node['id']]=node_osmid
            etree.SubElement(node_set, 'node', {
                'id': str(node_osmid),
                'x': '{:f}'.format(node['x']),
                'y': '{:f}'.format(node['y'])
            })
            node_id += 1

        # link_id_map = {}
        link_set = etree.SubElement(network, 'links')
        # link_id = 0
        for link_osmid, link in self.scenario['links'].items():
            # link_id_map[str(link['id'])] = link_id

            if link['start_node_id'] not in self.scenario['nodes'].keys():
                print('ERROR: link[start_node_id] not in nodes.keys()')

            if link['end_node_id'] not in self.scenario['nodes'].keys():
                print('ERROR: link[end_node_id] not in nodes.keys()')

            elink=etree.SubElement(link_set, 'link', {
                'id': str(link_osmid),
                'length': '{:.2f}'.format(link['length']),  # WHAT UNITS IS THIS IN?
                'full_lanes': str(max(1,link['lanes'])),  # HOW TO GET THE LANES?
                'start_node_id': str(link['start_node_id']),
                'end_node_id': str(link['end_node_id']),
                'roadparam': str(link['roadparam'])
            })
            # link_id += 1

            epoints = etree.SubElement(elink,'points')
            for node_id in link['nodes']:
                node= self.scenario['nodes'][node_id]
                etree.SubElement(epoints, 'point', {
                    'x': '{:f}'.format(node['x']),
                    'y': '{:f}'.format(node['y'])
                })

        # road connections ....................................
        rc_id = 0
        roadconnections = etree.SubElement(network, 'roadconnections')
        links_with_rcs = set()

        for road_conn in self.scenario['road_conns']:
            rc=etree.SubElement(roadconnections, 'roadconnection', {
                'id': str(rc_id),
                'in_link': str(road_conn['in_link']),
                'out_link': str(road_conn['out_link']),
            })
            links_with_rcs.add(road_conn['in_link'])
            if 'in_link_lanes' in road_conn:
                rc['in_link_lanes'] = '{}#{}'.format(min(road_conn['in_link_lanes']), max(road_conn['in_link_lanes']))
            if 'out_link_lanes' in road_conn:
                rc['out_link_lanes'] = '{}#{}'.format(min(road_conn['out_link_lanes']), max(road_conn['out_link_lanes']))
            rc_id += 1

        # actuators .............................
        actuators = etree.SubElement(scenario, 'actuators')

        actuator_id = 0
        for node in self.scenario['nodes'].values():

            if node['type']=='traffic_signals':

                if node['id'] not in self.scenario['external_nodes']:
                    print("Skipping traffic signal on internal node ", node['id'], " (consider splitting the link)")
                    continue

                in_links = [self.scenario['links'][link_id] for link_id in node['in_links']]
                road_conns = [road_conn for road_conn in self.scenario['road_conns'] if road_conn['in_link'] in node['in_links']]

                ### FIGURE OUT PHASES / ROAD CONNECTIONS

                actuator=etree.SubElement(actuators,'actuator',{'id':str(actuator_id),'type':'signal'})
                etree.SubElement(actuator,'actuator_target',{'type':'node','id':str(node['id'])})
                signal = etree.SubElement(actuator,'signal')

            if node['type']=='stop':

                if node['id'] not in self.scenario['external_nodes']:
                    print("Skipping stop sign on internal node ", node['id'], " (consider splitting the link)")
                    continue

                actuator=etree.SubElement(actuators,'actuator',{'id':str(actuator_id),'type':'stop'})
                etree.SubElement(actuator,'actuator_target',{'type':'node','id':str(node['id'])})


            actuator_id += 1

        # # SUBNETWORK DATA
        # subnetworks = SubElement(scenario, 'subnetworks')
        # # zip all edge ids to their respective subnetwork ids
        # subnet_pairs = [(graph.edges[edge]['link_id'], graph.edges[edge]['subnetwork_id']) for edge in graph.edges]
        # distinct_subnets = set(list(zip(*subnet_pairs))[1])
        #
        # for subnet_id in distinct_subnets:
        #     subnet_links = sorted([i[0] for i in subnet_pairs if i[1] == subnet_id])
        #     subnetwork = SubElement(subnetworks, 'subnetwork', {'id': str(subnet_id)})
        #     subnetwork.text = ','.join([str(i) for i in subnet_links])
        #

        # DEMANDS
        if 'demand_per_commodity_source' in self.scenario:
            demands = etree.SubElement(scenario, 'demands')
            for link in self.scenario['links'].values():
                start_node = self.scenario['nodes'][link['start_node_id']]
                end_node = self.scenario['nodes'][link['end_node_id']]
                if len(start_node['in_links'])==0 and len(end_node['out_links'])>0:
                    demand = etree.SubElement(demands, 'demand',{'link_id':str(link['id']),'commodity_id':'0'})
                    demand.text = str(self.scenario['demand_per_commodity_source'])

        # SPLITS
        if 'demand_per_commodity_source' in self.scenario:

            splits = etree.SubElement(scenario, 'splits')
            for node in self.scenario['nodes'].values():

                for in_link in node['in_links']:
                    rcs = [rc for rc in self.scenario['road_conns'] if rc['in_link']==in_link]

                    if len(rcs)==0:
                        reachable_links = node['out_links']
                    else:
                        reachable_links = [rc['out_link'] for rc in rcs]

                    if len(reachable_links)==0:
                        continue

                    split_node = etree.SubElement(splits, 'split_node',
                                                  {'commodity_id': '0', 'node_id': str(node['id']),
                                                   'link_in': str(in_link)})

                    for out_link in reachable_links:
                        split = etree.SubElement(split_node, 'split', {'link_out': str(out_link)})
                        split.text = str(1 / len(reachable_links))

        with open(outfile, 'wb') as xml_file:
            xml_file.write(etree.tostring(scenario, pretty_print=True))

