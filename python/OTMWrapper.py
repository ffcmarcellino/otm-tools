from otm.JavaConnect import JavaConnect
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import matplotlib.colors as pltc
from random import sample
import pandas as pd
import networkx as nx


class OTMWrapper:

    def __init__(self, configfile, jaxb_only=False):

        self.configfile = configfile
        self.sim_output = None
        self.start_time = None
        self.duration = None

        self.conn = JavaConnect()
        if self.conn.pid is not None:
            self.otm = self.conn.gateway.get()
            self.otm.load(configfile, True, jaxb_only)

    def __del__(self):
        if self.conn is not None:
            self.conn.close()

    def show_network(self, linewidth=1):

        fig, ax = plt.subplots()

        nodes = {}
        for node_id in self.otm.scenario().get_node_ids():
            node_info = self.otm.scenario().get_node_with_id(node_id)
            nodes[node_id] = {'x': node_info.getX(), 'y': node_info.getY()}

        lines = []
        minX = float('Inf')
        maxX = -float('Inf')
        minY = float('Inf')
        maxY = -float('Inf')
        for link_id in self.otm.scenario().get_link_ids():
            link_info = self.otm.scenario().get_link_with_id(link_id)

            start_point = nodes[link_info.getStart_node_id()]
            end_point = nodes[link_info.getEnd_node_id()]

            p0 = (start_point['x'], start_point['y'])
            p1 = (end_point['x'], end_point['y'])
            lines.append([p0, p1])

            minX = min([minX, p0[0], p1[0]])
            maxX = max([maxX, p0[0], p1[0]])
            minY = min([minY, p0[1], p1[1]])
            maxY = max([maxY, p0[1], p1[1]])

        all_colors = [k for k, v in pltc.cnames.items()]
        colors = sample(all_colors, len(lines))
        lc = LineCollection(lines, colors=colors)
        lc.set_linewidths(linewidth)
        ax.add_collection(lc)

        dY = maxY - minY
        dX = maxX - minX

        if (dY > dX):
            ax.set_ylim((minY, maxY))
            c = (maxX + minX) / 2
            ax.set_xlim((c - dY / 2, c + dY / 2))
        else:
            ax.set_xlim((minX, maxX))
            c = (maxY + minY) / 2
            ax.set_ylim((c - dX / 2, c + dX / 2))

        plt.draw()

    # run a simulation
    def run_simple(self, start_time=0., duration=3600., output_dt=30.):

        self.start_time = float(start_time)
        self.duration = float(duration)

        self.otm.output().clear()
        link_ids = self.otm.scenario().get_link_ids()
        self.otm.output().request_links_flow(None, link_ids, float(output_dt))
        self.otm.output().request_links_veh(None, link_ids, float(output_dt))

        # run the simulation
        self.otm.run(self.start_time, self.duration)

    def initialize(self, start_time=0):
        self.otm.initialize(start_time)

    def advance(self, duration):
        self.otm.advance(duration)

    def get_links_table(self):

        link_ids = []
        link_lengths = []
        link_lanes = []
        link_start = []
        link_end = []
        link_is_source = []
        link_is_sink = []
        link_capacity = []
        link_ffspeed = []
        link_jamdensity = []
        link_travel_time = []
        for link_id in self.otm.scenario().get_link_ids():
            link = self.otm.scenario().get_link_with_id(link_id)
            link_ids.append(link_id)
            link_lengths.append(link.getFull_length())
            link_lanes.append(link.getFull_lanes())
            link_start.append(link.getStart_node_id())
            link_end.append(link.getEnd_node_id())
            link_is_source.append(link.isIs_source())
            link_is_sink.append(link.isIs_sink())
            link_capacity.append(link.get_capacity_vphpl())
            link_ffspeed.append(link.get_ffspeed_kph())
            link_jamdensity.append(link.get_jam_density_vpkpl())
            link_travel_time.append(link.getFull_length() * 3.6 / link.get_ffspeed_kph())

        return pd.DataFrame(data={'id': link_ids,'length_meter': link_lengths,'lanes': link_lanes,'start_node': link_start,'end_node': link_end,'is_source': link_is_source,'is_sink': link_is_sink,'capacity_vphpl': link_capacity,'speed_kph': link_ffspeed,'max_vpl': link_jamdensity,'travel_time_sec': link_travel_time})

    def to_networkx(self):
        G = nx.MultiDiGraph()
        for node_id in self.otm.scenario().get_node_ids():
            node = self.otm.scenario().get_node_with_id(node_id)
            G.add_node(node_id, pos=(node.getX(), node.getY()))
        for link_id in self.otm.scenario().get_link_ids():
            link = self.otm.scenario().get_link_with_id(link_id)
            G.add_edge(link.getStart_node_id(),link.getEnd_node_id(), id=link_id)
        return G

    def get_state_trajectory(self):
        X = {'time': None, 'link_ids': None, 'vehs': None, 'flows_vph': None, 'speed_kph': None}
        output_data = self.otm.output().get_data()
        it = output_data.iterator()
        while (it.hasNext()):

            output = it.next()

            # collect common link ids
            if X['link_ids'] is None:
                link_list = list(output.get_link_ids())
                X['link_ids'] = np.array(link_list)
            else:
                if not np.array_equal(X['link_ids'], np.array(list(output.get_link_ids()))):
                    raise ValueError('incompatible output requests')

            # collect common time vector
            if X['time'] is None:
                X['time'] = np.array(list(output.get_time()))
            else:
                if not np.array_equal(X['time'], np.array(list(output.get_time()))):
                    raise ValueError('incompatible output requests')

        # initialize outputs
        num_time = len(X['time'])
        num_links = len(X['link_ids'])

        X['vehs'] = np.empty([num_links, num_time])
        X['flows_vph'] = np.empty([num_links, num_time])

        it = output_data.iterator()
        while (it.hasNext()):
            output = it.next()

            for i in range(len(link_list)):
                z = output.get_profile_for_linkid(link_list[i])
                classname = output.getClass().getSimpleName()
                if (classname == "LinkFlow"):
                    X['flows_vph'][i, 0:-1] = np.diff(np.array(list(z.get_values()))) * 3600.0 / z.get_dt()
                if (classname == "LinkVehicles"):
                    X['vehs'][i, :] = np.array(list(z.get_values()))

        X['speed_kph'] = np.empty([num_links, num_time])
        for i in range(len(link_list)):
            link_info = self.otm.scenario().get_link_with_id(link_list[i])
            if link_info.isIs_source():
                X['speed_kph'][i, :] = np.nan;
            else:
                ffspeed_kph = link_info.get_ffspeed_kph()
                link_length_km = link_info.getFull_length() / 1000.0;

                with np.errstate(divide='ignore', invalid='ignore'):
                    speed_kph = np.nan_to_num(link_length_km * np.divide(X['flows_vph'][i], X['vehs'][i]));
                speed_kph[speed_kph > ffspeed_kph] = ffspeed_kph;
                X['speed_kph'][i] = speed_kph;

        return X
