"""
generate_golden_dataset_v2.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generates RAGAS golden dataset v2 for evaluating the /ask endpoint
against the updated hybrid-search + parent-child chunking pipeline.

Distribution target
-------------------
  FACT        45%  (~25q)  SingleHopSpecificQuerySynthesizer       top_k=10 / final_k=3
  ANALYTICAL  35%  (~20q)  MultiHopAbstract + MultiHopSpecific     top_k=20 / final_k=5
  GUARDRAIL   20%  (~10q)  hand-written cross-category & OOS       expected refusal

Generation strategy
-------------------
  Auto-gen   : RAGAS 0.4.x TestsetGenerator, fully offline via Ollama:
               • Transforms  — Ollama qwen3:8b (local) via OllamaStructuredLLM, using
                               native JSON-schema-constrained decoding (format=<schema>)
                               so syntactically invalid JSON is impossible, with
                               think=False to skip qwen3's chain-of-thought (not useful
                               for extraction and ~3-4x slower). Falls back to a
                               validation-retry loop (re-prompt with the error) for
                               semantic mistakes the grammar constraint can't catch.
               • Synthesis   — Ollama llama3.1:8b (local), also via OllamaStructuredLLM
                               (not LangChain's ChatOllama — RAGAS's LangChain dispatch
                               path always calls the async interface, and a LangChain
                               model's cached async client breaks the moment a second
                               ragas.async_utils.run() stage reuses it across a fresh
                               event loop). SingleHop/MHSpecific may fail gracefully;
                               NaN-skip patch in RAGAS handles those failures.
               Embeddings    — HuggingFaceEmbeddings (BAAI/bge-base-en-v1.5), same as prod.
  Guardrail  : Hand-written; appended after auto-gen phase.

Documents
---------
  All PDFs in ingestion-docs/ are loaded and categorised (JV, Development,
  Strategic Alliance, Non-Compete).  To keep each batch's knowledge-graph build fast,
  up to DOCS_PER_CATEGORY PDFs are sampled per category. Raise that cap for richer
  coverage at the cost of longer local-inference time per batch.

Local-inference resilience
---------------------------
  • No external API rate limits — everything runs against your local Ollama server.
  • BATCH_SIZE defaults to 1 — one RAGAS call per question.  After each question
    the result is saved to the checkpoint immediately, so a crash or interrupt
    loses at most the one question in progress.
  • QUESTION_COOLDOWN_SECS (default 60) gives the laptop a full minute to cool
    between questions before the next local inference run starts.
  • Re-running the script picks up from the checkpoint automatically.

Ollama setup (one-time)
-----------------------
  ollama pull llama3.1:8b
  ollama pull qwen3:8b
  # Make sure Ollama is running: ollama serve

Outputs
-------
  Evaluation/golden_dataset_v2.json    full format — question, ground_truth,
                                       reference_contexts, intent, synthesizer,
                                       doc_category
  Evaluation/golden_dataset_v2.csv     flat, eval-script-compatible format
                                       (reference_contexts JSON-encoded)
  Evaluation/.checkpoint_v2.json       internal resume file (auto-managed)

Usage
-----
  # From the project root, with venv active:
  python Evaluation/generate_golden_dataset_v2.py

Required env vars
  None — everything runs locally against Ollama. Load a .env if you have one, but
  no API keys are required for this script.

Optional env vars
  OLLAMA_MODEL           Ollama model tag for synthesis (default llama3.1:8b)
  TRANSFORMS_OLLAMA_MODEL Ollama model tag for transforms/KG-build (default qwen3:8b)
  OLLAMA_BASE_URL        Ollama server URL (default http://localhost:11434)
  DOCS_PER_CATEGORY      max PDFs sampled per doc category for KG build (default 6)
  AUTO_GEN_COUNT         auto-generated question target (default 45; + 10 guardrail = 55 total)
  OUTPUT_DIR             directory for output files (default Evaluation/)
  BATCH_SIZE             questions generated per RAGAS run (default 1 = save after each)
  QUESTION_COOLDOWN_SECS seconds to wait between questions/batches (default 60)
  MAX_RETRIES            instructor structured-output validation retries per extractor call (default 10)
"""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_core.documents import Document
from ragas.llms import InstructorBaseRagasLLM

