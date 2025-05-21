FROM python:3.11
COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt
COPY run.py config.py .env bulk_rna_async.json star_salmon_short.json covid_data_cleaning.ipynb ./
COPY ./web ./web
CMD ["python3", "run.py"]
