from altair import Chart, X, Y, Axis, Data, DataFormat
import pandas as pd
import numpy as np
from flask import render_template, url_for, flash, redirect, request, make_response, jsonify, abort, session, send_file, g
from web import app
from web.utils import utils, altair_plot, plotly_plot
from .forms import SearchForm, BwbForm, create_results_table_form, create_srr_form
import json
import requests
from pysradb import SRAweb

import uuid
import os
import socket
import io
import time


# for bwb page
@app.route("/bwb")
def homepage():
    return render_template('bwb_page.html')

def query_rag(user_uuid, text_query_used, query, gene_set_used, gene_set, search, expand):
    # ssgsea = True
    # “uuid”: “<id_goes_here>”,
    # “text_query_used”: “True”,  //Should only be True or False
    # “text_query”: “<text_goes_here>”,
    # “gene_set_used”: “True”,  //Should only be True or False
    # “gene_set”: [‘gene1”, “gene2”, … ],  //There should be at least 5
    # “search”: “<value>”, //Should only be semantic or transcriptome
    # “expand”: “<value>” //Should only be semantic or transcriptome
    try:
        url = 'http://127.0.0.1:5001/query_rag'
        input_data = {'uuid': user_uuid,
                    'text_query_used': text_query_used,
                    'text_query': query,
                    'gene_set_used': gene_set_used,
                    'gene_set': gene_set,
                    'search': search,
                    'expand': expand}
        # print(input_data)
        res = requests.post(url, json=input_data)
        print('response from server:', res.text)

        return res.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

@app.route('/queue_position', methods=['GET'])
def get_queue():
    # get user uuid
    uuid = session.get('uuid')

    if not uuid:
        return jsonify({'error: search query is required'}), 400
    
    # make request to check queue position
    url = 'http://127.0.0.1:5001/queue_position'
    input_data = {'uuid': uuid}
    try:
        # fetch
        res = requests.post(url, json=input_data)
        print('get queue position, response from server:', res.text)

        return jsonify(res.json()), 200
    except requests.RequestException as e:
        # failed
        print(f"Error getting queue position: {e}")
        return jsonify({'error': 'error getting queue position'}), 500

def get_data_output(uuid, lines):
    # uuid = session.get('uuid')
    if not uuid or not lines:
        return jsonify({'error: A search with amount of lines is required'}), 400
    
    url = 'http://127.0.0.1:5001/data_output'
    input_data = {'uuid': uuid,
                    'amount_of_lines': int(lines)}
    try:
        # fetch
        res = requests.post(url, json=input_data)
        print('data_output, response from server:', str(res.text)[:100])

        return res.json()
    except requests.RequestException as e:
        # failed
        print(f"Error getting data output: {e}")
        return None

@app.route('/download_data', methods=['GET'])
def get_download_data():
    # retrieve uuid and amount of lines
    uuid = session.get('uuid')
    lines = session.get('lines')

    if not uuid or not lines:
        return jsonify({'error: A search with amount of lines is required'}), 400

    url = 'http://127.0.0.1:5001/file_download'
    input_data = {'uuid': uuid,
                    'amount_of_lines': lines}
    try:
        # fetch
        res_file = requests.post(url, json=input_data)

        if res_file.status_code == 400:
            print(res_file.text)
            return jsonify({'error': res_file.text}), 400
        
        zip_file = io.BytesIO(res_file.content)
        return send_file(zip_file, as_attachment=True, download_name='search-results.zip', mimetype='application/zip')
    except requests.RequestException as e:
        # failed
        print(f"Error getting data output: {e}")
        return jsonify({'error': str(e)}), 500
    
def extract_genes(input_genes):
    # filter out genes, save and return as a list of genes
    genes = input_genes.split()
    genes = [gene.strip() for gene in genes if gene.strip()]

    return genes

# BioRAG search
@app.route("/search", methods=['GET','POST'])
def search():
    form = SearchForm()

    if form.validate_on_submit():
        # generate uuid
        session['uuid'] = str(uuid.uuid4())
        user_uuid = session.get('uuid')

        # remove session key for previous search results
        if 'gse_sample_type' in session:
            del session['gse_sample_type']

        # user inputs
        query = form.query.data
        genes = form.genes.data
        expansion_strategy = form.expansion_strategy.data
        size = form.size.data
        print("INPUT SIZE:")
        print(size)

        # set search and expand from selected expansion strategy
        if expansion_strategy == 'semantic_transcriptome':
            search = 'semantic'
            expand = 'transcriptome'
        else:
            search = 'semantic'
            expand = 'semantic'

        # Check if search query and genes list was inputed
        has_query = bool(query)
        has_genes = bool(genes)
        # Save lines for future use
        if size:
            session['lines'] = int(size)
        # Create a gene set from input genes
        if genes:
            genes = extract_genes(genes)

        # make a query
        q_response = query_rag(user_uuid, has_query, query, has_genes, genes, search, expand)

        # check for query status
        if "status" in q_response:
            print("status:")
            print(q_response["status"])
        if "status" in q_response and q_response["status"] == "queued":
            return render_template('search.html', result=q_response, success=True, form=form)
        if "status" in q_response:
            return render_template('search.html', result=q_response, success=False, form=form)

        # error after attempting to make a request
        return render_template('search.html', result={"data": {"error": "There was an error making a search"}}, success=False, form=form)
    return render_template('search.html', form=form)

