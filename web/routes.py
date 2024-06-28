from altair import Chart, X, Y, Axis, Data, DataFormat
import pandas as pd
import numpy as np
from flask import render_template, url_for, flash, redirect, request, make_response, jsonify, abort
from web import app
from web.utils import utils, altair_plot, plotly_plot
import json

import os


# for bwb page
@app.route("/bwb")
def homepage():
    return render_template('bwb_page.html')

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
    else:
        status = -1

    return render_template('viz.html', status=status)

#for home page with sample plot
@app.route("/")
@app.route("/plot")
def plot_plotly_global():
    return render_template('plot.html')


