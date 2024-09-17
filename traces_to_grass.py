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
    traces = yaml.safe_load(text)["traces"]

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as file_:
            network = yaml.safe_load(file_)["network"]
        extent = network["extent"]
        north = extent["north"]
        south = extent["south"]
        east = extent["east"]
        west = extent["west"]
        resolution = network["resolution"]
        ns_res = resolution["ns"]
        ew_res = resolution["ew"]
    else:
        region = gs.region()
        north = region["n"]
        south = region["s"]
        east = region["e"]
        west = region["w"]
        ns_res = region["nsres"]
        ew_res = region["ewres"]

    nodes_by_id = {}
    csv = []
    delimeter = ","
    #num_traces = len(traces)
    #num_traces_digits = len(str(num_traces))
    #num_traces_offset = pow(10, num_traces_digits + 1)
    for trace_num, trace in enumerate(traces):
        for cell_num, cell in enumerate(trace["cells"]):
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
            csv.append(delimeter.join([str(i) for i in [cell_num + 1, x, y]]))
    text = "\n".join(csv)
    gs.write_command(
        "r.in.xyz",
        input="-",
        output="trace_cells",
        x=2,
        y=3,
        stdin=text,
        separator=delimeter,
        method="n",
    )
    gs.write_command(
        "v.in.ascii",
        input="-",
        output="trace_cell_centers",
        x=2,
        y=3,
        cat=1,
        z=1,
        stdin=text,
        separator=delimeter,
    )

    lines = []
    for num, trace in enumerate(traces):
        cells = trace["cells"]
        lines.append(f"L {len(cells)} 1")
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
        lines.append(f" 1 {num + 1}")
    gs.write_command(
        "v.in.ascii",
        input="-",
        output="traces",
        format="standard",
        stdin="\n".join(lines),
        flags="nt",
    )

    gs.run_command("r.mapcalc", expression="trace_cells_presence = if(trace_cells > 0, 1, null())")

if __name__ == "__main__":
    main()