# ── project root on sys.path so app.* imports work ───────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pdf_parser import extract_pages_from_pdf  # pipeline's own extractor

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
DOCS_DIR = ROOT / "ingestion-docs"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(ROOT / "Evaluation")))
DOCS_PER_CATEGORY = int(os.getenv("DOCS_PER_CATEGORY", "6"))
AUTO_GEN_COUNT = int(os.getenv("AUTO_GEN_COUNT", "45"))
# Cap pages extracted per PDF for KG building. Each page = 3 local LLM calls;
# a 36-page JV doc adds up fast even without any external rate limit.
# 5 pages/doc captures the key legal provisions; raise for richer KG coverage.
# Dry-run tip: set MAX_PAGES_PER_DOC=2 for a quick end-to-end smoke test.
MAX_PAGES_PER_DOC = int(os.getenv("MAX_PAGES_PER_DOC", "5"))
RANDOM_SEED = 42

# RAGAS query-distribution weights (must sum to 1.0).
# Env vars are percentages (0-100); script normalises them automatically.
# SingleHop → FACT intent,  MultiHop* → ANALYTICAL intent
_fw  = float(os.getenv("FACT_WEIGHT",              "55.6"))
_maw = float(os.getenv("MULTIHOP_ABSTRACT_WEIGHT", "22.2"))
_msw = float(os.getenv("MULTIHOP_SPECIFIC_WEIGHT", "22.2"))
_total = _fw + _maw + _msw
FACT_WEIGHT              = _fw  / _total
MULTIHOP_ABSTRACT_WEIGHT = _maw / _total
MULTIHOP_SPECIFIC_WEIGHT = _msw / _total

LLM_CONTEXT = (
    "Legal commercial agreements from U.S. corporate filings, including joint venture "
    "agreements, development agreements, strategic alliance agreements, and non-competition "
    "/ non-solicitation agreements.  Questions should focus on legal obligations, rights, "
    "payment terms, termination conditions, intellectual property, governing law, and "
    "confidentiality provisions."
)

# ── Ollama (local synthesis + transforms) configuration ───────────────────────
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
# qwen3:8b follows structured-output/tool-calling schemas more reliably than
# llama3.1:8b, which matters for the transforms stage (SummaryExtractor,
# ThemesExtractor, NERExtractor all require strict JSON).
TRANSFORMS_OLLAMA_MODEL = os.getenv("TRANSFORMS_OLLAMA_MODEL", "qwen3:8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Retry / thermal configuration ─────────────────────────────────────────────
# OllamaStructuredLLM (below) re-prompts with the validation error on failure —
# this is local retries for malformed JSON, not network rate-limit backoff.
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "10"))
# 1 question per RAGAS call → checkpoint written after every question.
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
# 60 s lets the CPU/GPU cool between local inference runs.
QUESTION_COOLDOWN_SECS = int(os.getenv("QUESTION_COOLDOWN_SECS", "60"))
CHECKPOINT_FILE = OUTPUT_DIR / ".checkpoint_v2.json"


