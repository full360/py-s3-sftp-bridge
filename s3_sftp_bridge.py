from __future__ import print_function
import argparse
import errno
import json
import os
import sys
import base64
# import hashlib
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

# We need to package pysftp with the Lambda function so add it to path
here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "vendored"))

import paramiko  # noqa: E402
import pysftp  # noqa: E402
import srvlookup  # noqa: E402
from dns import resolver  # noqa: E402

TMP_DIR = '/tmp'


def handler(event, context):
    if 'Records' in event and event['Records'][0]['eventSource'] == "aws:s3":
        s3_event = event['Records'][0]['s3']
        s3_bucket = s3_event['bucket']['name']
        s3_key = s3_event['object']['key']

        new_s3_object(s3_bucket, s3_key)

        response = {
            "statusCode": 200,

            "body": "Uploaded {}".format(s3_key)
        }

        return response

    else:
        retry_failed_messages()


def new_s3_object(s3_bucket, s3_key):
    try:
        _download_s3_object(s3_bucket, s3_key)
        _upload_file(s3_key)
    except Exception:
        print('Failed to transfer {}'.format(s3_key))
        raise


def _split_s3_path(s3_full_path):
    bucket = s3_full_path.split('/')[0]
    key_path = '/'.join(s3_full_path.split('/')[1:])

    return (bucket, key_path)


def _create_local_tmp_dirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def _download_s3_object(s3_bucket, s3_key):
    local_object_dir = '{}/{}'.format(TMP_DIR, os.path.dirname(s3_key))
    _create_local_tmp_dirs(local_object_dir)

    try:
        s3 = boto3.resource('s3', config=Config(signature_version='s3v4'))
        bucket = s3.Bucket(s3_bucket)
        bucket.download_file(s3_key, '{}/{}'.format(TMP_DIR, s3_key))
        print('fetched object {}'.format(s3_key))

    except ClientError:
        print('{} not found in {}'.format(s3_key, s3_bucket))
        raise

    except IOError:
        print('Unable to download {}'.format(s3_key))
        raise


def _upload_file(file_path):

    user = os.environ['SFTP_USER']
    sftp_location = os.environ['SFTP_LOCATION']

    # Set Host and Port
    host = os.environ['SFTP_HOST']

    # get port number using consul dns lookup
    my_resolver = resolver.Resolver()
    srv = srvlookup._build_result_set(my_resolver.query(host, 'SRV'))

    port = srv[0].port
    print('Host and Port: {}:{}'.format(host, port))

    # TODO memoize using port = int(os.environ['SFTP_PORT'])

    # Download set private key for sftp server
    s3_private_key = os.environ['SFTP_S3_SSH_KEY']
    s3_ssh_key_bucket, s3_ssh_key_path = _split_s3_path(s3_private_key)
    _download_s3_object(s3_ssh_key_bucket, s3_ssh_key_path)
    private_key = '{}/{}'.format(TMP_DIR, s3_ssh_key_path)
    print('Private Key {}'.format(private_key))

    # Download set host key for sftp server
    s3_host_key = os.environ['SFTP_S3_SSH_HOST_KEY']
    s3_ssh_host_key_bucket, s3_ssh_host_key_path = _split_s3_path(s3_host_key)
    _download_s3_object(s3_ssh_host_key_bucket, s3_ssh_host_key_path)
    ssh_host_key = '{}/{}'.format(TMP_DIR, s3_ssh_host_key_path)
    print('Host Key {}'.format(ssh_host_key))

    # Setting Host Key
    # not simple because there seems to be an issue with pysftp handling
    # host keys when non-standard ports are involved
    print('Setting cnopts')
    cnopts = pysftp.CnOpts()
    k = open(ssh_host_key, "r").read()
    k = k.strip().split()[1].encode('ascii')
    keydata = str.encode(k)
    key = paramiko.RSAKey(data=base64.b64decode(keydata))
    cnopts.hostkeys.clear()
    hostname_without_port = host
    print('Setting Host Key {}'.format(hostname_without_port))
    cnopts.hostkeys.add(hostname_without_port, 'ssh-rsa', key)
    hostname_with_port = "[{}]:{}".format(host, port)
    print('Setting Host Key {}'.format(hostname_with_port))
    cnopts.hostkeys.add(hostname_with_port, 'ssh-rsa', key)

    # connect and put
    try:
        with pysftp.Connection(host=host, port=port,
                               username=user,
                               private_key=private_key,
                               cnopts=cnopts) as sftp:
            with sftp.cd(sftp_location):
                sftp.makedirs(os.path.dirname(file_path))
                sftp.put('/tmp/{}'.format(file_path), file_path)
                print('uploaded {}'.format(file_path))

    except (pysftp.ConnectionException, pysftp.CredentialException,
            pysftp.SSHException, pysftp.AuthenticationException):
        print('SFTP connection error')
        raise

    except IOError:
        print('Failed to upload {}'.format(file_path))
        raise


def retry_failed_messages():
    print('Retrying failed messages')
    queue_name = os.environ['QUEUE_NAME']

    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=queue_name)

    for message in queue.receive_messages(MaxNumberOfMessages=10):
        handler(json.loads(message.body), 'context')
        message.delete()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                        description='Move a file from S3 to an SFTP server')
    parser.add_argument('s3_path', help='The full path to the s3 object. '
                        'eg. my_bucket/path/to/key')
    args = parser.parse_args()

    s3_bucket, s3_key = _split_s3_path(args.s3_path)

    new_s3_object(s3_bucket, s3_key)
