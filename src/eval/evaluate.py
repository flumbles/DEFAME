import csv
import inspect
import time
from multiprocessing import Pool, Queue
from queue import Empty
from typing import Optional, Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from tqdm import tqdm

from src.common.label import Label
from src.common.modeling import model_full_name_to_shorthand, AVAILABLE_MODELS, MLLM, LLM
from src.eval.averitec.compute_score import compute_averitec_score
from src.eval.benchmark import load_benchmark, AVeriTeC, Benchmark
from src.common.logger import Logger
from src.fact_checker import FactChecker
from src.tools import initialize_tools, Searcher
from src.tools.search.knowledge_base import KnowledgeBase
from src.utils.console import green, red, bold, sec2hhmmss
from src.utils.plot import plot_confusion_matrix


def evaluate(
        llm: str,
        benchmark_name: str,
        tools_config: dict[str, dict],
        fact_checker_kwargs: dict = None,
        llm_kwargs: dict = None,
        benchmark_kwargs: dict = None,
        mllm: str = None,
        mllm_kwargs: dict = None,
        n_samples: int = None,
        sample_ids: list[int] = None,
        random_sampling: bool = False,
        print_log_level: str = False,
        continue_experiment_dir: str = None,
        n_workers: int = None,
) -> Optional[float]:
    assert not n_samples or not sample_ids

    if llm_kwargs is None:
        llm_kwargs = dict()
    if mllm_kwargs is None:
        mllm_kwargs = dict()

    benchmark = load_benchmark(benchmark_name, **benchmark_kwargs)
    is_test = benchmark.variant == "test"

    llm = model_full_name_to_shorthand(llm) if llm not in AVAILABLE_MODELS["Shorthand"].values else llm
    logger = Logger(benchmark.shorthand,
                    llm,
                    print_log_level=print_log_level,
                    target_dir=continue_experiment_dir)

    is_resumed = continue_experiment_dir is not None

    status_verb = "Resuming" if is_resumed else "Starting"
    print(bold(f"{status_verb} evaluation for {benchmark.name}."))

    # Save hyperparams based on the signature of evaluate()
    if not is_resumed:
        signature = inspect.signature(evaluate)
        logger.save_config(signature, locals())

    # Load the tools and verify if they are allowed
    tools = initialize_tools(tools_config, logger=logger)
    if benchmark.available_actions is not None:
        for tool in tools:
            for action in tool.actions:
                assert action in benchmark.available_actions, \
                    f"Action {action} not available for benchmark {benchmark.name}."
    # del tools

    if random_sampling:
        benchmark.shuffle()

    if n_samples:
        samples = benchmark[:n_samples]
    elif sample_ids:
        samples = [benchmark.get_by_id(i) for i in sample_ids]
    else:
        samples = benchmark

    # Exclude already existing samples (relevant if evaluation is resumed)
    if is_resumed:
        samples_to_evaluate = []
        # Retrieve the IDs of already checked claims
        predictions_path = continue_experiment_dir + "/predictions.csv"
        df = pd.read_csv(predictions_path)
        checked_claim_ids = df["sample_index"].to_numpy()

        # Only keep samples that haven't been checked yet
        for sample in samples:
            if sample["id"] not in checked_claim_ids:
                samples_to_evaluate.append(sample)

    else:
        samples_to_evaluate = samples

    # Update number of to-be-checked samples
    n_samples = len(samples_to_evaluate)

    if n_samples == 0:
        raise RuntimeError("Nothing to evaluate.")

    is_averitec = isinstance(benchmark, AVeriTeC)

    start_time = time.time()

    input_queue = Queue()
    output_queue = Queue()
    devices_queue = Queue()

    fact_checker_kwargs.update(dict(
        class_definitions=benchmark.class_definitions,
        extra_prepare_rules=benchmark.extra_prepare_rules,
        extra_plan_rules=benchmark.extra_plan_rules,
        extra_judge_rules=benchmark.extra_judge_rules,
    ))

    if n_workers is None:
        n_workers = torch.cuda.device_count()
    print(f"Evaluating {n_samples} samples using {n_workers} workers...")

    logger_kwargs = dict(
        print_log_level=print_log_level,
        target_dir=logger.target_dir
    )

    worker_args = (llm, llm_kwargs, mllm, mllm_kwargs, fact_checker_kwargs,
                   tools_config, logger_kwargs, is_averitec, input_queue, output_queue, devices_queue)

    with Pool(n_workers, fact_check, worker_args):
        # Initialize workers by assigning them a GPU device
        for d in range(n_workers):
            devices_queue.put(d)

        # Fill the input queue with benchmark instances
        for instance in samples_to_evaluate:
            content = instance["content"]
            input_queue.put(content)

        # Gather worker results by reading the output queue
        for _ in tqdm(range(n_samples)):
            try:
                doc, q_and_a = output_queue.get(timeout=30 * 60)  # 30 minutes timeout
            except Empty as e:
                # Happens if some worker died during execution, causing an
                # incomplete number of instances
                break
            content = doc.claim.original_context
            claim_id = content.id_number
            instance = benchmark.get_by_id(claim_id)
            prediction = doc.verdict

            if is_averitec:
                if prediction == Label.CHERRY_PICKING:
                    # Merge cherry-picking and conflicting label
                    prediction = Label.CONFLICTING

                pred_label = benchmark.get_class_name(prediction)
                averitec_out_instance = {
                    "claim_id": claim_id,
                    "claim": content.text,
                    "evidence": q_and_a,
                    "pred_label": pred_label
                }

                logger.save_next_averitec_out(averitec_out_instance)

            logger.save_next_prediction(
                sample_index=claim_id,
                claim=doc.claim.text,
                target=instance.get("label"),
                justification=doc.justification,
                predicted=prediction,
                gt_justification=instance.get("justification")
            )
            logger.save_fc_doc(doc, instance['id'])

            if not is_test:
                prediction_is_correct = instance["label"] == prediction
                if prediction_is_correct:
                    logger.log(bold(green("CORRECT\n")))
                else:
                    logger.log(bold(red("WRONG - Ground truth: " + instance["label"].value + "\n")))

    end_time = time.time()

    return finalize_evaluation(logger.target_dir, benchmark, duration=end_time - start_time)


