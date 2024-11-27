import warnings
from multiprocessing import set_start_method

from defame.eval.evaluate import evaluate

warnings.filterwarnings("ignore")

if __name__ == '__main__':  # evaluation uses multiprocessing
    set_start_method("spawn")
    evaluate(
        llm="gpt_4o",
        tools_config=dict(searcher=dict(
            search_engine_config=dict(
                google=dict(),
                google_vision=dict(),
            ),
            limit_per_search=3
        ),
            geolocator=dict(),
            manipulation_detector=dict()
        ),
        fact_checker_kwargs=dict(
            procedure_variant="summary",
            interpret=True,
            decompose=False,
            decontextualize=False,
            filter_check_worthy=False,
            max_iterations=3,
            max_result_len=64_000,  # characters
        ),
        llm_kwargs=dict(temperature=0.01),
        benchmark_name="dgm4",
        benchmark_kwargs=dict(variant="val"),
        n_samples=None,
        print_log_level="info",
        random_sampling=False,
        n_workers=1,
    )
