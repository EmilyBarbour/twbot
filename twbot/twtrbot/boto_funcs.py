import boto3

class BotoError(Exception):
    """ raises error for boto """
    pass


def get_buckets(client, strip_chars=None):
    """ returns list of bucket's names """

    bucket_list = [bucket.name for bucket in client.buckets.all()]
    if strip_chars:
        bucket_list = [i.strip(strip_chars) for i in bucket_list if i.strip(strip_chars)]
    return bucket_list


def upload_file(client, bucketname, filename, filedata):
    """ uploads file to s3 bucket """

    bucket_obj = client.Bucket(bucketname)
    args= {"screenname": filedata.get("screenname"), "date": filedata.get("date"),
           "reply_to": filedata.get("reply_to")}
    try:
        bucket_obj.upload_file(filename, filename, ExtraArgs={"Metadata": args})
    except Exception as e:
        raise BotoError(e)
