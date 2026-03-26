import requests
from pathlib import Path
from tqdm import tqdm

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
        total_length = int(response.headers.get('content-length', 0))
        progress = tqdm(total=total_length, unit='iB', unit_scale=True)

        with open(resource.path, 'wb') as f:
            for data in response.iter_content(1024):  # 1KB
                progress.update(len(data))
                f.write(data)
        progress.close()

    except requests.exceptions.RequestException as e:
        print(f'Error downloading file: {e}')
        raise
    except IOError as e:
        print(f'Error saving file: {e}')
        raise
