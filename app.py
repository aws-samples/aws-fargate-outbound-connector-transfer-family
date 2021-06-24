import os
import boto3
import paramiko
import json
import zipfile
from boto3.s3.transfer import TransferConfig
from datetime import datetime


#SET VARIABLE NAMES
secret_name = os.environ['SECRET_NAME']
region_name = os.environ['REGION']
sftp_dir = os.environ['SFTP_DIRECTORY_PATH']
my_bucket = os.environ['BUCKET']
ftp_port = int(os.environ['PORT'])


#RETRIVE SECRETS FROM SECRETS MANAGER
session = boto3.session.Session()
secrets_manager = session.client(
    service_name='secretsmanager',
    region_name=region_name
    )

secrets_response = secrets_manager.get_secret_value(
    SecretId=secret_name
    )
    
secrets_dict = json.loads(secrets_response['SecretString'])


hostname=secrets_dict['SFTP_TEST_SERVER_HOST']
username=secrets_dict['SFTP_TEST_SERVER_USERNAME']
password=secrets_dict['SFTP_TEST_SERVER_PASSWORD']



#SET UP SFTP CONNECTION USING PARAMIKO
ssh_client =paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh_client.connect(
    hostname=secrets_dict['SFTP_TEST_SERVER_HOST'],
    username=secrets_dict['SFTP_TEST_SERVER_USERNAME'],
    password=secrets_dict['SFTP_TEST_SERVER_PASSWORD']
    )


#DEFINE SFTP CONNECTION USING SECRETS MANAGER SECRETS
def open_ftp_connection(ftp_host, ftp_port, ftp_username, ftp_password):
    client = paramiko.SSHClient()
    client.load_system_host_keys() 
    try:
        transport = paramiko.Transport(ftp_host, ftp_port)
    except Exception:
        return 'conn_error'
    try:
        transport.connect(username=ftp_username, password=ftp_password)
    except Exception:
        return 'auth_error'
    ftp_connection = paramiko.SFTPClient.from_transport(transport)
    return ftp_connection
    

#SET THE SFTP CONNECTION
ftp_connection = open_ftp_connection(hostname, ftp_port, username, password)

#SET THE SFTP DIRECTORY PATH
ftp_file = ftp_connection.chdir(sftp_dir)

#SELECT ALL FILES TO UPLOAD INTO LIST
files_to_upload = ftp_connection.listdir()


#DEFINE MULTIPART UPLOAD SPECS FOR FILES LARGERS THAN 100MB
MB = 1024 ** 2
GB = 1024 ** 3
MULTIPART_THRESHOLD = 100 * MB
MULTIPART_CHUNKSIZE=20 * MB
MAX_CONCURRENCY=10
USER_THREADS=True

config = TransferConfig(
    multipart_threshold=MULTIPART_THRESHOLD, 
    multipart_chunksize=MULTIPART_CHUNKSIZE,
    max_concurrency=MAX_CONCURRENCY,
    use_threads=True)


#UPLOAD TO S3 ALL FILES IN SFTP DIRECTORY PATH
for ftp_file in files_to_upload:
    sftp_file_obj = ftp_connection.file(ftp_file, mode='r')
    s3_connection = boto3.client('s3')
    s3_connection.upload_fileobj(sftp_file_obj, my_bucket, ftp_file, Config=config)
    

#OPTIONAL -- ZIP FILES INTO A SEPARATE FOLDER CALLED 'ZIPPEDFILES'
os.path.abspath(os.getcwd())
directory = "zippedfiles"
path = os.path.join(os.path.abspath(os.getcwd()), directory) 
os.mkdir(path)


s3 = boto3.resource('s3')

#SELECT ONLY ZIP FILES IN S3

my_bucket = s3.Bucket(my_bucket)
zip_files = my_bucket.objects.filter()

# DOWNLOAD FILES INTO FARGATE CURRENT PWD
for s3_object in my_bucket.objects.all():
    filename = s3_object.key
    my_bucket.download_file(s3_object.key, filename)
    

#UNZIP AN FILES THAT ARE ZIPPED IN MEMORY
dir = os.listdir()
for object in dir:
	with zipfile.ZipFile(object,"r") as zip_ref:
		zip_ref.extractall(path)
    

#UPLOAD ALL ZIPPED FILES TO S3
for subdir, dirs, files in os.walk(path):
    for file in files:
        full_path = os.path.join(subdir, file)
        with open(full_path, 'rb') as data:
            my_bucket.put_object(Key=full_path[len(path)+1:], Body=data)