# helper function that take a list of studies (dictionary) 
# and separates each gse_id in the study into its own study
def split_gse_ids(studies, gse_id_label):
    updated_studies = []
    for study in studies:
        gse_ids = [gse_id.strip() for gse_id in study[gse_id_label].split(',')]
        if len(gse_ids) > 1:
            for gse_id in gse_ids:
                modified_study = study.copy()
                modified_study[gse_id_label] = gse_id
                updated_studies.append(modified_study)
        else:
            updated_studies.append(study)
    
    return updated_studies

# helper function that removes duplicate gse_id's in a study
def remove_duplicate_gse_ids(studies, gse_id_label):
    unique_gse_ids = set()
    updated_studies = []
    for study in studies:
        gse_id = study[gse_id_label]
        if gse_id not in unique_gse_ids:
            updated_studies.append(study.copy())
        unique_gse_ids.add(gse_id)
    return updated_studies

# create new data by spliting listed gse_id's into its own study and removing duplicates
def reshape_data(data):
    updated_expansion_studies = split_gse_ids(data['data']['expansion_studies'], 'gse_id')
    updated_expansion_studies = remove_duplicate_gse_ids(updated_expansion_studies, 'gse_id')
    data['data']['expansion_studies'] = updated_expansion_studies

    updated_samples = split_gse_ids(data['data']['samples'], 'series_id')
    data['data']['samples'] = updated_samples

    updated_seed_studies = split_gse_ids(data['data']['seed_studies'], 'gse_id')
    updated_seed_studies = remove_duplicate_gse_ids(updated_seed_studies, 'gse_id')
    data['data']['seed_studies'] = updated_seed_studies

    return data

# get a list of unique gse id's
def get_all_gse_ids(data):
    all_gse_ids = set()
    for study in data['data']['expansion_studies']:
        gse_id = study.get('gse_id')
        if gse_id:
            all_gse_ids.add(gse_id)
    for study in data['data']['samples']:
        gse_id = study.get('series_id')
        if gse_id:
            all_gse_ids.add(gse_id)
    for study in data['data']['seed_studies']:
        gse_id = study.get('gse_id')
        if gse_id:
            all_gse_ids.add(gse_id)
    return list(all_gse_ids)

# Get sample type, Bulk or Single-cell, from session
def get_gse_sample_type(gse_id):
    if session.get('gse_sample_type') is None:
        return ''
    
    sample_type = session.get('gse_sample_type').get(gse_id)
    if sample_type:
        return sample_type
    else:
        return ''

# fetch metadata using pysradb for a list of gse id's and save results
def fetch_gse_metadata(gse_list):
    db = SRAweb()

    # setup saving locations
    metadata_collection = []
    if session.get('gse_sample_type') is None:
        # sample_dict = {'GSE141950': 'Bulk', 'GSE141099': 'Bulk', 'GSE126890': 'Bulk', 'GSE86244': 'Bulk', 'GSE140523': 'Bulk', 'GSE81405,GSE81406': 'Bulk', 'GSE109408': 'Bulk', 'GSE65634': 'Bulk', 'GSE43070': 'Bulk', 'GSE147561': 'Bulk', 'GSE87710,GSE87712': 'Bulk', 'GSE54308': 'Bulk', 'GSE118254,GSE118256': 'Bulk', 'GSE196855,GSE196856': 'Bulk', 'GSE174534': 'Bulk', 'GSE86189': 'Bulk', 'GSE148180,GSE148185': 'Bulk', 'GSE125504': 'Bulk', 'GSE113648': 'Bulk'}
        session['gse_sample_type'] = {}
    else:
        return None

    for gse_id in gse_list:
        try:
            db = SRAweb()

            srp_df = db.gse_to_srp(gse_id)
            study_accession = srp_df['study_accession'][0]
            metadata = db.sra_metadata(study_accession, detailed=True)

            # track metadata results
            metadata_subset = metadata[['library_name', 'library_strategy', 'run_accession', 'experiment_desc', 'source_name']]
            metadata_collection.append(metadata_subset)

            # save strategy to session
            contains_bulk = metadata['library_strategy'].str.contains('RNA-Seq').any()
            if contains_bulk:
                session['gse_sample_type'][gse_id] = 'Bulk'
            else:
                session['gse_sample_type'][gse_id] = 'Single-cell'
        except Exception as e:
            session['gse_sample_type'][gse_id] = ''
            error_message = f"Error: pysradb was unable to retrieve data for gse id {gse_id} \n {e}"
            print(error_message)
            time.sleep(0.5)
        time.sleep(0.5)

    # save metadata collection
    if metadata_collection:
        metadata_collection = pd.concat(metadata_collection, ignore_index=True)
        # metadata_collection.to_json('metadata.json')
        metadata_collection.to_csv("metadata.csv", index=False)

