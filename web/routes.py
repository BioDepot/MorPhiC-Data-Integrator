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
from web.utils import utils, sample_explorer_utils
from .forms import SearchForm, BwbForm, GroupForm, create_results_table_form, create_srr_form
import json
import requests
from werkzeug.utils import secure_filename

import uuid
import os
import socket
import io

BWB_SCHED_DIR='/home/patrick/SCHED_STORAGE'
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
        
        return render_template('search_results.html', data=search_results, form=form)
    return render_template('search_results.html')

@app.route('/metadata', methods=['GET', 'POST'])
def metadata():
    # get selected gse id's
    gse_ids = session.get('gse_ids')
    if gse_ids is None:
        return render_template('metadata.html')
    if gse_ids != session.get('prev_gse_ids_metadata'):
        # fetch metadata for gse_id's
        sra_web_api.get_metadata_for_gse_ids(gse_ids, save_to_file=True)
        session['prev_gse_ids_metadata'] = gse_ids

    # read saved csv metadata
    metadata_df = pd.read_csv('metadata.csv')

    # create Forms
    srr_ids = metadata_df['run_accession']
    srr_groups = session.get('srr_groups') # ["group_name_a", "group_name_b"]
    if srr_groups:
        SRRForm = create_srr_form(set(srr_ids), srr_groups)
        select_group_form = GroupForm(group_a=srr_groups[0], group_b=srr_groups[1])
    else:
        SRRForm = create_srr_form(set(srr_ids))
        select_group_form = GroupForm()
    form = SRRForm()

    if form.validate_on_submit():
        selected_srr_ids = {}
        for dropdown in form:
            if dropdown.data and dropdown.type == 'SelectField':
                group_name = dropdown.data
                group_srr_id = dropdown.id
                if group_name not in selected_srr_ids:
                    selected_srr_ids[group_name] = []
                selected_srr_ids[group_name].append(group_srr_id)
        session['srr_ids'] = selected_srr_ids
        # with open("srr_id_groups.json", "w") as json_file:
        #     json.dump(selected_srr_ids, json_file, indent=4)

    metadata = json.loads(metadata_df.to_json(orient='records'))
    return render_template('metadata.html', data=metadata, form=form, group_form=select_group_form, group_names=srr_groups)

@app.route('/create-group', methods=['POST'])
def create_group():
    form = GroupForm()
    if form.validate_on_submit():
        group_a_name = form.group_a.data
        group_b_name = form.group_b.data
        session['srr_groups'] = [group_a_name, group_b_name]
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

# for rendering visualization
@app.route("/run-bwb", methods=['POST'])
def run_bwb():
    form = BwbForm()
    randStr = str(uuid.uuid4())
    UPLOAD_FOLDER = os.path.join(BWB_SCHED_DIR, STORAGE_ID)
    
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    os.makedirs(os.path.join(UPLOAD_FOLDER, randStr))

    if not form.validate_on_submit():
        return render_template('dash.html', form=form, status=-1)

    srr_ids = session.get('srr_ids')
    read_type = form.read_type.data
    f = form.file.data
    print()
    if f:
        filename1 = secure_filename(f.filename)
        filepath1 = os.path.join(UPLOAD_FOLDER, randStr, filename1)
        f.save(filepath1)

    f_r2 = form.file_r2.data
    if f_r2:
        filename2 = secure_filename(f_r2.filename)
        filepath2 = os.path.join(UPLOAD_FOLDER, randStr, filename2)
        f_r2.save(filepath2)

    readType = form.read_type.data
    if readType == "single":
        fastqfiles = f"[/data/{randStr}/{filename1}]"
        cmd = (
            f"docker run -v /var/run/docker.sock:/var/run/docker.sock "
            f"-v \"$(pwd)\":/wfs "
            f"-v {BWB_SCHED_DIR}:{BWB_SCHED_DIR} "
            f"-e BWB_SCHED_DIR={BWB_SCHED_DIR} "
            f"patrickmckeever/bwb-scheduler:latest bwbSched run "
            f"--docker --noTemporal -v --storageId {STORAGE_ID} "
            f"-p Start.fastqfiles={fastqfiles} "
            f"/wfs/single_bulkrna.json"
        )
    else:
        fastqfiles = f"[/data/{randStr}/{filename1},/data/{randStr}/{filename2}]"
        cmd = (
            f"docker run -v /var/run/docker.sock:/var/run/docker.sock "
            f"-v \"$(pwd)\":/wfs "
            f"-v {BWB_SCHED_DIR}:{BWB_SCHED_DIR} "
            f"-e BWB_SCHED_DIR={BWB_SCHED_DIR} "
            f"patrickmckeever/bwb-scheduler:latest bwbSched run "
            f"--docker --noTemporal -v --storageId {STORAGE_ID} "
            f"-p Start.fastqfiles={fastqfiles} "
            f"/wfs/paired_bulkrna.json"
        )

    # submit job to queue
    print(cmd)
    job_id = JOB_MANAGER.submit(cmd)

    return render_template('dash.html', form=form, status=1, job_id=job_id)

@app.route("/dash")
@app.route("/visualize")
def dash():
    form = BwbForm()
    return render_template('dash.html', form=form)
