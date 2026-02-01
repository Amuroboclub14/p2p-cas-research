# src/network/dh_utils.py
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

def generate_dh_parameters():
    return dh.generate_parameters(generator=2, key_size=2048)
def generate_private_key(parameters):
    return parameters.generate_private_key()
def generate_shared_key(private_key, peer_public_key):
    shared_secret = private_key.exchange(peer_public_key)
    derived_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'handshake data',
    ).derive(shared_secret)
    return derived_key