import boto3

s3=boto3.client("s3")

def download_file(bucket,key):
    return s3.get_object(
        Bucket=bucket,
        Key=key
    )
