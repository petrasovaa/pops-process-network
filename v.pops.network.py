#!/usr/bin/env python3

############################################################################
#
# MODULE:       v.pops.network
# AUTHOR(S):    Anna Petrasova, Vaclav Petras
#
# PURPOSE:      Create a network CSV file for PoPS modeling
# COPYRIGHT:    (C) 2021-2022 by the GRASS Development Team
#
#               This program is free software under the GNU General
#               Public License (>=v2). Read the file COPYING that
#               comes with GRASS for details.
#
#############################################################################

# %module
# % description: Creates a network CSV file for PoPS modeling
# % keyword: vector
# % keyword: export
# %end
# %option G_OPT_V_INPUT
# % description:
# %end
# %option G_OPT_F_OUTPUT
# % key: segments
# % description: Name for output file with network segments
# % required : yes
# %end
# %option G_OPT_F_OUTPUT
# % key: nodes
# % description: Name for output file with network nodes
# % required : no
# %end
# %option
# % key: distance
# % type: double
# % required: yes
# % multiple: no
# % description: Distance for rasterization
# %end
# %option
# % key: digits
# % type: integer
# % required: yes
# % multiple: no
# % options: 0-10
# % answer: 2
# % description: Number of digits after decimal point
# %end
# %option G_OPT_V_OUTPUT
# % key: segments_check
# % required: no
# % description: Name of vector created by reading the resulting segment file
# %end
# %option G_OPT_V_OUTPUT
# % key: nodes_check
# % required: no
# % description: Name of vector created by reading the resulting node file
# %end


import os
import sys
import atexit
import tempfile
from math import sqrt

import grass.script as gs

TMP_VECTOR = []


def cleanup():
    gs.run_command("g.remove", type="vector", name=TMP_VECTOR, flags="f", quiet=True)


def get_tmp_name(name):
    tmp_name = gs.append_random(name, 8)
    TMP_VECTOR.append(tmp_name)
    return tmp_name


def dist(p1, p2):
    p1 = (float(p1[0]), float(p1[1]))
    p2 = (float(p2[0]), float(p2[1]))
    return sqrt((p1[0] - p2[0]) * (p1[0] - p2[0]) + (p1[1] - p2[1]) * (p1[1] - p2[1]))