# Search results
@app.route("/search-results", methods=['GET', 'POST'])
def search_results():
    if 'uuid' in session and 'lines' in session:
        uuid = session.get('uuid')
        lines = session.get('lines')

        # get search results
        res = get_data_output(uuid, lines)
        if not res or res.get('status') == 'query_not_present':
            return render_template('search_results.html')

        # split comma separated gse_ids and remove duplicates
        res = reshape_data(res)

        # get and save metadata info for gse id's in result data
        available_gse_ids = get_all_gse_ids(res)
        fetch_gse_metadata(available_gse_ids)

        # add sample type to result data
        for study in res['data']['expansion_studies']:
            gse_id = study.get('gse_id')
            if gse_id:
                study['sample_type'] = get_gse_sample_type(gse_id)
                available_gse_ids.append(gse_id)
        for study in res['data']['samples']:
            gse_id = study.get('series_id')
            if gse_id:
                study['sample_type'] = get_gse_sample_type(gse_id)
                available_gse_ids.append(gse_id)
        for study in res['data']['seed_studies']:
            gse_id = study.get('gse_id')
            if gse_id:
                study['sample_type'] = get_gse_sample_type(gse_id)
                available_gse_ids.append(gse_id)

        # Use a Form for gse_id's in result data
        ResultsTableForm = create_results_table_form(available_gse_ids)
        form = ResultsTableForm()

        if form.validate_on_submit():
            # list of selected/checked inputs
            selected_studies = [checkbox.label.text for checkbox in form if checkbox.data and checkbox.type == 'BooleanField']
            if selected_studies:
                session['gse'] = selected_studies
        
        return render_template('search_results.html', data=res, form=form)
    return render_template('search_results.html')

@app.route('/metadata', methods=['GET', 'POST'])
def metadata():
    # read saved csv metadata
    metadata_df = pd.read_csv('metadata.csv')

    # create Form
    srr_ids = metadata_df['run_accession']
    SRRForm = create_srr_form(set(srr_ids))
    form = SRRForm()

    if form.validate_on_submit():
        # list of selected/checked inputs
        selected_srr_ids = [checkbox.label.text for checkbox in form if checkbox.data and checkbox.type == 'BooleanField']
        if selected_srr_ids:
            session['srr_ids'] = selected_srr_ids

    metadata = json.loads(metadata_df.to_json(orient='records'))
    return render_template('metadata.html', data=metadata, form=form)

@app.route('/plots/p1.html')
def get_plot():
    return send_file('./plots/p1.html')

# for rendering visualization
@app.route("/view", methods=['POST'])
def plot_visuals():
    form = BwbForm()

    if form.validate_on_submit():

        # gse

        # workflow based on aligment name
        workflow = form.workflow.data

        # Stop docker container and delete cidfile
        cidfile = 'cidfile'
        if os.path.isfile(cidfile):
            os.system('docker stop $(cat cidfile)')
            os.remove(cidfile)

        # start  selected  workflow
        if (workflow == 'GSE224615'):
            status = os.system('docker run --rm -d  --init --cidfile=cidfile -p 6080:6080 -v ${PWD}:/data -v /var/run/docker.sock:/var/run/docker.sock -v /tmp/.X11-unix:/tmp/.X11-unix --privileged --group-add root -e STARTING_WORKFLOW=/data/star_salmon_short_ryan/star_salmon_short_ryan.ows biodepot/bwb')
        elif (workflow == 'GSE169687'):
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
        
        return render_template('viz.html', status=status)
    return render_template('viz.html', status=-1)

@app.route("/dashboard/gse/<gse>")
def dash_gse(gse):
    return render_template('plot.html', gse=gse)

@app.route("/")
@app.route("/plot")
def plot_plotly_global():
    form = BwbForm()
    return render_template('plot.html', form=form)
