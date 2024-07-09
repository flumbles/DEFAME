"""Creates the FEVER Wiki Dump database. Additionally, extracts the justifications from
the DB and saves them in an extra file."""
# TODO: Test this script

from config.globals import path_to_data
from tools.search.wiki_dump import WikiDumpAPI
from utils.parsing import extract_nth_sentence
from tqdm import tqdm
import orjsonl

# Construct the DB
wiki_dump = WikiDumpAPI()
wiki_dump.build_db(path_to_data + "FEVER/wiki-raw/")
wiki_dump._build_knn()


# Extract the ground truth justifications
def retrieve_justification(instance):
    justification = []
    evidences = instance["evidence"]
    if evidences:
        for evidence in evidences[0]:
            article_title, sentence_id = evidence[2], evidence[3]
            if article_title is not None and sentence_id is not None:
                evidence_text = wiki_dump.get_by_title(article_title)
                sentence = extract_nth_sentence(evidence_text, int(sentence_id))
                justification.append(sentence)
            else:
                justification.append("")
    else:
        justification.append("")
    return justification


variant = "dev"
for version in [1, 2]:
    raw_data = orjsonl.load(path_to_data + f"FEVER/fever{version}_{variant}.jsonl")
    justifications = []
    for i in tqdm(range(len(raw_data)), desc="Retrieving justifications"):
        instance = raw_data[i]
        justifications.append(retrieve_justification(instance))
    save_path = path_to_data + f"FEVER/gt_justification_fever{version}_{variant}.jsonl"
    orjsonl.save(save_path, justifications)
