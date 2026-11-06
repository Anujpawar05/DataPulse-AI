FROM apache/airflow:3.3.2

COPY requirements-airflow.txt /requirements-airflow.txt

RUN pip install --no-cache-dir \
    "apache-airflow==3.3.2" \
    -r /requirements-airflow.txt