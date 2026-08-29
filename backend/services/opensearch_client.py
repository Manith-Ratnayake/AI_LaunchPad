import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

from config.config import CONFIG


OPENSEARCH_CONFIG = CONFIG["opensearch"]
AWS_CONFIG = CONFIG["aws"]

DEFAULT_HOST = OPENSEARCH_CONFIG["host"].replace("https://", "").rstrip("/")
DEFAULT_INDEX = OPENSEARCH_CONFIG.get("index", "annual-reports")
DEFAULT_SERVICE = OPENSEARCH_CONFIG.get("service", "es")
DEFAULT_AWS_PROFILE = AWS_CONFIG.get("profile")
DEFAULT_AWS_REGION = AWS_CONFIG["region"]


def get_opensearch_client(profile_name=None, region_name=None):
    profile = profile_name or DEFAULT_AWS_PROFILE
    region = region_name or DEFAULT_AWS_REGION

    session = (
        boto3.Session(
            profile_name=profile,
            region_name=region,
        )
        if profile
        else boto3.Session(region_name=region)
    )

    auth = AWSV4SignerAuth(
        session.get_credentials(),
        region,
        DEFAULT_SERVICE,
    )

    client = OpenSearch(
        hosts=[
            {
                "host": DEFAULT_HOST,
                "port": 443,
            }
        ],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )

    return client, DEFAULT_SERVICE