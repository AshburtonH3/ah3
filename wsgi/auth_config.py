from os import environ
from authomatic.providers import oauth2


AUTH_CONFIG = {
    'github': {
        'class_': oauth2.GitHub,
        'consumer_key': environ['GITHUB_CLIENT_ID'],
        'consumer_secret': environ['GITHUB_CLIENT_SECRET'],
        'access_headers': {'User-Agent': 'AH3'},
        'scope': ['read:org'],
    }
}
