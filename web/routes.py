from altair import Chart, X, Y, Axis, Data, DataFormat
import pandas as pd
import numpy as np
from flask import render_template, url_for, flash, redirect, request, make_response, jsonify, abort, session, send_file, g
from web import app
from web.utils import utils, altair_plot, plotly_plot
from .forms import SearchForm, BwbForm
import json
import requests

import uuid
import os
import socket
import io


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

# BioRAG search results
@app.route("/search-results")
def search_results():
    if 'uuid' in session and 'lines' in session:
        uuid = session.get('uuid')
        lines = session.get('lines')

        res = get_data_output(uuid, lines)
        if not res:
            return render_template('search_results.html')

        return render_template('search_results.html', data=res)
    return render_template('search_results.html')

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