def main():
    options, flags = gs.parser()
    input_lines = options["input"]
    out_nodes = options["nodes"]
    out_segments = options["segments"]
    nodes_check = options["nodes_check"]
    segments_check = options["segments_check"]
    distance = float(options["distance"])
    digits = int(options["digits"])

    clean_tmp = get_tmp_name("clean")
    gs.run_command(
        "v.clean",
        input=input_lines,
        output=clean_tmp,
        tool="break,snap,rmdupl",
        threshold=[0, 1, 0],
    )
    poly_tmp = get_tmp_name("poly")
    gs.run_command(
        "v.build.polylines",
        input=clean_tmp,
        output=poly_tmp,
        cats="no",
        type="line",
    )
    simplified_tmp = get_tmp_name("simplified")
    gs.run_command(
        "v.category",
        input=poly_tmp,
        output=simplified_tmp,
        option="add",
    )
    gs.run_command("v.db.addtable", map=simplified_tmp)
    lengths = gs.read_command(
        "v.to.db",
        flags="p",
        map=simplified_tmp,
        type="line",
        option="length",
        columns="length",
        separator="comma",
        units="meters",
    )
    lengths = dict(
        [[float(each) for each in line.split(",")] for line in lengths.splitlines()[1:]]
    )
    nodes_tmp = get_tmp_name("nodes")
    gs.run_command(
        "v.to.points",
        flags="t",
        input=simplified_tmp,
        type="line",
        output=nodes_tmp,
        use="node",
    )
    nodes_out = gs.read_command(
        "v.out.ascii", input=nodes_tmp, format="standard"
    ).strip()
    nodes_by_coor = {}
    nodes_by_id = {}
    segments = {}
    for line in nodes_out.splitlines()[10:]:
        line = line.strip()
        if not (line.startswith("P") or line.startswith("1 ") or line.startswith("2 ")):
            x, y = line.split()
            x = str(round(float(x), 8))
            y = str(round(float(y), 8))
        elif line.startswith("1 "):
            seg_cat = int(line.split()[-1])
        elif line.startswith("2 "):
            node_cat = int(line.split()[-1])
            if (x, y) in nodes_by_coor:
                node_cat = nodes_by_coor[(x, y)]
            else:
                nodes_by_coor[(x, y)] = node_cat
                nodes_by_id[node_cat] = (x, y)
            seg_length = lengths.get(seg_cat, 0)
            if seg_cat in segments:
                segments[seg_cat] = (segments[seg_cat][0], node_cat, seg_length)
            else:
                segments[seg_cat] = (node_cat, None, None)

    if out_nodes:
        with open(out_nodes, "w") as fout:
            for key in nodes_by_coor:
                fout.write(f"{nodes_by_coor[key]},{key[0]},{key[1]}\n")

    vertices_tmp = get_tmp_name("vertices")
    gs.run_command(
        "v.to.points",
        flags="it",
        input=simplified_tmp,
        type="line",
        output=vertices_tmp,
        use="vertex",
        dmax=distance,
    )
    vertices_out = gs.read_command(
        "v.out.ascii", input=vertices_tmp, format="standard"
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
        if not (line.startswith("P") or line.startswith("1 ") or line.startswith("2 ")):
            x, y = line.split()
            x = str(round(float(x), digits))
            y = str(round(float(y), digits))
        elif line.startswith("1 "):
            seg_cat = int(line.split()[-1])
            if seg_cat not in vertices.keys():
                old = None
                vertices[seg_cat] = []
            if old:
                if dist(old, (x, y)) < distance / 2:
                    test_last = (seg_cat, x, y)
                    continue
                else:
                    # test_last vertex must be invalidated for that segment
                    # because another vertex is about to be added
                    test_last = None
            else:
                if test_last:
                    vertices[test_last[0]].append((test_last[1], test_last[2]))
                    test_last = None
            vertices[seg_cat].append((x, y))
            old = (x, y)

    with open(out_segments, "w") as fout:
        fout.write("node_1,node_2,cost,segment\n")
        for segment in segments:
            # filter segments of 0 length and same starting and ending node
            if (
                segments[segment][0] == segments[segment][1]
                and round(segments[segment][2]) == 0
            ):
                continue
            i = 0
            fout.write(
                f"{segments[segment][0]},{segments[segment][1]},{segments[segment][2]},"
            )
            for vertex in vertices[segment]:
                if i != 0:
                    fout.write(f";{vertex[0]};{vertex[1]}")
                else:
                    fout.write(f"{vertex[0]};{vertex[1]}")
                i += 1
            fout.write("\n")

    if out_nodes and nodes_check:
        parse_nodes(out_nodes, nodes_check)
    if segments_check:
        parse_segments(out_segments, segments_check)


def parse_nodes(nodes_file, nodes_check):
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
        output=nodes_check,
        separator="comma",
    )
    os.remove(name)


def parse_segments(seg_file, segments_check):
    with open(seg_file, "r") as fin, tempfile.NamedTemporaryFile(
        mode="w", delete=False
    ) as temp:
        cat = 0
        name = temp.name
        for line in fin:
            cat += 1
            # avoid header
            if cat == 1:
                continue
            try:
                node1, node2, length, segment = line.split(",")
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

    gs.run_command(
        "v.in.ascii",
        flags="nt",
        input=name,
        output=segments_check,
        format="standard",
        separator="comma",
    )
    os.remove(name)


if __name__ == "__main__":
    atexit.register(cleanup)
    sys.exit(main())
