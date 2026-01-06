import os
import yaml


class Config:

    _instance = None

    def __new__(cls, path="config.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._path = path
            cls._instance._load()
        return cls._instance

    def _load(self):
        if not os.path.exists(self._path):
            raise FileNotFoundError(f"配置文件不存在: {self._path}")

        with open(self._path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            raise ValueError("YAML 配置文件的顶层结构必须是字典。")

        self.__dict__["_data"] = self._to_namespace(data)

    def _to_namespace(self, data):
        if isinstance(data, dict):
            obj = type("Namespace", (), {})()
            for k, v in data.items():
                setattr(obj, k, self._to_namespace(v))
            return obj
        return data

    def reload(self):
        self._load()

    def __getattr__(self, name):
        return getattr(self._data, name)

    def __getitem__(self, key):
        return getattr(self._data, key)

    def as_dict(self):
        def unwrap(obj):
            if hasattr(obj, "__dict__"):
                return {k: unwrap(v) for k, v in obj.__dict__.items()}
            return obj

        return unwrap(self._data)

    def __repr__(self):
        return f"<Config path={self._path}>"


cfg = Config("config.yaml")
