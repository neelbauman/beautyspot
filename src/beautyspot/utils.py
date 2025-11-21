# src/beautyspot/utils.py

import hashlib
import os
import json

class KeyGen:
    @staticmethod
    def from_path_stat(filepath: str) -> str:
        """Fast: path + size + mtime"""
        if not os.path.exists(filepath): return f"MISSING_{filepath}"
        stat = os.stat(filepath)
        identifier = f"{filepath}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(identifier.encode()).hexdigest()

    @staticmethod
    def from_file_content(filepath: str) -> str:
        """Strict: file content hash"""
        if not os.path.exists(filepath): return f"MISSING_{filepath}"
        hasher = hashlib.md5()
        hasher.update(os.path.splitext(filepath)[1].lower().encode())
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
        except OSError: return f"ERROR_{filepath}"
        return hasher.hexdigest()

    @staticmethod
    def default(args, kwargs) -> str:
        """Fallback: args string representation"""
        try:
            s = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
            return hashlib.md5(s.encode()).hexdigest()
        except:
            return hashlib.md5(str((args, kwargs)).encode()).hexdigest()