def finalize_evaluation(experiment_dir: str | Path,
                        benchmark: Benchmark,
                        duration: float):
    experiment_dir = Path(experiment_dir)
    is_averitec = isinstance(benchmark, AVeriTeC)
    is_test = benchmark.variant == "test"

    # search_summary = {
    #     name: searcher.total_searches
    #     for tool in tools if isinstance(tool, Searcher)  # TODO: Not updated anymore due to multiprocessing
    #     for name, searcher in tool.search_apis.items()
    # }

    # Retrieve predictions and ground truth
    df = pd.read_csv(experiment_dir / "predictions.csv")
    predicted_labels = df["predicted"].to_numpy()
    ground_truth_labels = None if is_test else df["target"].to_numpy()

    benchmark_classes = benchmark.get_classes()
    if is_averitec:
        benchmark_classes.remove(Label.CHERRY_PICKING)

    accuracy = save_final_summary(predicted_labels=predicted_labels,
                                  ground_truth_labels=ground_truth_labels,
                                  duration=duration,
                                  # search_summary=search_summary,
                                  experiment_dir=experiment_dir)

    if not is_test:
        plot_confusion_matrix(predicted_labels,
                              ground_truth_labels,
                              benchmark_classes,
                              benchmark_name=benchmark.name,
                              save_dir=experiment_dir)

        if is_averitec:
            averitec_out_path = experiment_dir / Logger.averitec_out_filename
            scores = compute_averitec_score(benchmark.file_path, averitec_out_path)
            scores_path = experiment_dir / "averitec_scores.yaml"
            with open(scores_path, "w") as f:
                yaml.dump(scores, f, sort_keys=False)

        return accuracy


