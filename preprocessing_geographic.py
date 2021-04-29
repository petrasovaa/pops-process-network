#!/usr/bin/env python3

import os
import tempfile
from math import sqrt

import grass.script as gs


os.environ["GRASS_OVERWRITE"] = "1"


def dist(p1, p2):
    p1 = (float(p1[0]), float(p1[1]))
    p2 = (float(p2[0]), float(p2[1]))
    return sqrt((p1[0] - p2[0]) * (p1[0] - p2[0]) + (p1[1] - p2[1]) * (p1[1] - p2[1]))


def main(railroads, distance, out_nodes, out_segments):
    gs.run_command(
        "v.build.polylines",
        input=railroads,
        output=railroads + "_simplified",
        cats="first",
        type="line",
    )
    gs.run_command(
        "v.to.points",
        flags="t",
        input=railroads + "_simplified",
        type="line",
        output=railroads + "_nodes",
        use="node",
    )
    gs.run_command(
        "v.to.rast",
        input=railroads + "_nodes",
        type="point",
        output=railroads + "_nodes",
        use="val",
    )
    nodes_out = gs.read_command(
        "v.out.ascii", input=railroads + "_nodes", format="standard"
    ).strip()
    nodes_by_coor = {}
    nodes_by_id = {}
    segments = {}
    for line in nodes_out.splitlines()[10:]:
        line = line.strip()
        if not (line.startswith("P") or line.startswith("1") or line.startswith("2")):
            x, y = line.split()
            x = str(round(float(x), 8))
            y = str(round(float(y), 8))
        elif line.startswith("1"):
            seg_cat = int(line.split()[-1])
        elif line.startswith("2"):
            node_cat = int(line.split()[-1])
            if (x, y) in nodes_by_coor:
                node_cat = nodes_by_coor[(x, y)]
            else:
                nodes_by_coor[(x, y)] = node_cat
                nodes_by_id[node_cat] = (x, y)
            if seg_cat in segments:
                segments[seg_cat] = (segments[seg_cat][0], node_cat)
            else:
                segments[seg_cat] = (node_cat, None)

    with open(out_nodes, "w") as fout:
        for key in nodes_by_coor:
            fout.write(f"{nodes_by_coor[key]},{key[0]},{key[1]}\n")

    gs.run_command(
        "v.to.points",
        flags="it",
        input=railroads + "_simplified",
        type="line",
        output=railroads + "_vertices",
        use="vertex",
        dmax=distance,
    )
    vertices_out = gs.read_command(
        "v.out.ascii", input=railroads + "_vertices", format="standard"
    ).strip()
    #   P  1 2
    #   -81.96177273 37.54741428
    #   1     37566
    #   2     106743
    vertices = {}
    old = None
    test_last = None
    for line in vertices_out.splitlines()[10:]:
        line = line.strip()
        if not (line.startswith("P") or line.startswith("1") or line.startswith("2")):
            x, y = line.split()
            x = str(round(float(x), 8))
            y = str(round(float(y), 8))
        elif line.startswith("1"):
            seg_cat = int(line.split()[-1])
            if seg_cat not in vertices.keys():
                old = None
                vertices[seg_cat] = []
            if old:
                if dist(old, (x, y)) < distance / 2:
                    test_last = (seg_cat, x, y)
                    continue
            else:
                if test_last:
                    vertices[test_last[0]].append((test_last[1], test_last[2]))
                    test_last = None
            vertices[seg_cat].append((x, y))
            old = (x, y)

    with open(out_segments, "w") as fout:
        for segment in segments:
            i = 0
            fout.write(f"{segments[segment][0]},{segments[segment][1]},")
            for vertex in vertices[segment]:
                if i != 0:
                    fout.write(f";{vertex[0]};{vertex[1]}")
                else:
                    fout.write(f"{vertex[0]};{vertex[1]}")
                i += 1
            fout.write("\n")


def parse(nodes_file, seg_file):
    with open(nodes_file, "r") as fin, tempfile.NamedTemporaryFile(
        mode="w", delete=False
    ) as temp:
        name = temp.name
        for line in fin:
            node, x, y = line.split(",")
            temp.write(f"{node},{x},{y}\n")
    gs.run_command(
        "v.in.ascii",
        flags="t",
        input=name,
        x=2,
        y=3,
        cat=1,
        output="nodes_reimport_test",
        separator="comma",
    )
    os.remove(name)
    with open(seg_file, "r") as fin, tempfile.NamedTemporaryFile(
        mode="w", delete=False
    ) as temp:
        cat = 1
        name = temp.name
        for line in fin:
            try:
                node1, node2, segment = line.split(",")
            except:
                print(line)
            coords = segment.split(";")
            temp.write("L {} 1\n".format(int(len(coords) / 2)))
            coords = [(float(row), float(col)) for row, col in zip(*[iter(coords)] * 2)]
            for coord in coords:
                y = coord[1]
                x = coord[0]
                temp.write(f"{x} {y}\n")
            temp.write(f"1 {cat}\n")
            cat += 1
    gs.run_command(
        "v.in.ascii",
        flags="nt",
        input=name,
        output="segments_reimport_test",
        format="standard",
        separator="comma",
    )
    os.remove(name)


if __name__ == "__main__":
    railroads = "railroads_USDOT_BTS"
    out_nodes = "/tmp/nodes2.csv"
    out_segments = "/tmp/segments2.csv"
    distance = 1000
    main(railroads, distance, out_nodes, out_segments)

    parse(out_nodes, out_segments)
