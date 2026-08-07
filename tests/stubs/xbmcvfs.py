import os


def translatePath(path):
    return path


def exists(path):
    return os.path.exists(path)


def mkdirs(path):
    os.makedirs(path, exist_ok=True)
    return True