class OllamaStructuredLLM(InstructorBaseRagasLLM):
    """Structured-output LLM for the transforms stage (SummaryExtractor,
    ThemesExtractor, NERExtractor) using Ollama's native JSON-schema-constrained
    decoding — passing a Pydantic schema via `format=` makes syntactically
    invalid JSON impossible, unlike prompting a model and hoping for valid JSON.

    think=False disables qwen3's default chain-of-thought: a plain extraction
    call was measured at ~25s with thinking on vs ~7s with it off, and the
    reasoning trace serves no purpose for schema-constrained extraction.

    On top of the grammar constraint, failed *semantic* validation (e.g. a
    field of the wrong type) triggers up to `max_retries` re-prompts with the
    validation error fed back to the model — mirroring what the `instructor`
    library does for API-based LLMs, but fully local and without its slower
    OpenAI-compatible-endpoint round trip.

    Implements the InstructorBaseRagasLLM interface (generate/agenerate +
    is_async), which RAGAS's PydanticPrompt dispatches on directly — see
    ragas/prompt/pydantic_prompt.py's `is_async` branch. is_async is set to
    False deliberately: ollama.AsyncClient binds its HTTP transport to the
    asyncio event loop active at construction time, but RAGAS spins up a new
    event loop per batch (generate_with_chunks is called once per question in
    generate_in_batches), so a cached AsyncClient breaks with "Event loop is
    closed" from the second batch onward. The sync client has no such binding,
    and since RunConfig already forces max_workers=1, there's no concurrency
    to lose by calling it directly (it just blocks the current loop iteration).
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        temperature: float = 0.0,
        num_predict: int = 4096,
        max_retries: int = MAX_RETRIES,
    ):
        import ollama

        self.model = model
        self.client = ollama.Client(host=base_url)
        self.options = {"temperature": temperature, "num_predict": num_predict}
        self.max_retries = max_retries
        self.is_async = False  # tells PydanticPrompt to call generate(), not agenerate()

    def _build_messages(self, prompt, prior_content=None, validation_error=None):
        messages = [{"role": "user", "content": prompt}]
        if prior_content is not None:
            messages.append({"role": "assistant", "content": prior_content})
            messages.append({
                "role": "user",
                "content": (
                    f"That response failed schema validation: {validation_error}. "
                    "Return corrected JSON only."
                ),
            })
        return messages

    def generate(self, prompt: str, response_model):
        content, last_err = None, None
        for _ in range(self.max_retries + 1):
            resp = self.client.chat(
                model=self.model,
                messages=self._build_messages(prompt, content, last_err),
                format=response_model.model_json_schema(),
                think=False,
                options=self.options,
            )
            content = resp["message"]["content"]
            try:
                return response_model.model_validate_json(content)
            except Exception as exc:
                last_err = exc
        raise last_err

    async def agenerate(self, prompt: str, response_model):
        # Never called: is_async=False routes PydanticPrompt to generate() instead.
        # Implemented only to satisfy the InstructorBaseRagasLLM abstract interface.
        return self.generate(prompt, response_model)


# ── Document-category patterns ────────────────────────────────────────────────
# Order matters: more-specific patterns first.
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("JOINT VENTURE",       "joint_venture"),
    ("JV AGREEMENT",        "joint_venture"),
    ("JV CONTRACT",         "joint_venture"),
    ("NON-COMPETITION",     "non_compete"),
    ("NON COMPETITION",     "non_compete"),
    ("NON SOLICITATION",    "non_compete"),
    ("STRATEGIC ALLIANCE",  "strategic_alliance"),
    ("DEVELOPMENT AGREEMENT", "development"),
    ("DEVELOPMENT1",        "development"),
    ("DEVELOPMENT2",        "development"),
]

_INTENT_MAP: dict[str, str] = {
    "single_hop_specific_query_synthesizer": "FACT",
    "multi_hop_abstract_query_synthesizer": "ANALYTICAL",
    "multi_hop_specific_query_synthesizer": "ANALYTICAL",
}


# ── Guardrail questions (hand-written) ────────────────────────────────────────
# Each tests that the pipeline correctly refuses to answer:
#   - cross-category mismatch: provision from one doc type asked about another
#   - out-of-scope: topic not present in any of the 40 indexed contracts
_GUARDRAIL_QUESTIONS: list[dict] = [
    # ── Cross-category: JV provisions asked of a Non-Compete doc ─────────────
    {
        "question": (
            "What is the profit-sharing percentage and capital contribution schedule "
            "for each party in the Quaker Chemical agreement?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "non_compete",
        "mismatch_type": "jv_provisions_in_noncompete",
    },
    # ── Cross-category: JV governance asked of a Development Agreement ────────
    {
        "question": (
            "What are the board seat allocations, governance rights, and voting "
            "thresholds defined in the Coherus Biosciences agreement?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "development",
        "mismatch_type": "jv_governance_in_dev_agreement",
    },
    # ── Cross-category: Non-Compete provisions asked of a JV Agreement ────────
    {
        "question": (
            "What non-solicitation restrictions and employee poaching prohibitions "
            "are imposed on the parties in the VEONEER Joint Venture Agreement?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "joint_venture",
        "mismatch_type": "noncompete_provisions_in_jv",
    },
    # ── Cross-category: Royalties/milestones asked of a Non-Compete doc ───────
    {
        "question": (
            "What milestone payment triggers and royalty rates apply under "
            "the Vivint Solar non-competition agreement?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "non_compete",
        "mismatch_type": "royalties_in_noncompete",
    },
    # ── Out-of-scope: Employment law ──────────────────────────────────────────
    {
        "question": (
            "What severance packages, equity vesting schedules, and health benefit "
            "continuation terms apply to executives terminating employment under "
            "these agreements?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "out_of_scope",
        "mismatch_type": "employment_law",
    },
    # ── Out-of-scope: Tax ─────────────────────────────────────────────────────
    {
        "question": (
            "What IRS withholding obligations and federal tax reporting requirements "
            "apply to income distributions from the joint ventures?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "out_of_scope",
        "mismatch_type": "tax_law",
    },
    # ── Out-of-scope: Antitrust ───────────────────────────────────────────────
    {
        "question": (
            "What Hart-Scott-Rodino antitrust pre-merger notification filings are "
            "required before the parties can close the joint ventures?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "out_of_scope",
        "mismatch_type": "antitrust_regulation",
    },
    # ── Out-of-scope: Environmental ───────────────────────────────────────────
    {
        "question": (
            "What EPA environmental impact assessments and NEPA compliance steps "
            "must the strategic alliance parties satisfy before commencing operations?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "out_of_scope",
        "mismatch_type": "environmental_regulation",
    },
    # ── Out-of-scope: Patent registry ─────────────────────────────────────────
    {
        "question": (
            "What is the USPTO registration number and filing date for the patents "
            "referenced in the ENERGOUS Strategic Alliance Agreement?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "out_of_scope",
        "mismatch_type": "patent_registry",
    },
    # ── Out-of-scope: Immigration ─────────────────────────────────────────────
    {
        "question": (
            "What H-1B visa sponsorship or immigration requirements apply to "
            "personnel assigned under the development agreements?"
        ),
        "ground_truth": (
            "I cannot answer this based on the provided documents. "
            "No relevant context was found."
        ),
        "intent": "GUARDRAIL",
        "synthesizer": "HAND_WRITTEN",
        "doc_category": "out_of_scope",
        "mismatch_type": "immigration_law",
    },
]


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def load_checkpoint() -> list[dict]:
    """Load previously saved questions from the checkpoint file."""
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, encoding="utf-8") as f:
                records = json.load(f)
            logger.info(
                "Resuming from checkpoint — %d questions already saved.", len(records)
            )
            return records
        except Exception as exc:
            logger.warning("Could not read checkpoint (%s) — starting fresh.", exc)
    return []


def save_checkpoint(records: list[dict]) -> None:
    """Atomically write records to the checkpoint file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    tmp.replace(CHECKPOINT_FILE)
    logger.info("Checkpoint saved: %d questions total.", len(records))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_category(filename: str) -> str:
    """Return document category from filename (upper-cased for matching)."""
    upper = filename.upper()
    for pattern, category in _CATEGORY_PATTERNS:
        if pattern in upper:
            return category
    # JOINT FILING AGREEMENT (e.g. Galera) → treat as development-adjacent
    if "JOINT FILING" in upper:
        return "development"
    return "development"  # safe fallback for unknown agreement types


