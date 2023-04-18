"""Performs a `graphlet_size` graphlet detection and
calculates each metric in `metrics` for each graphlet occurrence."""
import shutil
from pathlib import Path

from pmotif_lib.p_motif_graph import PMotifGraph
from pmotif_lib.config import DATASET_DIRECTORY
from pmotif_lib.gtrieScanner.wrapper import run_gtrieScanner
from pmotif_lib.p_metric.p_degree import PDegree
from pmotif_lib.p_metric.metric_processing import calculate_metrics

DATASET = DATASET_DIRECTORY / "kaggle_star_wars.edgelist"
GRAPHLET_SIZE = 3
OUTPUT = Path("./showcase_output")


def main(edgelist: Path, output: Path, graphlet_size: int):
    pmotif_graph = PMotifGraph(edgelist, output)

    run_gtrieScanner(
        graph_edgelist=pmotif_graph.get_graph_path(),
        graphlet_size=graphlet_size,
        output_directory=pmotif_graph.get_graphlet_directory(),
    )

    degree_metric = PDegree()
    metric_results = calculate_metrics(
        pmotif_graph, graphlet_size, [degree_metric], True
    )

    graphlet_occurrences = pmotif_graph.load_graphlet_pos_zip(graphlet_size)
    print(graphlet_occurrences[0].graphlet_class, graphlet_occurrences[0].nodes)
    print(metric_results[0].graphlet_metrics[0])


if __name__ == "__main__":
    if OUTPUT.is_dir():
        shutil.rmtree(OUTPUT)
    main(DATASET, OUTPUT, GRAPHLET_SIZE)
