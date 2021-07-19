FROM python:3
ADD app.py /
RUN pip install boto3
RUN pip install paramiko
CMD [ "python", "./app.py" ]
