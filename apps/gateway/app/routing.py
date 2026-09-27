import json
import re
from pathlib import Path


def load_routes(path: Path | None = None) -> list[dict]:
    path = path or Path(__file__).with_name("routes.generated.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def match_route(routes: list[dict], method: str, path: str) -> dict | None:
    candidates = []
    for route in routes:
        methods = {route["method"]}
        if method == "HEAD" and route["method"] == "GET":
            methods.add("HEAD")
        if method not in methods or not re.fullmatch(route["regex"], path):
            continue
        path_template = route["path_template"]
        segment_specificity = tuple(0 if segment.startswith("{") and segment.endswith("}") else 1
                                    for segment in path_template.strip("/").split("/"))
        literal_chars = len(re.sub(r"\{[^{}]+\}", "", path_template))
        parameter_count = path_template.count("{")
        candidates.append(((segment_specificity, literal_chars, -parameter_count, len(path_template)), route))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None
