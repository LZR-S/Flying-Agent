"""Optional, grounded image edits. No flight state or evaluator data crosses this API."""
import base64
import binascii
import hashlib
import json
import os
import re
import struct
import time

import cv2
import httpx
import numpy as np

from .artifacts import write_json
from .protocol import GenerateReference


MAX_RESPONSE_BYTES = 36 * 1024 * 1024
IMAGE_MODEL = 'gpt-image-2'


def reference_environment(values):
    """Image credentials never fall back to the selected decision-model provider."""
    explicit = ('DRONE_PHOTO_IMAGE_BASE_URL', 'DRONE_PHOTO_IMAGE_API_KEY')
    keys = explicit if any(values.get(k) for k in explicit) else ('BASE_URL', 'API_KEY')
    url, key = (values.get(k) for k in keys)
    if not url or not key:
        return {}
    parsed = httpx.URL(url)
    if parsed.scheme not in ('https', 'http') or not parsed.host or parsed.userinfo or parsed.query or parsed.fragment:
        raise ValueError('invalid_reference_endpoint')
    return dict(zip(explicit, (url, key)))


def validate_reference_png(data):
    if (not isinstance(data, bytes) or len(data) < 33 or len(data) > MAX_RESPONSE_BYTES
            or not data.startswith(b'\x89PNG\r\n\x1a\n') or data[12:16] != b'IHDR'):
        raise ValueError('invalid_reference_image')
    width, height = struct.unpack('>II', data[16:24])
    if not width or not height or width * height > 16_000_000:
        raise ValueError('invalid_reference_dimensions')
    pixels = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if pixels is None or pixels.shape[:2] != (height, width):
        raise ValueError('invalid_reference_image')
    return width, height


def _usage(body):
    value = body.get('usage')
    if not isinstance(value, dict):
        return None
    result = {k: value[k] for k in ('input_tokens', 'output_tokens', 'total_tokens')
              if type(value.get(k)) is int and value[k] >= 0}
    for key in ('input_tokens_details', 'output_tokens_details'):
        if isinstance(value.get(key), dict):
            result[key] = {k: v for k, v in value[key].items()
                           if k in ('text_tokens', 'image_tokens', 'cached_tokens') and type(v) is int and v >= 0}
    return result or None


class ReferenceGenerator:
    def __init__(self, config, artifacts, *, base_url=None, api_key=None, transport=None):
        self.config, self.artifacts, self.transport = config, artifacts, transport
        self.base_url = (base_url or os.getenv('DRONE_PHOTO_IMAGE_BASE_URL') or '').rstrip('/')
        self.api_key = api_key or os.getenv('DRONE_PHOTO_IMAGE_API_KEY')
        if self.base_url:
            reference_environment({'DRONE_PHOTO_IMAGE_BASE_URL': self.base_url,
                                   'DRONE_PHOTO_IMAGE_API_KEY': self.api_key or 'validation'})
            if httpx.URL(self.base_url).path in ('', '/'):
                self.base_url += '/v1'

    @property
    def available(self):
        return bool(self.base_url and self.api_key)

    def generate(self, *, source_id, source, guidance, aspect_ratio, call_id):
        arguments = GenerateReference(source_id=source_id, guidance=guidance, aspect_ratio=aspect_ratio)
        if not self.available:
            raise ValueError('reference_unavailable')
        if re.fullmatch(r'ref_request_[0-9]{6}', call_id) is None:
            raise ValueError('invalid_reference_request_id')
        prompt = (
            'Create a grounded photography composition reference from the supplied real camera image. '
            'Preserve the visible person identity, pose, clothes, hair, hands, held objects, scene geometry, '
            'materials, lighting and rendered appearance. Do not beautify, add objects, fabricate unseen '
            'body parts or background, change facial expression, or invent shallow depth of field or lighting. '
            'The aircraft has a fixed camera (960x720), relative flight movements and pixel-preserving crops; '
            'no gimbal, optical zoom or synthesized final delivery. Suggest an achievable viewpoint and framing '
            'with natural balance; no mandatory grid or subject-size threshold. Exact body boundaries and '
            'preserving requested parts take priority. Recompose deliberately for the requested output format: '
            'show the intended finished photograph after feasible camera movement and software viewfinder cropping, '
            'rather than keeping every margin of the starting drone view. Background outside the intended framing '
            'may be excluded without removing or restaging objects in the scene. Do not obtain a portrait result '
            'by canvas outpainting or mechanically adding empty sky or floor. Balance readable subject detail, '
            'purposeful negative space and useful scene context; neither a tighter crop nor a grid is automatically better. '
            'For head-to-thigh briefs, end the visible body region at the thighs rather than retaining knees or feet; '
            'for full-body briefs, keep the head and both feet complete with visible margins. '
            'This is synthetic advisory imagery, not navigation or proof '
            'of an achievable result. The original task below has priority over the composition guidance.\n'
            f'Original user task: {self.config.brief}\n'
            f'Composition guidance: {arguments.guidance}\nRequested aspect ratio: {arguments.aspect_ratio}'
        )
        parameters = {'model': IMAGE_MODEL, 'n': 1, 'quality': 'medium',
                      'size': '1024x1536' if aspect_ratio == '2:3' else '1024x768', 'output_format': 'png'}
        directory = self.artifacts.directory / 'reference-api'
        directory.mkdir(parents=True, exist_ok=True)
        source_path = directory / f'{call_id}.source.png'
        source_path.write_bytes(source)
        write_json(directory / f'{call_id}.request.json', {
            'endpoint': self.base_url + '/images/edits',
            'source_id': source_id, 'source_sha256': hashlib.sha256(source).hexdigest(),
            'source_path': str(source_path.relative_to(self.artifacts.directory)),
            'parameters': parameters, 'prompt': prompt})
        started = time.monotonic()
        try:
            with httpx.Client(transport=self.transport, trust_env=False) as client:
                with client.stream('POST', self.base_url + '/images/edits',
                                   headers={'Authorization': 'Bearer ' + self.api_key},
                                   data={k: str(v) for k, v in parameters.items()} | {'prompt': prompt},
                                   files={'image': ('source.png', source, 'image/png')},
                                   timeout=self.config.reference_timeout_s) as response:
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() - started >= self.config.reference_timeout_s:
                            raise ValueError('reference_timeout')
                        if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ValueError('reference_response_too_large')
                        data.extend(chunk)
            body = json.loads(data)
            items = body.get('data') if isinstance(body, dict) else None
            if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
                raise ValueError('invalid_reference_response')
            encoded = items[0].get('b64_json')
            if not isinstance(encoded, str):
                raise ValueError('reference_base64_required')
            image = base64.b64decode(encoded, validate=True)
            validate_reference_png(image)
        except httpx.TimeoutException:
            raise ValueError('reference_timeout') from None
        except httpx.HTTPError:
            raise ValueError('reference_http_error') from None
        except (json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
            raise ValueError('invalid_reference_response') from None
        usage = _usage(body)
        # Provider free text/URLs are deliberately excluded from persisted evidence.
        write_json(directory / f'{call_id}.response.json', {'data': [{'b64_json': encoded}], 'usage': usage})
        return {'image': image, 'model': IMAGE_MODEL, 'usage': usage, 'parameters': parameters}
