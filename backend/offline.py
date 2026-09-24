"""Fail closed if a Python dependency attempts an Internet connection."""
import socket


def enforce_offline():
    original = socket.socket

    class LocalSocket(original):
        def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
            if family in (socket.AF_INET, socket.AF_INET6):
                raise OSError("Decky Pinyin inference is offline; network access is disabled")
            super().__init__(family, type, proto, fileno)

        def connect(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise OSError("Decky Pinyin inference is offline; network access is disabled")
            return super().connect(address)

        def connect_ex(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise OSError("Decky Pinyin inference is offline; network access is disabled")
            return super().connect_ex(address)

    socket.socket = LocalSocket
    def no_dns(*args, **kwargs):
        raise OSError("Decky Pinyin inference is offline; network access is disabled")
    socket.getaddrinfo = no_dns
