#!/usr/bin/env python3
"""Generate a Mihon index.pb from the selected Keiyoushi packages."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
UPSTREAM = "https://raw.githubusercontent.com/keiyoushi/extensions/repo/"


def fetch(url):
    request = Request(url, headers={"User-Agent": "mihon-sources-generator/1.0"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def fetch_json(url):
    return json.loads(fetch(url).decode("utf-8"))


def read_varint(data, pos):
    value = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise ValueError("invalid protobuf")
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, pos
        shift += 7


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def fields(data):
    result, pos = [], 0
    while pos < len(data):
        start = pos
        key, pos = read_varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            payload_start = pos
            _, pos = read_varint(data, pos)
            payload = data[payload_start:pos]
        elif wire == 1:
            payload, pos = data[pos:pos + 8], pos + 8
        elif wire == 2:
            length, pos = read_varint(data, pos)
            payload, pos = data[pos:pos + length], pos + length
        elif wire == 5:
            payload, pos = data[pos:pos + 4], pos + 4
        else:
            raise ValueError("unsupported protobuf wire type")
        if pos > len(data):
            raise ValueError("truncated protobuf")
        result.append((number, wire, payload, data[start:pos]))
    return result


def length_field(number, payload):
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def string_field(number, value):
    return length_field(number, value.encode("utf-8"))


def package_from_pb(message):
    for number, wire, payload, _ in fields(message):
        if number == 2 and wire == 2:
            return payload.decode("utf-8")
    raise ValueError("packageName is missing from the protobuf")


def filter_pb(compressed, selected_packages, store_name):
    raw = gzip.decompress(compressed)
    rebuilt, found, selected_in_pb = bytearray(), False, set()
    for number, wire, payload, raw_field in fields(raw):
        if number == 1 and wire == 2:
            rebuilt.extend(string_field(1, store_name))
        elif number == 101 and wire == 2:
            found = True
            extension_list = bytearray()
            for child_number, child_wire, child_payload, child_raw in fields(payload):
                if child_number != 1 or child_wire != 2:
                    extension_list.extend(child_raw)
                    continue
                package = package_from_pb(child_payload)
                if package in selected_packages:
                    extension_list.extend(child_raw)
                    selected_in_pb.add(package)
            rebuilt.extend(length_field(101, bytes(extension_list)))
        else:
            rebuilt.extend(raw_field)
    if not found or selected_in_pb != selected_packages:
        missing = sorted(selected_packages - selected_in_pb)
        raise ValueError("packages missing from the official index.pb: " + ", ".join(missing))
    compressed = bytearray(gzip.compress(bytes(rebuilt), mtime=0))
    compressed[9] = 255
    return bytes(compressed)


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    legacy = json.loads((ROOT / "index.min.json").read_text(encoding="utf-8"))
    packages = [str(item["pkg"]) for item in legacy]
    if len(packages) != len(set(packages)):
        raise SystemExit("index.min.json contains duplicate packages")

    index = fetch_json(UPSTREAM + "index.json")
    available = {item["packageName"] for item in index["extensionList"]["extensions"]}
    selected = set(packages)
    missing = sorted(selected - available)
    if missing:
        raise SystemExit("Packages not found in Keiyoushi: " + ", ".join(missing))

    raw_base = config["raw_base_url"].rstrip("/")
    pb = filter_pb(fetch(UPSTREAM + "index.pb"), selected, "Mihon Sources")
    (ROOT / "index.pb").write_bytes(pb)
    descriptor = {
        "index_v2": f"{raw_base}/index.pb",
        "meta": {
            "name": "Mihon Sources",
            "website": config["website"],
            "signingKeyFingerprint": index["signingKey"],
        },
    }
    (ROOT / "repo.json").write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(selected)} extensions")
    print("Add this repository to Mihon:")
    print(f"  {raw_base}/repo.json")


if __name__ == "__main__":
    main()