def load_pdfs_as_lc_documents(pdf_paths: list[Path]) -> list[Document]:
    """
    Extract text from each PDF using the pipeline's PyMuPDF parser and wrap
    each page as a LangChain Document.  One Document per page preserves
    page-level metadata and gives RAGAS fine-grained context to work with.
    """
    docs: list[Document] = []
    for pdf_path in pdf_paths:
        try:
            all_pages = extract_pages_from_pdf(str(pdf_path))
            cat = _detect_category(pdf_path.name)
            # Cap pages per PDF to keep total KG LLM calls manageable under Groq
            # rate limits. Legal agreements front-load key provisions, so first N
            # pages are the highest-signal source for question synthesis.
            pages = all_pages[:MAX_PAGES_PER_DOC]
            for page_num, text in pages:
                if text.strip():
                    docs.append(Document(
                        page_content=text,
                        metadata={
                            "source": pdf_path.name,
                            "page": page_num,
                            "doc_category": cat,
                        },
                    ))
            logger.info(
                "Loaded %s (%d/%d pages used, category=%s)",
                pdf_path.name, len(pages), len(all_pages), cat,
            )
        except Exception as exc:
            logger.warning("Skipping %s — extraction failed: %s", pdf_path.name, exc)
    return docs


def sample_pdfs_per_category(
    pdf_paths: list[Path], cap: int
) -> list[Path]:
    """
    Stratified sample: up to *cap* PDFs per doc category.
    Sampling is seeded for reproducibility.

    Non-Compete has only 3 docs → all 3 are always included.
    Strategic Alliance has 5 → up to *cap* included.
    """
    rng = random.Random(RANDOM_SEED)
    by_cat: dict[str, list[Path]] = {}
    for p in pdf_paths:
        cat = _detect_category(p.name)
        by_cat.setdefault(cat, []).append(p)

    selected: list[Path] = []
    for cat, paths in sorted(by_cat.items()):
        rng.shuffle(paths)
        chosen = paths[:cap]
        selected.extend(chosen)
        logger.info(
            "Category %-20s : %d/%d PDFs selected",
            cat, len(chosen), len(paths),
        )
    return selected


