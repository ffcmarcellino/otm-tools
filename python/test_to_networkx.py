import os
import inspect
from OTMWrapper import OTMWrapper
import networkx as nx
import matplotlib.pyplot as plt
import random
import csv
import numpy as np
import pickle
import matplotlib.animation as animation

# # define the input file
# this_folder = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
# root_folder = os.path.dirname(this_folder)
# # configfile = os.path.join(root_folder, 'configs', 'berkeley.xml')
# configfile = '/home/gomes/Desktop/miami/2/var_dem_miami_cfg_0.xml'
#
# # open the api
# otm = OTMWrapper(configfile)
#
# # convert to networkx and plot
# G = otm.to_networkx()
#
# # nx.draw(G, nx.get_node_attributes(G, 'pos'), node_size=0, width=2)
# # plt.show()
#
# prefix = '/home/gomes/Desktop/miami/2/test_10_g_'
# qty = 'link_veh'
#
# # read link ids
# with open(f'{prefix}{qty}_links.txt') as file:
#     reader = csv.reader(file,delimiter ='\t')
#     row = next(reader)
#     link_ids = [int(i.strip()) for i in row if len(i) > 0]
#
# # read vehicle matrix
# vehs = []
# with open(f'{prefix}{qty}.txt') as file:
#     reader = csv.reader(file)
#     for row in reader:
#         vehs.append([float(i) for i in row])
#
# # read time
# times = []
# with open(f'{prefix}{qty}_time.txt') as file:
#     reader = csv.reader(file)
#     for row in reader:
#         times.append(float(row[0]))
#
# with open('/home/gomes/Desktop/miami/2/data', 'wb') as f:
#     pickle.dump([link_ids, vehs, times, G], f)

with open('/home/gomes/Desktop/miami/2/data', 'rb') as f:
    link_ids, vehs, times, G = pickle.load(f)

# TIME SERIES #####################################

# # compute TVH
# vht = [sum(v) for v in vehs]
# plt.plot(times, vht)
# plt.show()

# PLOT ON GRAPH ######################################
id2edge = {}
for e in G.edges(data='id'):
    id2edge[e[2]] = e
edges = []
for link_id in link_ids:
    edges.append(id2edge[link_id])


def animate(t, G, vehs):
    nx.draw(G, nx.get_node_attributes(G, 'pos'), node_size=0, width=1, with_labels=False, edgelist=edges, edge_color=vehs[t])



# First set up the figure, the axis, and the plot element we want to animate
fig = plt.gcf()
axes = plt.gca()

anim = animation.FuncAnimation(fig, animate, frames=20, fargs=(G, vehs))
# anim.save('animation_1.gif', writer='imagemagick')

plt.show()


# always end by deleting the wrapper
# del otm