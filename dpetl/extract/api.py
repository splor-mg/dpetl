import requests
from pathlib import Path

def extract_api(resource, **kwargs):
    try:
        sources = resource.sources
        sources = [
            source for source in sources if source.get('method') is not None
        ]
        source = sources[0]
        if source:
            func = getattr(requests, source['method'])
            response = func(
                source['path'],
                timeout=source.get('timeout', 30),
                params=source.get('params', {}),
                headers=source.get('headers', {}),
                stream=source.get('stream', False),
            )
            response.raise_for_status()

        Path(resource.path).parent.mkdir(parents=True, exist_ok=True)

        with open(resource.path, 'wb') as f:
            f.write(response.content)

    except requests.exceptions.RequestException as e:
        print(f'Error downloading file: {e}')
        raise
    except IOError as e:
        print(f'Error saving file: {e}')
        raise
