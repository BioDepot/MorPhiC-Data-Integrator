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

UPLOAD_FOLDER = 'uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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

# for rendering visualization
@app.route("/run-bwb", methods=['POST'])
def run_bwb():
    form = BwbForm()

    if form.validate_on_submit():

        # gse

        # file upload
        f = form.file.data
        filename = secure_filename(f.filename)
        # f.save(os.path.join(
        #     app.instance_path, UPLOAD_FOLDER, filename
        # ))

        # workflow based on aligment name
        workflow = form.workflow.data

        # Stop docker container and delete cidfile
        cidfile = 'cidfile'
        if os.path.isfile(cidfile):
            os.system('docker stop $(cat cidfile)')
            os.remove(cidfile)

        # start  selected  workflow
        if (workflow == 'star_salmon_short_ryan'):
            status = os.system('docker run --rm -d  --init --cidfile=cidfile -p 6080:6080 -v ${PWD}:/data -v /var/run/docker.sock:/var/run/docker.sock -v /tmp/.X11-unix:/tmp/.X11-unix --privileged --group-add root -e STARTING_WORKFLOW=/data/star_salmon_short_ryan/star_salmon_short_ryan.ows biodepot/bwb')
        elif (workflow == 'star_salmon_short_yin'):
            status = os.system('docker run --rm -d  --init --cidfile=cidfile -p 6080:6080 -v ${PWD}:/data -v /var/run/docker.sock:/var/run/docker.sock -v /tmp/.X11-unix:/tmp/.X11-unix --privileged --group-add root -e STARTING_WORKFLOW=/data/star_salmon_short_yin/star_salmon_short_yin.ows biodepot/bwb')
        elif (workflow == 'notebook'):
            status = 0
        else:
            status = -1

        # Check if port has opened
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 6080))
        if result == 0:
            print("------------ Port is open --------------")
            session['bwb_opened'] = True
        else:
            print("------------- Port is NOT open ---------")
            session['bwb_opened'] = False
        sock.close
        
        return render_template('dash.html', form=form, status=status)
    return render_template('dash.html', form=form, status=-1)

@app.route("/")
def plot_plotly_global():
    form = BwbForm()
    return render_template('dash.html', form=form)