def map_intent(synthesizer_name: str) -> str:
    return _INTENT_MAP.get(synthesizer_name.lower(), "FACT")


# ── Main generation logic ─────────────────────────────────────────────────────

def generate_auto_questions(
    lc_docs: list[Document],
    synthesis_llm: "InstructorBaseRagasLLM",
    transforms_llm: "InstructorBaseRagasLLM",
    target: int,
) -> pd.DataFrame:
    """
    Run RAGAS TestsetGenerator and return a DataFrame with columns:
      question, ground_truth, reference_contexts, intent, synthesizer, doc_category
    """
    from ragas.testset import TestsetGenerator
    from ragas.testset.synthesizers import (
        SingleHopSpecificQuerySynthesizer,
        MultiHopAbstractQuerySynthesizer,
        MultiHopSpecificQuerySynthesizer,
    )
    from ragas.testset.transforms import default_transforms_for_prechunked, CustomNodeFilter
    from ragas.run_config import RunConfig
    from ragas.embeddings import LangchainEmbeddingsWrapper

    # Use the same embedding model as the production pipeline
    from app.database import embeddings as pipeline_embeddings

    # Build the TestsetGenerator directly from our own ragas LLM instead of
    # TestsetGenerator.from_langchain(): a LangChain chat model (e.g. ChatOllama)
    # gets dispatched through RAGAS's is_langchain_llm() branch, which always
    # calls the LangChain model's async agenerate_prompt() — and RAGAS calls
    # ragas.async_utils.run() (a fresh asyncio.run(), i.e. a brand-new event
    # loop) separately for the transforms stage, persona generation, AND
    # scenario generation. A LangChain chat model's cached async HTTP client is
    # bound to whichever loop existed at first use, so it breaks the moment a
    # *second* stage touches it — persona generation would succeed, then
    # scenario generation fails with "Event loop is closed" (reproduced with a
    # freshly-built ChatOllama per batch — the mismatch happens *within* one
    # batch, not just across batches). synthesis_llm is an OllamaStructuredLLM,
    # same event-loop-safe sync-only class as transforms_llm, so this doesn't
    # apply here.
    generator = TestsetGenerator(
        llm=synthesis_llm,
        embedding_model=LangchainEmbeddingsWrapper(pipeline_embeddings),
        llm_context=LLM_CONTEXT,
    )

    query_distribution = [
        (SingleHopSpecificQuerySynthesizer(llm=generator.llm, llm_context=LLM_CONTEXT), FACT_WEIGHT),
        (MultiHopAbstractQuerySynthesizer(llm=generator.llm, llm_context=LLM_CONTEXT), MULTIHOP_ABSTRACT_WEIGHT),
        (MultiHopSpecificQuerySynthesizer(llm=generator.llm, llm_context=LLM_CONTEXT), MULTIHOP_SPECIFIC_WEIGHT),
    ]

    # default_transforms_for_prechunked skips HeadlinesExtractor + HeadlineSplitter.
    # HeadlinesExtractor can miss nodes on extraction failure, leaving HeadlineSplitter
    # with nodes that have no 'headlines' property → hard crash.
    # Our page-level docs are already the right granularity; generate_with_chunks
    # registers them as CHUNK nodes so the prechunked transforms apply directly.
    prechunked_transforms = default_transforms_for_prechunked(
        llm=transforms_llm,
        embedding_model=generator.embedding_model,
    )
    # Drop CustomNodeFilter: quality filtering adds no value for legal PDF pages,
    # which are substantive by definition, and a single extraction failure here
    # would otherwise abort the entire generation run.
    prechunked_transforms = [
        t for t in prechunked_transforms if not isinstance(t, CustomNodeFilter)
    ]

    # Flatten Parallel blocks so every LLM-based extractor runs sequentially.
    # Ollama serves one model at a time by default; firing ThemesExtractor and
    # NERExtractor concurrently just queues on the same local server anyway, so
    # running them sequentially avoids piling up concurrent requests for no benefit.
    try:
        from ragas.testset.transforms import Parallel as RagasParallel
    except ImportError:
        from ragas.testset.transforms.engine import Parallel as RagasParallel  # type: ignore

    flat_transforms: list = []
    for t in prechunked_transforms:
        if isinstance(t, RagasParallel):
            flat_transforms.extend(t.transformations)
        else:
            flat_transforms.append(t)
    prechunked_transforms = flat_transforms

    # ragas.testset.transforms.engine.apply_transforms lets every node finish (a node
    # whose extractor returns non-JSON text just logs "Task failed" and keeps that
    # property unset) but then re-raises the first exception it saw. raise_exceptions=False
    # on generate_with_chunks only covers the synthesis step, so that re-raise still
    # propagates and aborts the whole batch even when 59/60 nodes succeeded. Patch it to
    # log and continue instead, same rationale as dropping CustomNodeFilter above.
    import ragas.testset.transforms.engine as _ragas_engine

    if not getattr(_ragas_engine.run_async_tasks, "_patched_non_fatal", False):
        _original_run_async_tasks = _ragas_engine.run_async_tasks

        def _non_fatal_run_async_tasks(*args, **kwargs):
            try:
                return _original_run_async_tasks(*args, **kwargs)
            except Exception as exc:
                logger.warning("Transform step had partial node failures, continuing: %s", exc)
                return []

        _non_fatal_run_async_tasks._patched_non_fatal = True
        _ragas_engine.run_async_tasks = _non_fatal_run_async_tasks

    run_config = RunConfig(
        timeout=300,
        max_retries=2,   # instructor already retries heavily on validation failure; this is a safety net
        max_wait=120,
        max_workers=1,   # single-threaded — avoid piling up concurrent requests on one local Ollama server
    )

    logger.info(
        "Starting RAGAS TestsetGenerator (prechunked): target=%d, chunks=%d, "
        "dist=[FACT=%.0f%%, MHAbstract=%.0f%%, MHSpecific=%.0f%%]",
        target, len(lc_docs),
        FACT_WEIGHT * 100, MULTIHOP_ABSTRACT_WEIGHT * 100, MULTIHOP_SPECIFIC_WEIGHT * 100,
    )

    testset = generator.generate_with_chunks(
        chunks=lc_docs,
        testset_size=target,
        transforms=prechunked_transforms,
        query_distribution=query_distribution,
        run_config=run_config,
        raise_exceptions=False,   # survive individual synthesis failures
    )

    raw_df = testset.to_pandas()
    logger.info("RAGAS generated %d samples (requested %d)", len(raw_df), target)

    # Normalise column names to our schema
    rows = []
    for _, row in raw_df.iterrows():
        synth = str(row.get("synthesizer_name", "")).strip()
        contexts = row.get("reference_contexts") or []
        if not isinstance(contexts, list):
            contexts = [str(contexts)] if contexts else []

        rows.append({
            "question":           str(row.get("user_input", "")).strip(),
            "ground_truth":       str(row.get("reference", "")).strip(),
            "reference_contexts": contexts,
            "intent":             map_intent(synth),
            "synthesizer":        synth or "unknown",
            "doc_category":       "auto",  # RAGAS doesn't expose source file in output
        })

    return pd.DataFrame(rows)


