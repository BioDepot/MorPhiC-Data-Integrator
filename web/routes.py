from altair import Chart, X, Y, Axis, Data, DataFormat
import pandas as pd
import numpy as np
from flask import render_template, url_for, flash, redirect, request, make_response, jsonify, abort, session, send_file, g
from web import app
from web.utils import utils, altair_plot, plotly_plot
import json

import os
import socket


# for bwb page
@app.route("/bwb")
def homepage():
    return render_template('bwb_page.html')

def query_rag(uuid):
    # g.uuid = '123'

    if uuid:
        try:
            dictToSend = {'uuid': uuid,
                        'gene_set': ['MMP8', 'LTF', 'CAMP', 'HP', 'DCLK2', 'GOLGA8R','KIR3DL2', 'PTPRN2-AS1', 'SERPINB9', 'B3GAT1'],
                        'text_query_used': 'Dataset used: Ryan Et al (GSE169687).  Groups compared: C (all patients with mild LC symptoms) vs E & F (all patients with severe or critical LC symptoms).  What are the ranges of differential expression for each gene provided in the gene-signature list for the group labelled "mild"?',
                        'text_query': 'Dataset used: Ryan Et al (GSE169687).  Groups compared: C (all patients with mild LC symptoms) vs E & F (all patients with severe or critical LC symptoms).  What are the ranges of differential expression for each gene provided in the gene-signature list for the group labelled "mild"?',
                        'gene_set_used': ['MMP8', 'LTF', 'CAMP', 'HP', 'DCLK2', 'GOLGA8R','KIR3DL2', 'PTPRN2-AS1', 'SERPINB9', 'B3GAT1'],
                        'ss_gesa': False}
            res = requests.post('http://127.0.0.1:5001/query_rag', json=dictToSend)
            print('response from server:', res.text)
            # return jsonify(res.json), 200
            return res
        except requests.exceptions.RequestException as e:
            print({'error': f'post error: {str(e)}'})
            jsonify({"error": "Fail to make search"}), 500
            return None
    else:
        return {'error': 'No uuid for query'}

@app.route('/queue_position', methods=['POST'])
def get_queue():
    # get user uuid
    uuid = request.json.get('uuid')

    dictToSend = {'uuid': '001'}
    try:
        #fetch
        res = requests.post('http://127.0.0.1:5001/queue_position', json=dictToSend)
        print('get queue position, response from server:', res.text)
        data = res.json()
        return jsonify(res)
    except requests.RequestException as e:
        # failed
        return f"Error getting queue position: {e}"

# @app.route('/data_output', methods=['POST'])
def get_response_data(uuid, lines):
    # get user uuid
    uuid = request.json.get('uuid')
    lines = request.json.get('lines')
    
    dictToSend = {'uuid': uuid,
                    'amount_of_lines': lines}
    try:
        # fetch
        res = requests.post('http://127.0.0.1:5001/data_output', json=dictToSend)
        print('data_output, response from server:', str(res.text)[:200])
        # res = res.json()

        # with open('query_data_output2.json', 'w') as f:
        #     json.dump(dictFromServer, f)

        return jsonify(res)
    except requests.RequestException as e:
        # failed
        print(f"Error getting data output: {e}")
        return None

@app.route('/download_data', methods=['POST'])
def get_download_data(uuid):
    # get user uuid
    uuid = request.json.get('uuid')
    lines = request.json.get('lines')

    dictToSend = {'uuid': uuid,
                    'amount_of_lines': lines}
    try:
        # fetch
        res_file = requests.post('http://127.0.0.1:5001/file_download', json=dictToSend)
        # res = res.json()

        # if res_file.status_code == 200:
        #     with open("query_result2.zip","wb") as f:
        #         f.write(res_file.content)
        # else:
        #     print('response from server:', res_file.text)

        return jsonify(res_file)
    except requests.RequestException as e:
        # failed
        return f"Error getting data output: {e}"

# BioRAG search
@app.route("/search", methods=['GET','POST'])
def search():
    if request.method == 'POST':
        g.uuid = '001'
        print('/query ', g.uuid)

        # user inputs
        query = request.form['query']
        genes = request.form['genes']
        ssgsea = 'ssGSEA' in request.form
        size = request.form['resultSize']

        print("QUERY INPUT: \n", query, 
            "\n GENES: ", genes.split(), 
            "\n ssGSEA: ", ssgsea,
            "\n SIZE: ", size)

        q_response = query_rag(g.uuid)
        print("q_responnse")
        print(q_response.text)
        
        return render_template('search.html', result=q_response, uuid=g.uuid, lines=int(size))
    return render_template('search.html')

# BioRAG search results
@app.route("/search-results")
def search_results():
    uuid = request.args.get('uuid')
    lines = request.args.get('lines')
    res = get_response_data(uuid, lines)

    return render_template('search-results.html', data=res)

@app.route('/plots/p1.html')
def get_plot():
    return send_file('./plots/p1.html')

# for rendering visualization
@app.route("/view", methods=['POST'])
def plot_visuals():
    gse = request.form['geo_name']

    workflow = request.form.get('alignment_name')
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

@app.route("/dashboard/gse/<gse>")
def dash_gse(gse):
    return render_template('plot.html', gse=gse)

@app.route("/")
@app.route("/plot")
def plot_plotly_global():
    return render_template('plot.html')


