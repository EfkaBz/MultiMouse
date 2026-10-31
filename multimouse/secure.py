"""Encrypted, length-prefixed message channel over TCP.

Every machine shares a pairing code. A session key is derived from the code and
two random nonces exchanged at connection time (scrypt + HKDF-like SHA-256), then
each JSON message is sealed with AES-256-GCM. A wrong code fails the first
decryption, so the peer is rejected before any input event is accepted.
"""
import hashlib
import json
import os
import socket
import struct
import threading

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MMSE1"
_KEY_CACHE = {}


def _base_key(code: str) -> bytes:
    code = code.strip().upper()
    if code not in _KEY_CACHE:
        _KEY_CACHE[code] = hashlib.scrypt(code.encode(), salt=b"multimouse-v1", n=2 ** 14, r=8, p=1, dklen=32)
    return _KEY_CACHE[code]


def _session_key(code, n_client, n_server, label):
    return hashlib.sha256(_base_key(code) + n_client + n_server + label).digest()


class AuthError(Exception):
    pass


class Channel:
    def __init__(self, sock: socket.socket, code: str, is_server: bool):
        self.sock = sock
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._send_lock = threading.Lock()
        self._send_ctr = 0
        self._recv_ctr = 0
        mine = os.urandom(16)
        if is_server:
            self._sendall(MAGIC + mine)
            hdr = self._recv_exact(len(MAGIC) + 16)
            n_client, n_server = hdr[len(MAGIC):], mine
        else:
            hdr = self._recv_exact(len(MAGIC) + 16)
            self._sendall(MAGIC + mine)
            n_client, n_server = mine, hdr[len(MAGIC):]
        if hdr[: len(MAGIC)] != MAGIC:
            raise AuthError("protocole inconnu")
        c2s = AESGCM(_session_key(code, n_client, n_server, b"c2s"))
        s2c = AESGCM(_session_key(code, n_client, n_server, b"s2c"))
        self._tx, self._rx = (s2c, c2s) if is_server else (c2s, s2c)
        self._tx_dir, self._rx_dir = (b"S", b"C") if is_server else (b"C", b"S")

    def _sendall(self, data):
        self.sock.sendall(data)

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("connexion fermée")
            buf += chunk
        return bytes(buf)

    def send(self, msg: dict):
        payload = json.dumps(msg, separators=(",", ":")).encode()
        with self._send_lock:
            nonce = self._tx_dir + b"\0\0\0" + struct.pack(">Q", self._send_ctr)
            self._send_ctr += 1
            sealed = self._tx.encrypt(nonce, payload, None)
            self._sendall(struct.pack(">I", len(sealed)) + sealed)

    def recv(self) -> dict:
        (length,) = struct.unpack(">I", self._recv_exact(4))
        if length > 8 * 1024 * 1024:
            raise ConnectionError("message trop grand")
        sealed = self._recv_exact(length)
        nonce = self._rx_dir + b"\0\0\0" + struct.pack(">Q", self._recv_ctr)
        self._recv_ctr += 1
        try:
            payload = self._rx.decrypt(nonce, sealed, None)
        except Exception:
            raise AuthError("code d'appairage incorrect")
        return json.loads(payload)

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
