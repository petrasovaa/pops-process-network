#!/usr/bin/env python3

import os
import tempfile
from multiprocessing import Pool

import grass.script as gs


os.environ["GRASS_OVERWRITE"] = "1"


def northing_to_row(north, region):
    return int((region["n"] - north) / region["nsres"])


def easting_to_col(east, region):
    return int((east - region["w"]) / region["ewres"])


def row_to_northing(row, region):
    return region["n"] - row * region["nsres"]


def col_to_easting(col, region):
    return region["w"] + col * region["ewres"]


def run_process(seg_cat, segments, nodes_by_id, railroads):
    cells = {}
    env = os.environ.copy()
    node_id = segments[seg_cat][0]
    print(seg_cat)
    gs.run_command(
        "v.to.rast",
        input=railroads + "_simplified",
        quiet=True,
        type="line",
        cats=seg_cat,
        output=railroads + "_segment_" + str(seg_cat),
        use="val",
    )
    gs.run_command(
        "r.patch",
        input=[railroads + "_segment_" + str(seg_cat), railroads + "_nodes"],
        output=railroads + "_" + str(seg_cat),
        quiet=True,
    )
    env["GRASS_REGION"] = gs.region_env(zoom=railroads + "_" + str(seg_cat))
    gs.run_command(
        "r.cost",
        flags="n",
        input=railroads + "_" + str(seg_cat),
        output=railroads + "_cumcost_" + str(seg_cat),
        start_coordinates=nodes_by_id[node_id],
        quiet=True,
        env=env,
    )
    stats = gs.read_command(
        "r.stats",
        output="-",
        flags="xn",
        quiet=True,
        input=railroads + "_cumcost_" + str(seg_cat),
    ).strip()
    cells[seg_cat] = []
    for line in stats.splitlines():
        row, col, cost = line.strip().split()
        row, col, cost = int(row), int(col), float(cost)
        cells[seg_cat].append((cost, row, col))
    cells[seg_cat].sort()
    return cells


def main(railroads, out_nodes, out_segments):
    region = gs.region()
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
            (
                x,
                y,
            ) = line.split()
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
                n1x = float(nodes_by_id[segments[seg_cat][0]][0])
                n2x = float(x)
                segments[seg_cat] = (segments[seg_cat][0], node_cat)
            else:
                segments[seg_cat] = (node_cat, None)

    with Pool(processes=4) as pool:
        results = list(
            pool.apply_async(
                run_process, args=(seg_cat, segments, nodes_by_id, railroads)
            )
            for seg_cat in segments
        )
        results = [r.get() for r in results]
    cells = {}
    for d in results:
        cells.update(d)

    with open(out_nodes, "w") as fout:
        for key in nodes_by_coor:
            row = northing_to_row(float(key[1]), region)
            col = easting_to_col(float(key[0]), region)
            fout.write(f"{nodes_by_coor[key]},{col},{row}\n")

    with open(out_segments, "w") as fout:
        for segment in segments:
            i = 0
            if segment not in cells:
                print(f"Segment {segment} not found")
                continue
            fout.write(f"{segments[segment][0]},{segments[segment][1]},")
            for cell in cells[segment]:
                if i != 0:
                    fout.write(f";{cell[1]};{cell[2]}")
                else:
                    fout.write(f"{cell[1]};{cell[2]}")
                i += 1
            fout.write("\n")


def parse(nodes_file, seg_file):
    region = gs.region()
    with open(nodes_file, "r") as fin, tempfile.NamedTemporaryFile(
        mode="w", delete=False
    ) as temp:
        name = temp.name
        for line in fin:
            node, x, y = line.split(",")
            y = row_to_northing(float(y) + 0.5, region)
            x = col_to_easting(float(x) + 0.5, region)
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
                y = row_to_northing(float(coord[1]) + 0.5, region)
                x = col_to_easting(float(coord[0] + 0.5), region)
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
    railroads = "railroads_USDOT_BTS_test"
    out_nodes = "/tmp/nodes.csv"
    out_segments = "/tmp/segments.csv"
    main(railroads, out_nodes, out_segments)

    parse(out_nodes, out_segments)
