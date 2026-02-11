import queue
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
from .forms import SearchForm, BwbForm, GroupForm, create_results_table_form, create_srr_form, create_morphic_form
import requests
from werkzeug.utils import secure_filename
import json
from collections import defaultdict


import uuid
import os
import socket
import io

BWB_SCHED_DIR=os.path.expanduser("~/SCHED_STORAGE")
STORAGE_ID='storageID'

class JobManager:
    def __init__(self):
        self.queue = queue.Queue()
        self.current_job = None
        self.lock = threading.Lock()
        self.jobs = {}          # job_id -> job info
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()

    def submit(self, cmd):
        job_id = str(uuid.uuid4())
        job_info = {
            "id": job_id,
            "cmd": cmd,
            "status": "queued",
            "result": None,
            "start_time": None,
            "end_time": None,
            "container_name": job_id  # container will use job_id as name
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

@app.route("/")
def landing():
    return render_template('landing.html')

@app.route("/explore")
def explore():
    return render_template('explore.html')

# for bwb page
@app.route("/bwb")
def homepage():
    return render_template('bwb_page.html')

@app.route('/queue_position', methods=['GET'])
def get_queue():
    # get user uuid
    user_uuid = session.get('uuid')
    if not user_uuid:
        return jsonify({'error: search query is required'}), 400

    response = SampleExplorerAPI().get_queue_position(user_uuid)

    if response:
        return jsonify(response), 200
    else:
        return jsonify({'error': 'error getting queue position'}), 500

@app.route('/download_data', methods=['GET'])
def get_download_data():
    # retrieve uuid and amount of lines
    user_uuid = session.get('uuid')
    lines = session.get('lines')

    if not user_uuid or not lines:
        return jsonify({'error': 'A search with amount of lines is required'}), 400

    response_file = SampleExplorerAPI().get_download_file(user_uuid, lines)

    if response_file is None:
        return jsonify({'error': 'Error getting download file'}), 500
    zip_file = io.BytesIO(response_file.content)
    return send_file(zip_file, as_attachment=True, download_name='testing-search-results.zip', mimetype='application/zip')

@app.route("/search", methods=['GET','POST'])
def search():
    form = SearchForm()

    if form.validate_on_submit():
        # generate uuid
        user_uuid = str(uuid.uuid4())

        # user inputs
        query = form.query.data
        genes = form.genes.data
        expansion_strategy = form.expansion_strategy.data
        size = form.size.data

        # set search and expand from selected expansion strategy
        if expansion_strategy == 'semantic_transcriptome':
            search = 'semantic'
            expand = 'transcriptome'
        else:
            search = 'semantic'
            expand = 'semantic'

        # check if search query and genes list is in input
        has_query = bool(query)
        has_genes = bool(genes)

        # create a gene set from input genes
        if genes:
            genes = utils.format_genes_from_str_to_list(genes)

        # make a query
        q_response = SampleExplorerAPI().make_query(user_uuid, has_query, query, has_genes, genes, search, expand)

        # when successful status
        if "status" in q_response and q_response["status"] == "queued":
            # save uuid for future use
            session['uuid'] = user_uuid
            # save lines for future use
            if size:
                session['lines'] = int(size)
            # remove session key for previous search results
            if 'gse_sample_type' in session:
                del session['gse_sample_type']

            return render_template('search.html', result=q_response, success=True, form=form)
        # when status is abnormal
        if "status" in q_response:
            print("status:")
            print(q_response["status"])

            return render_template('search.html', result=q_response, success=False, form=form)

        # error after attempting to make a request
        return render_template('search.html', result={"data": {"error": "There was an error making a search"}}, success=False, form=form)
    return render_template('search.html', form=form)

@app.route("/search/status", methods=['GET'])
def search_status():
    return render_template('search_status.html')

# Search results
@app.route("/search-results", methods=['GET', 'POST'])
def search_results():
    if 'uuid' in session and 'lines' in session:
        user_uuid = session.get('uuid')
        lines = session.get('lines')

        # get search results
        search_results = SampleExplorerAPI().get_data_output(user_uuid, lines)
        if not search_results:
            return render_template('search_results.html')

        # split comma separated gse_id's and remove duplicates
        search_results = sample_explorer_utils.reshape_data(search_results)

        gse_ids_in_search_results = sample_explorer_utils.get_unique_gse_ids(search_results)

        # retrieve previously saved gse id's with sample types, Bulk or Single-cell, format: {'gse_id': 'sample-type'}
        if session.get('gse_sample_type') is None:
            # sample_dict = {'GSE141950': 'Bulk', 'GSE141099': 'Bulk', 'GSE126890': 'Bulk', 'GSE86244': 'Bulk', 'GSE140523': 'Bulk'}
            session['gse_sample_type'] = {}
        saved_sample_types = session.get('gse_sample_type', {})

        # diff: gse id's in search results - saved gse ids with sample types
        gse_ids_without_sample_types = set(gse_ids_in_search_results) - set(saved_sample_types.keys())

        # fetch sample types for new gse id's
        library_strategies = sra_web_api.get_library_strategy_for_gse_ids(gse_ids_without_sample_types)

        # save sample types: {'gse_id': 'sample-type'}
        saved_sample_types.update(library_strategies)
        session['gse_sample_type'] = saved_sample_types

        # add sample type to search results
        search_results = sample_explorer_utils.add_sample_type_to_studies_data(saved_sample_types, search_results)

        # Use a Form for gse_id's in result data
        ResultsTableForm = create_results_table_form(gse_ids_in_search_results)
        form = ResultsTableForm()

        if form.validate_on_submit():
            # list of selected/checked inputs
            selected_studies = [checkbox.label.text for checkbox in form if checkbox.data and checkbox.type == 'BooleanField']
            if selected_studies:
                session['gse_ids'] = selected_studies
                return redirect('/metadata')

        return render_template('search_results.html', data=search_results, form=form)
    return render_template('search_results.html')

@app.route("/morphic", methods=['GET', 'POST'])
def morphic_data():
    morphic_api = MorphicAPI()
    morphic_full_data = morphic_api.get_data()

    if morphic_full_data is None:
        return render_template("morphic_data.html", error_message="Error loading data")

    studies = morphic_full_data['_embedded']['studies']
    data = []
    for study in studies:
        study_content = study["content"]
        new_study = {
            "study_title": study_content["study_title"],
            "target_genes": study_content["target_genes"],
            "readout_assay": study_content["readout_assay"],
            "erp_accession": study["accessions"][0],
            "geo_accession": study["accessions"][1]
        }
        data.append(new_study)

    # Create a Form from available gse ids
    morphic_erp_ids = [study["erp_accession"] for study in data]
    MorphicForm = create_morphic_form(morphic_erp_ids)
    form = MorphicForm()

    # Save submitted gse ids
    if form.validate_on_submit():
        selected_ids = [box.id for box in form if box.data and box.type == 'BooleanField']
        print("Setting gse id")
        session['gse_ids'] = selected_ids

    # Update form with previously saved inputs
    for checkbox in form:
        if checkbox.type == 'BooleanField' and session.get('gse_ids') and checkbox.id in session.get('gse_ids'):
            checkbox.data = True

    return render_template("morphic_data.html", form=form, data=data)

@app.route('/metadata', methods=['GET', 'POST'])
def metadata():
    # get user selected gse id's
    gse_ids = session.get('gse_ids')
    if gse_ids is None or not gse_ids:
        return render_template('metadata.html', error_message="Please select a study to view metadata")
    if gse_ids != session.get('prev_gse_ids_metadata'):
        # fetch metadata for gse_id's
        api_response = sra_web_api.get_metadata_for_gse_ids(gse_ids, save_to_file=True)
        if api_response is None:
            error_message = f"No results were found for: {', '.join(gse_ids)}"
            return render_template('metadata.html', error_message=error_message)
        session['prev_gse_ids_metadata'] = gse_ids

    # read saved csv metadata
    metadata_df = pd.read_csv('metadata.csv')

    # create Forms
    srr_ids = metadata_df['run_accession']
    user_selected_metadata = session.get('user_selected_metadata', {})
    if user_selected_metadata is not None and user_selected_metadata and user_selected_metadata.get('groups'):
        group_names  = [group['name'] for group in user_selected_metadata.get('groups', []) if 'name' in group]

        SRRForm = create_srr_form(set(srr_ids), group_names)
        select_group_form = GroupForm(group_a=group_names[0], group_b=group_names[1])
    else:
        SRRForm = create_srr_form(set(srr_ids))
        select_group_form = GroupForm()
    form = SRRForm()

    if form.validate_on_submit():
        form_selected_metadata = user_selected_metadata
        for dropdown in form:
            if dropdown.data and dropdown.type == 'SelectField':
                new_group_name = dropdown.data
                new_srr_id = dropdown.id

                for group_info in form_selected_metadata.get('groups', []):
                    if group_info['name'] == new_group_name and new_srr_id not in group_info['samples']:
                        group_info['samples'].append(new_srr_id)
                for group_info in form_selected_metadata.get('groups', []):
                    if group_info['name'] != new_group_name and new_srr_id in group_info['samples']:
                        group_info['samples'].remove(new_srr_id)
                form_selected_metadata.get('samples')[new_srr_id] = new_group_name

        # save selected ids
        session['user_selected_metadata'] = form_selected_metadata
        session.modified = True
        with open("srr_id_groups.json", "w") as json_file:
            json.dump(form_selected_metadata, json_file, indent=4)

    # update form with previously saved inputs
    for dropdown in form:
        if dropdown.type == 'SelectField':
            if user_selected_metadata is not None and isinstance(user_selected_metadata, dict) and user_selected_metadata:
                metadata_samples = user_selected_metadata.get('samples')
                if metadata_samples:
                    dropdown.data = metadata_samples.get(dropdown.id)

    available_groups = [group['name'] for group in user_selected_metadata.get('groups', []) if 'name' in group]
    metadata = json.loads(metadata_df.to_json(orient='records'))
    return render_template('metadata.html', data=metadata, form=form, group_form=select_group_form, group_names=available_groups)# group_names=srr_groups)

@app.route('/create-group', methods=['POST'])
def create_group():
    form = GroupForm()
    if form.validate_on_submit():
        group_a_name = form.group_a.data
        group_b_name = form.group_b.data
        session['user_selected_metadata'] = {
            'groups': [
                {"name": group_a_name, "samples": []},
                {"name": group_b_name, "samples": []}
            ],
            'samples': {}
        }
        session.modified = True
    return redirect('/metadata')

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
    else:
        return jsonify({"error": msg}), 400

@app.route("/job-status/<job_id>", methods=["GET"])
def job_status(job_id):
    return jsonify(JOB_MANAGER.get_status(job_id))

def write_metadata_json(samples, srr_groups, output_path):
    """
    Write metadata JSON in the format expected by BWB workflows.

    Expected output structure:
    {
      "groups": [
        {
          "name": "<group_name>",
          "samples": [
            {
              "srr_id": "<sample_name>",
              "layout": "SINGLE" | "PAIRED"
            }
          ]
        }
      ]
    }

    Parameters
    ----------
    samples : list of dict
        Each dict must contain:
        - name   : sample identifier
        - group  : group/condition name
        - layout : SINGLE or PAIRED
        
    srr_groups : list of dict or None
        Groups from session metadata, each containing:
        - name    : group name
        - samples : list of SRR IDs
        
    output_path : str
        Path where metadata JSON will be written
    """

    grouped = defaultdict(list)

    # Add uploaded FASTQ samples
    for sample in samples:
        grouped[sample["group"]].append({
            "srr_id": sample["name"],
            "layout": sample["layout"]
        })
    
    # Add SRR ID samples from session metadata
    if srr_groups:
        for group in srr_groups:
            group_name = group.get("name")
            srr_samples = group.get("samples", [])
            
            for srr_id in srr_samples:
                # Assume SRR samples are PAIRED by default (can be adjusted)
                grouped[group_name].append({
                    "srr_id": srr_id,
                    "layout": "PAIRED"  # or derive from metadata if available
                })

    metadata = {
        "groups": [
            {
                "name": group_name,
                "samples": group_samples
            }
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
        # Form-level validation will ensure all sample fields are correct
        return render_template("dash.html", form=form, status=-1)

    randStr = str(uuid.uuid4())
    upload_root = os.path.join(BWB_SCHED_DIR, STORAGE_ID, randStr)
    os.makedirs(upload_root, exist_ok=True)

    srr_metadata = session.get('user_selected_metadata')
    print(srr_metadata)
    srr_groups = None
    
    if srr_metadata:
        srr_groups = srr_metadata.get("groups", [])

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

    # Enforce all samples share the same layout (if samples provided)
    first_layout = None
    if sample_indices:
        first_layout = request.form.get(f"samples[{sample_indices[0]}][layout]")
        if first_layout not in {"SINGLE", "PAIRED"}:
            form.workflow.errors.append("Invalid read layout for the first sample.")
            return render_template("dash.html", form=form, status=-1)

    samples = []
    for idx in sample_indices:
        prefix = f"samples[{idx}]"

        name   = request.form.get(f"{prefix}[name]")
        group  = request.form.get(f"{prefix}[group]")
        layout = request.form.get(f"{prefix}[layout]")

        # All layouts must match
        if layout != first_layout:
            form.workflow.errors.append(
                f"Sample {name or idx} has layout {layout}, "
                f"but all samples must be {first_layout}."
            )
            return render_template("dash.html", form=form, status=-1)

        r1 = request.files.get(f"{prefix}[r1]")
        r2 = request.files.get(f"{prefix}[r2]")

        # Create per-sample directory
        sample_dir = upload_root
        os.makedirs(sample_dir, exist_ok=True)

        # Save FASTQ files with names based on user-given sample name
        r1_path = None
        if r1 and r1.filename:
            # Use sample name with _1 suffix
            r1_filename = f"{name}_1.fastq"
            r1_path = os.path.join(sample_dir, r1_filename)
            r1.save(r1_path)

        r2_path = None
        if layout == "PAIRED":
            if not r2 or not r2.filename:
                form.workflow.errors.append(
                    f"Sample {name}: R2 FASTQ is required for paired-end layout."
                )
                return render_template("dash.html", form=form, status=-1)
            # Use sample name with _2 suffix
            r2_filename = f"{name}_2.fastq"
            r2_path = os.path.join(sample_dir, r2_filename)
            r2.save(r2_path)

        samples.append({
            "name": name,
            "group": group,
            "layout": layout,
            "r1": r1_path,
            "r2": r2_path,
        })

    metadata_path = os.path.join(upload_root, "metadata.json")
    metadata_cnt_path = os.path.join("/data", randStr, "metadata.json")
    write_metadata_json(
        samples=samples,
        srr_groups=srr_groups,
        output_path=metadata_path
    )

    srr_ids = []
    if srr_groups:
        for group in srr_groups:
            srr_ids.extend(group.get("samples", []))

    srr_ids = []
    if srr_groups:
        for group in srr_groups:
            srr_ids.extend(group.get("samples", []))
    
    srrIds = '[' + ','.join(srr_ids) + ']'
    if srr_ids:
        print("SRR IDs:", ",".join(srr_ids))
    else:
        print("SRR IDs: None")
    cmd = (
        f"docker run -v /var/run/docker.sock:/var/run/docker.sock "
        f"-v \"$(pwd)\":/wfs "
        f"-v {BWB_SCHED_DIR}:{BWB_SCHED_DIR} "
        f"-e BWB_SCHED_DIR={BWB_SCHED_DIR} "
        f"patrickmckeever/bwb-scheduler:latest bwbSched run "
        f"--docker --noTemporal -v --storageId {STORAGE_ID} "
        f"-p Start.srridsAll={srrIds} "
        f"-p Start.fastqdir=/data/{randStr} "
        f"-p Start.metadata_json={metadata_cnt_path} "
        f"/wfs/bulkrna.json"
    )

    print(cmd)
    job_id = JOB_MANAGER.submit(cmd)

    return render_template(
        "dash.html",
        form=form,
        status=1,
        job_id=job_id
    )

# TODO: Update this to have per-job directories later.
@app.route("/heatmap/<job_id>")
def heatmap(job_id):
    """
    Serve the final workflow image for a completed job.
    """

    # Defensive: job_id should be a UUID-like string
    if "/" in job_id or ".." in job_id:
        abort(400)

    image_path = f"{BWB_SCHED_DIR}/{STORAGE_ID}/processing/Tables/heatmap.png"
    if not os.path.exists(image_path):
        abort(404)

    return send_file(
        image_path,
        mimetype="image/png",
        conditional=True
    )

# TODO: Update this to have per-job directories later.
@app.route("/volcano/<job_id>")
def volcano(job_id):
    """
    Serve the final workflow image for a completed job.
    """

    # Defensive: job_id should be a UUID-like string
    if "/" in job_id or ".." in job_id:
        abort(400)

    image_path = f"{BWB_SCHED_DIR}/{STORAGE_ID}/processing/Tables/volcano_plot.png"
    if not os.path.exists(image_path):
        abort(404)

    return send_file(
        image_path,
        mimetype="image/png",
        conditional=True
    )

@app.route("/dash")
@app.route("/visualize")
def dash():
    form = BwbForm()
    return render_template('dash.html', form=form)