def generate_in_batches(
    lc_docs: list[Document],
    synthesis_llm: "InstructorBaseRagasLLM",
    transforms_llm: "InstructorBaseRagasLLM",
    total_target: int,
) -> pd.DataFrame:
    """Generate questions BATCH_SIZE at a time, saving a checkpoint after each batch.

    On restart the checkpoint is loaded automatically so only the remaining
    questions are generated.  If a KeyboardInterrupt occurs, whatever has been
    saved so far is preserved and generation stops cleanly.
    """
    checkpoint = load_checkpoint()

    if len(checkpoint) >= total_target:
        logger.info(
            "Checkpoint already has %d/%d questions — skipping generation.",
            len(checkpoint), total_target,
        )
        return pd.DataFrame(checkpoint)

    batch_num = 0
    while len(checkpoint) < total_target:
        remaining = total_target - len(checkpoint)
        batch_size = min(BATCH_SIZE, remaining)
        batch_num += 1

        logger.info(
            "── Batch %d: generating %d question(s)  (%d/%d done) ──",
            batch_num, batch_size, len(checkpoint), total_target,
        )

        try:
            batch_df = generate_auto_questions(
                lc_docs, synthesis_llm, transforms_llm, target=batch_size,
            )
            new_records = batch_df.to_dict(orient="records")

        except KeyboardInterrupt:
            logger.info(
                "Interrupted by user — %d/%d questions saved to checkpoint.",
                len(checkpoint), total_target,
            )
            break

        except Exception as exc:
            logger.error(
                "Batch %d failed: %s\n"
                "%d questions saved — stopping. Re-run to resume.",
                batch_num, exc, len(checkpoint),
            )
            break

        if new_records:
            # Deduplicate against already-saved questions before extending.
            # Each batch rebuilds the KG from the same doc set so duplicates
            # across batches are expected without this guard.
            seen_questions = {r["question"].strip().lower() for r in checkpoint}
            unique_records = [
                r for r in new_records
                if r["question"].strip()  # drop empty synthesis failures
                and r["question"].strip().lower() not in seen_questions
            ]
            dropped = len(new_records) - len(unique_records)
            if dropped:
                logger.warning(
                    "Batch %d: dropped %d duplicate/empty question(s)",
                    batch_num, dropped,
                )
            checkpoint.extend(unique_records)
            save_checkpoint(checkpoint)
            logger.info(
                "Batch %d complete: +%d new  (%d/%d total)",
                batch_num, len(unique_records), len(checkpoint), total_target,
            )
        else:
            logger.warning(
                "Batch %d returned 0 questions (all synthesis attempts failed) — "
                "skipping cooldown and retrying.",
                batch_num,
            )
            continue

        if len(checkpoint) < total_target:
            logger.info(
                "Cooling down %ds before next question (laptop thermal relief) …",
                QUESTION_COOLDOWN_SECS,
            )
            time.sleep(QUESTION_COOLDOWN_SECS)

    return pd.DataFrame(checkpoint) if checkpoint else pd.DataFrame()


