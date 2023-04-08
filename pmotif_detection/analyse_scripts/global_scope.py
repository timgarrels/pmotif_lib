from multiprocessing import Pool

import pandas as pd
from typing import Dict, List
import matplotlib.pyplot as plt
from tqdm import tqdm
from scipy.stats import mannwhitneyu
from statistics import median

from pmotifs.analysis_utilities.loading import Result
from pmotifs.config import WORKERS
from pmotifs.graphlet_representation import graphlet_class_to_name, graphlet_classes_from_size
from pmotifs.PMotifGraph import PMotifGraph
from pmotifs.graphlet_representation import GRAPHLET_CLASS_NAME_LOOKUP

from pmotif_detection.analyse_scripts.util import to_graphlet_class_frequency, get_zscore, extract_metric_distribution, add_consolidated_metrics


class GlobalScope:
    """Creates an analysis utility object focussed on comparisons against a random baseline,
    handling data loading, refining, and exposes special analysis methods"""
    def __init__(self, result: Result):
        self.result = result

        self.graphlet_classes = graphlet_classes_from_size(self.result.graphlet_size)

        self.randomized_results = self._load_randomized_results()

        self._pmotif_analysis_cache = {}

    def _load_randomized_results(self) -> Dict[PMotifGraph, pd.DataFrame]:
        """Loads the results of the computations on the random graphs
        generated from the graph which the original result was based on"""
        randomized_results = Result.load_randomized_results(
            self.result.pmotif_graph,
            self.result.graphlet_size,
            supress_tqdm=True,
        )

        randomized_results = GlobalScope._consolidate_randomized_results(randomized_results)

        randomized_results = {
            r.pmotif_graph: r.positional_metric_df
            for r in randomized_results
        }
        return randomized_results

    @staticmethod
    def _consolidate_randomized_results(randomized_results: List[Result]):
        """Consolidates the positional metrics in all given Results in a parallelized way"""
        if WORKERS == 1:
            return [
                add_consolidated_metrics(r)
                for r in tqdm(randomized_results, desc="(Seq) Consolidating metrics on randomized results")
            ]

        with Pool(
            processes=WORKERS
        ) as p:
            pbar = tqdm(
                randomized_results,
                desc="Consolidating metrics on randomized results",
            )
            return p.map(
                add_consolidated_metrics,
                pbar,
                chunksize=10,
            )

    def plot_graphlet_frequency(self):
        """Classic Motif Analysis, compare the frequency of each graphlet class in the original graph
        against the frequency distribution found in all random graphs"""
        original_frequencies = to_graphlet_class_frequency(self.result.positional_metric_df)

        data = []
        for random_df in tqdm(self.randomized_results.values()):
            data.append(to_graphlet_class_frequency(random_df))
        random_frequencies = pd.DataFrame(data)

        fig, axes = plt.subplots(1, len(self.graphlet_classes), figsize=(10, 5))
        for i, graphlet_class in enumerate(self.graphlet_classes):
            ax = axes[i]

            original_value = original_frequencies[graphlet_class]
            distribution = random_frequencies[graphlet_class]
            z_score = get_zscore(original_value, distribution)

            distribution.plot.hist(ax=ax, label="Expected Distribution")

            ax.axvline(original_value, color="tab:orange", label=f"Original (zscore={round(z_score, 2)})")
            ax.set_title(GRAPHLET_CLASS_NAME_LOOKUP[graphlet_class])
            ax.legend(loc="upper right")
        return fig

    def get_pmotif_analysis_data(self, metric_name: str) -> Dict[str, pd.DataFrame]:
        """Performs the pairwise mann whitney u tests between the original graph and each random graph
        Caches results!"""
        if self._pmotif_analysis_cache.get(metric_name, None) is None:

            original_distribution = extract_metric_distribution(self.result.positional_metric_df, metric_name)

            data = {}
            pbar = tqdm(total=len(self.randomized_results.values()))
            for graphlet_class in self.graphlet_classes:
                data[graphlet_class] = []
                for r_df in self.randomized_results.values():
                    pbar.update(1 / len(self.graphlet_classes))

                    random_distribution = extract_metric_distribution(r_df, metric_name)

                    mwu_result = mannwhitneyu(
                        original_distribution[graphlet_class],
                        random_distribution[graphlet_class],
                    )

                    data[graphlet_class].append(
                        {
                            "u-statistic": mwu_result.statistic,
                            "p-value": mwu_result.pvalue,
                            "sample-size": len(random_distribution[graphlet_class]),
                            "sample-median": median(random_distribution[graphlet_class]),
                            "original-size": len(original_distribution[graphlet_class]),
                            "original-median": median(original_distribution[graphlet_class]),
                        }
                    )

            result_dfs = {
                graphlet_class: pd.DataFrame(d)
                for graphlet_class, d in data.items()
            }
            self._pmotif_analysis_cache[metric_name] = result_dfs

        return self._pmotif_analysis_cache[metric_name]

    def pmotif_analysis_result(self, metric_name: str, alpha_global: float = 0.05) -> pd.DataFrame:
        """Counts the random graphs, where the mann whitney u test resulted in significance"""
        pmotif_analysis_data = self.get_pmotif_analysis_data(metric_name)

        analysis_result = []
        for graphlet_class, result_df in pmotif_analysis_data.items():
            # Bonferroni Correction
            alpha_local = alpha_global / result_df.shape[0]

            relevant_rows = result_df[result_df["p-value"] < alpha_local]

            analysis_result.append({
                "graphlet_class": graphlet_class,
                "relevant": relevant_rows.shape[0],
                "total": result_df.shape[0],
            })

        return pd.DataFrame(analysis_result)

    def plot_sample_size_distribution(self, metric_name: str):
        """Plot the distribution of graphlet frequencies in random graphs, and
        highlight the graphlet occurrence frequency of the original graph"""

        pmotif_analysis_data = self.get_pmotif_analysis_data(metric_name)

        fig, axes = plt.subplots(1, len(self.graphlet_classes), figsize=(len(self.graphlet_classes) * 5, 5))
        for i, graphlet_class in enumerate(self.graphlet_classes):
            ax = axes[i]
            pmotif_analysis_data[graphlet_class][["sample-size"]].plot.hist(ax=ax)

            ax.axvline(pmotif_analysis_data[graphlet_class]["original-size"][0], label="original", color="tab:orange")
            ax.set_title(graphlet_class_to_name(graphlet_class))
            ax.legend()
            ax.set_xlabel(f"# of {graphlet_class_to_name(graphlet_class)} occurrences")
        fig.suptitle("sample-size")

        return fig

    def plot_median_distribution(self, metric_name: str):
        """Plot the distribution of the medians of the positional metrics in random graphs, and
        highlight the graphlet occurrence medians of the original graph"""
        pmotif_analysis_data = self.get_pmotif_analysis_data(metric_name)

        fig, axes = plt.subplots(1, len(self.graphlet_classes), figsize=(len(self.graphlet_classes) * 5, 5))
        for i, graphlet_class in enumerate(self.graphlet_classes):
            ax = axes[i]
            pmotif_analysis_data[graphlet_class][["sample-median"]].plot.hist(ax=ax)

            ax.axvline(pmotif_analysis_data[graphlet_class]["original-median"][0], label="original", color="tab:orange")
            ax.set_title(graphlet_class_to_name(graphlet_class))
            ax.legend()
            ax.set_xlabel(metric_name)
        fig.suptitle("sample-median")

        return fig
