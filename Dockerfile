FROM apache/airflow:2.9.2-python3.11
RUN python -m pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt
RUN pip install great-expectations