def build_guardrail_df() -> pd.DataFrame:
    rows = []
    for q in _GUARDRAIL_QUESTIONS:
        rows.append({
            "question":           q["question"],
            "ground_truth":       q["ground_truth"],
            "reference_contexts": [],  # guardrail questions have no expected context
            "intent":             "GUARDRAIL",
            "synthesizer":        "HAND_WRITTEN",
            "doc_category":       q["doc_category"],
        })
    return pd.DataFrame(rows)


def save_outputs(df: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON (rich format) ────────────────────────────────────────────────────
    json_path = output_dir / "golden_dataset_v2.json"
    records = df.to_dict(orient="records")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info("Saved JSON → %s  (%d records)", json_path, len(records))

    # ── CSV (eval-script-compatible flat format) ───────────────────────────────
    # reference_contexts is JSON-encoded so it survives CSV round-trips
    csv_df = df.copy()
    csv_df["reference_contexts"] = csv_df["reference_contexts"].apply(json.dumps)
    csv_path = output_dir / "golden_dataset_v2.csv"
    csv_df.to_csv(csv_path, index=False, encoding="utf-8")
    logger.info("Saved CSV  → %s  (%d rows)", csv_path, len(csv_df))


def print_summary(df: pd.DataFrame) -> None:
    total = len(df)
    print("\n" + "=" * 60)
    print(f"  Golden Dataset v2 — {total} questions total")
    print("=" * 60)
    print(df.groupby(["intent", "synthesizer"]).size().to_string())
    print("=" * 60)
    fact_n = (df["intent"] == "FACT").sum()
    anal_n = (df["intent"] == "ANALYTICAL").sum()
    guard_n = (df["intent"] == "GUARDRAIL").sum()
    print(f"  FACT        {fact_n:3d}  ({fact_n/total*100:.0f}%)")
    print(f"  ANALYTICAL  {anal_n:3d}  ({anal_n/total*100:.0f}%)")
    print(f"  GUARDRAIL   {guard_n:3d}  ({guard_n/total*100:.0f}%)")
    print("=" * 60 + "\n")


def main() -> None:
    logger.info(
        "Config: BATCH_SIZE=%d  QUESTION_COOLDOWN=%ds  MAX_RETRIES=%d  "
        "DOCS_PER_CATEGORY=%d  MAX_PAGES_PER_DOC=%d",
        BATCH_SIZE, QUESTION_COOLDOWN_SECS, MAX_RETRIES,
        DOCS_PER_CATEGORY, MAX_PAGES_PER_DOC,
    )
    logger.info(
        "Synthesis: Ollama %s @ %s  |  Transforms: Ollama %s @ %s (both via OllamaStructuredLLM)",
        OLLAMA_MODEL, OLLAMA_BASE_URL, TRANSFORMS_OLLAMA_MODEL, OLLAMA_BASE_URL,
    )

    # ── 1. Collect and sample PDFs ────────────────────────────────────────────
    all_pdfs = sorted(
        [p for p in DOCS_DIR.iterdir() if p.suffix.lower() == ".pdf"],
        key=lambda p: p.name,
    )
    if not all_pdfs:
        raise FileNotFoundError(f"No PDFs found in {DOCS_DIR}")

    logger.info("Found %d PDFs in %s", len(all_pdfs), DOCS_DIR)
    sampled_pdfs = sample_pdfs_per_category(all_pdfs, cap=DOCS_PER_CATEGORY)
    logger.info("Using %d PDFs for knowledge-graph build", len(sampled_pdfs))

    # ── 2. Load as LangChain Documents ───────────────────────────────────────
    lc_docs = load_pdfs_as_lc_documents(sampled_pdfs)
    if not lc_docs:
        raise RuntimeError("No pages extracted — check PDF files and pdf_parser.")
    logger.info("Loaded %d page-level Documents for RAGAS", len(lc_docs))

    # ── 3. Initialise LLMs ───────────────────────────────────────────────────
    # Both synthesis and transforms use OllamaStructuredLLM (a sync-only client)
    # rather than LangChain's ChatOllama: RAGAS calls ragas.async_utils.run()
    # (a fresh asyncio.run() / event loop) separately per stage — transforms,
    # persona generation, scenario generation, question generation — and any
    # LLM with a cached async HTTP client breaks the moment a second stage
    # reuses it ("Event loop is closed"). The sync client has no such binding,
    # so both can safely be built once here and reused across every stage.
    synthesis_llm = OllamaStructuredLLM(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
        num_predict=4096,
        max_retries=MAX_RETRIES,
    )
    transforms_llm = OllamaStructuredLLM(
        model=TRANSFORMS_OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
        num_predict=4096,
        max_retries=MAX_RETRIES,
    )

    # ── 4. Auto-generate FACT + ANALYTICAL questions (batched, resumable) ────
    auto_df = generate_in_batches(
        lc_docs,
        synthesis_llm=synthesis_llm,
        transforms_llm=transforms_llm,
        total_target=AUTO_GEN_COUNT,
    )

    if auto_df.empty:
        logger.warning(
            "No auto-generated questions produced. "
            "Saving guardrail-only dataset and exiting."
        )

    # ── 5. Append hand-written GUARDRAIL questions ────────────────────────────
    guardrail_df = build_guardrail_df()
    full_df = pd.concat([auto_df, guardrail_df], ignore_index=True) if not auto_df.empty else guardrail_df

    # ── 6. Save outputs ───────────────────────────────────────────────────────
    save_outputs(full_df, OUTPUT_DIR)
    print_summary(full_df)

    # Clean up checkpoint only on fully successful run
    if len(auto_df) >= AUTO_GEN_COUNT and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("Checkpoint removed — generation complete.")


if __name__ == "__main__":
    main()