def save_final_summary(predicted_labels: Sequence[Label],
                       duration: float,
                       # search_summary: dict,
                       experiment_dir: Path,
                       ground_truth_labels: Sequence[Label] = None,
                       print_summary: bool = True) -> Optional[float]:
    n_samples = len(predicted_labels)
    n_refused = np.count_nonzero(np.array(predicted_labels) == Label.REFUSED_TO_ANSWER)
    # search_summary = ", ".join(f"{searcher}: {n_searches}" for searcher, n_searches in search_summary.items())

    result_summary = {
        "Total samples": n_samples,
        "Refused predictions": int(n_refused),
        "Run duration": sec2hhmmss(duration),
        # "Total searches": search_summary,
    }

    if ground_truth_labels is not None:
        correct_predictions = np.asarray(np.array(predicted_labels) == np.array(ground_truth_labels))
        n_correct_predictions = np.sum(correct_predictions)
        n_wrong_predictions = n_samples - n_correct_predictions - n_refused
        accuracy = n_correct_predictions / (n_samples - n_refused)

        result_summary.update({
            "Correct predictions": int(n_correct_predictions),
            "Wrong predictions": int(n_wrong_predictions),
            "Accuracy": f"{accuracy * 100:.1f} %",
        })

    else:
        accuracy = None

    with open(experiment_dir / 'results.yaml', "w") as f:
        yaml.dump(result_summary, f, sort_keys=False)

    if print_summary:
        print("Results:")
        bold_print_dict(result_summary)

    return accuracy


def fact_check(llm: str, llm_kwargs: dict, mllm: str, mllm_kwargs: dict,
               fact_checker_kwargs: dict, tools_config: dict, logger_kwargs: dict,
               is_averitec: bool, input_queue: Queue, output_queue: Queue, devices_queue: Queue):
    device = f"cuda:{devices_queue.get()}"

    logger = Logger(**logger_kwargs)

    tools = initialize_tools(tools_config, logger=logger, device=device)

    # Initialize model(s)
    llm = LLM(llm, logger=logger, device=device, **llm_kwargs)
    if mllm is not None:
        mllm = MLLM(name=mllm, logger=logger, device=device, **mllm_kwargs)

    # Setup fact-checker
    fc = FactChecker(
        llm=llm,
        mllm=mllm,
        tools=tools,
        logger=logger,
        **fact_checker_kwargs,
    )

    # Get the knowledge base object
    if is_averitec:
        searcher = tools[0]
        assert isinstance(searcher, Searcher)
        kb = searcher.search_apis["averitec_kb"]
        assert isinstance(kb, KnowledgeBase)
    else:
        kb = None

    # Run fact-checks as long as there is work to do
    while True:
        content = input_queue.get()
        if is_averitec:
            # Restrict the KB to the current claim's resources
            kb.current_claim_id = content.id_number
        logger.set_current_fc_id(content.id_number)
        _, docs, q_and_a = fc.check(content)
        doc = docs[0]
        output_queue.put((doc, q_and_a))


def load_results(path: str):
    ground_truth = []
    predictions = []
    for _, target, predicted, _ in next_result(path):
        ground_truth.append(Label[target])
        predictions.append(Label[predicted])
    return ground_truth, predictions


def next_result(path: str):
    with open(path) as f:
        reader = csv.reader(f)
        next(reader)  # skip header line
        for row in reader:
            yield row


def compute_accuracy(predictions: pd.DataFrame) -> float:
    correct_stats = predictions["correct"].value_counts()
    prediction_stats = predictions["predicted"].value_counts()
    n_refused = prediction_stats["REFUSED_TO_ANSWER"] if "REFUSED_TO_ANSWER" in list(prediction_stats.keys()) else 0
    accuracy = correct_stats[True] / (len(predictions) - n_refused)
    return accuracy


def naive_evaluate(model: str, model_kwargs: dict = None, benchmark_name: str = "fever1", n_samples: int = None,
                   **kwargs) -> float:
    benchmark = load_benchmark(benchmark_name)
    model = LLM(model, **model_kwargs)
    samples_to_evaluate = benchmark[:n_samples] if n_samples else benchmark

    eval_log = []
    predictions = []
    for instance in samples_to_evaluate:
        query = f"Check if the following claim is 'supported', 'not enough information', or 'refuted' using your available knowledge. Answer with only one of the three options. Claim: {instance['content']}"
        prediction = model.generate(query).replace("'", "").replace(".", "").lower()
        if prediction not in ['supported', 'not enough information', 'refuted']:
            print(instance["id"], prediction)
        eval_log.append({"claim": instance["content"], "pred_label": prediction})
        prediction_is_correct = instance["label"].value == prediction
        predictions.append(prediction_is_correct)
    accuracy = np.average(predictions)

    return accuracy, eval_log


def bold_print_dict(dictionary: dict):
    for key, value in dictionary.items():
        print(f"\t{bold(str(key))}: {value}")
