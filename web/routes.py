import queue
import re
import shutil
import signal
import time
import subprocess
import threading
import pandas as pd
from flask import render_template, url_for, flash, redirect, request, make_response, jsonify, abort, session, send_file, g
from web import app
from web.apis.sample_explorer_api import SampleExplorerAPI
from web.apis import sra_web_api
from web.apis.morphic_data_api import MorphicAPI
from web.utils import utils, sample_explorer_utils
from .forms import SearchForm, BwbForm, create_results_table_form
import requests
from werkzeug.utils import secure_filename
import json
from collections import defaultdict


import uuid
import os
import socket
import io

STORAGE_ID='storageID'
if "BWB_SCHED_DIR" not in os.environ:
    BWB_SCHED_DIR = os.path.expanduser("~/SCHED_STORAGE")
else:
    BWB_SCHED_DIR = os.environ["BWB_SCHED_DIR"]
    
pathToMake = os.path.join(BWB_SCHED_DIR, STORAGE_ID)
print("MAKING STORAGE DIR", pathToMake)
os.makedirs(pathToMake, exist_ok=True)


class JobManager:
    def __init__(self):
        self.queue = queue.Queue()
        self.current_job = None
        self.lock = threading.Lock()
        self.jobs = {}          # job_id -> job info
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()

    def submit(self, cmd, output_dir=None):
        job_id = str(uuid.uuid4())
        job_info = {
            "id": job_id,
            "cmd": cmd,
            "status": "queued",
            "result": None,
            "start_time": None,
            "end_time": None,
            "container_name": job_id,  # container will use job_id as name
            "output_dir": output_dir,  # where this job's plots/counts are written, if job-scoped
        }
        with self.lock:
            self.jobs[job_id] = job_info
        self.queue.put(job_id)
        return job_id

    def worker_loop(self):
        while True:
            job_id = self.queue.get()

            with self.lock:
                job = self.jobs[job_id]
                job["status"] = "running"
                job["start_time"] = time.time()
                self.current_job = job_id

            # modify cmd to include --name
            cmd_with_name = job["cmd"].replace("docker run", f"docker run --name {job_id}")

            try:
                proc = subprocess.Popen(
                    cmd_with_name,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                with self.lock:
                    job["proc"] = proc  # store process if needed

                stdout, stderr = proc.communicate()

                with self.lock:
                    if job["status"] == "canceled":
                        job["result"] = "Job was canceled."
                    elif proc.returncode == 0:
                        job["status"] = "done"
                        job["result"] = stdout.decode()
                    else:
                        job["status"] = f"error: {stderr.decode()}"

            except Exception as e:
                with self.lock:
                    job["status"] = "error"
                    job["result"] = str(e)

            finally:
                with self.lock:
                    job["end_time"] = time.time()
                    self.current_job = None
                    job.pop("proc", None)

            time.sleep(0.1)

    def cancel_running_job(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False, "not found"
            if job["status"] != "running":
                return False, "not running"
            job["status"] = "canceled"

        # kill docker container by name
        try:
            subprocess.run(
                ["docker", "kill", job["container_name"]],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return True, "killed"
        except subprocess.CalledProcessError as e:
            return False, f"docker kill failed: {e.stderr.decode()}"

    def get_status(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                return {"error": "job not found"}
            job = self.jobs[job_id]
            position = None
            if job["status"] == "queued":
                ids_in_queue = list(self.queue.queue)
                position = ids_in_queue.index(job_id) + 1 if job_id in ids_in_queue else None
            return {
                "id": job_id,
                "status": job["status"],
                "queue_position": position,
                "result": job["result"] if job["status"] in ("done", "error") else None,
            }

JOB_MANAGER = JobManager()

DEFAULT_TABLES_DIR = os.path.join(BWB_SCHED_DIR, STORAGE_ID, "processing", "Tables")

def get_job_output_dir(job_id):
    """
    Resolve the directory a job's plots (heatmap.png, volcano_plot.png,
    pca_plot.png) and genesCounts.csv live in.

    Jobs submitted with a job-scoped output_dir (the direct rnotebook
    container path) use that. Everything else (the bulkrna_full.json
    scheduler path, or an unknown/expired job_id) falls back to the shared
    static path that bwbSched has always written its "13.tablesDir" output to.
    """
    with JOB_MANAGER.lock:
        job = JOB_MANAGER.jobs.get(job_id)
    if job and job.get("output_dir"):
        return job["output_dir"]
    return DEFAULT_TABLES_DIR

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/explore")
def explore():
    return render_template("explore.html")

@app.route("/bwb")
def homepage():
    return render_template("bwb_page.html")

@app.route("/queue_position", methods=["GET"])
def get_queue():
    user_uuid = session.get("uuid")
    if not user_uuid:
        return jsonify({"error": "search query is required"}), 400
    response = SampleExplorerAPI().get_queue_position(user_uuid)
    if response:
        return jsonify(response), 200
    return jsonify({"error": "error getting queue position"}), 500

@app.route("/download_data", methods=["GET"])
def get_download_data():
    user_uuid = session.get("uuid")
    lines = session.get("lines")
    if not user_uuid or not lines:
        return jsonify({"error": "A search with amount of lines is required"}), 400
    response_file = SampleExplorerAPI().get_download_file(user_uuid, lines)
    if response_file is None:
        return jsonify({"error": "Error getting download file"}), 500
    zip_file = io.BytesIO(response_file.content)
    return send_file(zip_file, as_attachment=True, download_name="testing-search-results.zip", mimetype="application/zip")

@app.route("/search", methods=["GET", "POST"])
def search():
    form = SearchForm()

    if form.validate_on_submit():
        user_uuid = str(uuid.uuid4())

        query = form.query.data
        genes = form.genes.data
        expansion_strategy = form.expansion_strategy.data
        size = form.size.data

        if expansion_strategy == "semantic_transcriptome":
            search_type = "semantic"
            expand = "transcriptome"
        else:
            search_type = "semantic"
            expand = "semantic"

        has_query = bool(query)
        has_genes = bool(genes)

        if genes:
            genes = utils.format_genes_from_str_to_list(genes)

        q_response = SampleExplorerAPI().make_query(user_uuid, has_query, query, has_genes, genes, search_type, expand)

        if "status" in q_response and q_response["status"] == "queued":
            session["uuid"] = user_uuid
            if size:
                session["lines"] = int(size)
            session.pop("gse_sample_type", None)
            return render_template("search.html", result=q_response, success=True, form=form)

        if "status" in q_response:
            print("status:", q_response["status"])
            return render_template("search.html", result=q_response, success=False, form=form)

        return render_template("search.html", result={"data": {"error": "There was an error making a search"}}, success=False, form=form)

    return render_template("search.html", form=form)

@app.route("/search/status", methods=["GET"])
def search_status():
    return render_template("search_status.html")

@app.route("/search-results", methods=["GET"])
def search_results():
    if "uuid" not in session or "lines" not in session:
        return render_template("search_results.html")

    user_uuid = session["uuid"]
    lines = session["lines"]

    results = SampleExplorerAPI().get_data_output(user_uuid, lines)
    if not results:
        return render_template("search_results.html")

    results = sample_explorer_utils.reshape_data(results)
    gse_ids_in_results = sample_explorer_utils.get_unique_gse_ids(results)

    if session.get("gse_sample_type") is None:
        session["gse_sample_type"] = {}
    saved_sample_types = session.get("gse_sample_type", {})

    gse_ids_without_types = set(gse_ids_in_results) - set(saved_sample_types.keys())
    library_strategies = sra_web_api.get_library_strategy_for_gse_ids(gse_ids_without_types)
    saved_sample_types.update(library_strategies)
    session["gse_sample_type"] = saved_sample_types

    results = sample_explorer_utils.add_sample_type_to_studies_data(saved_sample_types, results)

    ResultsTableForm = create_results_table_form(gse_ids_in_results)
    form = ResultsTableForm()

    return render_template("search_results.html", data=results, form=form)

# ── JSON API endpoints ─────────────────────────────────────────────────────────

@app.route("/api/morphic-studies", methods=["GET"])
def api_morphic_studies():
    """Return MorPhiC studies catalog as JSON. Pass ?refresh=true to bypass file cache."""
    data_file_name = "morphic_data.json"
    refresh = request.args.get("refresh", "false").lower() == "true"
    morphic_full_data = utils.load_json_file(data_file_name)

    if morphic_full_data is None or refresh:
        morphic_full_data = MorphicAPI().get_data()
        if morphic_full_data:
            utils.save_json_file(morphic_full_data, data_file_name)

    if morphic_full_data is None:
        return jsonify({"error": "Error loading data"}), 500

    # Assays compatible with workflow
    def is_bulk_rnaseq(readout_assay: str) -> bool:
        assay = readout_assay.lower().strip()
        exclude_assays = [
            r"\bsc[\s-]?rna\b",
            r"\bscrna\b",
            r"\bsingle[- ]cell\b",
            r"\bsnrna\b",
            r"\bsmall rna\b",
            r"\batac[\s-]?seq\b",
            r"\bgrna\b",
        ]
        include_assays = [
            r"\brnaseq\b",
            r"\brna[\s-]?seq\b",
            r"\brna sequencing\b",
            r"\bmrna sequencing\b",
            r"\bmrna\b",
        ]

        excluded = any(re.search(p, assay) for p in exclude_assays)
        included = any(re.search(p, assay) for p in include_assays)
        return included and not excluded

    # Extract GEO and ERP accession ids, ids other than GEO are defaulted to ERP
    def extract_accessions(accessions: list) -> dict:
        study_accessions = {"erp_accession": "", "geo_accession": ""}
        for acc_id in accessions:
            if "gse" in acc_id.lower():
                study_accessions["geo_accession"] = acc_id
            else:
                study_accessions["erp_accession"] = acc_id
        return study_accessions

    # Select relevant study information
    studies = morphic_full_data['_embedded']['studies']
    data = []
    for study in studies:
        study_content = study.get("content", {})
        study_accessions = study.get("accessions", [])
        if not study_content and not study_accessions:
            continue
        study_readout_assay = study_content.get("readout_assay", "")
        if not study_readout_assay:
            continue
        if not is_bulk_rnaseq(study_readout_assay):
            continue

        # Get ERP ID from GSE ID, add ERP ID to available accessions
        has_erp = any("erp" in s.lower() for s in study_accessions)
        gse_id = next((s for s in study_accessions if "gse" in s.lower()), "")
        if not has_erp and gse_id:
            study_accessions.append(sra_web_api.get_erp_from_gse_id(gse_id))
        
        new_study = {
            "study_title": study_content.get("study_title", ""),
            "target_genes": study_content.get("target_genes", ""),
            "readout_assay": study_readout_assay
        }
        new_study.update(extract_accessions(study_accessions))
        data.append(new_study)
    return jsonify(data)

@app.route("/api/fetch-metadata", methods=["POST"])
def api_fetch_metadata():
    """Fetch SRA run metadata for a list of external accession IDs. Returns JSON."""
    body = request.get_json(silent=True) or {}
    gse_ids = body.get("gse_ids", [])
    if not gse_ids:
        return jsonify({"error": "No IDs provided"}), 400

    api_response = sra_web_api.get_metadata_for_gse_ids(gse_ids, file_name="metadata.csv")
    ids_with_no_metadata = (api_response or {}).get("ids_with_no_metadata", [])

    metadata_df = utils.load_csv_file_as_df("metadata.csv")
    if metadata_df is None:
        return jsonify({"error": "No metadata found", "ids_with_no_metadata": ids_with_no_metadata}), 404

    return jsonify({
        "metadata": json.loads(metadata_df.to_json(orient="records")),
        "ids_with_no_metadata": ids_with_no_metadata,
    })

@app.route("/api/fetch-morphic-metadata", methods=["POST"])
def api_fetch_morphic_metadata():
    """Look up per-sample metadata for MorPhiC GSE ids from perSampleMetadata.tsv. Returns JSON.

    Unlike /api/fetch-metadata, this never calls out to the SRA API — MorPhiC
    sample metadata (cell line, knockout gene, time point) is sourced entirely
    from perSampleMetadata.tsv.
    """
    body = request.get_json(silent=True) or {}
    gse_ids = body.get("gse_ids", [])
    if not gse_ids:
        return jsonify({"error": "No IDs provided"}), 400

    try:
        metadata_df = utils.get_morphic_metadata_for_gse_ids(gse_ids)
    except (ValueError, FileNotFoundError, KeyError) as e:
        return jsonify({"error": str(e)}), 422

    return jsonify({
        "metadata": json.loads(metadata_df.to_json(orient="records")),
        "ids_with_no_metadata": [],
    })

@app.route('/experiment/<srr_id>/bulk-rna-seq', methods=['GET'])
def is_human_bulk_rna_seq(srr_id):
    """Determines if SRR ID is human bulk RNA-seq"""

    try:
        # Get metadata for SRR ID
        metadata_df = sra_web_api.get_metadata_for_accession_id(srr_id)

        if metadata_df is None or metadata_df.empty:
            return jsonify({"error": "Could not determine if accession ID is human bulk RNA-seq"}), 422
        
        # Normalize columns
        metadata_df.columns = [c.lower() for c in metadata_df.columns]
        
        # Check organism
        is_human = metadata_df['organism_name'].str.contains("Homo sapiens", case=False, na=False).any()

        # Check RNA-seq
        is_rnaseq = metadata_df['library_strategy'].str.contains("RNA-seq", case=False, na=False).any()

        # Check bulk vs single-cell
        is_single_cell = metadata_df.apply(
            lambda row: any(
                kw in str(row).lower()
                for kw in ["single-cell", "scrna", "10x", "smart-seq"]
            ), axis=1
        ).any()

        is_bulk = is_rnaseq and not is_single_cell

        if not (is_human and is_rnaseq and is_bulk):
            return jsonify({"error": "Accession ID was not bulk RNA-seq"}), 422

        return jsonify({"id": srr_id, "is_human_bulk_rna_seq": is_human and is_rnaseq and is_bulk}), 200
    except Exception:
        return jsonify({"error": "Something went wrong"}), 500

# ── Page routes ────────────────────────────────────────────────────────────────

@app.route("/morphic", methods=["GET"])
def morphic_data():
    return render_template("morphic_data.html")

@app.route("/morphic/refresh-data", methods=["GET"])
def morphic_refresh_data():
    data_file_name = "morphic_data.json"
    fresh = MorphicAPI().get_data()
    if fresh:
        utils.save_json_file(fresh, data_file_name)
    return redirect("/morphic")

@app.route("/metadata", methods=["GET"])
def metadata():
    return render_template("metadata.html")

@app.route("/cancel-job/<job_id>", methods=["POST"])
def cancel_job(job_id):
    with JOB_MANAGER.lock:
        job = JOB_MANAGER.jobs.get(job_id)
        if not job:
            return jsonify({"error": "not found"}), 404

    if job["status"] == "queued":
        try:
            JOB_MANAGER.queue.queue.remove(job_id)
            job["status"] = "canceled"
            return jsonify({"status": "canceled"})
        except ValueError:
            pass

    ok, msg = JOB_MANAGER.cancel_running_job(job_id)
    if ok:
        return jsonify({"status": "killed"})
    return jsonify({"error": msg}), 400

@app.route("/job-status/<job_id>", methods=["GET"])
def job_status(job_id):
    return jsonify(JOB_MANAGER.get_status(job_id))

def write_metadata_json(samples, srr_groups, srr_entries, output_path):
    grouped = defaultdict(list)

    for sample in samples:
        grouped[sample["group"]].append({
            "srr_id": sample["name"],
            "layout": sample["layout"],
            "preprocessed": False,
        })

    if srr_groups:
        for group in srr_groups:
            group_name = group.get("name")
            for srr_id in group.get("samples", []):
                grouped[group_name].append({
                    "srr_id": srr_id,
                    "layout": "PAIRED",
                    "preprocessed": True,
                })

    for entry in (srr_entries or []):
        grouped[entry["group"]].append({
            "srr_id": entry["id"],
            "layout": "PAIRED",
            "preprocessed": False,
        })

    metadata = {
        "groups": [
            {"name": group_name, "samples": group_samples}
            for group_name, group_samples in grouped.items()
        ]
    }

    with open(output_path, "w") as fh:
        json.dump(metadata, fh, indent=2)

# Key assumptions of bulkrna.json:
#   - All paired end fastq files are named "sample_1.fastq" and "sample_2.fastq"
#   - There is an entry in metadata.json corresponding to each SRR ID / user uploaded file.
#   - If the sample name "sample" (key "srr_id" in metadata.json, which is actually kind of a misnomer)
#     exists, then the file "sample_1.fastq" (and possibly its R2) are present in the directory passed
#     as Start.fastqdir.
@app.route("/run-bwb", methods=["POST"])
def run_bwb():
    form = BwbForm()

    if not form.validate_on_submit():
        return render_template("dash.html", form=form, status=-1)

    randStr = str(uuid.uuid4())
    shutil.copy("./mergedCounts.tsv", os.path.join(BWB_SCHED_DIR, STORAGE_ID, "mergedCounts.tsv"))
    upload_root = os.path.join(BWB_SCHED_DIR, STORAGE_ID, randStr)
    os.makedirs(upload_root, exist_ok=True)

    raw = form.sra_ids.data or ""
    sra_ids = [s.strip() for s in re.split(r"[\s,]+", raw) if s.strip()]

    # Read group/sample assignments from the serialised state the client submits
    srr_metadata_json = request.form.get("srr_metadata_json", "")
    srr_groups = None
    if srr_metadata_json:
        try:
            srr_metadata = json.loads(srr_metadata_json)
            srr_groups = srr_metadata.get("groups") or None
        except (json.JSONDecodeError, TypeError):
            pass
    print("srr_groups:", srr_groups)

    sample_indices = sorted(
        set(
            key.split("[", 1)[1].split("]", 1)[0]
            for key in request.form
            if key.startswith("samples[") and key.endswith("][name]")
        )
    )

    if not sample_indices and not srr_groups:
        form.workflow.errors.append("No samples or SRR IDs were provided.")
        return render_template("dash.html", form=form, status=-1)

    first_layout = None
    if sample_indices:
        first_layout = request.form.get(f"samples[{sample_indices[0]}][layout]")
        if first_layout not in {"SINGLE", "PAIRED"}:
            form.workflow.errors.append("Invalid read layout for the first sample.")
            return render_template("dash.html", form=form, status=-1)

    samples = []
    userUploadedFiles = False
    for idx in sample_indices:
        prefix = f"samples[{idx}]"
        name   = request.form.get(f"{prefix}[name]")
        group  = request.form.get(f"{prefix}[group]")
        layout = request.form.get(f"{prefix}[layout]")

        if layout != first_layout:
            form.workflow.errors.append(
                f"Sample {name or idx} has layout {layout}, "
                f"but all samples must be {first_layout}."
            )
            return render_template("dash.html", form=form, status=-1)

        r1 = request.files.get(f"{prefix}[r1]")
        r2 = request.files.get(f"{prefix}[r2]")

        sample_dir = upload_root
        os.makedirs(sample_dir, exist_ok=True)

        r1_path = None
        if r1 and r1.filename:
            userUploadedFiles = True
            r1_path = os.path.join(sample_dir, f"{name}_1.fastq")
            r1.save(r1_path)

        r2_path = None
        if layout == "PAIRED":
            if not r2 or not r2.filename:
                form.workflow.errors.append(f"Sample {name}: R2 FASTQ is required for paired-end layout.")
                return render_template("dash.html", form=form, status=-1)
            r2_path = os.path.join(sample_dir, f"{name}_2.fastq")
            r2.save(r2_path)

        samples.append({"name": name, "group": group, "layout": layout, "r1": r1_path, "r2": r2_path})

    print(f"USER UPLOADED FILES: {userUploadedFiles}")
    metadata_path     = os.path.join(upload_root, "metadata.json")
    metadata_cnt_path = os.path.join("/data", randStr, "metadata.json")

    srr_entries = []
    i = 0
    while True:
        srr_id    = request.form.get(f"srr_entries[{i}][id]", "").strip()
        srr_group = request.form.get(f"srr_entries[{i}][group]", "").strip()
        if not srr_id and not srr_group:
            break
        if srr_id:
            srr_entries.append({"id": srr_id, "group": srr_group})
        i += 1

    write_metadata_json(samples=samples, srr_groups=srr_groups, srr_entries=srr_entries, output_path=metadata_path)

    srr_ids = []
    if srr_groups:
        for group in srr_groups:
            srr_ids.extend(group.get("samples", []))
    srrIds = "[" + ",".join(srr_ids) + "]"
    print("SRR IDs:", ",".join(srr_ids) if srr_ids else "None")

    manual_sra_ids = [e["id"] for e in srr_entries]
    sraIds = "[" + ",".join(manual_sra_ids) + "]"

    output_dir = None

    if userUploadedFiles or manual_sra_ids:
        cmd = (
            f"docker run -v /var/run/docker.sock:/var/run/docker.sock "
            f"-v \"$(pwd)\":/wfs "
            f"-v {BWB_SCHED_DIR}:{BWB_SCHED_DIR} "
            f"-e BWB_SCHED_DIR={BWB_SCHED_DIR} "
            f"patrickmckeever/bwb_scheduler:latest bwbSched run "
            f"--docker --noTemporal -v --storageId {STORAGE_ID} "
            f"-p Start.fastqdir=/data/{randStr} "
            f"-p Start.metadata_json={metadata_cnt_path} "
            f"-p Start.samplesToRetain={srrIds} "
            f"-p Start.srridsAll={sraIds} "
            f"-p Start.preprocessedCnts=/data/mergedCounts.tsv "
            f"/wfs/bulkrna_full.json"
        )
    else:
        # No uploaded FASTQs and no manually-entered SRR IDs: every selected
        # sample is a MorPhiC ERR id that already has preprocessed counts in
        # mergedCounts.tsv, so skip the bwbSched/bulkrna_preprocessed.json
        # pipeline entirely and run the rnotebook analysis container directly
        # against a per-job subset of mergedCounts.tsv.
        if not srr_ids:
            form.workflow.errors.append("No samples or SRR IDs were provided.")
            return render_template("dash.html", form=form, status=-1)

        output_dir = os.path.join(upload_root, "processing", "Tables")
        os.makedirs(output_dir, exist_ok=True)
        counts_path = os.path.join(output_dir, "genesCounts.csv")

        merged_counts_path = os.path.join(BWB_SCHED_DIR, STORAGE_ID, "mergedCounts.tsv")
        try:
            utils.subset_counts_file(merged_counts_path, srr_ids, counts_path)
        except ValueError as e:
            form.workflow.errors.append(str(e))
            return render_template("dash.html", form=form, status=-1)

        cmd = (
            f"docker run "
            f"-v {output_dir}:{output_dir} "
            f"-v {metadata_path}:{metadata_path} "
            f"-e counts_dir={output_dir} "
            f"-e metadata_json={metadata_path} "
            f"patrickmckeever/rnotebook:0.3 Rscript /app/pca.R"
        )

    print(cmd)
    job_id = JOB_MANAGER.submit(cmd, output_dir=output_dir)
    return render_template("dash.html", form=form, status=1, job_id=job_id)

@app.route("/heatmap/<job_id>")
def heatmap(job_id):
    if "/" in job_id or ".." in job_id:
        abort(400)
    image_path = os.path.join(get_job_output_dir(job_id), "heatmap.png")
    if not os.path.exists(image_path):
        abort(404)
    return send_file(image_path, mimetype="image/png", conditional=True)

@app.route("/volcano/<job_id>")
def volcano(job_id):
    if "/" in job_id or ".." in job_id:
        abort(400)
    image_path = os.path.join(get_job_output_dir(job_id), "volcano_plot.png")
    if not os.path.exists(image_path):
        abort(404)
    return send_file(image_path, mimetype="image/png", conditional=True)

@app.route("/pca/<job_id>")
def pca(job_id):
    if ".." in job_id or "/" in job_id:
        return "Invalid job ID", 400
    image_path = os.path.join(get_job_output_dir(job_id), "pca_plot.png")
    if not os.path.exists(image_path):
        abort(404)
    return send_file(image_path, mimetype="image/png")

@app.route("/counts/<job_id>")
def counts(job_id):
    if "/" in job_id or ".." in job_id:
        abort(400)
    counts_path = os.path.join(get_job_output_dir(job_id), "genesCounts.csv")
    if not os.path.exists(counts_path):
        abort(404)
    return send_file(counts_path, mimetype="text/csv", as_attachment=True, download_name="genesCounts.csv")

@app.route("/dash")
@app.route("/visualize")
def dash():
    form = BwbForm()
    return render_template("dash.html", form=form)
