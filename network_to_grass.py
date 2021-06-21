#!/usr/bin/env python

import fileinput
import sys
import os
import yaml

import grass.script as gs


def row_col_to_xy(row, col, /, north, south, east, west, ns_res, ew_res):
    x = west + ew_res * (col + 0.5)
    y = north - ns_res * (row + 0.5)
    return x, y


def main():

    os.environ["GRASS_OVERWRITE"] = "1"

    text = sys.stdin.read()
    network = yaml.safe_load(text)["network"]
    extent = network["extent"]
    north = extent["north"]
    south = extent["south"]
    east = extent["east"]
    west = extent["west"]
    resolution = network["resolution"]
    ns_res = resolution["ns"]
    ew_res = resolution["ew"]

    print(
        f"g.region n={north} s={south} e={east} w={west} nsres={ns_res} ewres={ew_res}"
    )

    nodes_by_id = {}
    csv = []
    delimeter = ","
    for node in network["nodes"]:
        x, y = row_col_to_xy(
            node["row"],
            node["col"],
            north=north,
            south=south,
            east=east,
            west=west,
            ns_res=ns_res,
            ew_res=ew_res,
        )
        node_id = node["id"]
        csv.append(delimeter.join([str(i) for i in [node_id, x, y]]))
        nodes_by_id[node_id] = [x, y]
    text = "\n".join(csv)
    gs.write_command(
        "r.in.xyz",
        input="-",
        output="nodes",
        x=2,
        y=3,
        stdin=text,
        separator=delimeter,
        method="n",
    )
    gs.write_command(
        "v.in.ascii",
        input="-",
        output="nodes",
        x=2,
        y=3,
        stdin=text,
        separator=delimeter,
    )

    csv = []
    segment_number = 0
    for segment in network["segments"]:
        segment_number += 1
        for cell in segment["cells"]:
            x, y = row_col_to_xy(
                cell[0],
                cell[1],
                north=north,
                south=south,
                east=east,
                west=west,
                ns_res=ns_res,
                ew_res=ew_res,
            )
            csv.append(delimeter.join([str(i) for i in [segment_number, x, y]]))
    gs.write_command(
        "r.in.xyz",
        input="-",
        output="segments",
        x=2,
        y=3,
        stdin="\n".join(csv),
        separator=delimeter,
        method="n",
    )

    max_node_id = network["statistics"]["min_node_id"]
    node_id_digits = len(str(max_node_id))
    # Here we assume small id numbers.
    node_id_offset = pow(10, node_id_digits + 1)

    lines = []
    for segment in network["segments"]:
        cells = segment["cells"]
        lines.append(f"L {len(cells)} 3")
        for cell in cells:
            x, y = row_col_to_xy(
                cell[0],
                cell[1],
                north=north,
                south=south,
                east=east,
                west=west,
                ns_res=ns_res,
                ew_res=ew_res,
            )
            lines.append(f" {x} {y}")
        composite_id = node_id_offset * segment['start_node'] + segment['end_node']
        lines.append(f" 1 {composite_id}")
        lines.append(f" 2 {segment['start_node']}")
        lines.append(f" 3 {segment['end_node']}")
    gs.write_command(
        "v.in.ascii",
        input="-",
        output="segments",
        format="standard",
        stdin="\n".join(lines),
        flags="nt",
    )
    gs.run_command("r.mapcalc", expression="segments_presence = if(segments > 0, 1, null())")

    lines = []
    edge_number = 0
    for edge in network["edges"]:
        edge_number += 1
        lines.append(f"L 2 1")
        for node_id in edge:
            x, y = nodes_by_id[node_id]
            lines.append(f" {x} {y}")
        lines.append(f" 1 {edge_number}")
    gs.write_command(
        "v.in.ascii",
        input="-",
        output="edges",
        format="standard",
        stdin="\n".join(lines),
        flags="nt",
    )

if __name__ == "__main__":
    main()
